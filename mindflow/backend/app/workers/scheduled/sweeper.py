"""Stuck-capture sweeper.

The queue is a cache, not the source of truth (ADR-006). If Redis restarts, or
the process dies between the commit and the enqueue, the capture is still in the
database in a non-terminal state — this job finds it and re-runs the pipeline.

Without it, ADR-010's durability claim would rest on Redis, which does not
guarantee it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import Settings
from app.domain.enums import CaptureStatus
from app.infra.db.models.core import Capture
from app.infra.db.session import privileged_session
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("worker.sweeper")

STUCK_AFTER = timedelta(minutes=10)
ABANDON_AFTER = timedelta(hours=24)
BATCH = 50


async def sweep_stuck_captures(settings: Settings) -> int:
    """Re-run captures stalled in a non-terminal state; abandon never-uploaded ones."""
    from app.workers.pipeline.runner import build_pipeline

    now = datetime.now(UTC)
    stuck: list[tuple[str, str]] = []

    async with privileged_session() as session:
        rows = await session.execute(
            select(Capture.id, Capture.account_id, Capture.status, Capture.created_at)
            .where(
                Capture.deleted_at.is_(None),
                Capture.status.in_(
                    [
                        CaptureStatus.UPLOADED.value,
                        CaptureStatus.TRANSCRIBING.value,
                        CaptureStatus.TRANSCRIBED.value,
                        CaptureStatus.EXTRACTING.value,
                        CaptureStatus.PENDING_UPLOAD.value,
                    ]
                ),
                Capture.updated_at < now - STUCK_AFTER,
            )
            .limit(BATCH)
        )
        for capture_id, account_id, status, created_at in rows.all():
            if status == CaptureStatus.PENDING_UPLOAD.value:
                # Never uploaded: the audio only ever existed on the device, and
                # the client's own queue is responsible for retrying it.
                if now - created_at > ABANDON_AFTER:
                    capture = await session.get(Capture, capture_id)
                    if capture is not None:
                        capture.status = CaptureStatus.ABANDONED.value
                continue
            stuck.append((str(capture_id), str(account_id)))

    pipeline = build_pipeline(settings)
    for capture_id, account_id in stuck:
        import uuid as _uuid

        log.warning("sweeper.recovering", capture_id=capture_id)
        metrics.job_retries_total.labels("process_capture", "swept").inc()
        try:
            await pipeline.run(_uuid.UUID(capture_id), _uuid.UUID(account_id))
        except Exception as exc:
            log.error("sweeper.recovery_failed", capture_id=capture_id, error=type(exc).__name__)
    return len(stuck)
