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


class WorkerSettings:
    functions: ClassVar[list[Any]] = [process_capture_job]
    cron_jobs: ClassVar[list[Any]] = [
        # Recovers captures whose enqueue was lost (Redis restart, crash between
        # commit and enqueue). The database is the source of truth, not the queue.
        cron(sweep_job, minute=set(range(0, 60, 5)), run_at_startup=True),
        cron(dispatch_job, second={0, 10, 20, 30, 40, 50}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 5
    job_timeout = 600
    keep_result = 3600

    @staticmethod
    def redis_settings() -> RedisSettings:
        return redis_settings(get_settings())
