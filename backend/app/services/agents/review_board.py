"""The review board agent.

Two decisions shape this module.

**The context is assembled deterministically and tested on its own.** A
critique built without the sensitivity analysis, or without the scoring
rubric, reads exactly as convincing as one built with them — so no assertion
on the *output* would catch the omission. `build_case_context` is a pure
function of the database, and the tests check what the agent was asked, not
only what it replied.

**The overall score is computed here, not taken from the model.** The agent
scores each criterion; the weighting is the rubric's, and the rubric lives in
the database. Trusting a model's weighted arithmetic would make every stored
score depend on it having multiplied correctly, and would silently break the
moment the weights were rebalanced.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Assumption,
    BusinessCase,
    CaseReview,
    CaseReviewChallenge,
    CaseReviewScore,
    ReviewCriterion,
    RoiModel,
    Solution,
)
from app.models.base import REVIEW_PERSONAS, SEVERITIES
from app.services import business_case as bc
from app.services import roi
from app.services.agents.client import AgentError, LlmClient
from app.services.agents.runner import run_agent


class CriterionScoreOut(BaseModel):
    criterion_code: str = Field(description="Exact code from the supplied rubric.")
    score: float = Field(ge=0, le=10)
    comment: str


class ChallengeOut(BaseModel):
    persona: str = Field(description="cfo, coo or cio")
    severity: str = Field(description="blocking, major or minor")
    target_assumption_code: str | None = Field(
        default=None,
        description="Exact assumption code this objection attacks, or null if "
        "no single assumption is responsible.",
    )
    target_area: str | None = Field(
        default=None, description="Used only when target_assumption_code is null."
    )
    challenge: str
    evidence_demanded: str | None = None


class ReviewBoardOutput(BaseModel):
    verdict: str
    summary: str
    scores: list[CriterionScoreOut]
    challenges: list[ChallengeOut]


def build_case_context(
    session: Session, case: BusinessCase, model: RoiModel | None
) -> dict[str, Any]:
    """Everything the board needs, and nothing it should be guessing.

    Includes the rubric from the database so the agent scores against the same
    criteria the interface displays, rather than a copy embedded in the prompt
    that would drift the first time the rubric was edited.
    """
    tree = bc.build_cause_tree(session, case, "base")
    audit = bc.audit_assumptions(session, case)
    solution = session.scalar(select(Solution).where(Solution.case_id == case.id))
    criteria = list(
        session.scalars(select(ReviewCriterion).order_by(ReviewCriterion.ordinal))
    )

    context: dict[str, Any] = {
        "case": {
            "title": case.title,
            "industry": case.industry,
            "currency": case.currency,
            "symptom": case.symptom,
            "company_context": case.company_context,
            "claimed_annual_loss": case.claimed_annual_loss,
        },
        "rubric": [
            {
                "code": criterion.code,
                "name": criterion.name,
                "weight": criterion.weight,
                "definition": criterion.definition,
            }
            for criterion in criteria
        ],
        "assumptions": [
            {
                "code": a.code,
                "label": a.label,
                "unit": a.unit,
                "low": a.low_value,
                "base": a.base_value,
                "high": a.high_value,
                "confidence": a.confidence,
                "source": a.source,
                "rationale": a.rationale,
            }
            for a in sorted(case.assumptions, key=lambda x: x.code)
        ],
        "cause_tree": {
            "total": tree.total,
            "leaves": [
                {
                    "label": leaf.label,
                    "value": leaf.value,
                    "drivers": [driver.code for driver in leaf.drivers],
                    "evidence_note": leaf.evidence_note,
                }
                for leaf in tree.ranked_leaves
            ],
            "reconciliation": {
                "bottom_up_total": tree.reconciliation.bottom_up_total,
                "claimed": tree.reconciliation.claimed_annual_loss,
                "gap": tree.reconciliation.gap,
                "gap_ratio": tree.reconciliation.gap_ratio,
            },
        },
        "assumption_audit": {
            "total": audit.total,
            "unsourced": audit.unsourced,
            "point_estimates": audit.point_estimates,
            "low_confidence": audit.low_confidence,
            "unused": audit.unused,
        },
        "solution": None,
        "roi": None,
    }

    if solution is not None:
        context["solution"] = {
            "data_requirements": solution.data_requirements,
            "architecture": solution.architecture,
            "ai_component": solution.ai_component,
            "automation_component": solution.automation_component,
            "process_change": solution.process_change,
            "governance": solution.governance,
            "deployment_plan": solution.deployment_plan,
            "key_risks": solution.key_risks,
            "kpis": [
                {
                    "name": kpi.name,
                    "baseline": kpi.baseline_value,
                    "target": kpi.target_value,
                    "frequency": kpi.measurement_frequency,
                }
                for kpi in solution.kpis
            ],
        }

    if model is not None and model.lines:
        scenarios = roi.compare_scenarios(model)
        fragility = roi.fragility(model)
        context["roi"] = {
            "version": model.version,
            "horizon_years": model.horizon_years,
            "discount_rate": model.discount_rate,
            "lines": [
                {
                    "kind": line.kind,
                    "category": line.category,
                    "label": line.label,
                    "year_index": line.year_index,
                    "amount_code": line.amount_assumption.code,
                    "quantity": line.quantity,
                }
                for line in sorted(model.lines, key=lambda x: (x.year_index, x.kind))
            ],
            "scenarios": {
                name: {
                    "npv": result.npv,
                    "benefit_cost_ratio": result.benefit_cost_ratio,
                    "payback_years": result.payback_years,
                    "total_cost_pv": result.total_cost_pv,
                    "total_benefit_pv": result.total_benefit_pv,
                }
                for name, result in scenarios.items()
            },
            "sensitivity": [
                {
                    "code": row.code,
                    "swing": row.swing,
                    "npv_at_low": row.npv_at_low,
                    "npv_at_high": row.npv_at_high,
                    "flips_the_decision": row.flips_the_decision,
                    "confidence": row.confidence,
                }
                for row in roi.tornado(model)
            ],
            "fragility_headline": fragility.headline,
            "survives_pessimistic": fragility.survives_pessimistic,
            "only_fails_in_combination": fragility.only_fails_in_combination,
        }

    return context


def weighted_score(
    scores: dict[str, Decimal], criteria: list[ReviewCriterion]
) -> Decimal:
    """Roll the per-criterion marks up using the stored rubric weights."""
    total = Decimal(0)
    for criterion in criteria:
        if criterion.code in scores:
            total += scores[criterion.code] * criterion.weight
    return total.quantize(Decimal("0.01"))


def review_case(
    session: Session,
    case: BusinessCase,
    client: LlmClient,
    roi_model: RoiModel | None = None,
    reviewed_on: date | None = None,
    model_name: str | None = None,
) -> CaseReview:
    """Run the board and persist its critique."""
    if roi_model is None and case.roi_models:
        roi_model = max(case.roi_models, key=lambda m: m.version)

    criteria = list(session.scalars(select(ReviewCriterion)))
    by_code = {criterion.code: criterion for criterion in criteria}
    assumptions = {
        a.code: a
        for a in session.scalars(select(Assumption).where(Assumption.case_id == case.id))
    }

    context = build_case_context(session, case, roi_model)
    run, output = run_agent(
        session,
        agent_name="review_board",
        prompt_name="review_board",
        payload=context,
        output_model=ReviewBoardOutput,
        client=client,
        model=model_name,
    )

    unknown = [s.criterion_code for s in output.scores if s.criterion_code not in by_code]
    if unknown:
        raise AgentError(
            f"the board scored criteria that are not in the rubric: {sorted(unknown)}"
        )
    missing = [code for code in by_code if code not in {s.criterion_code for s in output.scores}]
    if missing:
        raise AgentError(f"the board did not score every criterion. Missing: {sorted(missing)}")

    scores = {s.criterion_code: Decimal(str(s.score)) for s in output.scores}

    review = CaseReview(
        case_id=case.id,
        roi_model_id=roi_model.id if roi_model else None,
        agent_run_id=run.id,
        reviewed_on=reviewed_on or date.today(),
        overall_score=weighted_score(scores, criteria),
        verdict=output.verdict,
        summary=output.summary,
    )
    session.add(review)
    session.flush()

    for score in output.scores:
        session.add(
            CaseReviewScore(
                review_id=review.id,
                criterion_id=by_code[score.criterion_code].id,
                score=Decimal(str(score.score)),
                comment=score.comment,
            )
        )

    for challenge in output.challenges:
        if challenge.persona not in REVIEW_PERSONAS or challenge.severity not in SEVERITIES:
            # Dropped rather than fatal: one malformed objection should not
            # discard a critique that is otherwise usable.
            continue
        target = assumptions.get(challenge.target_assumption_code or "")
        session.add(
            CaseReviewChallenge(
                review_id=review.id,
                persona=challenge.persona,
                severity=challenge.severity,
                target_assumption_id=target.id if target else None,
                # A code the agent invented is kept as free text rather than
                # silently dropped: knowing it hallucinated an assumption name
                # is useful, and losing the objection is not.
                target_area=(
                    challenge.target_area
                    or (challenge.target_assumption_code if target is None else None)
                ),
                challenge=challenge.challenge,
                evidence_demanded=challenge.evidence_demanded,
            )
        )

    session.flush()
    return review
