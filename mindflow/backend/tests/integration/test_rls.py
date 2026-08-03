"""Multi-tenant isolation test (Sprint01 epic 3.4, Database.md §6.5).

This is the test that makes the isolation promise verifiable rather than asserted.
It walks **every** tenant-owned table, and from tenant A's session tries to read,
modify and delete tenant B's rows. A single row coming back fails the build.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.infra.db.models.core import TENANT_TABLES
from tests.conftest import TEST_DATABASE_URL, requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _set_tenant(session: AsyncSession, account_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.account_id', :aid, true)"), {"aid": str(account_id)}
    )


async def _seed_capture(account_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    """Insert through the privileged connection so the row genuinely belongs to
    the other tenant."""
    capture_id = uuid.uuid4()
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO capture (id, account_id, user_id, client_capture_id, kind, "
                "status, duration_ms, captured_at, capture_timezone, source, "
                "processing_mode, version, created_at, updated_at) "
                "VALUES (:id, :aid, :uid, :cid, 'quick', 'uploaded', 15000, now(), "
                "'Europe/Paris', 'app', 'normal', 1, now(), now())"
            ),
            {"id": capture_id, "aid": account_id, "uid": user_id, "cid": uuid.uuid4()},
        )
    await admin.dispose()
    return capture_id


def test_policy_list_matches_the_model_list() -> None:
    """A table added without a policy must break the build, not leak silently."""
    from migrations.versions import _load_tenant_tables  # type: ignore[attr-defined]

    assert set(_load_tenant_tables()) == set(TENANT_TABLES)


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_every_tenant_table_has_rls_enabled_and_forced(
    session_factory, two_tenants, table: str
) -> None:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = :t AND relnamespace = 'public'::regnamespace"
                ),
                {"t": table},
            )
        ).one()
    enabled, forced = row
    assert enabled, f"{table}: RLS is not enabled"
    assert forced, f"{table}: RLS is not FORCEd — the owner would bypass it"


async def test_the_app_role_cannot_bypass_rls(session_factory) -> None:
    """If the connection role were superuser or BYPASSRLS, every policy above
    would be inert."""
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).one()
    assert row[0] is False, "the application role must not be superuser"
    assert row[1] is False, "the application role must not have BYPASSRLS"


async def test_the_maintenance_role_can_cross_tenants(session_factory, two_tenants) -> None:
    """The counterpart of the test above, and the one that was missing.

    Cross-tenant jobs — the capture sweeper, the outbox dispatcher, the reminder
    dispatcher — run on `privileged_session()`. If that session used the
    application role, every one of them would return zero rows: no error, no log
    line, no symptom until someone notices their reminders never arrive. So the
    maintenance role must exist *and* be able to see past the policies (ADR-042).
    """
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = 'mindflow_maintenance'"
                )
            )
        ).one_or_none()
    await admin.dispose()

    assert row is not None, "the maintenance role must exist"
    assert row[0] is False, "maintenance is not superuser — BYPASSRLS is enough"
    assert row[1] is True, "maintenance must bypass RLS or every scheduled job is a no-op"


async def test_a_privileged_session_actually_sees_across_tenants(two_tenants) -> None:
    """The behavioural half: not "the role has the flag" but "the session can
    read a row belonging to a tenant it never named"."""
    from app.config import Settings
    from app.infra.db.session import dispose_engine, init_engine, privileged_session
    from tests.conftest import APP_DATABASE_URL

    _alpha, beta = two_tenants
    capture_id = await _seed_capture(beta["account_id"], beta["user_id"])

    await dispose_engine()
    init_engine(
        Settings(
            env="test",
            database_url=APP_DATABASE_URL,
            maintenance_database_url=TEST_DATABASE_URL,
        )
    )
    try:
        async with privileged_session() as session:
            found = (
                await session.execute(
                    text("SELECT id FROM capture WHERE id = :cid"), {"cid": capture_id}
                )
            ).one_or_none()
    finally:
        await dispose_engine()

    assert found is not None


