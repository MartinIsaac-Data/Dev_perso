"""Exception handlers — every error becomes RFC 9457 (API.md §6.1).

No stack trace, no SQL, no table name ever reaches the client. Unexpected
exceptions are logged with their traceback and returned as an opaque 500 carrying
only the request id, which is what the user quotes when reporting the problem.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import MindFlowError
from app.observability.logging import get_logger

log = get_logger("api.errors")

PROBLEM_JSON = "application/problem+json"

_STATUS_CODES = {
    400: ("bad_request", "Requête invalide"),
    401: ("unauthenticated", "Authentification requise"),
    403: ("insufficient_scope", "Accès refusé"),
    404: ("resource_not_found", "Ressource introuvable"),
    405: ("method_not_allowed", "Méthode non autorisée"),
    409: ("duplicate_resource", "Conflit"),
    413: ("payload_too_large", "Corps de requête trop volumineux"),
    422: ("validation_failed", "Requête invalide"),
    428: ("precondition_required", "En-tête If-Match requis"),
    429: ("rate_limited", "Trop de requêtes"),
    503: ("service_unavailable", "Service indisponible"),
}


def _problem(status: int, body: dict[str, Any], request: Request) -> JSONResponse:
    body.setdefault("instance", request.url.path)
    body["request_id"] = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_JSON)


async def mindflow_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, MindFlowError)
    if exc.status >= 500:
        log.error("error.domain", code=exc.code, status=exc.status, exc_info=exc)
    else:
        log.info("error.domain", code=exc.code, status=exc.status)
    return _problem(exc.status, exc.as_problem(), request)


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            # Drop the "body"/"query" prefix: it is FastAPI plumbing, not a field name.
            "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
            "code": err["type"],
            "detail": err["msg"],
        }
        for err in exc.errors()
    ]
    return _problem(
        422,
        {
            "type": "https://api.mindflow.ai/errors/validation_failed",
            "title": "Requête invalide",
            "status": 422,
            "code": "validation_failed",
            "detail": "Un ou plusieurs champs sont invalides.",
            "errors": errors,
        },
        request,
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code, title = _STATUS_CODES.get(exc.status_code, ("http_error", "Erreur"))
    detail = exc.detail if isinstance(exc.detail, str) else title
    return _problem(
        exc.status_code,
        {
            "type": f"https://api.mindflow.ai/errors/{code}",
            "title": title,
            "status": exc.status_code,
            "code": code,
            "detail": detail,
        },
        request,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("error.unhandled", exc_info=exc)
    return _problem(
        500,
        {
            "type": "https://api.mindflow.ai/errors/internal_error",
            "title": "Erreur interne",
            "status": 500,
            "code": "internal_error",
            "detail": "Une erreur interne est survenue. Contactez le support avec l'identifiant "
            "de requête ci-dessous.",
        },
        request,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(MindFlowError, mindflow_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
