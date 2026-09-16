"""Point d'entrée de l'API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from spp import __version__
from spp.api.errors import insufficient_data_handler, leakage_handler
from spp.api.routers import health
from spp.common.config import get_settings
from spp.common.errors import InsufficientDataError, LeakageError
from spp.common.logging import configure_logging, get_logger

DISCLAIMER = (
    "Estimations probabilistes produites par un modèle statistique. Elles "
    "comportent une incertitude quantifiée et ne constituent ni une prédiction "
    "certaine ni un conseil."
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    get_logger(__name__).info("api.start", env=settings.env, version=__version__)
    yield
    get_logger(__name__).info("api.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Sports Prediction Platform",
        version=__version__,
        description=DISCLAIMER,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_exception_handler(InsufficientDataError, insufficient_data_handler)
    app.add_exception_handler(LeakageError, leakage_handler)

    app.include_router(health.router, prefix="/api/v1")

    @app.get("/api/v1", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "name": "sports-prediction-platform",
            "version": __version__,
            "disclaimer": DISCLAIMER,
        }

    return app


app = create_app()
