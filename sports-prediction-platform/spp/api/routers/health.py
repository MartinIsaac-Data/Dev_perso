"""Sondes de santé.

Trois niveaux, délibérément distincts : le processus répond, les données sont
fraîches, le modèle est calibré. Un système de prédiction peut être
parfaitement vivant et totalement inutilisable (docs/12 §5.3).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from spp import __version__
from spp.common.config import get_settings
from spp.core.sports import registered_sports
from spp.core.time import utc_now

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Le processus répond")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "env": settings.env,
        "sports": [s.value for s in registered_sports()],
        "server_time": utc_now().isoformat(),
    }


@router.get("/data", summary="Fraîcheur des sources de données")
def health_data() -> dict[str, Any]:
    # Phase 3 : alimenté par ops.data_freshness_status.
    return {
        "status": "unknown",
        "detail": "Ingestion non implémentée (phase 3).",
        "sources": [],
    }


@router.get("/models", summary="Calibration et dérive du modèle champion")
def health_models() -> dict[str, Any]:
    # Phase 6 : alimenté par ml.calibration_snapshots.
    return {
        "status": "unknown",
        "detail": "Aucun modèle entraîné (phase 5-6).",
        "champion": None,
        "signals_suspended": True,
        "reason": "no_model_trained",
    }
