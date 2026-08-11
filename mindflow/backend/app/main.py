"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
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

    # Sans cela, le client web ne peut appeler aucune route : le navigateur
    # bloque la requête avant qu'elle parte, l'API ne voit rien, et
    # l'application paraît cassée sans qu'aucun journal ne le dise. Le défaut se
    # voit uniquement depuis un navigateur servi sur une autre origine — ni les
    # tests HTTP, ni `flutter test`, ni le test de fumée web ne le rencontrent.
    origins = settings.cors_origins
    origin_regex = settings.cors_origin_regex
    if origins or origin_regex:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_origin_regex=origin_regex,
            allow_methods=["*"],
            allow_headers=["*"],
            # L'en-tête que le client lit pour corréler un incident avec un
            # journal serveur. Non exposé, il est invisible au JavaScript.
            expose_headers=["X-Request-Id"],
            # Faux, partout : l'authentification passe par `Authorization`,
            # jamais par un cookie (ADR-029).
            allow_credentials=False,
        )

    register_error_handlers(app)

    from app.api.v1 import (
        admin,
        assistant,
        captures,
        enterprise,
        entries,
        health,
        insights,
        me,
        meetings,
        notifications,
        planning,
        projects,
        storage,
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(me.router, prefix=settings.api_prefix, tags=["me"])
    app.include_router(captures.router, prefix=settings.api_prefix, tags=["captures"])
    app.include_router(entries.router, prefix=settings.api_prefix, tags=["entries"])
    app.include_router(projects.router, prefix=settings.api_prefix, tags=["projects"])
    # Phase 2. Split by concern rather than by resource: the planning surface
    # spans entries, subtasks and the calendar, and one router per table would
    # scatter a single feature across four files.
    app.include_router(planning.router, prefix=settings.api_prefix, tags=["planning"])
    app.include_router(notifications.router, prefix=settings.api_prefix, tags=["notifications"])
    app.include_router(insights.router, prefix=settings.api_prefix, tags=["insights"])
    app.include_router(assistant.router, prefix=settings.api_prefix, tags=["assistant"])
    app.include_router(meetings.router, prefix=settings.api_prefix, tags=["meetings"])
    app.include_router(enterprise.router, prefix=settings.api_prefix, tags=["enterprise"])
    app.include_router(admin.router, prefix=settings.api_prefix, tags=["admin"])
    if settings.storage_backend == "local":
        # Local-only: lets the client follow the same signed-URL flow it will use
        # against Supabase Storage in production.
        app.include_router(storage.router, prefix=settings.api_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
