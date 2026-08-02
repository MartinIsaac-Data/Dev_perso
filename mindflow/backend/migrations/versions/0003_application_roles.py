"""Application roles (Database.md §6.3)

Why this migration exists at all: `FORCE ROW LEVEL SECURITY` makes policies apply
to the table *owner*, but a **superuser always bypasses RLS**. If the application
connects as `postgres`, every policy written in 0002 is inert and the isolation
guarantee is theatre. The app must therefore connect as a role that is neither
superuser nor BYPASSRLS.

`mindflow_maintenance` is granted BYPASSRLS on purpose: GDPR purges and the outbox
dispatcher legitimately cross tenants. It is used by workers only, never by a
request handler.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "mindflow_app"
READONLY_ROLE = "mindflow_readonly"
MAINTENANCE_ROLE = "mindflow_maintenance"


def upgrade() -> None:
    # Roles are cluster-scoped, so creation is conditional: a second database in
    # the same cluster must not fail on an existing role.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READONLY_ROLE}') THEN
                CREATE ROLE {READONLY_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{MAINTENANCE_ROLE}') THEN
                CREATE ROLE {MAINTENANCE_ROLE} NOLOGIN NOSUPERUSER BYPASSRLS;
            END IF;
        END
        $$;
        """
    )

    for role in (APP_ROLE, READONLY_ROLE, MAINTENANCE_ROLE):
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {READONLY_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {MAINTENANCE_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {MAINTENANCE_ROLE}")

    # Tables created by later migrations inherit these grants automatically.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {READONLY_ROLE}"
    )


def downgrade() -> None:
    for role in (APP_ROLE, READONLY_ROLE, MAINTENANCE_ROLE):
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role}")
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
    # The roles themselves are left in place: dropping a cluster-scoped role that
    # another database may still use would be destructive beyond this migration.
