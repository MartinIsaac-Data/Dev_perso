from __future__ import annotations

from datetime import UTC, datetime

import pytest
from spp.core.entities import Competitor, Match, MatchResult
from spp.core.enums import CompetitorKind, SportCode


@pytest.fixture
def home_team() -> Competitor:
    return Competitor(1, SportCode.FOOTBALL, CompetitorKind.TEAM, "FC Nantes", "NAN")


@pytest.fixture
def away_team() -> Competitor:
    return Competitor(2, SportCode.FOOTBALL, CompetitorKind.TEAM, "Stade Rennais", "REN")


@pytest.fixture
def match(home_team: Competitor, away_team: Competitor) -> Match:
    return Match(
        match_id=884213,
        sport=SportCode.FOOTBALL,
        competition_id=12,
        season_id=7,
        kickoff_utc=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
        home=home_team,
        away=away_team,
    )


@pytest.fixture
def result_2_1() -> MatchResult:
    return MatchResult(match_id=884213, home_score=2, away_score=1)
