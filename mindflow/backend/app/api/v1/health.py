"""Liveness and readiness (Sprint01 epic 4.5)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import SettingsDep
from app.infra.db.session import tenant_session
from app.observability.logging import get_logger

log = get_logger("api.health")

router = APIRouter()


@router.get("/health", summary="Liveness — le processus répond")
async def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "version": settings.version, "env": settings.env}


@router.get("/ready", summary="Readiness — les dépendances répondent")
async def ready(response: Response) -> dict[str, object]:
    """Readiness checks the database, because an instance that cannot reach it
    must leave the load-balancer rotation rather than serve 500s."""
    checks: dict[str, str] = {}
    try:
        async with tenant_session(None) as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.error("health.database_unreachable", error=type(exc).__name__)
        checks["database"] = "unreachable"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
