"""Pipeline entry points shared by the API (inline mode) and the arq worker."""

from __future__ import annotations

import uuid
from typing import Any

from app.config import Settings
from app.domain.enums import CaptureStatus
from app.infra.ai import factory as ai_factory
from app.infra.queue.inline import InlineQueue
from app.infra.storage import factory as storage_factory
from app.observability.logging import get_logger
from app.workers.pipeline.orchestrator import CapturePipeline

log = get_logger("pipeline.runner")

PROCESS_CAPTURE = "process_capture"


def build_pipeline(settings: Settings) -> CapturePipeline:
    # Resolved through the module, not a bound name: an adapter must stay
    # substitutable at call time (AI.md I1).
    return CapturePipeline(
        settings=settings,
        storage=storage_factory.build_storage(settings),
        transcriber=ai_factory.build_transcriber(settings),
        analyzer=ai_factory.build_analyzer(settings),
    )


async def process_capture(
    settings: Settings, capture_id: str | uuid.UUID, account_id: str | uuid.UUID
) -> str:
    status: CaptureStatus = await build_pipeline(settings).run(
        uuid.UUID(str(capture_id)), uuid.UUID(str(account_id))
    )
    return status.value


_inline: InlineQueue | None = None


def inline_queue(settings: Settings) -> InlineQueue:
    """Singleton so the handler registry survives across requests."""
    global _inline
    if _inline is None:
        _inline = InlineQueue()

        async def handler(capture_id: Any, account_id: Any) -> None:
            await process_capture(settings, capture_id, account_id)

        _inline.register(PROCESS_CAPTURE, handler)
    return _inline


def reset_inline_queue() -> None:
    """Test hook — settings differ between test cases."""
    global _inline
    _inline = None
