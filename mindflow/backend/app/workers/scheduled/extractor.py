"""Running entity detection over entries that have none yet.

Separate from the capture pipeline on purpose (see `app.prompts.entities` for
the full reasoning): entity extraction must be re-runnable over the existing
corpus when the taxonomy improves, and it must never be able to fail a capture.
An entry with no entities is still a perfectly good entry.

Finding the backlog is the only interesting part. There is no `extracted_at`
column — adding one would mean a second source of truth to keep in step with the
mention rows — so the backlog is "entries with no mention row and no attempt
recorded". That is an anti-join, which is cheap here because it is bounded by
the batch size and ordered by recency: the notes a user is most likely to ask
about are the ones they just wrote.

The consequence, stated plainly: an entry that genuinely contains no entity is
retried on every pass. That is the accepted cost of not carrying a status
column, and it is bounded by the batch size — the worker re-reads a fixed number
of empty entries per tick, not a growing number.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.config import Settings
from app.domain.errors import ExtractionUnavailableError
from app.infra.ai.factory import build_chat
from app.infra.db.models.ai import EntityMention
from app.infra.db.models.core import Entry
from app.infra.db.session import privileged_session, tenant_session
from app.observability.logging import get_logger
from app.services.knowledge_service import KnowledgeService

log = get_logger("worker.extractor")

MAX_ACCOUNTS = 10
BATCH = 20


async def extract_entities(settings: Settings) -> int:
    """Extract entities for recent entries that have none. Returns the count."""
    if settings.chat_backend == "fake":
        log.debug("extractor.skipped", reason="fake_chat")
        return 0

    accounts = await _accounts_with_entries()
    if not accounts:
        return 0

    chat = build_chat(settings)
    processed = 0

    for account_id in accounts:
        try:
            async with tenant_session(account_id) as session:
                service = KnowledgeService(session, chat=chat)
                for entry in await _pending(session, limit=BATCH):
                    try:
                        await service.extract_for_entry(entry)
                        processed += 1
                    except ExtractionUnavailableError:
                        # The provider is down for everyone, not just this
                        # entry. Stopping the account's batch avoids burning
                        # the rest of the tick on calls that will all fail.
                        log.warning("extractor.unavailable", account_id=account_id)
                        break
        except Exception:
            log.exception("extractor.account_failed", account_id=account_id)

    if processed:
        log.info("extractor.tick", accounts=len(accounts), processed=processed)
    return processed


async def _pending(session, *, limit: int) -> list[Entry]:  # type: ignore[no-untyped-def]
    """Recent entries with no mention row.

    Newest first: the notes a user is most likely to ask about are the ones they
    just wrote, and a knowledge graph that is current at the edges is far more
    useful than one that is complete at the beginning.
    """
    linked = select(EntityMention.entry_id).where(EntityMention.entry_id.is_not(None))
    rows = (
        await session.execute(
            select(Entry)
            .where(Entry.deleted_at.is_(None), Entry.id.not_in(linked))
            .order_by(Entry.occurred_at.desc())
            .limit(limit)
        )
    ).scalars()
    return list(rows)


async def _accounts_with_entries() -> list[str]:
    """Tenants with at least one unprocessed entry.

    Cross-tenant, so privileged (ADR-042).
    """
    async with privileged_session() as session:
        linked = select(EntityMention.entry_id).where(EntityMention.entry_id.is_not(None))
        rows = (
            await session.execute(
                select(Entry.account_id, func.max(Entry.occurred_at).label("newest"))
                .where(Entry.deleted_at.is_(None), Entry.id.not_in(linked))
                .group_by(Entry.account_id)
                .order_by(func.max(Entry.occurred_at).desc())
                .limit(MAX_ACCOUNTS)
            )
        ).all()
        return [str(row[0]) for row in rows]
