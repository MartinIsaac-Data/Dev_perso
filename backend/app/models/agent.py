"""Agent execution log.

Every call to the Anthropic API is a row here, and everything an agent
produces — an extraction, a review board critique, a weekly review — points
back at the run that produced it.

The reason is reproducibility. A critique that scored a business case 6/10
eighteen months ago is only interpretable if you know which prompt version and
which model produced it. Storing `prompt_sha256` alongside the path means a
silently edited prompt file cannot masquerade as the one that was actually
used: the hash will not match the file on disk.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    AGENT_RUN_STATUSES,
    Base,
    Code,
    TimestampMixin,
    enum_check,
)


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(Code, nullable=False)
    # Path relative to the repository root, e.g.
    # backend/app/services/agents/prompts/review_board.md
    prompt_path: Mapped[str] = mapped_column(String(512), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (enum_check("status", AGENT_RUN_STATUSES, "status"),)


__all__ = ["AgentRun"]
