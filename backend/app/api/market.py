"""Gap Radar and agent endpoints.

Agent endpoints return 503 with an instruction when no API key is configured,
rather than 500 with a stack trace. Everything else in this application works
without a key, and the error should say that rather than looking like a fault.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_profile
from app.db import get_db
from app.models import AgentRun, JobPosting, Profile
from app.services import market
from app.services.agents.client import AgentError, AgentNotConfigured, default_client
from app.services.agents.extraction import extract_posting
from app.services.agents.periodic_review import generate_review
from app.services.agents.runner import verify_prompt

router = APIRouter(tags=["market"])


class SkillDemandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_code: str
    skill_name: str
    domain_name: str
    demand_count: int = Field(description="How many captured postings ask for it at all.")
    must_have_count: int
    demanded_level: int | None = Field(
        default=None, description="The deepest level any posting asks for."
    )
    current_level: int
    target_level: int
    market_gap: int
    is_critical: bool


class MarketGapOut(BaseModel):
    target_role_code: str | None = None
    postings_analysed: int
    demands: list[SkillDemandOut] = []
    unmapped: list[tuple[str, int]] = Field(
        default=[],
        description="Requirements the taxonomy could not express, with how often "
        "they appeared. The most interesting output of this module.",
    )


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_label: str
    skill_id: int | None = None
    required_level: int | None = None
    importance: str
    evidence_quote: str | None = None


class PostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str | None = None
    location: str | None = None
    seniority_label: str | None = None
    source: str | None = None
    posted_on: date | None = None
    captured_on: date
    requirements: list[RequirementOut] = []


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_name: str
    model: str
    status: str
    prompt_path: str
    prompt_sha256: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    prompt_unchanged: bool


@router.get("/market/gaps", response_model=MarketGapOut)
def get_market_gaps(
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
    target_role: str | None = Query(default=None, description="Filter to one target role."),
) -> MarketGapOut:
    """What the captured postings demand, against what this profile holds."""
    try:
        report = market.market_gaps(db, profile.id, target_role)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    return MarketGapOut(
        target_role_code=report.target_role_code,
        postings_analysed=report.postings_analysed,
        demands=[SkillDemandOut.model_validate(d) for d in report.demands],
        unmapped=report.unmapped,
    )


@router.get("/postings", response_model=list[PostingOut])
def list_postings(db: Session = Depends(get_db)) -> list[JobPosting]:
    """Captured adverts, newest first. Nothing is ever overwritten."""
    return list(
        db.scalars(
            select(JobPosting)
            .options(selectinload(JobPosting.requirements))
            .order_by(JobPosting.captured_on.desc())
        )
    )


@router.get("/agent-runs", response_model=list[AgentRunOut])
def list_agent_runs(db: Session = Depends(get_db), limit: int = 25) -> list[AgentRunOut]:
    """The execution log, with whether each prompt has changed since."""
    runs = list(
        db.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
    )
    return [
        AgentRunOut(
            id=run.id,
            agent_name=run.agent_name,
            model=run.model,
            status=run.status,
            prompt_path=run.prompt_path,
            prompt_sha256=run.prompt_sha256,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            error=run.error,
            prompt_unchanged=verify_prompt(run),
        )
        for run in runs
    ]


def _client():  # noqa: ANN202
    try:
        return default_client()
    except AgentNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/postings/extract", response_model=PostingOut, status_code=201)
def extract(
    raw_text: str = Body(..., embed=True, min_length=40),
    target_role: str | None = Body(default=None, embed=True),
    source: str | None = Body(default=None, embed=True),
    db: Session = Depends(get_db),
) -> JobPosting:
    """Turn an advert into structured requirements. Requires an API key."""
    client = _client()
    try:
        posting = extract_posting(
            db, raw_text, client, target_role_code=target_role, source=source
        )
    except AgentError as exc:
        db.commit()  # keep the failed agent_run row
        raise HTTPException(502, f"extraction failed: {exc}") from exc
    db.commit()
    return posting


class PeriodicReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    period_start: date
    period_end: date
    body_md: str
    next_action: str | None = None
    next_action_rationale: str | None = None


@router.get("/periodic-reviews", response_model=list[PeriodicReviewOut])
def list_periodic_reviews(
    profile: Profile = Depends(get_profile), db: Session = Depends(get_db)
) -> list[PeriodicReviewOut]:
    from app.models import PeriodicReview

    return list(
        db.scalars(
            select(PeriodicReview)
            .where(PeriodicReview.profile_id == profile.id)
            .order_by(PeriodicReview.period_start.desc())
        )
    )


@router.post("/periodic-reviews", response_model=PeriodicReviewOut, status_code=201)
def create_periodic_review(
    kind: str = Body("weekly", embed=True),
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> PeriodicReviewOut:
    """Generate the weekly or quarterly review. Requires an API key."""
    client = _client()
    try:
        review = generate_review(db, profile, kind, client)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except AgentError as exc:
        db.commit()
        raise HTTPException(502, f"the review failed: {exc}") from exc
    db.commit()
    return PeriodicReviewOut.model_validate(review)
