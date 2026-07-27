"""Review board critiques and periodic reviews.

The review board is an adversarial agent, not an assistant. It does not write
the case; it attacks one. So the schema stores what an attack actually
consists of: a persona, a severity, the specific assumption being challenged,
and what evidence would settle it. A free-text blob of feedback would be
unusable after the fifth case — these rows are queryable, which is what turns
"I got criticised a lot" into "my cost assumptions are consistently the weakest
part of my cases, and have been for a year".

Scores are stored per criterion rather than as a single mark, for the same
reason. The trajectory needs to show which dimension of analytical rigour is
improving.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    PERIODIC_REVIEW_KINDS,
    REVIEW_PERSONAS,
    SEVERITIES,
    Base,
    Code,
    Label,
    TimestampMixin,
    enum_check,
)

if TYPE_CHECKING:
    from app.models.agent import AgentRun
    from app.models.business_case import Assumption, BusinessCase, RoiModel
    from app.models.profile import Profile


class ReviewCriterion(Base, TimestampMixin):
    """assumption_rigour, technical_feasibility, roi_credibility,
    narrative_clarity, risk_management.

    A lookup table so the scoring rubric is data the agent prompt reads, not a
    constant duplicated between Python, the prompt file and the front end.
    """

    __tablename__ = "review_criterion"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    # Relative weight in the overall mark. Stored, so the rubric can be
    # rebalanced without rewriting history.
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=1)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CaseReview(Base, TimestampMixin):
    __tablename__ = "case_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("business_case.id", ondelete="CASCADE"), nullable=False
    )
    # Which financial model was on the table. Null only for cases reviewed
    # before any ROI model existed.
    roi_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("roi_model.id", ondelete="SET NULL")
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_run.id", ondelete="SET NULL")
    )
    reviewed_on: Mapped[date] = mapped_column(Date, nullable=False)
    # Weighted roll-up of the per-criterion scores, 0-10. Stored because it is
    # the agent's own verdict at a point in time, not a recomputable
    # aggregate: the criterion weights may change afterwards.
    overall_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    verdict: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)

    case: Mapped[BusinessCase] = relationship()
    roi_model: Mapped[RoiModel | None] = relationship()
    agent_run: Mapped[AgentRun | None] = relationship()
    scores: Mapped[list[CaseReviewScore]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    challenges: Mapped[list[CaseReviewChallenge]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 0 AND 10", name="overall_score_range"),
    )


class CaseReviewScore(Base, TimestampMixin):
    __tablename__ = "case_review_score"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("case_review.id", ondelete="CASCADE"), nullable=False
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("review_criterion.id", ondelete="RESTRICT"), nullable=False
    )
    score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    review: Mapped[CaseReview] = relationship(back_populates="scores")
    criterion: Mapped[ReviewCriterion] = relationship()

    __table_args__ = (
        UniqueConstraint("review_id", "criterion_id", name="uq_review_criterion"),
        CheckConstraint("score BETWEEN 0 AND 10", name="score_range"),
    )


class CaseReviewChallenge(Base, TimestampMixin):
    """One specific objection from one persona.

    `target_assumption_id` is what makes this table worth having: an objection
    pinned to an assumption can be answered by editing that assumption and
    re-running the review, and the two runs can be compared row by row.
    """

    __tablename__ = "case_review_challenge"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("case_review.id", ondelete="CASCADE"), nullable=False
    )
    persona: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    target_assumption_id: Mapped[int | None] = mapped_column(
        ForeignKey("assumption.id", ondelete="SET NULL")
    )
    target_area: Mapped[str | None] = mapped_column(Label)
    challenge: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_demanded: Mapped[str | None] = mapped_column(Text)
    # Filled in by the owner, not the agent: how the objection was answered.
    response: Mapped[str | None] = mapped_column(Text)
    resolved_on: Mapped[date | None] = mapped_column(Date)

    review: Mapped[CaseReview] = relationship(back_populates="challenges")
    target_assumption: Mapped[Assumption | None] = relationship()

    __table_args__ = (
        enum_check("persona", REVIEW_PERSONAS, "persona"),
        enum_check("severity", SEVERITIES, "severity"),
    )


class PeriodicReview(Base, TimestampMixin):
    """A generated weekly or quarterly review.

    Stored so that "what did I say I would do next" is answerable four weeks
    later, and so that a run of reviews saying nothing shipped is visible as a
    pattern rather than forgotten one week at a time.
    """

    __tablename__ = "periodic_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_run.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text)
    next_action_rationale: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[Profile] = relationship()
    agent_run: Mapped[AgentRun | None] = relationship()

    __table_args__ = (
        enum_check("kind", PERIODIC_REVIEW_KINDS, "kind"),
        UniqueConstraint("profile_id", "kind", "period_start", name="uq_periodic_review"),
        CheckConstraint("period_end >= period_start", name="period_order"),
    )
