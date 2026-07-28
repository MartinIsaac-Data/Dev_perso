"""Business Case Lab endpoints.

Read endpoints compute everything from base rows on every call — no NPV,
branch total or tornado is stored (ADR-008). Write endpoints exist for the
things a case actually iterates on: assumptions get revised after a review,
cause branches get added when a new one is found, and a ROI model gets a new
version rather than being edited in place, so the critique attached to version
1 keeps meaning what it meant.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_profile
from app.db import get_db
from app.models import (
    Assumption,
    BusinessCase,
    CaseReview,
    CaseReviewChallenge,
    CauseDriver,
    CauseNode,
    Profile,
    RoiLine,
    RoiModel,
    Solution,
)
from app.schemas.business_case import (
    AssumptionAuditOut,
    AssumptionIn,
    AssumptionOut,
    AssumptionUpdateIn,
    BusinessCaseDetailOut,
    BusinessCaseIn,
    BusinessCaseSummaryOut,
    CaseReviewOut,
    CauseNodeIn,
    CauseTreeOut,
    ChallengeResponseIn,
    FragilityOut,
    ReviewChallengeOut,
    ReviewScoreOut,
    RoiLineIn,
    RoiLineOut,
    RoiModelIn,
    RoiModelOut,
    RoiResultOut,
    ScenarioComparisonOut,
    SolutionOut,
    TornadoRowOut,
)
from app.services import business_case as bc
from app.services import roi

router = APIRouter(prefix="/cases", tags=["business cases"])

SCENARIO_QUERY = Query(
    default="base",
    description="pessimistic takes the unfavourable end of every range, "
    "optimistic the favourable end. See ADR-007.",
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _load_case(db: Session, case_id: int, profile: Profile) -> BusinessCase:
    case = db.scalar(
        select(BusinessCase)
        .options(
            selectinload(BusinessCase.assumptions),
            selectinload(BusinessCase.roi_models)
            .selectinload(RoiModel.lines)
            .selectinload(RoiLine.amount_assumption),
        )
        .where(BusinessCase.id == case_id)
    )
    if case is None or case.profile_id != profile.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business case not found")
    return case


def _assumption_by_code(db: Session, case: BusinessCase, code: str) -> Assumption:
    found = db.scalar(
        select(Assumption).where(Assumption.case_id == case.id, Assumption.code == code)
    )
    if found is None:
        known = sorted(a.code for a in case.assumptions)
        raise HTTPException(
            422,
            f"unknown assumption '{code}' on this case. Known codes: {', '.join(known)}",
        )
    return found


def _validate_scenario(scenario: str) -> roi.Scenario:
    if scenario not in roi.SCENARIOS:
        raise HTTPException(422, f"scenario must be one of {', '.join(roi.SCENARIOS)}")
    return scenario  # type: ignore[return-value]


def _pick_model(case: BusinessCase, version: int | None) -> RoiModel:
    if not case.roi_models:
        raise HTTPException(
            404, "this case has no ROI model yet — create one before asking for a result"
        )
    if version is None:
        return max(case.roi_models, key=lambda m: m.version)
    for model in case.roi_models:
        if model.version == version:
            return model
    available = sorted(m.version for m in case.roi_models)
    raise HTTPException(404, f"no ROI model version {version}. Available: {available}")


def _roi_model_out(model: RoiModel) -> RoiModelOut:
    return RoiModelOut(
        id=model.id,
        version=model.version,
        horizon_years=model.horizon_years,
        discount_rate=model.discount_rate,
        currency=model.currency,
        notes=model.notes,
        lines=[
            RoiLineOut(
                id=line.id,
                kind=line.kind,
                category=line.category,
                label=line.label,
                year_index=line.year_index,
                quantity=line.quantity,
                amount_assumption_id=line.amount_assumption_id,
                amount_code=line.amount_assumption.code,
                notes=line.notes,
            )
            for line in sorted(model.lines, key=lambda x: (x.year_index, x.kind, x.label))
        ],
    )


def _reviews_out(db: Session, case: BusinessCase) -> list[CaseReviewOut]:
    reviews = list(
        db.scalars(
            select(CaseReview)
            .options(
                selectinload(CaseReview.scores),
                selectinload(CaseReview.challenges),
                selectinload(CaseReview.roi_model),
            )
            .where(CaseReview.case_id == case.id)
            .order_by(CaseReview.reviewed_on.desc())
        )
    )
    codes = {a.id: a.code for a in case.assumptions}
    return [
        CaseReviewOut(
            id=review.id,
            reviewed_on=review.reviewed_on,
            roi_model_version=review.roi_model.version if review.roi_model else None,
            overall_score=review.overall_score,
            verdict=review.verdict,
            summary=review.summary,
            scores=[
                ReviewScoreOut(
                    criterion_code=score.criterion.code,
                    criterion_name=score.criterion.name,
                    weight=score.criterion.weight,
                    score=score.score,
                    comment=score.comment,
                )
                for score in sorted(review.scores, key=lambda s: s.criterion.ordinal)
            ],
            challenges=[
                ReviewChallengeOut(
                    id=challenge.id,
                    persona=challenge.persona,
                    severity=challenge.severity,
                    target_assumption_id=challenge.target_assumption_id,
                    target_assumption_code=codes.get(challenge.target_assumption_id),
                    target_area=challenge.target_area,
                    challenge=challenge.challenge,
                    evidence_demanded=challenge.evidence_demanded,
                    response=challenge.response,
                    resolved_on=challenge.resolved_on,
                )
                for challenge in sorted(
                    review.challenges,
                    key=lambda c: (
                        {"blocking": 0, "major": 1, "minor": 2}[c.severity],
                        c.persona,
                    ),
                )
            ],
        )
        for review in reviews
    ]


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


@router.get("", response_model=list[BusinessCaseSummaryOut])
def list_cases(
    profile: Profile = Depends(get_profile), db: Session = Depends(get_db)
) -> list[BusinessCaseSummaryOut]:
    cases = list(
        db.scalars(
            select(BusinessCase)
            .options(
                selectinload(BusinessCase.assumptions),
                selectinload(BusinessCase.roi_models)
                .selectinload(RoiModel.lines)
                .selectinload(RoiLine.amount_assumption),
            )
            .where(BusinessCase.profile_id == profile.id)
            .order_by(BusinessCase.opened_on.desc())
        )
    )

    summaries: list[BusinessCaseSummaryOut] = []
    for case in cases:
        tree = bc.build_cause_tree(db, case, "base")
        latest = max(case.roi_models, key=lambda m: m.version, default=None)
        base_npv = roi.compute(latest, "base").npv if latest and latest.lines else None

        review = db.scalar(
            select(CaseReview)
            .where(CaseReview.case_id == case.id)
            .order_by(CaseReview.reviewed_on.desc())
            .limit(1)
        )
        open_challenges = (
            db.scalar(
                select(func.count())
                .select_from(CaseReviewChallenge)
                .join(CaseReview)
                .where(
                    CaseReview.case_id == case.id,
                    CaseReviewChallenge.resolved_on.is_(None),
                )
            )
            or 0
        )

        summaries.append(
            BusinessCaseSummaryOut(
                id=case.id,
                title=case.title,
                industry=case.industry,
                currency=case.currency,
                status=case.status,
                opened_on=case.opened_on,
                claimed_annual_loss=case.claimed_annual_loss,
                bottom_up_total=tree.total,
                gap_ratio=tree.reconciliation.gap_ratio,
                assumption_count=len(case.assumptions),
                latest_roi_version=latest.version if latest else None,
                base_npv=base_npv,
                latest_review_score=review.overall_score if review else None,
                open_challenges=open_challenges,
            )
        )
    return summaries


@router.post("", response_model=BusinessCaseSummaryOut, status_code=201)
def create_case(
    payload: BusinessCaseIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> BusinessCaseSummaryOut:
    case = BusinessCase(
        profile_id=profile.id,
        title=payload.title,
        symptom=payload.symptom,
        industry=payload.industry,
        company_context=payload.company_context,
        claimed_annual_loss=payload.claimed_annual_loss,
        currency=payload.currency,
        status=payload.status,
        opened_on=payload.opened_on or date.today(),
    )
    db.add(case)
    db.commit()
    return BusinessCaseSummaryOut(
        id=case.id,
        title=case.title,
        industry=case.industry,
        currency=case.currency,
        status=case.status,
        opened_on=case.opened_on,
        claimed_annual_loss=case.claimed_annual_loss,
        bottom_up_total=Decimal(0),
        gap_ratio=None,
        assumption_count=0,
        latest_roi_version=None,
        base_npv=None,
        latest_review_score=None,
        open_challenges=0,
    )


@router.get("/{case_id}", response_model=BusinessCaseDetailOut)
def get_case(
    case_id: int,
    scenario: str = SCENARIO_QUERY,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> BusinessCaseDetailOut:
    case = _load_case(db, case_id, profile)
    tree = bc.build_cause_tree(db, case, _validate_scenario(scenario))
    solution = db.scalar(
        select(Solution)
        .options(selectinload(Solution.kpis))
        .where(Solution.case_id == case.id)
    )

    return BusinessCaseDetailOut(
        id=case.id,
        title=case.title,
        symptom=case.symptom,
        industry=case.industry,
        company_context=case.company_context,
        currency=case.currency,
        status=case.status,
        opened_on=case.opened_on,
        claimed_annual_loss=case.claimed_annual_loss,
        assumptions=sorted(case.assumptions, key=lambda a: a.code),
        cause_tree=CauseTreeOut.model_validate(tree),
        solution=SolutionOut.model_validate(solution) if solution else None,
        roi_models=[
            _roi_model_out(model)
            for model in sorted(case.roi_models, key=lambda m: m.version)
        ],
        reviews=_reviews_out(db, case),
        audit=AssumptionAuditOut.model_validate(bc.audit_assumptions(db, case)),
    )


# --------------------------------------------------------------------------
# Cause tree
# --------------------------------------------------------------------------


@router.get("/{case_id}/cause-tree", response_model=CauseTreeOut)
def get_cause_tree(
    case_id: int,
    scenario: str = SCENARIO_QUERY,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> CauseTreeOut:
    """The tree, quantified bottom-up, reconciled against the claimed loss."""
    case = _load_case(db, case_id, profile)
    tree = bc.build_cause_tree(db, case, _validate_scenario(scenario))
    return CauseTreeOut.model_validate(tree)


@router.post("/{case_id}/cause-nodes", status_code=201, response_model=CauseTreeOut)
def add_cause_node(
    case_id: int,
    payload: CauseNodeIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> CauseTreeOut:
    case = _load_case(db, case_id, profile)

    if payload.parent_id is not None:
        parent = db.get(CauseNode, payload.parent_id)
        if parent is None or parent.case_id != case.id:
            raise HTTPException(422, "parent node does not belong to this case")

    node = CauseNode(
        case_id=case.id,
        parent_id=payload.parent_id,
        label=payload.label,
        description=payload.description,
        evidence_note=payload.evidence_note,
        ordinal=payload.ordinal,
    )
    db.add(node)
    db.flush()

    for index, code in enumerate(payload.driver_codes):
        assumption = _assumption_by_code(db, case, code)
        db.add(
            CauseDriver(cause_node_id=node.id, assumption_id=assumption.id, ordinal=index)
        )
    db.commit()
    return CauseTreeOut.model_validate(bc.build_cause_tree(db, case, "base"))


@router.delete("/{case_id}/cause-nodes/{node_id}", status_code=204)
def delete_cause_node(
    case_id: int,
    node_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> None:
    case = _load_case(db, case_id, profile)
    node = db.get(CauseNode, node_id)
    if node is None or node.case_id != case.id:
        raise HTTPException(404, "cause node not found")
    # Children cascade. That is the intent: deleting a branch deletes what
    # hangs off it, rather than orphaning sub-causes into the root.
    db.delete(node)
    db.commit()


# --------------------------------------------------------------------------
# Assumptions
# --------------------------------------------------------------------------


@router.post("/{case_id}/assumptions", status_code=201, response_model=AssumptionOut)
def create_assumption(
    case_id: int,
    payload: AssumptionIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> Assumption:
    case = _load_case(db, case_id, profile)
    if any(a.code == payload.code for a in case.assumptions):
        raise HTTPException(409, f"assumption '{payload.code}' already exists on this case")

    assumption = Assumption(case_id=case.id, **payload.model_dump())
    db.add(assumption)
    db.commit()
    return assumption


@router.patch("/{case_id}/assumptions/{code}", response_model=AssumptionOut)
def update_assumption(
    case_id: int,
    code: str,
    payload: AssumptionUpdateIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> Assumption:
    """Revise an assumption. The usual answer to a review board challenge."""
    case = _load_case(db, case_id, profile)
    assumption = _assumption_by_code(db, case, code)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(assumption, field_name, value)

    # The database enforces the ordering too, but a 422 that names the field
    # beats an IntegrityError from three layers down.
    if assumption.low_value is not None and assumption.low_value > assumption.base_value:
        db.rollback()
        raise HTTPException(422, "low_value cannot exceed base_value")
    if assumption.high_value is not None and assumption.high_value < assumption.base_value:
        db.rollback()
        raise HTTPException(422, "high_value cannot be below base_value")

    db.commit()
    return assumption


@router.delete("/{case_id}/assumptions/{code}", status_code=204)
def delete_assumption(
    case_id: int,
    code: str,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> None:
    case = _load_case(db, case_id, profile)
    assumption = _assumption_by_code(db, case, code)
    try:
        db.delete(assumption)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            409,
            f"'{code}' is still referenced by a cause driver or a ROI line; "
            "remove those first",
        ) from exc


@router.get("/{case_id}/audit", response_model=AssumptionAuditOut)
def get_audit(
    case_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> AssumptionAuditOut:
    """Structural weaknesses that need no financial model to find."""
    case = _load_case(db, case_id, profile)
    return AssumptionAuditOut.model_validate(bc.audit_assumptions(db, case))


# --------------------------------------------------------------------------
# ROI
# --------------------------------------------------------------------------


@router.post("/{case_id}/roi-models", status_code=201, response_model=RoiModelOut)
def create_roi_model(
    case_id: int,
    payload: RoiModelIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> RoiModelOut:
    """Open a new version. Models are never edited in place.

    A critique is attached to the version it actually reviewed; rebuilding a
    model after a hostile review and comparing the two is the exercise.
    """
    case = _load_case(db, case_id, profile)
    next_version = max((m.version for m in case.roi_models), default=0) + 1

    model = RoiModel(
        case_id=case.id,
        version=next_version,
        horizon_years=payload.horizon_years,
        discount_rate=payload.discount_rate,
        currency=payload.currency or case.currency,
        notes=payload.notes,
    )
    db.add(model)
    db.commit()
    return _roi_model_out(model)


@router.post(
    "/{case_id}/roi-models/{version}/lines", status_code=201, response_model=RoiModelOut
)
def add_roi_line(
    case_id: int,
    version: int,
    payload: RoiLineIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> RoiModelOut:
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    assumption = _assumption_by_code(db, case, payload.amount_code)

    db.add(
        RoiLine(
            roi_model_id=model.id,
            kind=payload.kind,
            category=payload.category,
            label=payload.label,
            year_index=payload.year_index,
            amount_assumption_id=assumption.id,
            quantity=payload.quantity,
            notes=payload.notes,
        )
    )
    db.commit()
    db.refresh(model)
    return _roi_model_out(model)


@router.delete("/{case_id}/roi-models/{version}/lines/{line_id}", status_code=204)
def delete_roi_line(
    case_id: int,
    version: int,
    line_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> None:
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    line = db.get(RoiLine, line_id)
    if line is None or line.roi_model_id != model.id:
        raise HTTPException(404, "ROI line not found on that model version")
    db.delete(line)
    db.commit()


@router.get("/{case_id}/roi", response_model=RoiResultOut)
def get_roi(
    case_id: int,
    scenario: str = SCENARIO_QUERY,
    version: int | None = Query(default=None, description="Defaults to the latest."),
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> RoiResultOut:
    """Discounted cash flow for one model version under one scenario."""
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    return RoiResultOut.model_validate(roi.compute(model, _validate_scenario(scenario)))


@router.get("/{case_id}/roi/scenarios", response_model=ScenarioComparisonOut)
def get_scenarios(
    case_id: int,
    version: int | None = None,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> ScenarioComparisonOut:
    """All three scenarios side by side. The first thing a CFO asks for."""
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    results = roi.compare_scenarios(model)
    return ScenarioComparisonOut(
        pessimistic=RoiResultOut.model_validate(results["pessimistic"]),
        base=RoiResultOut.model_validate(results["base"]),
        optimistic=RoiResultOut.model_validate(results["optimistic"]),
    )


@router.get("/{case_id}/roi/tornado", response_model=list[TornadoRowOut])
def get_tornado(
    case_id: int,
    version: int | None = None,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> list[TornadoRowOut]:
    """One assumption varied at a time, ranked by how far it moves the NPV."""
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    return [TornadoRowOut.model_validate(row) for row in roi.tornado(model)]


@router.get("/{case_id}/roi/fragility", response_model=FragilityOut)
def get_fragility(
    case_id: int,
    version: int | None = None,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> FragilityOut:
    """Where the case is weakest, before anyone else points it out."""
    case = _load_case(db, case_id, profile)
    model = _pick_model(case, version)
    return FragilityOut.model_validate(roi.fragility(model))


# --------------------------------------------------------------------------
# Reviews
# --------------------------------------------------------------------------


@router.get("/{case_id}/reviews", response_model=list[CaseReviewOut])
def get_reviews(
    case_id: int,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> list[CaseReviewOut]:
    case = _load_case(db, case_id, profile)
    return _reviews_out(db, case)


@router.post(
    "/{case_id}/challenges/{challenge_id}/response", response_model=ReviewChallengeOut
)
def answer_challenge(
    case_id: int,
    challenge_id: int,
    payload: ChallengeResponseIn,
    profile: Profile = Depends(get_profile),
    db: Session = Depends(get_db),
) -> ReviewChallengeOut:
    """Record how an objection was answered.

    Kept on the challenge rather than in a free-text note so that "which of
    the board's objections are still open" stays a query rather than a
    reading exercise.
    """
    case = _load_case(db, case_id, profile)
    challenge = db.get(CaseReviewChallenge, challenge_id)
    if challenge is None or challenge.review.case_id != case.id:
        raise HTTPException(404, "challenge not found on this case")

    challenge.response = payload.response
    challenge.resolved_on = payload.resolved_on or date.today()
    db.commit()

    codes = {a.id: a.code for a in case.assumptions}
    return ReviewChallengeOut(
        id=challenge.id,
        persona=challenge.persona,
        severity=challenge.severity,
        target_assumption_id=challenge.target_assumption_id,
        target_assumption_code=codes.get(challenge.target_assumption_id),
        target_area=challenge.target_area,
        challenge=challenge.challenge,
        evidence_demanded=challenge.evidence_demanded,
        response=challenge.response,
        resolved_on=challenge.resolved_on,
    )
