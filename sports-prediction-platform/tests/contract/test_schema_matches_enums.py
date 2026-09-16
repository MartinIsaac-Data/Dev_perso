"""Le schéma SQL et les énumérations Python doivent dire la même chose.

Une divergence entre une contrainte CHECK et une StrEnum produit une erreur
d'insertion en production et une fausse réussite en test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from spp.core.enums import BetStatus, LineupSource, MatchStatus

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def _table_body(table: str) -> str:
    """Isole le corps d'un CREATE TABLE.

    Plusieurs tables portent une colonne `status` avec des valeurs autorisées
    différentes : chercher la première occurrence dans tout le fichier compare
    les mauvaises listes.
    """
    sql = SCHEMA.read_text(encoding="utf-8")
    start = sql.find(f"CREATE TABLE {table} (")
    if start == -1:
        pytest.fail(f"Table introuvable dans le schéma : {table}")
    end = sql.find("\n);", start)
    return sql[start:end]


def _check_values(table: str, column: str) -> set[str]:
    """Valeurs autorisées par une contrainte CHECK ... IN (...) d'une table."""
    body = _table_body(table)
    pattern = rf"{column}\s+\w+[^,]*?CHECK\s*\({column}\s+IN\s*\(([^)]*)\)"
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if match is None:
        pytest.fail(f"Contrainte CHECK introuvable pour {table}.{column}")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_schema_file_exists() -> None:
    assert SCHEMA.exists(), f"Schéma SQL introuvable : {SCHEMA}"


def test_match_status_matches_schema() -> None:
    assert _check_values("core.matches", "status") == {s.value for s in MatchStatus}


def test_bet_status_matches_schema() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    for status in BetStatus:
        if status is BetStatus.OPEN:
            continue
        assert f"'{status.value}'" in sql, f"{status.value} absent du schéma SQL"


def test_lineup_source_matches_schema() -> None:
    assert _check_values("core.lineups", "source") == {s.value for s in LineupSource}
