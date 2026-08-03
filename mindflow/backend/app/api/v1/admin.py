"""Administration, audit and analytics for an account (API.md §17).

Everything here is admin-gated and **account-scoped**. There is no cross-tenant
administration surface, deliberately: a "super admin" endpoint that can read any
account is a single credential away from being the worst breach the product can
have, and every operational need it would serve is better served by a database
console with its own audit trail.

The audit log is append-only and unbounded, so it is partitioned by month
(migration 0008). Reading it is a range scan on the partition key, which is why
the date filters below are not optional conveniences — without them the query
touches every partition.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.domain.permissions import Action
from app.infra.db.models.ai import Chunk
from app.infra.db.models.core import AppUser, AuditLog, Capture, Entry
from app.infra.db.models.enterprise import (
    Comment,
    IntegrationConnection,
    ShareLink,
    Workspace,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter(responses=ERROR_RESPONSES)

# The audit query is a range scan on the partition key. Without a bound it
# touches every partition, which is the difference between a millisecond and a
# table scan of the whole history.
DEFAULT_AUDIT_WINDOW = timedelta(days=30)
MAX_AUDIT_WINDOW = timedelta(days=400)


class AuditEntryView(BaseModel):
    id: int
    actor_user_id: uuid.UUID | None = None
    actor_type: str
    action: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class AccountOverview(BaseModel):
    """What an administrator needs on one screen."""

    members: int = 0
    workspaces: int = 0
    entries: int = 0
    captures: int = 0
    comments: int = 0
    active_share_links: int = 0
    connected_integrations: int = 0
    # Connections that will never recover on their own. Surfaced first because
    # it is the only number on this screen that requires somebody to act.
    integrations_needing_attention: int = 0
    indexed_chunks: int = 0
    pending_chunks: int = 0


class UsagePoint(BaseModel):
    day: date
    captures: int = 0
    entries: int = 0
    comments: int = 0


class HealthView(BaseModel):
    """Operational state of one account, for support conversations."""

    embedding_backlog: int = 0
    oldest_pending_chunk: datetime | None = None
    failing_integrations: list[str] = Field(default_factory=list)
    audit_partitions: int = 0
    # True when the newest audit partition does not cover next month. A month
    # arriving with no partition makes every audit insert fail, and this is the
    # only place it is visible before it happens.
    audit_partition_gap: bool = False


@router.get(
    "/admin/overview", response_model=Envelope[AccountOverview], summary="Vue d'ensemble du compte"
)
async def overview(session: SessionDep, principal: PrincipalDep) -> Envelope[AccountOverview]:
    await WorkspaceService(session, principal=principal).require(Action.ANALYTICS_READ)

    async def _count(model: Any, *where: Any) -> int:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int((await session.execute(stmt)).scalar_one())

    return Envelope(
        data=AccountOverview(
            members=await _count(AppUser, AppUser.deleted_at.is_(None)),
            workspaces=await _count(Workspace, Workspace.archived_at.is_(None)),
            entries=await _count(Entry, Entry.deleted_at.is_(None)),
            captures=await _count(Capture, Capture.deleted_at.is_(None)),
            comments=await _count(Comment, Comment.deleted_at.is_(None)),
            active_share_links=await _count(ShareLink, ShareLink.revoked_at.is_(None)),
            connected_integrations=await _count(
                IntegrationConnection, IntegrationConnection.status == "active"
            ),
            integrations_needing_attention=await _count(
                IntegrationConnection,
                IntegrationConnection.status.in_(("expired", "error")),
            ),
            indexed_chunks=await _count(Chunk, Chunk.embedding.is_not(None)),
            pending_chunks=await _count(Chunk, Chunk.embedding.is_(None)),
        )
    )


@router.get("/admin/audit", response_model=Collection[AuditEntryView], summary="Journal d'audit")
async def audit(
    session: SessionDep,
    principal: PrincipalDep,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Collection[AuditEntryView]:
    """Read the audit trail for this account.

    The window is bounded whether or not the caller asks: `audit_log` is
    partitioned by month, and an unbounded range scans every partition ever
    created. Thirty days by default, four hundred at most.
    """
    await WorkspaceService(session, principal=principal).require(Action.AUDIT_READ)

    now = datetime.now(UTC)
    start = since or now - DEFAULT_AUDIT_WINDOW
    if now - start > MAX_AUDIT_WINDOW:
        start = now - MAX_AUDIT_WINDOW
    end = until or now

    stmt = (
        select(AuditLog)
        .where(
            AuditLog.account_id == principal.account_id,
            AuditLog.occurred_at >= start,
            AuditLog.occurred_at <= end,
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)

    rows = list((await session.execute(stmt)).scalars())
    return Collection(
        data=[
            AuditEntryView(
                id=row.id,
                actor_user_id=row.actor_user_id,
                actor_type=row.actor_type,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                metadata=dict(row.metadata_ or {}),
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
    )


@router.get("/admin/usage", response_model=Collection[UsagePoint], summary="Usage par jour")
async def usage(
    session: SessionDep,
    principal: PrincipalDep,
    days: Annotated[int, Query(ge=1, le=180)] = 30,
) -> Collection[UsagePoint]:
    """Daily counts, aggregated in SQL.

    Three grouped queries rather than one join: joining three independent
    per-day aggregates produces a cross product that is wrong in a way nobody
    notices until the numbers are quietly doubled.
    """
    await WorkspaceService(session, principal=principal).require(Action.ANALYTICS_READ)
    start = datetime.now(UTC) - timedelta(days=days)

    async def _by_day(model: Any, column: Any, *where: Any) -> dict[date, int]:
        stmt = (
            select(func.date(column).label("day"), func.count())
            .where(column >= start, *where)
            .group_by(text("day"))
        )
        return {row[0]: int(row[1]) for row in (await session.execute(stmt)).all()}

    captures = await _by_day(Capture, Capture.created_at, Capture.deleted_at.is_(None))
    entries = await _by_day(Entry, Entry.created_at, Entry.deleted_at.is_(None))
    comments = await _by_day(Comment, Comment.created_at, Comment.deleted_at.is_(None))

    days_seen = sorted(set(captures) | set(entries) | set(comments))
    return Collection(
        data=[
            UsagePoint(
                day=day,
                captures=captures.get(day, 0),
                entries=entries.get(day, 0),
                comments=comments.get(day, 0),
            )
            for day in days_seen
        ]
    )


@router.get("/admin/health", response_model=Envelope[HealthView], summary="État opérationnel")
async def health(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> Envelope[HealthView]:
    """The numbers a support conversation actually needs.

    `audit_partition_gap` is the one worth watching: a month arriving with no
    partition makes every audit insert fail, and this is the only place it is
    visible *before* it happens rather than in an incident channel.
    """
    await WorkspaceService(session, principal=principal).require(Action.ANALYTICS_READ)

    backlog = int(
        (
            await session.execute(
                select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
            )
        ).scalar_one()
    )
    oldest = (
        await session.execute(select(func.min(Chunk.created_at)).where(Chunk.embedding.is_(None)))
    ).scalar_one()

    failing = list(
        (
            await session.execute(
                select(IntegrationConnection.provider).where(
                    IntegrationConnection.status.in_(("expired", "error"))
                )
            )
        ).scalars()
    )

    # Partition bookkeeping is global rather than per-account, but it is read
    # here because this is the screen somebody is looking at when things are
    # going wrong.
    partitions = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM pg_class c "
                    "JOIN pg_inherits i ON i.inhrelid = c.oid "
                    "JOIN pg_class p ON p.oid = i.inhparent "
                    "WHERE p.relname = 'audit_log'"
                )
            )
        ).scalar_one()
    )
    next_month = (datetime.now(UTC).replace(day=1) + timedelta(days=32)).strftime("%Y%m")
    gap = not bool(
        (
            await session.execute(
                text("SELECT 1 FROM pg_class WHERE relname = :name"),
                {"name": f"audit_log_{next_month}"},
            )
        ).scalar_one_or_none()
    )

    return Envelope(
        data=HealthView(
            embedding_backlog=backlog,
            oldest_pending_chunk=oldest,
            failing_integrations=sorted(set(failing)),
            audit_partitions=partitions,
            audit_partition_gap=gap,
        )
    )
