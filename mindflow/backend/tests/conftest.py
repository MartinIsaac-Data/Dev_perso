"""Shared test fixtures.

Integration tests run against a **real PostgreSQL** (Sprint01 DoD): RLS, partial
indexes, CHECK constraints and `SET LOCAL` semantics have no equivalent in a
substitute engine, and those are exactly what the tests need to prove.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

TEST_DATABASE_URL = os.environ.get(
    "MINDFLOW_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/mindflow_test",
)
# The application connects as a non-superuser role so RLS actually applies
# (migration 0003). Superusers bypass RLS whatever the policies say.
APP_DATABASE_URL = TEST_DATABASE_URL.replace("postgres@", "mindflow_app_test@")


def _pg_available() -> bool:
    try:
        import asyncio

        import asyncpg

        async def probe() -> None:
            dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
            conn = await asyncpg.connect(dsn)
            await conn.close()

        asyncio.run(probe())
        return True
    except Exception:
        return False


PG_AVAILABLE = _pg_available()
requires_db = pytest.mark.skipif(not PG_AVAILABLE, reason="no PostgreSQL available")


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        env="test",
        database_url=APP_DATABASE_URL,
        storage_backend="local",
        storage_local_root="/tmp/mindflow-test-objects",
        stt_backend="fake",
        llm_backend="fake",
        queue_backend="inline",
        log_format="console",
        log_level="warning",
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Apply migrations once per session, then hand the app role a login."""
    if not PG_AVAILABLE:
        yield
        return

    import asyncio

    import asyncpg

    async def reset_schema() -> None:
        """Recreate the schema from scratch rather than downgrading.

        A downgrade depends on the migration files still describing the revision
        recorded in `alembic_version`; during development they may not. Dropping
        the schema is unambiguous and leaves no silent-failure path.
        """
        dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(dsn)
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        await conn.close()

    asyncio.run(reset_schema())

    env = {**os.environ, "MINDFLOW_DATABASE_URL": TEST_DATABASE_URL, "MINDFLOW_ENV": "test"}
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"], env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"migrations failed:\n{result.stdout}\n{result.stderr}")

    async def grant_login() -> None:
        dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(dsn)
        await conn.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mindflow_app_test') THEN
                    CREATE ROLE mindflow_app_test LOGIN NOSUPERUSER NOBYPASSRLS;
                END IF;
            END $$;
            """
        )
        await conn.execute("GRANT mindflow_app TO mindflow_app_test")
        await conn.execute("GRANT CONNECT ON DATABASE mindflow_test TO mindflow_app_test")
        await conn.close()

    asyncio.run(grant_login())
    yield


@pytest_asyncio.fixture
async def engine(settings: Settings):  # type: ignore[no-untyped-def]
    if not PG_AVAILABLE:
        pytest.skip("no PostgreSQL available")
    eng = create_async_engine(settings.database_url, poolclass=None, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[no-untyped-def]
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def clean_db(engine) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Truncate tenant data between tests.

    TRUNCATE runs as the migration owner (superuser), which is the only reason it
    can see across tenants here.
    """
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE account, app_user, device, capture, transcript, "
                "transcript_segment, project, tag, entry, task, entry_tag, "
                "entry_link, correction_event, ai_run, subscription, "
                "usage_counter, outbox, job_run, audit_log RESTART IDENTITY CASCADE"
            )
        )
    await admin.dispose()
    yield


@pytest_asyncio.fixture
async def two_tenants(clean_db) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID]]:  # type: ignore[no-untyped-def]
    """Create two isolated accounts, each with a user. Uses the admin connection
    because RLS would otherwise prevent creating the second tenant."""
    admin = create_async_engine(TEST_DATABASE_URL, echo=False)
    tenants = []
    async with admin.begin() as conn:
        for name in ("alpha", "beta"):
            account_id = uuid.uuid4()
            user_id = uuid.uuid4()
            await conn.execute(
                text(
                    "INSERT INTO account (id, kind, display_name, data_region, status, "
                    "created_at, updated_at) VALUES (:id, 'personal', :name, 'eu', "
                    "'active', now(), now())"
                ),
                {"id": account_id, "name": name},
            )
            await conn.execute(
                text(
                    "INSERT INTO app_user (id, account_id, auth_subject, email, timezone, "
                    "locale, role, status, created_at, updated_at) VALUES (:uid, :aid, "
                    ":sub, :email, 'Europe/Paris', 'fr-FR', 'owner', 'active', now(), now())"
                ),
                {
                    "uid": user_id,
                    "aid": account_id,
                    "sub": f"sub-{name}-{user_id}",
                    "email": f"{name}-{user_id}@example.test",
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO subscription (id, account_id, plan_code, status, seats, "
                    "current_period_start, current_period_end, created_at, updated_at) "
                    "VALUES (:id, :aid, 'free', 'active', 1, now(), "
                    "now() + interval '30 days', now(), now())"
                ),
                {"id": uuid.uuid4(), "aid": account_id},
            )
            tenants.append({"account_id": account_id, "user_id": user_id})
    await admin.dispose()
    return tenants[0], tenants[1]


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
