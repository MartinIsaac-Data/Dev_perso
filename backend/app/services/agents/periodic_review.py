"""Weekly and quarterly review.

The value of this agent is almost entirely in the context it is handed. Given
the quota status, the decay list, the critical path, the market gap and what
the *previous* review said the next action would be, a competent model writes
a useful review. Given none of that, it writes encouragement.

So `build_review_context` is the substance of this module, and it is a pure
function of the database, tested on its own. The generation step is thin on
purpose.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CaseReview,
    CaseReviewChallenge,
    Deliverable,
    PeriodicReview,
    Profile,
)
from app.services import deliverables as deliverable_service
from app.services import market, skill_graph
from app.services.agents.client import LlmClient
from app.services.agents.runner import run_agent


class PeriodicReviewOutput(BaseModel):
    body_md: str = Field(description="Short markdown with bold section headings.")
    next_action: str = Field(description="One concrete thing to do next. Not a list.")
    next_action_rationale: str = Field(
        description="Why that one rather than the obvious alternative."
    )


def period_bounds(kind: str, as_of: date) -> tuple[date, date]:
    """The period being reviewed, ending on `as_of`."""
    if kind == "weekly":
        # Monday to Sunday of the week containing as_of.
        start = as_of - timedelta(days=as_of.weekday())
        return start, start + timedelta(days=6)
    if kind == "quarterly":
        quarter = deliverable_service.quarter_of(as_of)
        return deliverable_service.quarter_bounds(as_of.year, quarter)
    raise ValueError(f"unknown review kind '{kind}'")


def build_review_context(
    session: Session,
    profile: Profile,
    kind: str,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    period_start, period_end = period_bounds(kind, as_of)

    published = [
        d
        for d in session.scalars(
            select(Deliverable)
            .options(selectinload(Deliverable.type))
            .where(
                Deliverable.profile_id == profile.id,
                Deliverable.status == "published",
                Deliverable.published_on.isnot(None),
            )
        )
        if period_start <= d.published_on <= period_end
    ]

    # Anything opened but not finished, oldest first. A project that has been
    # "in progress" for three quarters is the signal this review exists for.
    stalled = sorted(
        (
            d
            for d in session.scalars(
                select(Deliverable)
                .options(selectinload(Deliverable.type))
                .where(
                    Deliverable.profile_id == profile.id,
                    Deliverable.status.in_(("in_progress", "planned")),
                )
            )
            if d.started_on is not None
        ),
        key=lambda d: d.started_on,
    )

    previous = session.scalar(
        select(PeriodicReview)
        .where(
            PeriodicReview.profile_id == profile.id,
            PeriodicReview.kind == kind,
            PeriodicReview.period_start < period_start,
        )
        .order_by(PeriodicReview.period_start.desc())
        .limit(1)
    )

    open_challenges = list(
        session.scalars(
            select(CaseReviewChallenge)
            .join(CaseReview)
            .where(CaseReviewChallenge.resolved_on.is_(None))
            .order_by(CaseReview.reviewed_on)
        )
    )

    gaps = market.market_gaps(session, profile.id)
    quotas = deliverable_service.quota_status(session, profile.id, as_of, quarters_back=5)
    decayed = skill_graph.decayed_skills(session, profile.id, as_of)
    critical = skill_graph.critical_path(session, profile.id, limit=8, as_of=as_of)

    return {
        "profile": {"code": profile.code, "display_name": profile.display_name},
        "period": {"kind": kind, "start": period_start, "end": period_end, "as_of": as_of},
        "published_this_period": [
            {
                "title": d.title,
                "type": d.type.code,
                "published_on": d.published_on,
                "skills": [link.skill.code for link in d.skills],
            }
            for d in published
        ],
        "stalled": [
            {
                "title": d.title,
                "type": d.type.code,
                "status": d.status,
                "started_on": d.started_on,
                "days_open": (as_of - d.started_on).days,
            }
            for d in stalled
        ],
        "quota_status": [
            {
                "quarter": f"{q.year}Q{q.quarter}",
                "in_scope": q.in_scope,
                "is_current": q.is_current,
                "is_silent": q.is_silent,
                "met": q.met,
                "published": q.total_published,
                "shortfalls": [
                    {"type": line.type_code, "published": line.published, "required": line.required}
                    for line in q.lines
                    if not line.met
                ],
            }
            for q in quotas
        ],
        "decayed_skills": [
            {
                "code": p.code,
                "level": p.current_level,
                "months_since_practice": p.months_since_practice,
                "decay_months": p.decay_months,
                "gates": p.blocks_below_target,
            }
            for p in decayed
        ],
        "critical_path": [
            {
                "code": p.code,
                "current_level": p.current_level,
                "target_level": p.target_level,
                "gates": p.blocks_below_target,
                "blocked_by": [u.code for u in p.unmet_prerequisites],
            }
            for p in critical
        ],
        "market_gaps": [
            {
                "code": d.skill_code,
                "demanded_level": d.demanded_level,
                "current_level": d.current_level,
                "gap": d.market_gap,
                "must_have_in_postings": d.must_have_count,
            }
            for d in gaps.demands
            if d.market_gap > 0
        ][:12],
        "unmapped_market_requirements": [
            {"label": label, "count": count} for label, count in gaps.unmapped[:8]
        ],
        "open_review_board_objections": [
            {
                "persona": c.persona,
                "severity": c.severity,
                "challenge": c.challenge,
                "assumption": (
                    c.target_assumption.code if c.target_assumption else c.target_area
                ),
            }
            for c in open_challenges
        ][:10],
        "previous_review": (
            {
                "period_start": previous.period_start,
                "next_action": previous.next_action,
                "next_action_rationale": previous.next_action_rationale,
            }
            if previous
            else None
        ),
    }


def generate_review(
    session: Session,
    profile: Profile,
    kind: str,
    client: LlmClient,
    as_of: date | None = None,
    model_name: str | None = None,
) -> PeriodicReview:
    as_of = as_of or date.today()
    period_start, period_end = period_bounds(kind, as_of)

    context = build_review_context(session, profile, kind, as_of)
    run, output = run_agent(
        session,
        agent_name=f"periodic_review_{kind}",
        prompt_name="periodic_review",
        payload=context,
        output_model=PeriodicReviewOutput,
        client=client,
        model=model_name,
        max_tokens=4000,
    )

    # One review per profile, kind and period. Re-running replaces rather than
    # accumulating, so a period has one answer and the unique constraint holds.
    existing = session.scalar(
        select(PeriodicReview).where(
            PeriodicReview.profile_id == profile.id,
            PeriodicReview.kind == kind,
            PeriodicReview.period_start == period_start,
        )
    )
    if existing is not None:
        session.delete(existing)
        session.flush()

    review = PeriodicReview(
        profile_id=profile.id,
        agent_run_id=run.id,
        kind=kind,
        period_start=period_start,
        period_end=period_end,
        body_md=output.body_md,
        next_action=output.next_action,
        next_action_rationale=output.next_action_rationale,
    )
    session.add(review)
    session.flush()
    return review
