"""Initial schema (Database.md §5)

Revision ID: 0001
Revises:
Create Date: 2026-08-02 15:39:26.731897
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions first: pgcrypto for gen_random_uuid, pg_trgm + unaccent for the
    # French text search configuration used from v0.5 onward (Database.md §5.1).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.create_table(
        "account",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="personal", nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("data_region", sa.String(length=8), server_default="eu", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("data_region IN ('eu','us')", name=op.f("account_data_region_valid")),
        sa.CheckConstraint("kind IN ('personal','team')", name=op.f("account_kind_valid")),
        sa.CheckConstraint(
            "status IN ('active','suspended','pending_deletion','deleted')",
            name=op.f("account_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("account_pkey")),
    )
    op.create_table(
        "job_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("aggregate_id", sa.UUID(), nullable=True),
        sa.Column("queue", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','dead')",
            name=op.f("job_run_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("job_run_pkey")),
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=48), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','dispatched','failed')", name=op.f("outbox_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("outbox_pkey")),
    )
    op.create_index(
        "outbox_pending_idx",
        "outbox",
        ["available_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "plan",
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("display_name", sa.String(length=60), nullable=False),
        sa.Column("price_cents_month", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("max_quick_captures_month", sa.Integer(), nullable=True),
        sa.Column("max_meeting_minutes_month", sa.Integer(), nullable=True),
        sa.Column("max_capture_duration_ms", sa.Integer(), nullable=False),
        sa.Column("history_retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "features", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("plan_pkey")),
    )
    op.create_table(
        "app_user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("auth_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Paris", nullable=False),
        sa.Column("locale", sa.String(length=8), server_default="fr-FR", nullable=False),
        sa.Column("role", sa.String(length=16), server_default="owner", nullable=False),
        sa.Column("daily_review_at", sa.String(length=5), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('owner','admin','member')", name=op.f("app_user_role_valid")),
        sa.CheckConstraint(
            "status IN ('active','suspended','pending_deletion','deleted')",
            name=op.f("app_user_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("app_user_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("app_user_pkey")),
        sa.UniqueConstraint("auth_subject", name="app_user_auth_subject_unique"),
        sa.UniqueConstraint("email", name="app_user_email_unique"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_type", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=48), nullable=True),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user','system','admin','integration')",
            name=op.f("audit_log_actor_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("audit_log_account_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("audit_log_pkey")),
    )
    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=140), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("depth", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("depth BETWEEN 0 AND 2", name=op.f("project_depth_range")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("project_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["project.id"], name=op.f("project_parent_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("project_pkey")),
        sa.UniqueConstraint("account_id", "slug", name="project_slug_unique"),
    )
    op.create_table(
        "subscription",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("plan_code", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("seats", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("subscription_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_code"],
            ["plan.code"],
            name=op.f("subscription_plan_code_fkey"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("subscription_pkey")),
        sa.UniqueConstraint("account_id", name=op.f("subscription_account_id_unique")),
    )
    op.create_table(
        "tag",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("normalized", sa.String(length=60), nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("tag_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("tag_pkey")),
        sa.UniqueConstraint("account_id", "normalized", name="tag_unique"),
    )
    op.create_table(
        "usage_counter",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("value", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("usage_counter_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "account_id", "metric", "period_start", name=op.f("usage_counter_pkey")
        ),
    )
    op.create_table(
        "device",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("os_version", sa.String(length=32), nullable=True),
        sa.Column("push_token", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_cursor", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "platform IN ('ios','android','web','watchos','wearos')",
            name=op.f("device_platform_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("device_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("device_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("device_pkey")),
    )
    op.create_table(
        "capture",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=True),
        sa.Column("client_capture_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), server_default="quick", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending_upload", nullable=False),
        sa.Column("audio_object_key", sa.Text(), nullable=True),
        sa.Column("audio_bytes", sa.BigInteger(), nullable=True),
        sa.Column("audio_format", sa.String(length=16), nullable=True),
        sa.Column("audio_sample_rate", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_timezone", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=24), server_default="app", nullable=False),
        sa.Column("language_hint", sa.String(length=8), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=48), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("processing_mode", sa.String(length=16), server_default="normal", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "audio_format IS NULL OR audio_format IN ('m4a','opus','wav','mp3','webm')",
            name=op.f("capture_audio_format_valid"),
        ),
        sa.CheckConstraint(
            "kind IN ('quick', 'meeting', 'dictation', 'imported')", name=op.f("capture_kind_valid")
        ),
        sa.CheckConstraint(
            "processing_mode IN ('normal','degraded')", name=op.f("capture_processing_mode_valid")
        ),
        sa.CheckConstraint(
            "source IN ('app', 'widget', 'watch', 'carplay', 'shortcut', 'web', 'api')",
            name=op.f("capture_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'uploaded', 'transcribing', 'transcribed', 'extracting', 'completed', 'partially_processed', 'transcription_failed', 'abandoned')",
            name=op.f("capture_status_valid"),
        ),
        sa.CheckConstraint(
            "audio_bytes IS NULL OR audio_bytes >= 0", name=op.f("capture_bytes_positive")
        ),
        sa.CheckConstraint("duration_ms > 0", name=op.f("capture_duration_positive")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("capture_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["device.id"], name=op.f("capture_device_id_fkey"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("capture_user_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("capture_pkey")),
        sa.UniqueConstraint("user_id", "client_capture_id", name="capture_client_id_unique"),
    )
    op.create_index(
        "capture_account_time_idx",
        "capture",
        ["account_id", sa.literal_column("captured_at DESC")],
        unique=False,
    )
    op.create_index(
        "capture_processing_idx",
        "capture",
        ["status", "created_at"],
        unique=False,
        postgresql_where=sa.text("(status NOT IN ('completed', 'abandoned'))"),
    )
    op.create_table(
        "ai_run",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("capture_id", sa.UUID(), nullable=True),
        sa.Column("prompt_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_micro_eur", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "operation IN ('classify', 'extract', 'summarize', 'answer', 'embed', 'transcribe', 'link')",
            name=op.f("ai_run_operation_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'refused', 'schema_violation', 'timeout')",
            name=op.f("ai_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("ai_run_account_id_fkey"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"], ["capture.id"], name=op.f("ai_run_capture_id_fkey"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("ai_run_pkey")),
    )
    op.create_table(
        "entry",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("capture_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin", sa.String(length=16), server_default="ai", nullable=False),
        sa.Column("ai_run_id", sa.UUID(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source_span_start", sa.Integer(), nullable=True),
        sa.Column("source_span_end", sa.Integer(), nullable=True),
        sa.Column("edited_by_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "entry_type IN ('task', 'idea', 'note', 'decision', 'question', 'meeting', 'reminder')",
            name=op.f("entry_entry_type_valid"),
        ),
        sa.CheckConstraint(
            "origin IN ('ai', 'user', 'integration', 'transform')", name=op.f("entry_origin_valid")
        ),
        sa.CheckConstraint(
            "status IN ('needs_review', 'active', 'done', 'archived', 'snoozed')",
            name=op.f("entry_status_valid"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("entry_confidence_range"),
        ),
        sa.CheckConstraint(
            "source_span_start IS NULL OR source_span_end > source_span_start",
            name=op.f("entry_span_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("entry_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"], ["capture.id"], name=op.f("entry_capture_id_fkey"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("entry_project_id_fkey"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("entry_user_id_fkey"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("entry_pkey")),
    )
    op.create_index(
        "entry_account_occurred_idx",
        "entry",
        ["account_id", sa.literal_column("occurred_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "entry_account_type_idx",
        "entry",
        ["account_id", "entry_type", sa.literal_column("occurred_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "entry_needs_review_idx",
        "entry",
        ["account_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'needs_review'"),
    )
    op.create_index("entry_sync_idx", "entry", ["account_id", "updated_at", "id"], unique=False)
    op.create_table(
        "transcript",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("capture_id", sa.UUID(), nullable=False),
        sa.Column("engine", sa.String(length=48), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("words", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revision", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("transcript_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("transcript_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["capture.id"],
            name=op.f("transcript_capture_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("transcript_pkey")),
    )
    op.create_index(
        "transcript_one_current_idx",
        "transcript",
        ["capture_id"],
        unique=True,
        postgresql_where=sa.text("is_current IS true"),
    )
    op.create_table(
        "correction_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("ai_run_id", sa.UUID(), nullable=True),
        sa.Column("field", sa.String(length=48), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("corrected_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("correction_event_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_run_id"],
            ["ai_run.id"],
            name=op.f("correction_event_ai_run_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entry.id"],
            name=op.f("correction_event_entry_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("correction_event_pkey")),
    )
    op.create_table(
        "entry_link",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("source_entry_id", sa.UUID(), nullable=False),
        sa.Column("target_entry_id", sa.UUID(), nullable=False),
        sa.Column("link_type", sa.String(length=24), nullable=False),
        sa.Column("strength", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("origin", sa.String(length=8), server_default="ai", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "link_type IN ('derived_from','similar_to','blocks','follows_up','contradicts','mentions','supersedes')",
            name=op.f("entry_link_link_type_valid"),
        ),
        sa.CheckConstraint(
            "source_entry_id <> target_entry_id", name=op.f("entry_link_no_self_link")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("entry_link_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_id"],
            ["entry.id"],
            name=op.f("entry_link_source_entry_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entry_id"],
            ["entry.id"],
            name=op.f("entry_link_target_entry_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("entry_link_pkey")),
        sa.UniqueConstraint(
            "source_entry_id", "target_entry_id", "link_type", name="entry_link_unique"
        ),
    )
    op.create_table(
        "entry_tag",
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("origin", sa.String(length=8), server_default="ai", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("origin IN ('ai','user')", name=op.f("entry_tag_origin_valid")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("entry_tag_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("entry_tag_entry_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tag.id"], name=op.f("entry_tag_tag_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id", "tag_id", name=op.f("entry_tag_pkey")),
    )
    op.create_table(
        "task",
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_precision", sa.String(length=8), nullable=True),
        sa.Column("due_raw_expression", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=8), server_default="normal", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("assignee_label", sa.String(length=120), nullable=True),
        sa.Column("recurrence_rule", sa.String(length=255), nullable=True),
        sa.Column("external_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "due_precision IS NULL OR due_precision IN ('day','hour','minute')",
            name=op.f("task_due_precision_valid"),
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')", name=op.f("task_priority_valid")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("task_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("task_entry_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id", name=op.f("task_pkey")),
    )
    op.create_index(
        "task_due_idx",
        "task",
        ["due_at"],
        unique=False,
        postgresql_where=sa.text("completed_at IS NULL AND due_at IS NOT NULL"),
    )
    op.create_table(
        "transcript_segment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("transcript_id", sa.UUID(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(length=32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.CheckConstraint("end_ms > start_ms", name=op.f("transcript_segment_segment_order")),
        sa.CheckConstraint("start_ms >= 0", name=op.f("transcript_segment_segment_start_positive")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("transcript_segment_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcript.id"],
            name=op.f("transcript_segment_transcript_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("transcript_segment_pkey")),
        sa.UniqueConstraint("transcript_id", "seq", name="transcript_segment_seq_unique"),
    )


def downgrade() -> None:
    op.drop_table("transcript_segment")
    op.drop_index(
        "task_due_idx",
        table_name="task",
        postgresql_where=sa.text("completed_at IS NULL AND due_at IS NOT NULL"),
    )
    op.drop_table("task")
    op.drop_table("entry_tag")
    op.drop_table("entry_link")
    op.drop_table("correction_event")
    op.drop_index(
        "transcript_one_current_idx",
        table_name="transcript",
        postgresql_where=sa.text("is_current IS true"),
    )
    op.drop_table("transcript")
    op.drop_index("entry_sync_idx", table_name="entry")
    op.drop_index(
        "entry_needs_review_idx",
        table_name="entry",
        postgresql_where=sa.text("status = 'needs_review'"),
    )
    op.drop_index(
        "entry_account_type_idx", table_name="entry", postgresql_where=sa.text("deleted_at IS NULL")
    )
    op.drop_index(
        "entry_account_occurred_idx",
        table_name="entry",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("entry")
    op.drop_table("ai_run")
    op.drop_index(
        "capture_processing_idx",
        table_name="capture",
        postgresql_where=sa.text("(status NOT IN ('completed', 'abandoned'))"),
    )
    op.drop_index("capture_account_time_idx", table_name="capture")
    op.drop_table("capture")
    op.drop_table("device")
    op.drop_table("usage_counter")
    op.drop_table("tag")
    op.drop_table("subscription")
    op.drop_table("project")
    op.drop_table("audit_log")
    op.drop_table("app_user")
    op.drop_table("plan")
    op.drop_index(
        "outbox_pending_idx", table_name="outbox", postgresql_where=sa.text("status = 'pending'")
    )
    op.drop_table("outbox")
    op.drop_table("job_run")
    op.drop_table("account")
