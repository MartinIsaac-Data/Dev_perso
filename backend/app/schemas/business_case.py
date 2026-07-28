"""Request and response models for the Business Case Lab."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.base import (
    CASE_STATUSES,
    CONFIDENCE,
    ROI_CATEGORIES,
    ROI_KINDS,
)

# --------------------------------------------------------------------------
# Assumptions
# --------------------------------------------------------------------------


class AssumptionIn(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=255)
    base_value: Decimal
    unit: str | None = None
    low_value: Decimal | None = None
    high_value: Decimal | None = None
    source: str | None = None
    confidence: str = "medium"
    rationale: str | None = None

    @model_validator(mode="after")
    def _check(self) -> AssumptionIn:
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"confidence must be one of {', '.join(CONFIDENCE)}")
        # Mirrors the database CHECK, but with a message that says which way
        # round the bounds go.
        if self.low_value is not None and self.low_value > self.base_value:
            raise ValueError("low_value cannot exceed base_value")
        if self.high_value is not None and self.high_value < self.base_value:
            raise ValueError("high_value cannot be below base_value")
        return self


class AssumptionUpdateIn(BaseModel):
    """Partial update. Absent fields are left untouched."""

    label: str | None = None
    unit: str | None = None
    base_value: Decimal | None = None
    low_value: Decimal | None = None
    high_value: Decimal | None = None
    source: str | None = None
    confidence: str | None = None
    rationale: str | None = None


class AssumptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str
    unit: str | None = None
    base_value: Decimal
    low_value: Decimal | None = None
    high_value: Decimal | None = None
    source: str | None = None
    confidence: str
    rationale: str | None = None


# --------------------------------------------------------------------------
# Cause tree
# --------------------------------------------------------------------------


class CauseNodeIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None
    description: str | None = None
    evidence_note: str | None = None
    ordinal: int = 0
    driver_codes: list[str] = Field(
        default_factory=list,
        description="Assumption codes whose product gives this leaf's value. "
        "Only meaningful on a leaf: an internal node's value is its children's.",
    )


class DriverBreakdownOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assumption_id: int
    code: str
    label: str
    unit: str | None = None
    value: Decimal
    confidence: str
    has_source: bool


class CauseNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: int
    parent_id: int | None = None
    label: str
    description: str | None = None
    evidence_note: str | None = None
    depth: int
    is_leaf: bool
    value: Decimal
    drivers: list[DriverBreakdownOut] = []
    children: list[CauseNodeOut] = []


class ReconciliationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bottom_up_total: Decimal
    claimed_annual_loss: Decimal | None = None
    currency: str
    gap: Decimal | None = None
    gap_ratio: Decimal | None = None
    verdict: str


class CauseTreeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario: str
    currency: str
    total: Decimal
    roots: list[CauseNodeOut] = []
    ranked_leaves: list[CauseNodeOut] = []
    reconciliation: ReconciliationOut


# --------------------------------------------------------------------------
# ROI
# --------------------------------------------------------------------------


class RoiLineIn(BaseModel):
    kind: str
    category: str
    label: str = Field(min_length=1, max_length=255)
    year_index: int = Field(ge=0, le=14)
    amount_code: str = Field(description="Code of the assumption giving the amount.")
    quantity: Decimal = Decimal(1)
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> RoiLineIn:
        if self.kind not in ROI_KINDS:
            raise ValueError(f"kind must be one of {', '.join(ROI_KINDS)}")
        if self.category not in ROI_CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(ROI_CATEGORIES)}")
        return self


class RoiLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    category: str
    label: str
    year_index: int
    quantity: Decimal
    amount_assumption_id: int
    amount_code: str
    notes: str | None = None


class RoiModelIn(BaseModel):
    horizon_years: int = Field(default=5, ge=1, le=15)
    discount_rate: Decimal = Field(default=Decimal("0.12"), ge=0, le=1)
    currency: str | None = None
    notes: str | None = None


class RoiModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    horizon_years: int
    discount_rate: Decimal
    currency: str
    notes: str | None = None
    lines: list[RoiLineOut] = []


class YearFlowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year_index: int
    costs: Decimal
    benefits: Decimal
    net: Decimal


class RoiResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario: str
    currency: str
    discount_rate: Decimal
    horizon_years: int
    flows: list[YearFlowOut] = []
    npv: Decimal
    total_cost_pv: Decimal
    total_benefit_pv: Decimal
    total_cost_nominal: Decimal
    total_benefit_nominal: Decimal
    payback_years: Decimal | None = None
    benefit_cost_ratio: Decimal | None = None
    is_positive: bool


class ScenarioComparisonOut(BaseModel):
    pessimistic: RoiResultOut
    base: RoiResultOut
    optimistic: RoiResultOut


class TornadoRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assumption_id: int
    code: str
    label: str
    unit: str | None = None
    confidence: str
    source: str | None = None
    base_value: Decimal
    low_value: Decimal
    high_value: Decimal
    npv_at_low: Decimal
    npv_at_high: Decimal
    swing: Decimal
    has_range: bool
    flips_the_decision: bool


class FragilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_npv: Decimal
    pessimistic_npv: Decimal
    optimistic_npv: Decimal
    survives_pessimistic: bool
    only_fails_in_combination: bool
    headline: str
    decision_flipping: list[TornadoRowOut] = []
    unsourced: list[TornadoRowOut] = []
    low_confidence_high_impact: list[TornadoRowOut] = []
    point_estimates: list[TornadoRowOut] = []


class AssumptionAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    unsourced: list[str] = []
    point_estimates: list[str] = []
    low_confidence: list[str] = []
    unused: list[str] = []
    sourced_ratio: Decimal


# --------------------------------------------------------------------------
# Solution and reviews
# --------------------------------------------------------------------------


class SolutionKpiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    definition: str | None = None
    unit: str | None = None
    baseline_value: Decimal | None = None
    target_value: Decimal | None = None
    measurement_frequency: str | None = None
    data_source: str | None = None


class SolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data_requirements: str | None = None
    architecture: str | None = None
    ai_component: str | None = None
    automation_component: str | None = None
    process_change: str | None = None
    governance: str | None = None
    deployment_plan: str | None = None
    key_risks: str | None = None
    kpis: list[SolutionKpiOut] = []


class ReviewScoreOut(BaseModel):
    criterion_code: str
    criterion_name: str
    weight: Decimal
    score: Decimal
    comment: str | None = None


class ReviewChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona: str
    severity: str
    target_assumption_id: int | None = None
    target_assumption_code: str | None = None
    target_area: str | None = None
    challenge: str
    evidence_demanded: str | None = None
    response: str | None = None
    resolved_on: date | None = None


class CaseReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reviewed_on: date
    roi_model_version: int | None = None
    overall_score: Decimal
    verdict: str | None = None
    summary: str | None = None
    scores: list[ReviewScoreOut] = []
    challenges: list[ReviewChallengeOut] = []


class ChallengeResponseIn(BaseModel):
    response: str = Field(min_length=1)
    resolved_on: date | None = None


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


class BusinessCaseIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    symptom: str = Field(min_length=1)
    opened_on: date | None = None
    industry: str | None = None
    company_context: str | None = None
    claimed_annual_loss: Decimal | None = None
    currency: str = "EUR"
    status: str = "draft"

    @model_validator(mode="after")
    def _check(self) -> BusinessCaseIn:
        if self.status not in CASE_STATUSES:
            raise ValueError(f"status must be one of {', '.join(CASE_STATUSES)}")
        return self


class BusinessCaseSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    industry: str | None = None
    currency: str
    status: str
    opened_on: date
    claimed_annual_loss: Decimal | None = None
    bottom_up_total: Decimal
    gap_ratio: Decimal | None = None
    assumption_count: int
    latest_roi_version: int | None = None
    base_npv: Decimal | None = None
    latest_review_score: Decimal | None = None
    open_challenges: int


class BusinessCaseDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    symptom: str
    industry: str | None = None
    company_context: str | None = None
    currency: str
    status: str
    opened_on: date
    claimed_annual_loss: Decimal | None = None
    assumptions: list[AssumptionOut] = []
    cause_tree: CauseTreeOut
    solution: SolutionOut | None = None
    roi_models: list[RoiModelOut] = []
    reviews: list[CaseReviewOut] = []
    audit: AssumptionAuditOut
