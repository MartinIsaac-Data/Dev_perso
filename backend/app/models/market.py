"""Gap Radar: what the market asks for, versus what the profile holds.

The whole point of this module is the time axis. A single scrape of today's
job adverts tells you what to learn this quarter; six years of them tell you
which requirements are structural and which were a fashion. So nothing here is
overwritten — a posting is captured once, with its date, and stays.

`raw_text` is retained in full alongside the extracted requirements. When the
extraction prompt improves in 2028, the 2026 postings can be re-processed
rather than lost, and the two extractions can be compared.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    IMPORTANCE,
    Base,
    Label,
    TimestampMixin,
    enum_check,
)

if TYPE_CHECKING:
    from app.models.agent import AgentRun
    from app.models.profile import TargetRole
    from app.models.skill import Skill


class JobPosting(Base, TimestampMixin):
    __tablename__ = "job_posting"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("target_role.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Label, nullable=False)
    company: Mapped[str | None] = mapped_column(Label)
    location: Mapped[str | None] = mapped_column(Label)
    # Free text on purpose: "Senior", "Lead", "Principal" and "Head of" are
    # not a scale, and pretending otherwise would lose information.
    seniority_label: Mapped[str | None] = mapped_column(Label)
    source: Mapped[str | None] = mapped_column(Label)
    url: Mapped[str | None] = mapped_column(String(1024))
    posted_on: Mapped[date | None] = mapped_column(Date)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    target_role: Mapped[TargetRole | None] = relationship()
    requirements: Mapped[list[JobRequirement]] = relationship(
        back_populates="posting", cascade="all, delete-orphan"
    )


class JobRequirement(Base, TimestampMixin):
    """One extracted requirement, kept in both raw and normalised form.

    `raw_label` is what the advert said; `skill_id` is where the agent mapped
    it in the taxonomy, and it is nullable. An unmapped requirement is not a
    failure to discard — it is the most interesting row in the table, because
    it means the market is asking for something the taxonomy does not yet
    describe.
    """

    __tablename__ = "job_requirement"

    id: Mapped[int] = mapped_column(primary_key=True)
    posting_id: Mapped[int] = mapped_column(
        ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_run.id", ondelete="SET NULL")
    )
    raw_label: Mapped[str] = mapped_column(Label, nullable=False)
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skill.id", ondelete="SET NULL"))
    required_level: Mapped[int | None] = mapped_column(Integer)
    importance: Mapped[str] = mapped_column(String(32), nullable=False, default="must_have")
    evidence_quote: Mapped[str | None] = mapped_column(Text)

    posting: Mapped[JobPosting] = relationship(back_populates="requirements")
    skill: Mapped[Skill | None] = relationship()
    agent_run: Mapped[AgentRun | None] = relationship()

    __table_args__ = (
        enum_check("importance", IMPORTANCE, "importance"),
        UniqueConstraint("posting_id", "raw_label", "agent_run_id", name="uq_requirement"),
    )
