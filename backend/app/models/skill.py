"""Skill graph.

The design decision that shapes this whole module: a skill is a *node in a
directed acyclic graph*, not a row in a list. `dimensional modelling` is not
merely "another skill after SQL" — it is unreachable until window functions
and set operations are real, and it in turn gates Fabric architecture. Storing
that as an edge table makes two questions answerable in SQL that a flat list
can never answer:

  - which skill, if left where it is, blocks the largest subtree downstream
    (the critical path);
  - which skills are actually available to work on right now, because all
    their prerequisites are already at the required level.

Acyclicity is not enforceable by a CHECK constraint in either SQLite or
Postgres. It is enforced in the service layer and asserted by tests; see
ADR-004 in ARCHITECTURE.md.

Levels are 0-5 and their meaning lives in the `skill_level` lookup table
rather than in a comment, because "level 3" has to mean the same thing in the
market gap analysis as it does in a self-assessment.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Code, Label, TimestampMixin, enum_check

if TYPE_CHECKING:
    from app.models.deliverable import Deliverable
    from app.models.profile import Profile


class SkillDomain(Base, TimestampMixin):
    """Broad family: data engineering, analytics, AI, business, leadership."""

    __tablename__ = "skill_domain"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    skills: Mapped[list[Skill]] = relationship(back_populates="domain")


class SkillLevel(Base):
    """The 0-5 scale, defined once, referenced everywhere."""

    __tablename__ = "skill_level"

    level: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    # What kind of evidence is normally required to claim this level.
    evidence_expectation: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (enum_check("level", tuple("012345"), "level_range"),)


class Skill(Base, TimestampMixin):
    """A node in the graph. Shared referential, not per-profile state."""

    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("skill_domain.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    # Months without practice after which this skill is flagged at risk.
    # Null falls back to settings.default_skill_decay_months. Hands-on
    # technical skills decay faster than conceptual ones, hence per-skill.
    decay_months: Mapped[int | None] = mapped_column(Integer)

    domain: Mapped[SkillDomain] = relationship(back_populates="skills")

    prerequisite_edges: Mapped[list[SkillEdge]] = relationship(
        back_populates="dependent",
        foreign_keys="SkillEdge.dependent_skill_id",
        cascade="all, delete-orphan",
    )
    dependent_edges: Mapped[list[SkillEdge]] = relationship(
        back_populates="prerequisite",
        foreign_keys="SkillEdge.prerequisite_skill_id",
        cascade="all, delete-orphan",
    )


class SkillEdge(Base, TimestampMixin):
    """`prerequisite` must be held before `dependent` can be meaningfully learned."""

    __tablename__ = "skill_edge"

    id: Mapped[int] = mapped_column(primary_key=True)
    prerequisite_skill_id: Mapped[int] = mapped_column(
        ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    dependent_skill_id: Mapped[int] = mapped_column(
        ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    # Level the prerequisite must reach before the dependent is unblocked.
    required_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    note: Mapped[str | None] = mapped_column(Text)

    prerequisite: Mapped[Skill] = relationship(
        back_populates="dependent_edges", foreign_keys=[prerequisite_skill_id]
    )
    dependent: Mapped[Skill] = relationship(
        back_populates="prerequisite_edges", foreign_keys=[dependent_skill_id]
    )

    __table_args__ = (
        UniqueConstraint("prerequisite_skill_id", "dependent_skill_id", name="uq_skill_edge"),
        enum_check("required_level", tuple("012345"), "required_level_range"),
        # The only cycle a CHECK can catch cheaply: the self-loop. Longer
        # cycles need a traversal, which lives in the service layer.
        CheckConstraint(
            "prerequisite_skill_id <> dependent_skill_id", name="no_self_dependency"
        ),
    )


class SkillState(Base, TimestampMixin):
    """Per-profile position on one skill.

    Separated from `skill` so the taxonomy stays a shared referential that the
    demo profile and the real profile both point at, rather than two divergent
    copies of the same graph.
    """

    __tablename__ = "skill_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_level: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # Denormalised from the most recent evidence, for cheap decay queries.
    # Recomputed by the service layer, never edited by hand.
    last_practised_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[Profile] = relationship()
    skill: Mapped[Skill] = relationship()

    __table_args__ = (
        UniqueConstraint("profile_id", "skill_id", name="uq_skill_state_profile_skill"),
        enum_check("current_level", tuple("012345"), "current_level_range"),
        enum_check("target_level", tuple("012345"), "target_level_range"),
    )


class SkillLevelChange(Base, TimestampMixin):
    """Append-only history of level movements.

    This table is where the rule "a level only rises against evidence" is
    enforced, and it is enforced by the schema rather than by a service method
    that a future refactor could bypass: a row whose `to_level` exceeds its
    `from_level` and carries no deliverable is rejected by the database.

    Downgrades need no evidence — admitting decay should never require
    paperwork, or it will not be recorded.
    """

    __tablename__ = "skill_level_change"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    from_level: Mapped[int] = mapped_column(Integer, nullable=False)
    to_level: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_on: Mapped[date] = mapped_column(Date, nullable=False)
    # The evidence. RESTRICT, not CASCADE: deleting a deliverable that once
    # justified a promotion must be a deliberate act, not a side effect.
    deliverable_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverable.id", ondelete="RESTRICT")
    )
    rationale: Mapped[str | None] = mapped_column(Text)

    deliverable: Mapped[Deliverable | None] = relationship()

    __table_args__ = (
        enum_check("from_level", tuple("012345"), "from_level_range"),
        enum_check("to_level", tuple("012345"), "to_level_range"),
        # The evidence rule, in SQL.
        CheckConstraint(
            "to_level <= from_level OR deliverable_id IS NOT NULL",
            name="promotion_needs_evidence",
        ),
    )
