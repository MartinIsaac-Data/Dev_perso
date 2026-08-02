"""Tables for Phase 1 (Database.md §5).

Scope note: the semantic-search tables (`chunk`, embeddings) belong to sprint 06
in the Roadmap and are not part of this phase; the schema is otherwise faithful to
Database.md, including `account_id` on every tenant-owned table so RLS applies
uniformly (ADR-005).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    AiOperation,
    AiRunStatus,
    CaptureKind,
    CaptureSource,
    CaptureStatus,
    EntryOrigin,
    EntryStatus,
    EntryType,
    Priority,
)
from app.infra.db.models.base import Base, TimestampMixin, uuid_pk


def _enum_check(column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=f"{column}_valid")


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
class Account(Base, TimestampMixin):
    __tablename__ = "account"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(
        String(16), default="personal", server_default="personal", nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    data_region: Mapped[str] = mapped_column(
        String(8), default="eu", server_default="eu", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default="active", server_default="active", nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('personal','team')", name="kind_valid"),
        CheckConstraint("data_region IN ('eu','us')", name="data_region_valid"),
        CheckConstraint(
            "status IN ('active','suspended','pending_deletion','deleted')",
            name="status_valid",
        ),
    )


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    # Supabase `auth.users.id` — the external identity this row mirrors (ADR-029).
    auth_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_name: Mapped[str | None] = mapped_column(String(120))
    # Presentation data, but load-bearing: "jeudi" cannot be resolved without it.
    timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Paris", server_default="Europe/Paris", nullable=False
    )
    locale: Mapped[str] = mapped_column(
        String(8), default="fr-FR", server_default="fr-FR", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(16), default="owner", server_default="owner", nullable=False
    )
    daily_review_at: Mapped[str | None] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(
        String(24), default="active", server_default="active", nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("auth_subject", name="app_user_auth_subject_unique"),
        UniqueConstraint("email", name="app_user_email_unique"),
        CheckConstraint("role IN ('owner','admin','member')", name="role_valid"),
        CheckConstraint(
            "status IN ('active','suspended','pending_deletion','deleted')",
            name="status_valid",
        ),
    )


class Device(Base, TimestampMixin):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(32))
    os_version: Mapped[str | None] = mapped_column(String(32))
    push_token: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "platform IN ('ios','android','web','watchos','wearos')", name="platform_valid"
        ),
    )


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #
class Capture(Base, TimestampMixin):
    __tablename__ = "capture"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device.id", ondelete="SET NULL")
    )

    # Idempotency key generated client-side before recording (ADR-009). Replaying
    # the declaration is a no-op, which is what makes offline retry safe.
    client_capture_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    kind: Mapped[str] = mapped_column(
        String(16), default=CaptureKind.QUICK, server_default="quick", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=CaptureStatus.PENDING_UPLOAD,
        server_default="pending_upload",
        nullable=False,
    )

    audio_object_key: Mapped[str | None] = mapped_column(Text)
    audio_bytes: Mapped[int | None] = mapped_column(BigInteger)
    audio_format: Mapped[str | None] = mapped_column(String(16))
    audio_sample_rate: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(
        String(24), default=CaptureSource.APP, server_default="app", nullable=False
    )
    language_hint: Mapped[str | None] = mapped_column(String(8))

    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(48))
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    # Set when the plan quota is exceeded: the capture is still stored and
    # transcribed, only the AI enrichment is deferred (ADR-026).
    processing_mode: Mapped[str] = mapped_column(
        String(16), default="normal", server_default="normal", nullable=False
    )

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transcripts: Mapped[list[Transcript]] = relationship(
        back_populates="capture", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "client_capture_id", name="capture_client_id_unique"),
        CheckConstraint("duration_ms > 0", name="duration_positive"),
        CheckConstraint("audio_bytes IS NULL OR audio_bytes >= 0", name="bytes_positive"),
        CheckConstraint("processing_mode IN ('normal','degraded')", name="processing_mode_valid"),
        _enum_check("kind", CaptureKind),
        _enum_check("status", CaptureStatus),
        _enum_check("source", CaptureSource),
        CheckConstraint(
            "audio_format IS NULL OR audio_format IN ('m4a','opus','wav','mp3','webm')",
            name="audio_format_valid",
        ),
        Index("capture_account_time_idx", "account_id", captured_at.desc()),
        Index(
            "capture_processing_idx",
            "status",
            "created_at",
            postgresql_where=status.notin_(("completed", "abandoned")),
        ),
    )


class Transcript(Base):
    __tablename__ = "transcript"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    capture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capture.id", ondelete="CASCADE"), nullable=False
    )

    engine: Mapped[str] = mapped_column(String(48), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    is_fallback: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    language: Mapped[str] = mapped_column(String(8), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    words: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Immutable: a re-transcription creates a new revision, it never overwrites
    # (ADR-011).
    revision: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1", nullable=False
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    capture: Mapped[Capture] = relationship(back_populates="transcripts")

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index(
            "transcript_one_current_idx",
            "capture_id",
            unique=True,
            postgresql_where=is_current.is_(True),
        ),
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segment"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcript.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    __table_args__ = (
        CheckConstraint("end_ms > start_ms", name="segment_order"),
        CheckConstraint("start_ms >= 0", name="segment_start_positive"),
        UniqueConstraint("transcript_id", "seq", name="transcript_segment_seq_unique"),
    )


# --------------------------------------------------------------------------- #
# Knowledge
# --------------------------------------------------------------------------- #
class Project(Base, TimestampMixin):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))
    # Spoken aliases feed project matching during extraction (AI.md §5.2).
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("account_id", "slug", name="project_slug_unique"),
        CheckConstraint("depth BETWEEN 0 AND 2", name="depth_range"),
    )


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    normalized: Mapped[str] = mapped_column(String(60), nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("account_id", "normalized", name="tag_unique"),)


class Entry(Base, TimestampMixin):
    __tablename__ = "entry"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    # SET NULL, not CASCADE: deleting the audio must not destroy the tasks drawn
    # from it (ADR-028).
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capture.id", ondelete="SET NULL")
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL")
    )

    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default=EntryStatus.ACTIVE, server_default="active", nullable=False
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    origin: Mapped[str] = mapped_column(
        String(16), default=EntryOrigin.AI, server_default="ai", nullable=False
    )
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    source_span_start: Mapped[int | None] = mapped_column(Integer)
    source_span_end: Mapped[int | None] = mapped_column(Integer)

    # Authoritative: a reprocessing run never overwrites a human correction
    # (ADR-027).
    edited_by_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task | None] = relationship(
        back_populates="entry", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    __table_args__ = (
        _enum_check("entry_type", EntryType),
        _enum_check("status", EntryStatus),
        _enum_check("origin", EntryOrigin),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint(
            "source_span_start IS NULL OR source_span_end > source_span_start",
            name="span_valid",
        ),
        Index(
            "entry_account_occurred_idx",
            "account_id",
            occurred_at.desc(),
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "entry_account_type_idx",
            "account_id",
            "entry_type",
            occurred_at.desc(),
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "entry_needs_review_idx",
            "account_id",
            "created_at",
            postgresql_where=status == "needs_review",
        ),
        Index("entry_sync_idx", "account_id", "updated_at", "id"),
    )


class Task(Base):
    __tablename__ = "task"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_precision: Mapped[str | None] = mapped_column(String(8))
    # The user's own wording, kept so a wrong resolution can be audited.
    due_raw_expression: Mapped[str | None] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(
        String(8), default=Priority.NORMAL, server_default="normal", nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    assignee_label: Mapped[str | None] = mapped_column(String(120))
    recurrence_rule: Mapped[str | None] = mapped_column(String(255))
    external_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    entry: Mapped[Entry] = relationship(back_populates="task")

    __table_args__ = (
        _enum_check("priority", Priority),
        CheckConstraint(
            "due_precision IS NULL OR due_precision IN ('day','hour','minute')",
            name="due_precision_valid",
        ),
        Index(
            "task_due_idx",
            "due_at",
            postgresql_where=completed_at.is_(None) & due_at.isnot(None),
        ),
    )


class EntryTag(Base):
    __tablename__ = "entry_tag"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    origin: Mapped[str] = mapped_column(
        String(8), default="ai", server_default="ai", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (CheckConstraint("origin IN ('ai','user')", name="origin_valid"),)


class EntryLink(Base):
    __tablename__ = "entry_link"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    source_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), nullable=False
    )
    target_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(24), nullable=False)
    strength: Mapped[float | None] = mapped_column(Numeric(4, 3))
    origin: Mapped[str] = mapped_column(
        String(8), default="ai", server_default="ai", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("source_entry_id <> target_entry_id", name="no_self_link"),
        CheckConstraint(
            "link_type IN ('derived_from','similar_to','blocks','follows_up',"
            "'contradicts','mentions','supersedes')",
            name="link_type_valid",
        ),
        UniqueConstraint(
            "source_entry_id", "target_entry_id", "link_type", name="entry_link_unique"
        ),
    )


# --------------------------------------------------------------------------- #
# Intelligence
# --------------------------------------------------------------------------- #
class AiRun(Base):
    __tablename__ = "ai_run"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL")
    )
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capture.id", ondelete="SET NULL")
    )
    prompt_name: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[int | None] = mapped_column(Integer)

    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_micro_eur: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    # No content, ever: not the rendered prompt, not the response (AI.md §10.2).
    error_code: Mapped[str | None] = mapped_column(String(48))
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        _enum_check("operation", AiOperation),
        _enum_check("status", AiRunStatus),
    )


class CorrectionEvent(Base):
    __tablename__ = "correction_event"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entry.id", ondelete="CASCADE"), nullable=False
    )
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_run.id", ondelete="SET NULL")
    )
    field: Mapped[str] = mapped_column(String(48), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------- #
# Billing (quota enforcement only in Phase 1)
# --------------------------------------------------------------------------- #
class Plan(Base):
    __tablename__ = "plan"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_cents_month: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    max_quick_captures_month: Mapped[int | None] = mapped_column(Integer)
    max_meeting_minutes_month: Mapped[int | None] = mapped_column(Integer)
    max_capture_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    history_retention_days: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscription"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    plan_code: Mapped[str] = mapped_column(
        ForeignKey("plan.code", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default="active", server_default="active", nullable=False
    )
    seats: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1", nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UsageCounter(Base):
    __tablename__ = "usage_counter"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    period_start: Mapped[datetime] = mapped_column(Date, primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
# Platform
# --------------------------------------------------------------------------- #
class Outbox(Base):
    """Transactional outbox (ADR-010): the event is written in the same
    transaction as the business change, so it cannot be lost."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(48), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending','dispatched','failed')", name="status_valid"),
        Index("outbox_pending_idx", "available_at", postgresql_where=status == "pending"),
    )


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    queue: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1", nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(48))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','dead')", name="status_valid"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(48))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default="{}", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user','system','admin','integration')", name="actor_type_valid"
        ),
    )


# Tables carrying tenant data — the RLS migration and the isolation test both
# iterate over this list, so adding a table without a policy is caught by tests.
TENANT_TABLES: tuple[str, ...] = (
    "app_user",
    "device",
    "capture",
    "transcript",
    "transcript_segment",
    "project",
    "tag",
    "entry",
    "task",
    "entry_tag",
    "entry_link",
    "correction_event",
    "subscription",
    "usage_counter",
)
