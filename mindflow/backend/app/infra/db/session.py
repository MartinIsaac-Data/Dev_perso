"""Async engine and the tenant session context (ADR-005).

The critical detail is `SET LOCAL`, not `SET`. With a connection pool, a plain
`SET` would leak one tenant's context into the next request served by the same
connection — a silent cross-tenant read. `SET LOCAL` is scoped to the transaction
and released at commit or rollback. `tests/integration/test_rls.py` proves it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.config import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# A second engine for cross-tenant work (ADR-042). It exists because the
# application role is `NOBYPASSRLS` by design: without a separate connection,
# `privileged_session()` would be filtered by the very policies it needs to see
# past, and every scheduled job would quietly process nothing.
_maintenance_engine: AsyncEngine | None = None
_maintenance_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine, _sessionmaker, _maintenance_engine, _maintenance_sessionmaker
    if _engine is not None:
        return _engine

    url = make_url(settings.database_url)
    _engine = create_async_engine(
        url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        echo=False,
        future=True,
    )
    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )

    _maintenance_engine = create_async_engine(
        make_url(settings.effective_maintenance_url),
        # Small on purpose: this pool serves a handful of background jobs, and
        # sizing it like the request pool would double the connection footprint
        # for no benefit.
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        echo=False,
        future=True,
    )
    _maintenance_sessionmaker = async_sessionmaker(
        _maintenance_engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialised — call init_engine() first.")
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker, _maintenance_engine, _maintenance_sessionmaker
    if _engine is not None:
        await _engine.dispose()
    if _maintenance_engine is not None:
        await _maintenance_engine.dispose()
    _engine = None
    _sessionmaker = None
    _maintenance_engine = None
    _maintenance_sessionmaker = None


def _factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Engine not initialised — call init_engine() first.")
    return _sessionmaker


async def set_tenant_context(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | str | None = None,
    auth_subject: str | None = None,
) -> None:
    """Post the RLS context for the current transaction.

    `set_config(..., true)` is the function form of `SET LOCAL`: scoped to the
    transaction, released on commit or rollback. The non-local form would leak
    one tenant's context into the next request served by the same pooled
    connection.
    """
    if account_id is not None:
        await session.execute(
            text("SELECT set_config('app.account_id', :value, true)"),
            {"value": str(account_id)},
        )
    if auth_subject is not None:
        await session.execute(
            text("SELECT set_config('app.auth_subject', :value, true)"),
            {"value": auth_subject},
        )


@asynccontextmanager
async def tenant_session(
    account_id: uuid.UUID | str | None,
    *,
    auth_subject: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open a session whose transaction carries the RLS tenant context.

    Passing `None` opens a session with no tenant context: under RLS that sees
    nothing, which is the safe default for anonymous paths.
    """
    async with _factory()() as session, session.begin():
        await set_tenant_context(session, account_id=account_id, auth_subject=auth_subject)
        yield session


@asynccontextmanager
async def privileged_session() -> AsyncIterator[AsyncSession]:
    """Session for maintenance work that must cross tenants (GDPR purges,
    outbox dispatch, scheduled jobs).

    Uses its **own engine and its own role** (ADR-042). Sharing the request
    engine would not merely be untidy: the application role is `NOBYPASSRLS`, so
    a cross-tenant query issued on it returns nothing and every scheduled job
    becomes a silent no-op — a failure mode with no error, no log line and no
    symptom until someone notices their reminders never arrive.

    Deliberately separate and deliberately rare: workers only, never a request
    handler.
    """
    if _maintenance_sessionmaker is None:
        raise RuntimeError("Engine not initialised — call init_engine() first.")
    async with _maintenance_sessionmaker() as session, session.begin():
        yield session
