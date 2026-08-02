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


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine, _sessionmaker
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
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialised — call init_engine() first.")
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def _factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Engine not initialised — call init_engine() first.")
    return _sessionmaker


@asynccontextmanager
async def tenant_session(account_id: uuid.UUID | str | None) -> AsyncIterator[AsyncSession]:
    """Open a session whose transaction carries the RLS tenant context.

    Passing `None` opens a session with no tenant context: under RLS that sees
    nothing, which is the safe default for anonymous paths.
    """
    async with _factory()() as session, session.begin():
        if account_id is not None:
            await session.execute(
                text("SELECT set_config('app.account_id', :account_id, true)"),
                {"account_id": str(account_id)},
            )
        yield session


@asynccontextmanager
async def privileged_session() -> AsyncIterator[AsyncSession]:
    """Session for maintenance work that must cross tenants (GDPR purges,
    outbox dispatch, scheduled jobs).

    Deliberately separate and deliberately rare: it is the one path where the RLS
    safety net does not apply, so it is used by workers only, never by a request
    handler.
    """
    async with _factory()() as session, session.begin():
        yield session
