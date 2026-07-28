"""Response and request models for deliverables, quotas and evidence."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.base import DELIVERABLE_STATUSES


class DeliverableTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_publication: bool
    description: str | None = None


class DeliverableSkillIn(BaseModel):
    skill_code: str
    contribution: int = Field(
        default=2,
        ge=1,
        le=3,
        description="3 central to this work, 2 meaningfully used, 1 touched.",
    )


class DeliverableSkillOut(BaseModel):
    skill_id: int
    skill_code: str
    skill_name: str
    contribution: int


class DeliverableImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_code: str
    value: Decimal
    unit: str | None = None
    measured_on: date
    source: str | None = None


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None = None
    type_code: str
    type_name: str
    status: str
    started_on: date | None = None
    published_on: date | None = None
    artifact_url: str | None = None
    business_value: Decimal | None = None
    skills: list[DeliverableSkillOut] = []
    impacts: list[DeliverableImpactOut] = []


class DeliverableIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    type_code: str
    status: str = "planned"
    summary: str | None = None
    started_on: date | None = None
    published_on: date | None = None
    artifact_url: str | None = None
    business_value: Decimal | None = None
    skills: list[DeliverableSkillIn] = []

    @model_validator(mode="after")
    def _check(self) -> DeliverableIn:
        if self.status not in DELIVERABLE_STATUSES:
            raise ValueError(
                f"status must be one of {', '.join(DELIVERABLE_STATUSES)}"
            )
        # Mirrors the database CHECK, but fails with a readable message at the
        # edge instead of an IntegrityError from three layers down.
        if self.status == "published" and self.published_on is None:
            raise ValueError("a published deliverable needs a published_on date")
        if (
            self.started_on
            and self.published_on
            and self.published_on < self.started_on
        ):
            raise ValueError("published_on cannot precede started_on")
        return self


class DeliverableUpdateIn(BaseModel):
    """Partial update. Absent fields are left untouched."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    status: str | None = None
    started_on: date | None = None
    published_on: date | None = None
    artifact_url: str | None = None
    business_value: Decimal | None = None
    skills: list[DeliverableSkillIn] | None = None


class QuotaLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type_code: str
    type_name: str
    required: int
    published: int
    met: bool
    shortfall: int


class QuarterStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    quarter: int
    starts_on: date
    ends_on: date
    phase_code: str | None = None
    phase_name: str | None = None
    is_current: bool
    in_scope: bool = Field(
        description="Whether the trajectory demanded anything of this quarter. "
        "`met` and `is_silent` are meaningless when false — a quarter that "
        "predates the plan cannot fail it."
    )
    met: bool
    is_silent: bool
    total_published: int
    lines: list[QuotaLineOut] = []


class EvidenceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    deliverable_id: int
    title: str
    type_code: str
    type_name: str
    published_on: date | None = None
    artifact_url: str | None = None
    cited_for_promotion: bool
    contribution: int | None = None


class SkillEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_code: str
    skill_name: str
    domain_name: str
    current_level: int
    is_defensible: bool
    evidence: list[EvidenceItemOut] = []
