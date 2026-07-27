"""All ORM models.

Alembic's autogenerate only sees tables that have been imported by the time it
inspects the metadata, so every model module is imported here and this module
is imported by alembic/env.py. A model that is not re-exported here will
silently never get a migration.
"""

from app.models.agent import AgentRun
from app.models.base import Base
from app.models.business_case import (
    Assumption,
    BusinessCase,
    CauseDriver,
    CauseNode,
    RoiLine,
    RoiModel,
    Solution,
    SolutionKpi,
)
from app.models.deliverable import (
    Deliverable,
    DeliverableImpact,
    DeliverableSkill,
    DeliverableType,
    Mention,
)
from app.models.market import JobPosting, JobRequirement
from app.models.profile import DeliverableQuota, Phase, Profile, TargetRole
from app.models.review import (
    CaseReview,
    CaseReviewChallenge,
    CaseReviewScore,
    PeriodicReview,
    ReviewCriterion,
)
from app.models.skill import (
    Skill,
    SkillDomain,
    SkillEdge,
    SkillLevel,
    SkillLevelChange,
    SkillState,
)

__all__ = [
    "AgentRun",
    "Assumption",
    "Base",
    "BusinessCase",
    "CaseReview",
    "CaseReviewChallenge",
    "CaseReviewScore",
    "CauseDriver",
    "CauseNode",
    "Deliverable",
    "DeliverableImpact",
    "DeliverableQuota",
    "DeliverableSkill",
    "DeliverableType",
    "JobPosting",
    "JobRequirement",
    "Mention",
    "PeriodicReview",
    "Phase",
    "Profile",
    "ReviewCriterion",
    "RoiLine",
    "RoiModel",
    "Skill",
    "SkillDomain",
    "SkillEdge",
    "SkillLevel",
    "SkillLevelChange",
    "SkillState",
    "Solution",
    "SolutionKpi",
    "TargetRole",
]
