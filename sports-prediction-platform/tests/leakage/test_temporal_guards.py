"""Tests anti-fuite applicables dès la phase 1.

La suite complète (les onze fuites de docs/07 §2) se construit au fil des
phases : la plupart nécessitent le repository point-in-time (phase 2) et le
feature store (phase 4). Les garde-fous ci-dessous existent déjà et doivent
rester verts.

Cette suite s'exécute seule (`make test-leakage`) et doit passer **avant tout
backtest** : un backtest lancé sur un pipeline qui fuit est pire qu'inutile,
il est convaincant.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest
from spp.core.enums import LeakageClass
from spp.core.time import ensure_utc, recency_weight

pytestmark = pytest.mark.leakage

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


# --------------------------------------------------------------------------
#  Garde-fous d'exécution
# --------------------------------------------------------------------------
def test_naive_timestamps_cannot_enter_the_domain() -> None:
    """Un `as_of_ts` naïf décalé d'une heure suffit à laisser entrer une
    composition officielle dans une prédiction censée l'ignorer."""
    with pytest.raises(ValueError, match="naïf"):
        ensure_utc(datetime(2026, 9, 20, 18, 0))  # noqa: DTZ001 - volontaire


def test_a_future_match_cannot_weight_a_past_form() -> None:
    """Un poids de récence négatif signifierait qu'un match postérieur
    contribue à une forme calculée avant lui."""
    with pytest.raises(ValueError, match="futur"):
        recency_weight(-0.001, 90.0)


def test_recency_weight_is_monotone_decreasing() -> None:
    weights = [recency_weight(d, 90.0) for d in (0.0, 30.0, 90.0, 365.0)]
    assert weights == sorted(weights, reverse=True)


def test_leakage_classes_are_exhaustive() -> None:
    """Les trois classes de docs/03 §1 existent — le moteur de features s'en
    servira pour refuser de calculer une feature `forbidden` en mode live."""
    assert {c.value for c in LeakageClass} == {"safe", "needs_lag", "forbidden"}


# --------------------------------------------------------------------------
#  Garde-fous structurels : le schéma rend-il le point-in-time possible ?
# --------------------------------------------------------------------------
REVISABLE_TABLES = [
    "stats.football_team_match",
    "stats.basketball_team_match",
    "stats.tennis_competitor_match",
    "stats.player_match",
    "core.availabilities",
]


def _table_body(table: str) -> str:
    sql = SCHEMA.read_text(encoding="utf-8")
    start = sql.find(f"CREATE TABLE {table} (")
    assert start != -1, f"Table introuvable : {table}"
    return sql[start : sql.find("\n);", start)]


@pytest.mark.parametrize("table", REVISABLE_TABLES)
def test_revisable_tables_are_bitemporal(table: str) -> None:
    """Toute table qu'un fournisseur peut réviser porte les deux axes du temps.

    Sans `recorded_at`/`superseded_at`, une correction à J+3 réécrit le passé
    et le backtest lit une donnée que le modèle n'avait pas (fuite n°2).
    """
    body = _table_body(table)
    assert "recorded_at" in body, f"{table} n'a pas de temps de connaissance"
    assert "superseded_at" in body, f"{table} ne peut pas être supersédée"


def test_feature_values_are_keyed_by_as_of_ts() -> None:
    """Il doit être structurellement impossible de stocker « la feature de ce
    match » sans dire à quel instant elle a été calculée."""
    body = _table_body("features.values")
    pk = re.search(r"PRIMARY KEY \(([^)]*)\)", body)
    assert pk is not None, "features.values n'a pas de clé primaire explicite"
    assert "as_of_ts" in pk.group(1)


def test_ratings_carry_their_computation_time() -> None:
    """Fuite n°3 : des ratings ré-estimés sur toute la saison et utilisés pour
    prédire la journée 5. `computed_at <= as_of_ts` doit être vérifiable."""
    body = _table_body("features.ratings_snapshots")
    assert "computed_at" in body
    assert "valid_from" in body


def test_odds_snapshots_carry_their_capture_time() -> None:
    body = _table_body("market.odds_snapshots")
    assert "captured_at" in body
    assert "is_closing" in body


def test_lineups_carry_their_publication_time() -> None:
    """Fuite n°6 : utiliser une composition officielle pour une prédiction
    horodatée avant sa publication."""
    body = _table_body("core.lineups")
    assert "published_at" in body


def test_weather_stores_forecasts_not_only_observations() -> None:
    """Fuite n°11 : utiliser la météo observée plutôt que la prévision."""
    body = _table_body("core.weather_observations")
    assert "'forecast'" in body
    assert "horizon_hours" in body
    assert "fetched_at" in body


def test_raw_observations_record_availability_time() -> None:
    """`fetched_at` est l'instant de disponibilité — le pivot de tout
    l'anti-look-ahead (ADR-0001)."""
    body = _table_body("raw.observations")
    assert "fetched_at" in body


def test_raw_layer_is_protected_against_rewriting() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    assert "REVOKE UPDATE, DELETE ON raw.observations" in sql


def test_predictions_store_the_feature_hash() -> None:
    """Sans le hash, on ne peut pas détecter qu'un fournisseur a révisé son
    historique sous une prédiction déjà produite."""
    body = _table_body("ml.predictions")
    assert "feature_hash" in body
    assert "as_of_ts" in body
