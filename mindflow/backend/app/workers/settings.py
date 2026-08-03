"""arq worker definition (ADR-006, Architecture.md §7.3).

Four queues with distinct SLAs. Retry policy: 5 attempts with exponential
backoff; after that the job goes to the dead-letter set and the capture is left
in a terminal-but-degraded state — consultable, never lost.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.infra.queue.arq_queue import redis_settings
from app.observability.logging import configure_logging, get_logger
from app.workers.outbox_dispatcher import dispatch_outbox
from app.workers.pipeline.runner import PROCESS_CAPTURE, process_capture
from app.workers.scheduled.digester import generate_due_digests
from app.workers.scheduled.extractor import extract_entities
from app.workers.scheduled.indexer import embed_backlog
from app.workers.scheduled.reminder_dispatcher import dispatch_due_reminders, sweep_snoozed
from app.workers.scheduled.sweeper import sweep_stuck_captures

log = get_logger("worker")


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings)
    from app.infra.db.session import init_engine

    init_engine(settings)
    ctx["settings"] = settings
    log.info("worker.startup", env=settings.env)


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.infra.db.session import dispose_engine

    await dispose_engine()
    log.info("worker.shutdown")


async def process_capture_job(ctx: dict[str, Any], capture_id: str, account_id: str) -> str:
    return await process_capture(ctx["settings"], capture_id, account_id)


process_capture_job.__name__ = PROCESS_CAPTURE


async def sweep_job(ctx: dict[str, Any]) -> int:
    return await sweep_stuck_captures(ctx["settings"])


async def dispatch_job(ctx: dict[str, Any]) -> int:
    return await dispatch_outbox(ctx["settings"])


async def reminder_job(ctx: dict[str, Any]) -> int:
    return await dispatch_due_reminders(ctx["settings"])


async def snooze_job(ctx: dict[str, Any]) -> int:
    return await sweep_snoozed(ctx["settings"])


async def embed_job(ctx: dict[str, Any]) -> int:
    return await embed_backlog(ctx["settings"])


async def digest_job(ctx: dict[str, Any]) -> int:
    return await generate_due_digests(ctx["settings"])


async def extract_job(ctx: dict[str, Any]) -> int:
    return await extract_entities(ctx["settings"])


class WorkerSettings:
    functions: ClassVar[list[Any]] = [process_capture_job]
    cron_jobs: ClassVar[list[Any]] = [
        # Recovers captures whose enqueue was lost (Redis restart, crash between
        # commit and enqueue). The database is the source of truth, not the queue.
        cron(sweep_job, minute=set(range(0, 60, 5)), run_at_startup=True),
        cron(dispatch_job, second={0, 10, 20, 30, 40, 50}),
        # Every minute: the finest granularity a reminder needs, and the
        # coarsest a user tolerates. At five minutes, "remind me at 14:00" would
        # arrive at 14:04, which is late enough to miss the meeting it was for.
        cron(reminder_job, second={5}, run_at_startup=True),
        # Waking a snoozed task is not urgent to the minute; a quarter-hour
        # cadence keeps the query cheap.
        cron(snooze_job, minute=set(range(0, 60, 15))),
        # Embedding backlog. Every two minutes rather than every minute: a
        # chunk that becomes semantically searchable ninety seconds later
        # than it might have is invisible to a user, and the looser cadence
        # lets batches fill up, which is where the cost saving is.
        cron(embed_job, minute=set(range(0, 60, 2)), run_at_startup=True),
        # Hourly, because "21:00" means twenty-four different instants and
        # each tick asks which users have just reached theirs.
        cron(digest_job, minute={2}),
        # Entity extraction costs a model call per entry, so it runs at a
        # far slower cadence than indexing and works newest-first: a
        # knowledge graph current at the edges beats one complete at the
        # beginning.
        cron(extract_job, minute={7, 27, 47}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 5
    job_timeout = 600
    keep_result = 3600

    @staticmethod
    def redis_settings() -> RedisSettings:
        return redis_settings(get_settings())
