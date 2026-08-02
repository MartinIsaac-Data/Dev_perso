"""Structured logging (Architecture.md §12.2).

JSON, one line per event, mandatory correlation fields. Personal data is banned
from logs — `tests/unit/test_logging.py` enforces that with a redaction test, and
the redactor below is the runtime backstop.
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

import structlog

from app.config import Settings

# Correlation context, populated by the middleware and inherited by every log
# line emitted while handling a request — including from worker tasks.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
account_id_var: ContextVar[str | None] = ContextVar("account_id", default=None)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_JWT = re.compile(r"\beyJ[A-Za-z0-9._-]{10,}")

# Keys whose value must never be logged, whatever it contains.
_FORBIDDEN_KEYS = frozenset(
    {
        "text",
        "transcript",
        "transcript_text",
        "content",
        "body",
        "title",
        "query",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "email",
        "audio",
        "prompt",
        "summary",
    }
)


def redact(value: str) -> str:
    value = _BEARER.sub(r"\1[redacted]", value)
    value = _JWT.sub("[redacted-jwt]", value)
    return _EMAIL.sub("[redacted-email]", value)


def _scrub_processor(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    for key in list(event_dict):
        if key.lower() in _FORBIDDEN_KEYS:
            event_dict[key] = "[redacted]"
        elif isinstance(event_dict[key], str):
            event_dict[key] = redact(event_dict[key])
    return event_dict


def _context_processor(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    if (request_id := request_id_var.get()) is not None:
        event_dict.setdefault("request_id", request_id)
    if (trace_id := trace_id_var.get()) is not None:
        event_dict.setdefault("trace_id", trace_id)
    if (account_id := account_id_var.get()) is not None:
        event_dict.setdefault("account_id", account_id)
    return event_dict


def configure_logging(settings: Settings) -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        _context_processor,
        _scrub_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # Uvicorn duplicates access logs we already emit ourselves.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
