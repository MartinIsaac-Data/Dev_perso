"""arq queue adapter (ADR-006).

Four queues with distinct SLAs (Architecture.md §7.3). Redis is a cache for the
queue, not the source of truth: a lost Redis loses pending jobs, and a periodic
sweep re-enqueues captures stuck in a non-terminal state from the database.
"""

from __future__ import annotations

from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import Settings
from app.observability.logging import get_logger

log = get_logger("queue.arq")

QUEUE_REALTIME = "capture.realtime"
QUEUE_BATCH = "capture.batch"
QUEUE_INDEX = "index"
QUEUE_SCHEDULED = "scheduled"


def redis_settings(settings: Settings) -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


class ArqQueue:
    def __init__(self, pool: ArqRedis, *, queue_name: str = QUEUE_REALTIME) -> None:
        self._pool = pool
        self._queue_name = queue_name

    @classmethod
    async def connect(cls, settings: Settings, *, queue_name: str = QUEUE_REALTIME) -> ArqQueue:
        return cls(await create_pool(redis_settings(settings)), queue_name=queue_name)

    async def enqueue(self, job: str, *args: Any, **kwargs: Any) -> str | None:
        result = await self._pool.enqueue_job(job, *args, _queue_name=self._queue_name, **kwargs)
        return result.job_id if result else None

    async def close(self) -> None:
        # `aclose` exists on the redis asyncio client at runtime; the arq stubs
        # still describe the older surface.
        await self._pool.aclose()  # type: ignore[attr-defined]
