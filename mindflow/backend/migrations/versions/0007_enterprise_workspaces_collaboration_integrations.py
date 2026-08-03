"""Enterprise: workspaces, membership, collaboration, integrations (Phase 4)

The important part of this migration is what it does **not** do.

It does not touch `current_account_id()`, nor any of the thirty-two tenant
isolation policies written since phase 1. The account remains the tenant, and an
organisation is simply an `account` with several `app_user` rows — a shape the
schema already permitted. Rewriting the tenant boundary to introduce an
`organisation` level would have meant re-deriving every policy and re-earning an
isolation guarantee that currently has a table-by-table test proving it.

What it adds is a **second, restrictive layer** (ADR-054). PostgreSQL AND-s
restrictive policies with permissive ones, so:

    visible  ⟺  account_id = current_account_id()          (unchanged, phase 1)
                AND workspace visibility                    (new, this migration)

A second *permissive* policy would have been the natural-looking mistake: those
are OR-ed, so it would have widened access rather than narrowing it.

**The restrictive policy passes when no user context is set.** That is a
deliberate, and the only, compatibility concession: every background job and
every phase 1–3 code path sets `app.account_id` and nothing else, and failing
closed there would silently disable the outbox dispatcher, the indexer and the
digest worker. The request path always sets both — `tests/integration/`
`test_workspaces.py::test_the_api_always_sets_the_user_context` is what keeps
that true.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TENANT_TABLES: tuple[str, ...] = (
    "workspace",
    "workspace_member",
    "invitation",
    "comment",
    "mention",
    "share_link",
    "integration_connection",
    "external_link",
    "meeting_session",
)

TS = sa.DateTime(timezone=True)


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # -- The session's user, alongside its account -----------------------------
    # Same shape as `current_account_id()`: the `true` argument makes a missing
    # setting return NULL rather than raising, so a session that never sets it
    # simply behaves as it did before this migration existed.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_user_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
        $$;
        """
    )

    # -- Widened vocabularies --------------------------------------------------
    # `viewer` for people who read and never write; `org` for an account that is
    # a company rather than a person.
    op.drop_constraint(op.f("app_user_role_valid"), "app_user", type_="check")
    op.create_check_constraint(
        op.f("app_user_role_valid"), "app_user", "role IN ('owner','admin','member','viewer')"
    )
    op.drop_constraint(op.f("account_kind_valid"), "account", type_="check")
    op.create_check_constraint(
        op.f("account_kind_valid"), "account", "kind IN ('personal','team','org')"
    )
    # `mention` and `comment` are separate kinds rather than folded into
    # `system`, because a mention is the one notification a person may
    # reasonably keep on while muting everything else: somebody asked them a
    # question by name.
    op.drop_constraint(op.f("notification_kind_valid"), "notification", type_="check")
    op.create_check_constraint(
        op.f("notification_kind_valid"),
        "notification",
        "kind IN ('reminder','due_soon','overdue','capture_ready','capture_failed',"
        "'review_pending','digest','mention','comment','system')",
    )

    # -- Workspaces ------------------------------------------------------------
    op.create_table(
        "workspace",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("color", sa.String(length=9), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", TS, nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("workspace_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("workspace_created_by_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("workspace_pkey")),
        sa.UniqueConstraint("account_id", "name", name="workspace_account_id_name_unique"),
    )
    op.create_index("workspace_account_id_idx", "workspace", ["account_id"])

    op.create_table(
        "workspace_member",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="editor", nullable=False),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("workspace_member_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("workspace_member_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("workspace_member_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("workspace_member_pkey")),
        sa.CheckConstraint(
            "role IN ('editor','commenter','reader')", name=op.f("workspace_member_role_valid")
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="workspace_member_workspace_id_user_id_unique"
        ),
    )
    # (user, workspace) rather than (workspace, user): the hot query is "which
    # workspaces may this person see", asked by the restrictive policy on every
    # single content read.
    op.create_index(
        "workspace_member_user_id_workspace_id_idx", "workspace_member", ["user_id", "workspace_id"]
    )

    op.create_table(
        "invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="member", nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("accepted_at", TS, nullable=True),
        sa.Column("revoked_at", TS, nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("invitation_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("invitation_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("invitation_pkey")),
        sa.CheckConstraint(
            "role IN ('owner','admin','member','viewer')", name=op.f("invitation_role_valid")
        ),
    )
    op.create_index(
        "invitation_account_id_email_unique",
        "invitation",
        ["account_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index("invitation_token_hash_idx", "invitation", ["token_hash"])

    # -- Content scoping -------------------------------------------------------
    # Nullable, and left NULL for every existing row: an entry with no workspace
    # is personal, which is exactly the phase 1 behaviour. No backfill, no
    # synthetic "default workspace", no rewrite of working data.
    op.add_column("entry", sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("entry_workspace_id_fkey"),
        "entry",
        "workspace",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "entry_workspace_id_occurred_at_idx",
        "entry",
        ["workspace_id", "occurred_at"],
        postgresql_where=sa.text("workspace_id IS NOT NULL AND deleted_at IS NULL"),
    )

    # -- Collaboration ---------------------------------------------------------
    op.create_table(
        "comment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("deleted_at", TS, nullable=True),
        sa.Column("resolved_at", TS, nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edited_at", TS, nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("comment_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("comment_entry_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["app_user.id"],
            name=op.f("comment_author_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["comment.id"], name=op.f("comment_parent_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("comment_pkey")),
        sa.CheckConstraint(
            "status IN ('open','resolved','deleted')", name=op.f("comment_status_valid")
        ),
    )
    op.create_index("comment_entry_id_created_at_idx", "comment", ["entry_id", "created_at"])
    op.create_index("comment_parent_id_idx", "comment", ["parent_id"])

    op.create_table(
        "mention",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("notified_at", TS, nullable=True),
        sa.Column("read_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("mention_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["comment.id"],
            name=op.f("mention_comment_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("mention_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("mention_pkey")),
        sa.UniqueConstraint("comment_id", "user_id", name="mention_comment_id_user_id_unique"),
    )
    op.create_index("mention_user_id_read_at_idx", "mention", ["user_id", "read_at"])

    op.create_table(
        "share_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_suffix", sa.String(length=8), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", TS, nullable=True),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_viewed_at", TS, nullable=True),
        sa.Column("allow_comments", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("share_link_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"], ["entry.id"], name=op.f("share_link_entry_id_fkey"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("share_link_workspace_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("share_link_pkey")),
        sa.UniqueConstraint("token_hash", name="share_link_token_hash_unique"),
        sa.CheckConstraint("scope IN ('entry','workspace')", name=op.f("share_link_scope_valid")),
        sa.CheckConstraint(
            "(entry_id IS NOT NULL) <> (workspace_id IS NOT NULL)",
            name=op.f("share_link_one_target_only"),
        ),
    )
    op.create_index("share_link_account_id_idx", "share_link", ["account_id"])

    # -- Integrations ----------------------------------------------------------
    op.create_table(
        "integration_connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("external_account_label", sa.String(length=255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", TS, nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("direction", sa.String(length=16), server_default="pull", nullable=False),
        sa.Column("settings", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("last_sync_at", TS, nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("integration_connection_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("integration_connection_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("integration_connection_pkey")),
        sa.CheckConstraint(
            "provider IN ('google_calendar','outlook_calendar','microsoft_todo',"
            "'slack','teams','notion','obsidian')",
            name=op.f("integration_connection_provider_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active','expired','revoked','error')",
            name=op.f("integration_connection_status_valid"),
        ),
        sa.CheckConstraint(
            "direction IN ('pull','push','two_way')",
            name=op.f("integration_connection_direction_valid"),
        ),
        sa.UniqueConstraint(
            "account_id", "user_id", "provider", name="integration_connection_unique"
        ),
    )
    op.create_index(
        "integration_connection_account_id_idx", "integration_connection", ["account_id"]
    )

    op.create_table(
        "external_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("external_etag", sa.String(length=512), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("last_pushed_at", TS, nullable=True),
        sa.Column("last_pulled_at", TS, nullable=True),
        sa.Column("conflict_at", TS, nullable=True),
        sa.Column("deleted_remotely_at", TS, nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("external_link_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connection.id"],
            name=op.f("external_link_connection_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entry.id"],
            name=op.f("external_link_entry_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("external_link_pkey")),
        sa.UniqueConstraint(
            "connection_id", "external_id", name="external_link_connection_external_unique"
        ),
    )
    op.create_index("external_link_entry_id_idx", "external_link", ["entry_id"])
    op.create_index(
        "external_link_account_id_provider_idx", "external_link", ["account_id", "provider"]
    )

    op.create_table(
        "meeting_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="live", nullable=False),
        sa.Column("started_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", TS, nullable=True),
        sa.Column("live_transcript", sa.Text(), nullable=True),
        sa.Column("live_suggestions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_ts_columns(),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("meeting_session_account_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("meeting_session_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspace.id"],
            name=op.f("meeting_session_workspace_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["capture.id"],
            name=op.f("meeting_session_capture_id_fkey"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("meeting_session_pkey")),
        sa.CheckConstraint(
            "status IN ('live','ended','abandoned')", name=op.f("meeting_session_status_valid")
        ),
    )
    op.create_index(
        "meeting_session_account_id_status_idx", "meeting_session", ["account_id", "status"]
    )

    # -- Tenant isolation for the new tables (unchanged mechanism, ADR-005) ----
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

    # -- Workspace visibility: the restrictive second layer (ADR-054) ---------
    #
    # AS RESTRICTIVE is the whole design. PostgreSQL OR-s permissive policies
    # and AND-s restrictive ones, so this narrows what the phase 1 policy allows
    # instead of widening it.
    #
    # The `current_user_id() IS NULL` escape is the compatibility concession
    # described in the module docstring: without it every background job — which
    # legitimately has an account context and no user — would see nothing.
    op.execute(
        """
        CREATE POLICY entry_workspace_visibility ON entry AS RESTRICTIVE
            USING (
                current_user_id() IS NULL
                OR user_id = current_user_id()
                OR (
                    workspace_id IS NOT NULL
                    AND EXISTS (
                        SELECT 1 FROM workspace_member wm
                        WHERE wm.workspace_id = entry.workspace_id
                          AND wm.user_id = current_user_id()
                    )
                )
            )
        """
    )

    # A comment inherits the visibility of the entry it hangs from. Deriving it
    # rather than duplicating `workspace_id` onto `comment` means the two can
    # never disagree — and an entry moved between workspaces takes its whole
    # thread with it, with no second write to forget.
    op.execute(
        """
        CREATE POLICY comment_workspace_visibility ON comment AS RESTRICTIVE
            USING (
                current_user_id() IS NULL
                OR author_id = current_user_id()
                OR EXISTS (
                    SELECT 1 FROM entry e
                    WHERE e.id = comment.entry_id
                      AND (
                        e.user_id = current_user_id()
                        OR (
                            e.workspace_id IS NOT NULL
                            AND EXISTS (
                                SELECT 1 FROM workspace_member wm
                                WHERE wm.workspace_id = e.workspace_id
                                  AND wm.user_id = current_user_id()
                            )
                        )
                      )
                )
            )
        """
    )

    # -- Privileges ------------------------------------------------------------
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO mindflow_maintenance"
    )
    for table in NEW_TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO mindflow_app")
        op.execute(f"GRANT SELECT ON {table} TO mindflow_readonly")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS comment_workspace_visibility ON comment")
    op.execute("DROP POLICY IF EXISTS entry_workspace_visibility ON entry")

    for table in reversed(NEW_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("entry_workspace_id_occurred_at_idx", table_name="entry")
    op.drop_constraint(op.f("entry_workspace_id_fkey"), "entry", type_="foreignkey")
    op.drop_column("entry", "workspace_id")

    op.drop_table("meeting_session")
    op.drop_table("external_link")
    op.drop_table("integration_connection")
    op.drop_table("share_link")
    op.drop_table("mention")
    op.drop_table("comment")
    op.drop_table("invitation")
    op.drop_table("workspace_member")
    op.drop_table("workspace")

    op.drop_constraint(op.f("account_kind_valid"), "account", type_="check")
    op.create_check_constraint(op.f("account_kind_valid"), "account", "kind IN ('personal','team')")
    op.drop_constraint(op.f("app_user_role_valid"), "app_user", type_="check")
    op.create_check_constraint(
        op.f("app_user_role_valid"), "app_user", "role IN ('owner','admin','member')"
    )

    op.execute("DROP FUNCTION IF EXISTS current_user_id()")
