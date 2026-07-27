"""Deliverables: the only unit of progress this system recognises.

There is deliberately no `hours_spent` column anywhere in this schema. Time
spent is an input, not an outcome, and a system that measures it optimises for
looking busy. What counts is what exists at the end: a published project, a
certification, an article, a talk, a merged contribution, a paid engagement.

`published_on` is nullable and separate from `started_on` for the same reason.
A deliverable that has been "in progress" for three quarters is precisely the
signal the quarterly review needs to surface.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    DELIVERABLE_STATUSES,
    Base,
    Code,
    Label,
    Money,
    TimestampMixin,
    enum_check,
)

if TYPE_CHECKING:
    from app.models.profile import Profile
    from app.models.skill import Skill


class DeliverableType(Base, TimestampMixin):
    """project, article, talk, certification, open_source, engagement.

    A lookup table rather than a CHECK constraint because the list is expected
    to grow with the trajectory — a `book_chapter` type belongs to the 2032+
    phase and adding it should be a row, not a migration.
    """

    __tablename__ = "deliverable_type"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    # Does this type count towards public visibility (Reputation Tracker)?
    # A certification is a real deliverable but it is not a publication.
    is_publication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text)


class Deliverable(Base, TimestampMixin):
    __tablename__ = "deliverable"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    type_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable_type.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Label, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    started_on: Mapped[date | None] = mapped_column(Date)
    published_on: Mapped[date | None] = mapped_column(Date)
    # The artefact itself: a repository, an article URL, a local file.
    artifact_url: Mapped[str | None] = mapped_column(String(1024))
    artifact_path: Mapped[str | None] = mapped_column(String(1024))
    # Only for engagements: what the client actually paid or saved.
    business_value: Mapped[Decimal | None] = mapped_column(Money)

    profile: Mapped[Profile] = relationship()
    type: Mapped[DeliverableType] = relationship()
    skills: Mapped[list[DeliverableSkill]] = relationship(
        back_populates="deliverable", cascade="all, delete-orphan"
    )
    impacts: Mapped[list[DeliverableImpact]] = relationship(
        back_populates="deliverable", cascade="all, delete-orphan"
    )

    __table_args__ = (
        enum_check("status", DELIVERABLE_STATUSES, "status"),
        # A published deliverable must say when. Anything else makes the
        # quarterly quota uncomputable.
        CheckConstraint(
            "status <> 'published' OR published_on IS NOT NULL",
            name="published_requires_date",
        ),
    )


class DeliverableSkill(Base, TimestampMixin):
    """Which skills a deliverable actually exercised, and how hard.

    `contribution` is 1-3, not a percentage: percentages invite the fiction
    that a project touched eleven skills at 9% each. Three levels force a
    choice between "central to this work", "meaningfully used" and "touched".
    """

    __tablename__ = "deliverable_skill"

    id: Mapped[int] = mapped_column(primary_key=True)
    deliverable_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skill.id", ondelete="RESTRICT"), nullable=False
    )
    contribution: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    deliverable: Mapped[Deliverable] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship()

    __table_args__ = (
        UniqueConstraint("deliverable_id", "skill_id", name="uq_deliverable_skill"),
        enum_check("contribution", ("1", "2", "3"), "contribution_range"),
    )


class DeliverableImpact(Base, TimestampMixin):
    """Measured reach or effect, as a time series rather than a single column.

    Views on an article three days after publication and three years after
    publication are different facts. Storing them as separate rows keeps the
    Reputation Tracker honest about when reach was measured.
    """

    __tablename__ = "deliverable_impact"

    id: Mapped[int] = mapped_column(primary_key=True)
    deliverable_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable.id", ondelete="CASCADE"), nullable=False
    )
    metric_code: Mapped[str] = mapped_column(Code, nullable=False)
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(Label)

    deliverable: Mapped[Deliverable] = relationship(back_populates="impacts")

    __table_args__ = (
        UniqueConstraint(
            "deliverable_id", "metric_code", "measured_on", name="uq_impact_point"
        ),
    )


class Mention(Base, TimestampMixin):
    """Third-party reference to the work: a citation, an invitation, a repost.

    Kept separate from DeliverableImpact because a mention is not a metric on
    something you produced — it is evidence that someone else acted on it, and
    it may not attach to any single deliverable.
    """

    __tablename__ = "mention"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )
    deliverable_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliverable.id", ondelete="SET NULL")
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(Label, nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    note: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[Profile] = relationship()
    deliverable: Mapped[Deliverable | None] = relationship()
