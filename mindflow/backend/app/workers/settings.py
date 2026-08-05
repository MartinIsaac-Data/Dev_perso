"""arq worker definition (ADR-006, Architecture.md §7.3).

Four queues with distinct SLAs. Retry policy: 5 attempts with exponential
backoff; after that the job goes to the dead-letter set and the capture is left
in a terminal-but-degraded state — consultable, never lost.
"""

from __future__ import annotations

from typing import Any, ClassVar

from arq import cron, func
from arq.connections import RedisSettings

from app.config import get_settings
from app.infra.queue.arq_queue import QUEUE_REALTIME
from app.infra.queue.arq_queue import redis_settings as build_redis_settings
from app.observability.logging import configure_logging, get_logger
from app.workers.outbox_dispatcher import dispatch_outbox
from app.workers.pipeline.runner import PROCESS_CAPTURE, process_capture
from app.workers.scheduled.digester import generate_due_digests
from app.workers.scheduled.extractor import extract_entities
from app.workers.scheduled.indexer import embed_backlog
from app.workers.scheduled.partitioner import maintain_audit_partitions
from app.workers.scheduled.reminder_dispatcher import dispatch_due_reminders, sweep_snoozed
from app.workers.scheduled.sweeper import sweep_stuck_captures
from app.workers.scheduled.synchroniser import sync_due_connections

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


async def partition_job(ctx: dict[str, Any]) -> int:
    return await maintain_audit_partitions(ctx["settings"])


async def sync_job(ctx: dict[str, Any]) -> int:
    return await sync_due_connections(ctx["settings"])


class WorkerSettings:
    # The name the API enqueues under, stated explicitly. arq names a job from
    # `__qualname__`, so this function would otherwise register as
    # `process_capture_job` while `app/api/v1/captures.py` enqueues
    # `process_capture`: the job is accepted, never run, and the capture sits at
    # `uploaded` while the sweeper re-enqueues it under the same wrong name.
    functions: ClassVar[list[Any]] = [func(process_capture_job, name=PROCESS_CAPTURE)]

    # The queue the API actually writes to (`ArqQueue.connect` defaults to it).
    # Left unset, arq listens on its own default queue and the two never meet —
    # the same silent failure as a name mismatch, one layer down.
    queue_name: ClassVar[str] = QUEUE_REALTIME
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
        # Audit partitions. Daily is far more often than needed — the job
        # creates three months ahead — and that is the point: the failure it
        # prevents is dated and total, so the cheapest possible insurance is
        # worth taking every day. `run_at_startup` covers the case where the
        # worker has been down across a month boundary, which is exactly when
        # nobody was watching.
        cron(partition_job, hour={3}, minute={11}, run_at_startup=True),
        # Integrations. Five minutes is well inside every provider's rate limit
        # and well under a user's patience; the per-connection cadence and the
        # failure backoff are decided inside the job, not by this cron, because
        # a connection that is failing must not be attempted as often as one
        # that is healthy.
        cron(sync_job, minute=set(range(2, 60, 5))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 5
    job_timeout = 600
    keep_result = 3600

    # A value, not a method. `arq.worker.get_kwargs` reads
    # `WorkerSettings.__dict__` rather than doing attribute lookup, so a
    # `@staticmethod` here reaches `create_pool` as the descriptor itself and
    # the worker dies at startup with `'staticmethod' object has no attribute
    # 'host'`. Evaluated at import, which is when the arq CLI reads this module
    # anyway; the API never imports it.
    redis_settings: ClassVar[RedisSettings] = build_redis_settings(get_settings())
