"""Row Level Security (ADR-005, Database.md §6)

Isolation does not rest on developer discipline. A forgotten `WHERE account_id`
in application code returns nothing instead of leaking — that is the whole point,
and `tests/integration/test_rls.py` proves it table by table.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept in sync with app.infra.db.models.core.TENANT_TABLES; the isolation test
# compares the two and fails if a table is added without a policy.
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

# `account` is filtered on its own primary key rather than an account_id column.
ACCOUNT_TABLE = "account"


def upgrade() -> None:
    # Reads the transaction-local setting posted by tenant_session(). The third
    # argument of current_setting() makes a missing setting return NULL instead
    # of raising, so an unscoped session simply sees nothing.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_account_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.account_id', true), '')::uuid
        $$;
        """
    )

    for table in TENANT_TABLES:
        # FORCE makes the policy apply to the table owner too. Without it, the
        # role that owns the schema bypasses RLS entirely and the protection is
        # theatre in every environment where the app connects as owner.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
                USING (account_id = current_account_id())
                WITH CHECK (account_id = current_account_id())
            """
        )

    op.execute(f"ALTER TABLE {ACCOUNT_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {ACCOUNT_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {ACCOUNT_TABLE}_tenant_isolation ON {ACCOUNT_TABLE}
            USING (id = current_account_id())
            WITH CHECK (id = current_account_id())
        """
    )

    # Seed the reference plans. `plan` carries no tenant data and stays outside
    # RLS (Database.md §6.4).
    op.execute(
        """
        INSERT INTO plan (code, display_name, price_cents_month, currency,
                          max_quick_captures_month, max_meeting_minutes_month,
                          max_capture_duration_ms, history_retention_days, features)
        VALUES
            ('free',     'Free',     0,    'EUR', 60,   30,   600000,  30,   '{}'),
            ('pro',      'Pro',      900,  'EUR', NULL, 600,  3600000, NULL, '{}'),
            ('business', 'Business', 1900, 'EUR', NULL, 1500, 3600000, NULL, '{}')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM plan WHERE code IN ('free','pro','business')")

    op.execute(f"DROP POLICY IF EXISTS {ACCOUNT_TABLE}_tenant_isolation ON {ACCOUNT_TABLE}")
    op.execute(f"ALTER TABLE {ACCOUNT_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {ACCOUNT_TABLE} DISABLE ROW LEVEL SECURITY")

    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS current_account_id()")
