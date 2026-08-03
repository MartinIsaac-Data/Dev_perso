"""AI layer: pgvector, chunks, entities, conversations, memory, digests (Phase 3)

Four things here are not mechanical.

* **`CREATE EXTENSION vector` needs privileges the application role does not
  have.** It runs as the migration role (a superuser or an `rds_superuser`
  equivalent), which is why it is `IF NOT EXISTS` and why the deployment notes
  say the extension may also be pre-created by the platform. On a managed
  Postgres where extension creation is denied outright, pre-creating it is the
  documented prerequisite — the migration then finds it and moves on.

* **The vector column's width comes from configuration** (ADR-045). Two
  embedding models produce vectors in different spaces, so switching provider
  means re-embedding the corpus regardless; the width is therefore a deployment
  decision, read from the same `embedding_dimensions` setting the model reads.
  A deployment that changes it must run a migration and a full re-index.

* **The HNSW index is built for cosine distance** (`vector_cosine_ops`), and the
  retrieval query must use the matching `<=>` operator. A mismatch between
  operator class and query operator does not error — it silently ignores the
  index and sequentially scans, which shows up as "search got slow" months
  later. pgvector 0.6 supports HNSW; IVFFlat is not used because it needs a
  populated table to train on and would build an index on zero rows here.

* **RLS goes on in the same migration that creates the tables.** A table that
  exists for even one deploy without a policy is a table that leaks for one
  deploy. `chunk` matters most: it holds a verbatim copy of every note.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.config import get_settings

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept in sync with app.infra.db.models.core.TENANT_TABLES; the isolation test
# compares the two and fails if a table is added without a policy.
NEW_TENANT_TABLES: tuple[str, ...] = (
    "chunk",
    "entity",
    "entity_mention",
    "conversation",
    "conversation_message",
    "memory",
    "digest",
)

EMBEDDING_DIMENSIONS = get_settings().embedding_dimensions


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=32), nullable=False),
        sa.Column("token_estimate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", _vector_type(), nullable=True),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("chunk_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("chunk_entry_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"], ["capture.id"], name=op.f("chunk_capture_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chunk_pkey")),
        sa.CheckConstraint(
            "(entry_id IS NOT NULL) <> (capture_id IS NOT NULL)", name=op.f("chunk_one_source_only")
        ),
        sa.UniqueConstraint("entry_id", "chunk_index", name="chunk_entry_id_chunk_index_unique"),
        sa.UniqueConstraint(
            "capture_id", "chunk_index", name="chunk_capture_id_chunk_index_unique"
        ),
    )
    op.create_index("chunk_account_id_idx", "chunk", ["account_id"])
    op.create_index("chunk_content_hash_idx", "chunk", ["content_hash"])
    op.create_index(
        "chunk_pending_embedding_idx",
        "chunk",
        ["account_id"],
        postgresql_where=sa.text("embedding IS NULL"),
    )
    # Cosine, to match the `<=>` operator the retrieval query uses. `m` and
    # `ef_construction` are pgvector's defaults, stated explicitly so that a
    # future change to them is a visible diff rather than a version upgrade.
    op.execute(
        "CREATE INDEX chunk_embedding_hnsw_idx ON chunk "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "entity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("resolution_key", sa.String(length=240), nullable=False),
        sa.Column("detail", sa.String(length=600), nullable=True),
        sa.Column("mention_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by_user_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("entity_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("entity_pkey")),
        sa.CheckConstraint(
            "kind IN ('person','product','company','project','decision','risk','action')",
            name=op.f("entity_kind_valid"),
        ),
        sa.UniqueConstraint(
            "account_id", "resolution_key", name="entity_account_id_resolution_key_unique"
        ),
    )
    op.create_index("entity_account_id_kind_idx", "entity", ["account_id", "kind"])
    op.create_index(
        "entity_account_id_mention_count_idx", "entity", ["account_id", "mention_count"]
    )

    op.create_table(
        "entity_mention",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source_span_start", sa.Integer(), nullable=True),
        sa.Column("source_span_end", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("entity_mention_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entity.id"],
            name=op.f("entity_mention_entity_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entry.id"],
            name=op.f("entity_mention_entry_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["capture.id"],
            name=op.f("entity_mention_capture_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("entity_mention_pkey")),
        sa.UniqueConstraint(
            "entity_id", "entry_id", name="entity_mention_entity_id_entry_id_unique"
        ),
    )
    op.create_index(
        "entity_mention_account_id_entity_id_idx", "entity_mention", ["account_id", "entity_id"]
    )
    op.create_index("entity_mention_entry_id_idx", "entity_mention", ["entry_id"])

    op.create_table(
        "conversation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("conversation_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("conversation_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("conversation_pkey")),
    )
    op.create_index(
        "conversation_account_id_last_message_at_idx",
        "conversation",
        ["account_id", "last_message_at"],
    )

    op.create_table(
        "conversation_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("intent", sa.String(length=24), nullable=True),
        sa.Column("citations", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("ai_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("conversation_message_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("conversation_message_conversation_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("conversation_message_pkey")),
        sa.CheckConstraint(
            "role IN ('user','assistant','system')", name=op.f("conversation_message_role_valid")
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="conversation_message_conversation_id_client_message_id_unique",
        ),
    )
    op.create_index(
        "conversation_message_conversation_id_created_at_idx",
        "conversation_message",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("statement", sa.String(length=300), nullable=False),
        sa.Column("statement_hash", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("source_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("memory_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("memory_user_id_fkey"), ondelete="CASCADE"
        ),
        # SET NULL: deleting a conversation loses the provenance of a memory, not
        # the memory itself.
        sa.ForeignKeyConstraint(
            ["source_conversation_id"],
            ["conversation.id"],
            name=op.f("memory_source_conversation_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("memory_pkey")),
        sa.CheckConstraint(
            "kind IN ('profile','preference','relation','routine')", name=op.f("memory_kind_valid")
        ),
        sa.UniqueConstraint(
            "account_id",
            "user_id",
            "statement_hash",
            name="memory_account_id_user_id_statement_hash_unique",
        ),
    )
    op.create_index("memory_account_id_user_id_idx", "memory", ["account_id", "user_id"])

    op.create_table(
        "digest",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("stats", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("entry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ai_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("digest_account_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("digest_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("digest_pkey")),
        sa.CheckConstraint(
            "period IN ('daily','weekly','monthly')", name=op.f("digest_period_valid")
        ),
        sa.CheckConstraint("period_end >= period_start", name=op.f("digest_period_ordered")),
        sa.UniqueConstraint(
            "account_id", "user_id", "period", "period_start", name="digest_period_unique"
        ),
    )
    op.create_index(
        "digest_account_id_period_period_start_idx",
        "digest",
        ["account_id", "period", "period_start"],
    )

    # -- Row Level Security for the new tenant tables (ADR-005) ---------------
    for table in NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (account_id = current_account_id())
                WITH CHECK (account_id = current_account_id())
            """
        )

    # -- Privileges ------------------------------------------------------------
    # `mindflow_app` inherits these from the default privileges set in migration
    # 0003. `mindflow_maintenance` does **not**: 0003 granted it the tables that
    # existed at the time but never set ALTER DEFAULT PRIVILEGES for it, so every
    # table created since — the five from phase 2 included — is invisible to the
    # cross-tenant worker connection (ADR-042).
    #
    # That gap has no symptom until a background job needs a newer table and
    # returns nothing, silently, exactly like the inert `privileged_session()`
    # found at the end of phase 2. It is closed here in both directions: a
    # catch-up grant for what already exists, and a default so it cannot recur.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mindflow_maintenance"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mindflow_maintenance"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO mindflow_maintenance"
    )
    # Explicit rather than relying on the default privileges above, because the
    # ordering of GRANT and CREATE within one migration is easy to get wrong and
    # the failure mode is a table the application cannot read.
    for table in NEW_TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO mindflow_app")
        op.execute(f"GRANT SELECT ON {table} TO mindflow_readonly")


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM mindflow_maintenance"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM mindflow_maintenance"
    )

    for table in reversed(NEW_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("digest")
    op.drop_table("memory")
    op.drop_table("conversation_message")
    op.drop_table("conversation")
    op.drop_table("entity_mention")
    op.drop_table("entity")
    op.drop_table("chunk")

    # The extension is deliberately left in place: another schema in the same
    # database may be using it, and dropping it would take their columns with it.


def _vector_type() -> sa.types.TypeEngine[object]:
    """The `vector(N)` column type, with N from configuration (ADR-045)."""
    from pgvector.sqlalchemy import Vector

    return Vector(EMBEDDING_DIMENSIONS)
