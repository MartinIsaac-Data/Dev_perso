"""Correlation, access logging and metrics (Architecture.md §7.2, §12)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability import metrics
from app.observability.logging import get_logger, request_id_var, trace_id_var

log = get_logger("api.access")

_Next = Callable[[Request], Awaitable[Response]]


def _route_template(request: Request) -> str:
    """Group metrics by route pattern, never by concrete id — a per-uuid label
    would blow up cardinality."""
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _Next) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:22]}"
        trace_id = request.headers.get("traceparent", "").split("-")[1:2] or [uuid.uuid4().hex]

        token_req = request_id_var.set(request_id)
        token_trace = trace_id_var.set(trace_id[0])
        request.state.request_id = request_id

        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = _route_template(request)
            if route != "/metrics":
                metrics.http_requests_total.labels(request.method, route, str(status)).inc()
                metrics.http_request_duration_seconds.labels(request.method, route).observe(elapsed)
                log.info(
                    "http.request",
                    method=request.method,
                    route=route,
                    status=status,
                    duration_ms=round(elapsed * 1000, 2),
                )
            request_id_var.reset(token_req)
            trace_id_var.reset(token_trace)
