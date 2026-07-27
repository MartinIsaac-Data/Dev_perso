"""Profile and trajectory phases.

Why a `profile` table in a single-user application?

Because the demo dataset and the real dataset must coexist without ever being
confused. Every row that holds user data carries a profile_id, and the demo
profile is flagged. Showing this application in an interview then means
selecting the demo profile, not maintaining a second database, a sanitising
export script, or a fixture that drifts from the real schema.

That is also why phases are rows and not constants: the 2026-2032 trajectory
is data, and the quota rules attached to each phase are data too. Nothing
about the plan is compiled into the code.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Code, Label, TimestampMixin

if TYPE_CHECKING:
    from app.models.deliverable import DeliverableType


class Profile(Base, TimestampMixin):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Label, nullable=False)
    # True for the shipped demo dataset, False for the owner's real data.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    based_in: Mapped[str | None] = mapped_column(Label)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")


class Phase(Base, TimestampMixin):
    """A segment of the 10-year trajectory, e.g. 2026-2027 'Foundations'."""

    __tablename__ = "phase"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)

    quotas: Mapped[list[DeliverableQuota]] = relationship(
        back_populates="phase", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("ordinal", name="uq_phase_ordinal"),)


class DeliverableQuota(Base, TimestampMixin):
    """How many deliverables of a given type a quarter must produce, per phase.

    Expressed per quarter rather than per year on purpose: an annual quota is
    satisfiable by a burst in December, which is exactly the failure mode this
    application exists to make visible.
    """

    __tablename__ = "deliverable_quota"

    id: Mapped[int] = mapped_column(primary_key=True)
    phase_id: Mapped[int] = mapped_column(
        ForeignKey("phase.id", ondelete="CASCADE"), nullable=False
    )
    deliverable_type_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable_type.id", ondelete="RESTRICT"), nullable=False
    )
    min_per_quarter: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    phase: Mapped[Phase] = relationship(back_populates="quotas")
    deliverable_type: Mapped[DeliverableType] = relationship()

    __table_args__ = (
        UniqueConstraint("phase_id", "deliverable_type_id", name="uq_quota_phase_type"),
    )


class TargetRole(Base, TimestampMixin):
    """A job title the trajectory aims at. Anchors the market gap analysis."""

    __tablename__ = "target_role"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Label, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