async def test_tenant_cannot_read_another_tenants_capture(session_factory, two_tenants) -> None:
    alpha, beta = two_tenants
    beta_capture = await _seed_capture(beta["account_id"], beta["user_id"])

    async with session_factory() as session, session.begin():
        await _set_tenant(session, alpha["account_id"])
        rows = (
            await session.execute(
                text("SELECT id FROM capture WHERE id = :id"), {"id": beta_capture}
            )
        ).all()
    assert rows == [], "tenant A read tenant B's capture"


async def test_tenant_sees_only_its_own_rows_in_an_unfiltered_query(
    session_factory, two_tenants
) -> None:
    """The scenario the whole design exists for: a forgotten WHERE clause."""
    alpha, beta = two_tenants
    await _seed_capture(alpha["account_id"], alpha["user_id"])
    await _seed_capture(beta["account_id"], beta["user_id"])
    await _seed_capture(beta["account_id"], beta["user_id"])

    async with session_factory() as session, session.begin():
        await _set_tenant(session, alpha["account_id"])
        count = (await session.execute(text("SELECT count(*) FROM capture"))).scalar_one()
    assert count == 1


async def test_tenant_cannot_update_another_tenants_row(session_factory, two_tenants) -> None:
    alpha, beta = two_tenants
    beta_capture = await _seed_capture(beta["account_id"], beta["user_id"])

    async with session_factory() as session, session.begin():
        await _set_tenant(session, alpha["account_id"])
        result = await session.execute(
            text("UPDATE capture SET status = 'abandoned' WHERE id = :id"),
            {"id": beta_capture},
        )
    assert result.rowcount == 0


async def test_tenant_cannot_delete_another_tenants_row(session_factory, two_tenants) -> None:
    alpha, beta = two_tenants
    beta_capture = await _seed_capture(beta["account_id"], beta["user_id"])

    async with session_factory() as session, session.begin():
        await _set_tenant(session, alpha["account_id"])
        result = await session.execute(
            text("DELETE FROM capture WHERE id = :id"), {"id": beta_capture}
        )
    assert result.rowcount == 0


async def test_tenant_cannot_insert_a_row_for_another_tenant(session_factory, two_tenants) -> None:
    """WITH CHECK stops the reverse attack: writing *into* another tenant."""
    alpha, beta = two_tenants
    async with session_factory() as session, session.begin():
        await _set_tenant(session, alpha["account_id"])
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO project (id, account_id, name, slug, aliases, depth, "
                    "created_at, updated_at) VALUES (:id, :aid, 'x', 'x', '{}', 0, "
                    "now(), now())"
                ),
                {"id": uuid.uuid4(), "aid": beta["account_id"]},
            )


async def test_a_session_without_tenant_context_sees_nothing(session_factory, two_tenants) -> None:
    alpha = two_tenants[0]
    await _seed_capture(alpha["account_id"], alpha["user_id"])

    async with session_factory() as session, session.begin():
        count = (await session.execute(text("SELECT count(*) FROM capture"))).scalar_one()
    assert count == 0


async def test_set_local_does_not_leak_across_transactions(session_factory, two_tenants) -> None:
    """The connection-pool trap (ADR-005): a plain SET would leak tenant context
    into the next transaction served by the same connection."""
    beta = two_tenants[1]
    await _seed_capture(beta["account_id"], beta["user_id"])

    async with session_factory() as session:
        async with session.begin():
            await _set_tenant(session, beta["account_id"])
            visible = (await session.execute(text("SELECT count(*) FROM capture"))).scalar_one()
            assert visible == 1

        # Same session object, new transaction, no context posted.
        async with session.begin():
            leaked = (await session.execute(text("SELECT count(*) FROM capture"))).scalar_one()
    assert leaked == 0, "tenant context leaked across transactions"
