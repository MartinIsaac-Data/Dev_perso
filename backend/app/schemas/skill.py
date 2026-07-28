"""Response and request models for the skill graph.

These exist as a boundary, not as duplication. The service layer returns
dataclasses carrying computed properties (`gap`, `is_blocked`); Pydantic
declares them as fields and reads them through `from_attributes`, so the
computation stays in one place and the wire format stays explicit.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SkillLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: int
    code: str
    name: str
    definition: str
    evidence_expectation: str | None = None


class SkillDomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    ordinal: int


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    decay_months: int | None = None


class SkillEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prerequisite_skill_id: int
    dependent_skill_id: int
    required_level: int
    note: str | None = None


class GraphOut(BaseModel):
    """The taxonomy itself, profile-independent. What the front end draws."""

    domains: list[SkillDomainOut]
    skills: list[SkillOut]
    edges: list[SkillEdgeOut]
    is_acyclic: bool
    longest_chain: int


class UnmetPrerequisiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    code: str
    name: str
    required_level: int
    current_level: int


class SkillPositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    code: str
    name: str
    domain_code: str
    domain_name: str
    description: str | None = None

    current_level: int
    target_level: int
    gap: int
    tracked: bool

    last_practised_on: date | None = None
    decay_months: int
    months_since_practice: int | None = None
    is_decayed: bool

    unlocks_total: int = Field(
        description="Skills downstream in the taxonomy, regardless of profile state."
    )
    blocks_below_target: int = Field(
        description="Downstream skills that are also below target — the actionable count."
    )

    is_blocked: bool
    is_available: bool
    unmet_prerequisites: list[UnmetPrerequisiteOut] = []


class DomainSummaryOut(BaseModel):
    domain_code: str
    domain_name: str
    skills: int
    targeted: int
    at_target: int
    total_gap: int
    decayed: int
    blocked: int


class SkillStateUpsertIn(BaseModel):
    """Set a target, or correct a current level without claiming progress.

    Deliberately cannot raise `current_level`: promotions go through
    /skills/{code}/level, which demands evidence. This endpoint exists for
    setting targets and for recording decay.
    """

    target_level: int = Field(ge=0, le=5)
    notes: str | None = None


class LevelChangeIn(BaseModel):
    to_level: int = Field(ge=0, le=5)
    changed_on: date | None = None
    deliverable_id: int | None = Field(
        default=None,
        description="Required when raising a level. Must be a published deliverable "
        "belonging to this profile and linked to this skill.",
    )
    rationale: str | None = None


class LevelChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int
    from_level: int
    to_level: int
    changed_on: date
    deliverable_id: int | None = None
    rationale: str | None = None
