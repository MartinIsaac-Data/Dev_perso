"""Identity self-lookup policy (ADR-029 + ADR-005)

The problem: resolving a Supabase token into a MindFlow principal means reading
`app_user` *before* the tenant is known, so `current_account_id()` is still NULL
and the tenant policy hides every row.

The tempting fix is to use a privileged, RLS-bypassing connection for that one
query. That would put a bypass on the hot path of **every authenticated request**
— the exact opposite of what ADR-005 buys.

Instead: a second, deliberately narrow policy. The request posts the token's
subject as `app.auth_subject`, and the policy exposes exactly the row whose
`auth_subject` matches. Policies are permissive, so this ORs with tenant
isolation and widens nothing else — a caller can see the one row that is already
provably theirs, because they hold a signed token for it.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION current_auth_subject() RETURNS text
        LANGUAGE sql STABLE AS $$
            SELECT NULLIF(current_setting('app.auth_subject', true), '')
        $$;
        """
    )
    # SELECT only. Provisioning does not rely on this policy: it generates the
    # account id first and posts it as the tenant context, so the INSERTs satisfy
    # the ordinary tenant policy's WITH CHECK.
    op.execute(
        """
        CREATE POLICY app_user_self_lookup ON app_user
            FOR SELECT
            USING (
                current_auth_subject() IS NOT NULL
                AND auth_subject = current_auth_subject()
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS app_user_self_lookup ON app_user")
    op.execute("DROP FUNCTION IF EXISTS current_auth_subject()")
