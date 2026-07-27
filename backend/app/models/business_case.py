"""Business Case Lab.

This is the module that separates "I build dashboards" from "I can stand in
front of a CFO". Its schema encodes one opinion above all others:

    every number in a business case traces back to a named, sourced assumption.

There is no free-floating `amount` column on a cost line and no hand-typed
total on a branch of the issue tree. A ROI line points at an Assumption. A leaf
of the cause tree is the product of Assumptions. That is the whole design, and
it is what makes the sensitivity analysis possible at all: if amounts were
typed directly, there would be nothing to vary.

Two consequences worth stating plainly:

  - Entering a case is slower than typing figures into a spreadsheet. That is
    the point. The friction is the training.
  - `low_value` / `high_value` are on the assumption, not on the scenario. A
    scenario is then a *rule* for picking one of the three (pessimistic picks
    the unfavourable end, given whether the line is a cost or a benefit),
    rather than a third set of hand-entered numbers that can drift out of
    step with the base case.

Derived quantities — branch totals, NPV, payback, tornado rankings — are
deliberately absent from this schema. They are computed from these rows in
Phase 2 and snapshotted only into the analytical star layer in Phase 4. A
normalised model that stores its own aggregates is a model that will
eventually disagree with itself.
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
    CASE_STATUSES,
    CONFIDENCE,
    ROI_CATEGORIES,
    ROI_KINDS,
    Base,
    Code,
    Label,
    Money,
    Rate,
    TimestampMixin,
    enum_check,
)

if TYPE_CHECKING:
    from app.models.profile import Profile


class BusinessCase(Base, TimestampMixin):
    __tablename__ = "business_case"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Label, nullable=False)
    company_context: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Label)
    # The sentence the director actually said: "we lose 20 million a year".
    symptom: Mapped[str] = mapped_column(Text, nullable=False)
    # What they claim it costs. Kept distinct from the bottom-up total the
    # cause tree produces, because the gap between the two is the first thing
    # any competent review board attacks.
    claimed_annual_loss: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    opened_on: Mapped[date] = mapped_column(Date, nullable=False)

    profile: Mapped[Profile] = relationship()
    assumptions: Mapped[list[Assumption]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    cause_nodes: Mapped[list[CauseNode]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    roi_models: Mapped[list[RoiModel]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )

    __table_args__ = (enum_check("status", CASE_STATUSES, "status"),)


class Assumption(Base, TimestampMixin):
    """A named quantity with a range, a source and a confidence level.

    `source` is nullable in the schema but the review board treats a null
    source as an automatic finding. Making it NOT NULL would only encourage
    typing "internal estimate" to satisfy the database.
    """

    __tablename__ = "assumption"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("business_case.id", ondelete="CASCADE"), nullable=False
    )
    # Short handle used when reading the model, e.g. `pallets_per_week`.
    code: Mapped[str] = mapped_column(Code, nullable=False)
    label: Mapped[str] = mapped_column(Label, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64))
    # Wide precision: this column holds unit costs, headcounts and rates
    # alike, so it cannot assume two decimal places.
    base_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    low_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    source: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    rationale: Mapped[str | None] = mapped_column(Text)

    case: Mapped[BusinessCase] = relationship(back_populates="assumptions")

    __table_args__ = (
        UniqueConstraint("case_id", "code", name="uq_assumption_case_code"),
        enum_check("confidence", CONFIDENCE, "confidence"),
        CheckConstraint(
            "low_value IS NULL OR low_value <= base_value", name="low_below_base"
        ),
        CheckConstraint(
            "high_value IS NULL OR high_value >= base_value", name="high_above_base"
        ),
    )


class CauseNode(Base, TimestampMixin):
    """A node of the issue tree, stored as an adjacency list.

    Adjacency list rather than nested sets or a materialised path: these trees
    have tens of nodes, not millions, and are edited constantly while
    reasoning. Recursive CTEs read them back in one query on both SQLite and
    Postgres, which is also a technique worth practising.

    Only leaves carry drivers. An internal node's value is the sum of its
    children — computed, never stored.
    """

    __tablename__ = "cause_node"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("business_case.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("cause_node.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(Label, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # How sure we are this branch is a real cause, independent of its size.
    evidence_note: Mapped[str | None] = mapped_column(Text)

    case: Mapped[BusinessCase] = relationship(back_populates="cause_nodes")
    parent: Mapped[CauseNode | None] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list[CauseNode]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    drivers: Mapped[list[CauseDriver]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class CauseDriver(Base, TimestampMixin):
    """One factor in a leaf's quantification.

    A leaf's annual cost is the product of its drivers:
    `120 pallets/week x 52 weeks x 38 EUR of rework` reads as three rows here.
    Forcing multiplication of named quantities rather than accepting a single
    typed total is what makes the branch defensible when someone asks "where
    does that number come from".
    """

    __tablename__ = "cause_driver"

    id: Mapped[int] = mapped_column(primary_key=True)
    cause_node_id: Mapped[int] = mapped_column(
        ForeignKey("cause_node.id", ondelete="CASCADE"), nullable=False
    )
    assumption_id: Mapped[int] = mapped_column(
        ForeignKey("assumption.id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    node: Mapped[CauseNode] = relationship(back_populates="drivers")
    assumption: Mapped[Assumption] = relationship()

    __table_args__ = (
        UniqueConstraint("cause_node_id", "assumption_id", name="uq_cause_driver"),
    )


class Solution(Base, TimestampMixin):
    """The designed answer. One per case; revisions overwrite.

    These are long-form text columns rather than a structured sub-schema, and
    that is a deliberate limit: the value of this section is the quality of the
    thinking, not the tidiness of its storage. The review board reads prose.
    KPIs are the exception — they are rows, because they must be countable.
    """

    __tablename__ = "solution"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("business_case.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    data_requirements: Mapped[str | None] = mapped_column(Text)
    architecture: Mapped[str | None] = mapped_column(Text)
    ai_component: Mapped[str | None] = mapped_column(Text)
    automation_component: Mapped[str | None] = mapped_column(Text)
    process_change: Mapped[str | None] = mapped_column(Text)
    governance: Mapped[str | None] = mapped_column(Text)
    deployment_plan: Mapped[str | None] = mapped_column(Text)
    key_risks: Mapped[str | None] = mapped_column(Text)

    case: Mapped[BusinessCase] = relationship()
    kpis: Mapped[list[SolutionKpi]] = relationship(
        back_populates="solution", cascade="all, delete-orphan"
    )


class SolutionKpi(Base, TimestampMixin):
    """A steering indicator, with the baseline it must move from."""

    __tablename__ = "solution_kpi"

    id: Mapped[int] = mapped_column(primary_key=True)
    solution_id: Mapped[int] = mapped_column(
        ForeignKey("solution.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Label, nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(64))
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    measurement_frequency: Mapped[str | None] = mapped_column(String(64))
    data_source: Mapped[str | None] = mapped_column(Label)

    solution: Mapped[Solution] = relationship(back_populates="kpis")


class RoiModel(Base, TimestampMixin):
    """A versioned financial model for a case.

    Versioned rather than mutable because the review board's critique is
    attached to the version it actually reviewed. Rebuilding a model after a
    hostile review and comparing the two is the exercise.
    """

    __tablename__ = "roi_model"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("business_case.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    horizon_years: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # Annual discount rate as a decimal fraction, e.g. 0.12 for 12%.
    discount_rate: Mapped[Decimal] = mapped_column(Rate, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    notes: Mapped[str | None] = mapped_column(Text)

    case: Mapped[BusinessCase] = relationship(back_populates="roi_models")
    lines: Mapped[list[RoiLine]] = relationship(
        back_populates="roi_model", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_roi_model_case_version"),
        CheckConstraint("horizon_years BETWEEN 1 AND 15", name="horizon_range"),
        CheckConstraint("discount_rate >= 0", name="discount_rate_non_negative"),
    )


class RoiLine(Base, TimestampMixin):
    """One cash flow in one year.

    `amount_assumption_id` is NOT NULL by design. A fixed, perfectly known cost
    is expressed as an assumption whose low, base and high values are equal and
    whose confidence is high — which costs one extra row and buys a model where
    every figure has a source field waiting to be filled.
    """

    __tablename__ = "roi_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    roi_model_id: Mapped[int] = mapped_column(
        ForeignKey("roi_model.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(Label, nullable=False)
    # 0 is the investment year. Costs usually start at 0, benefits later.
    year_index: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_assumption_id: Mapped[int] = mapped_column(
        ForeignKey("assumption.id", ondelete="RESTRICT"), nullable=False
    )
    # Optional multiplier for lines like "3 licences at the unit price"
    # without inventing a second assumption for the count.
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text)

    roi_model: Mapped[RoiModel] = relationship(back_populates="lines")
    amount_assumption: Mapped[Assumption] = relationship()

    __table_args__ = (
        enum_check("kind", ROI_KINDS, "kind"),
        enum_check("category", ROI_CATEGORIES, "category"),
        CheckConstraint("year_index >= 0", name="year_index_non_negative"),
    )
