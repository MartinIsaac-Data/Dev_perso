"""In-process queue.

Used by tests and by `docker compose` runs without a worker. It executes the job
immediately instead of enqueuing it, which keeps the pipeline itself
queue-agnostic: the orchestrator never knows which one it is running under.
"""

from __future__ import annotations

from typing import Any

from app.observability.logging import get_logger

log = get_logger("queue.inline")


class InlineQueue:
    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, name: str, handler: Any) -> None:
        self._handlers[name] = handler

    async def enqueue(self, job: str, *args: Any, **kwargs: Any) -> str | None:
        handler = self._handlers.get(job)
        if handler is None:
            log.warning("queue.no_handler", job=job)
            return None
        await handler(*args, **kwargs)
        return None
