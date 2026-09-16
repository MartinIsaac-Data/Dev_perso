"""Traduction des erreurs du domaine en réponses RFC 7807 (docs/10 §4)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from spp.common.errors import InsufficientDataError, LeakageError

PROBLEM_BASE = "https://sports-prediction-platform/problems"


async def insufficient_data_handler(_request: Request, exc: Exception) -> JSONResponse:
    """422 : la ressource existe, mais la prédiction n'est pas calculable.

    C'est le code le plus important de l'API : il distingue « pas de données »
    de « probabilité produite sur des données insuffisantes ».
    """
    assert isinstance(exc, InsufficientDataError)
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": f"{PROBLEM_BASE}/insufficient-data",
            "title": "Prédiction indisponible",
            "status": 422,
            "detail": exc.detail,
            "missing": exc.missing,
            "data_quality": exc.data_quality,
        },
    )


async def leakage_handler(_request: Request, exc: Exception) -> JSONResponse:
    """500 : une fuite de données est un défaut de conception, jamais une 4xx."""
    assert isinstance(exc, LeakageError)
    return JSONResponse(
        status_code=500,
        media_type="application/problem+json",
        content={
            "type": f"{PROBLEM_BASE}/leakage",
            "title": "Fuite de données détectée",
            "status": 500,
            "detail": str(exc),
        },
    )
