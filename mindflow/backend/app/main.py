"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.middleware.correlation import CorrelationMiddleware
from app.api.middleware.errors import register_error_handlers
from app.config import Settings, get_settings
from app.observability import metrics
from app.observability.logging import configure_logging, get_logger

log = get_logger("app")

DESCRIPTION = """
API MindFlow AI — capture vocale, transcription et extraction structurée.

**Pipeline** : voix → Whisper → texte → LLM → JSON typé → PostgreSQL.

Toutes les erreurs suivent la RFC 9457 (`application/problem+json`) et portent un
`code` applicatif stable : c'est ce code, et non le statut HTTP, qui constitue le
contrat.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from app.infra.db.session import dispose_engine, init_engine

        init_engine(settings)
        log.info("app.startup", env=settings.env, version=settings.version)
        yield
        await dispose_engine()
        log.info("app.shutdown")

    app = FastAPI(
        title="MindFlow AI",
        description=DESCRIPTION,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.state.settings = settings

    app.add_middleware(CorrelationMiddleware)
    register_error_handlers(app)

    from app.api.v1 import captures, entries, health, me, projects, storage

    app.include_router(health.router, tags=["health"])
    app.include_router(me.router, prefix=settings.api_prefix, tags=["me"])
    app.include_router(captures.router, prefix=settings.api_prefix, tags=["captures"])
    app.include_router(entries.router, prefix=settings.api_prefix, tags=["entries"])
    app.include_router(projects.router, prefix=settings.api_prefix, tags=["projects"])
    if settings.storage_backend == "local":
        # Local-only: lets the client follow the same signed-URL flow it will use
        # against Supabase Storage in production.
        app.include_router(storage.router, prefix=settings.api_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
