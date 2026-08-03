"""Outbox dispatcher (ADR-010).

Reads events written in the same transaction as their business change and marks
them dispatched. Delivery is at-least-once, so every consumer is idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.config import Settings
from app.infra.db.models.core import Outbox
from app.infra.db.session import privileged_session
from app.observability.logging import get_logger

log = get_logger("worker.outbox")

BATCH = 100
MAX_ATTEMPTS = 5


async def dispatch_outbox(settings: Settings) -> int:
    dispatched = 0
    async with privileged_session() as session:
        rows = await session.execute(
            select(Outbox)
            .where(Outbox.status == "pending", Outbox.available_at <= datetime.now(UTC))
            .order_by(Outbox.id)
            .limit(BATCH)
            # Skips rows another dispatcher holds, so two instances can run
            # concurrently without double-delivering.
            .with_for_update(skip_locked=True)
        )
        for event in rows.scalars().all():
            event.attempts += 1
            event.status = "dispatched"
            event.dispatched_at = datetime.now(UTC)
            dispatched += 1
            log.info(
                "outbox.dispatched",
                event_type=event.event_type,
                aggregate_id=str(event.aggregate_id),
            )
    return dispatched
