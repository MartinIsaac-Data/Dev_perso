"""Draining the embedding backlog, across every tenant.

This job exists because embedding is the one part of the AI layer that costs
money per call and must never sit on a user's critical path. Chunks are written
synchronously with a NULL embedding; this worker fills them in.

Two properties it must have, and both are easy to get wrong:

* **It spans tenants, so it runs privileged** (ADR-042). The `privileged_session`
  uses the `mindflow_maintenance` role, which is the only connection in the
  product that bypasses RLS. The per-account work re-enters a tenant-scoped
  session, so every write still goes through a policy.
* **A provider outage must not lose work.** A failed batch leaves the rows NULL
  and returns; the next tick retries them. There is deliberately no "failed"
  state, because a failed state needs a reset path and somebody to remember it
  exists.

The backlog gauge is the operational signal. Semantic search over a stale
corpus looks exactly like semantic search over a fresh one, right up until
someone asks about a note from this morning.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.config import Settings
from app.infra.ai.factory import build_embedder
from app.infra.db.models.ai import Chunk
from app.infra.db.session import privileged_session, tenant_session
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.indexing_service import IndexingService

log = get_logger("worker.indexer")

# Accounts touched per tick. Bounded so one account with a large import cannot
# starve everyone else's newest notes.
MAX_ACCOUNTS = 20


async def embed_backlog(settings: Settings) -> int:
    """Embed pending chunks for the accounts that have them. Returns the count."""
    if settings.embedding_backend == "fake":
        # The fake embedder produces vectors that index and retrieve
        # successfully and encode nothing. Running it here would fill the index
        # with noise that looks exactly like a working one.
        log.debug("indexer.skipped", reason="fake_embedder")
        return 0

    accounts = await _accounts_with_backlog()
    if not accounts:
        return 0

    embedder = build_embedder(settings)
    total = 0
    for account_id in accounts:
        try:
            async with tenant_session(str(account_id)) as session:
                service = IndexingService(session, embedder=embedder)
                result = await service.embed_pending(limit=settings.embedding_batch_size)
                total += result.embedded
        except Exception:
            # One account's failure must not stop the others: a single corrupt
            # row would otherwise freeze indexing for the whole platform.
            log.exception("indexer.account_failed", account_id=str(account_id))

    log.info("indexer.tick", accounts=len(accounts), embedded=total)
    return total


async def _accounts_with_backlog() -> list[str]:
    """Which tenants have work waiting.

    Ordered by oldest pending chunk so the queue is fair: an account that has
    been waiting an hour is served before one that started thirty seconds ago.
    """
    async with privileged_session() as session:
        rows = (
            await session.execute(
                select(Chunk.account_id, func.min(Chunk.created_at).label("oldest"))
                .where(Chunk.embedding.is_(None))
                .group_by(Chunk.account_id)
                .order_by(func.min(Chunk.created_at))
                .limit(MAX_ACCOUNTS)
            )
        ).all()

        backlog = (
            await session.execute(
                select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
            )
        ).scalar_one()
        metrics.embedding_backlog.set(int(backlog))

        return [str(row[0]) for row in rows]
