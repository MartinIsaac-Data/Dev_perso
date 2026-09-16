from __future__ import annotations

from datetime import UTC, datetime

import pytest
from spp.core.entities import Competitor, Match, MatchResult, OddsQuote, Selection
from spp.core.enums import CompetitorKind, Outcome1X2, SportCode


def test_outcome_is_derived_not_stored(result_2_1: MatchResult) -> None:
    assert result_2_1.outcome_1x2 is Outcome1X2.HOME
    assert result_2_1.margin == 1
    assert result_2_1.total == 3
    assert result_2_1.both_teams_scored is True


@pytest.mark.parametrize(
    ("home", "away", "expected"),
    [(2, 1, Outcome1X2.HOME), (1, 1, Outcome1X2.DRAW), (0, 3, Outcome1X2.AWAY)],
)
def test_outcome_mapping(home: int, away: int, expected: Outcome1X2) -> None:
    assert MatchResult(1, home, away).outcome_1x2 is expected


def test_negative_score_is_rejected() -> None:
    with pytest.raises(ValueError, match="négatif"):
        MatchResult(1, -1, 0)


def test_naive_kickoff_is_rejected(home_team: Competitor, away_team: Competitor) -> None:
    with pytest.raises(ValueError, match="naïf"):
        Match(
            match_id=1,
            sport=SportCode.FOOTBALL,
            competition_id=1,
            season_id=1,
            kickoff_utc=datetime(2026, 9, 20, 18, 0),  # noqa: DTZ001 - volontaire
            home=home_team,
            away=away_team,
        )


def test_team_cannot_play_itself(home_team: Competitor) -> None:
    with pytest.raises(ValueError, match="elle-même"):
        Match(
            match_id=1,
            sport=SportCode.FOOTBALL,
            competition_id=1,
            season_id=1,
            kickoff_utc=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
            home=home_team,
            away=home_team,
        )


def test_match_is_known_before_kickoff(match: Match) -> None:
    assert match.is_known_at(datetime(2026, 9, 20, 17, 0, tzinfo=UTC)) is True
    assert match.is_known_at(datetime(2026, 9, 20, 19, 0, tzinfo=UTC)) is False


def test_odds_must_exceed_one() -> None:
    sel = Selection(match_id=1, market="1X2", side="H")
    with pytest.raises(ValueError, match="invalide"):
        OddsQuote(sel, "pinnacle", 1.0, datetime(2026, 9, 20, tzinfo=UTC))


def test_raw_implied_probability_is_not_a_probability() -> None:
    sel = Selection(match_id=1, market="1X2", side="H")
    quote = OddsQuote(sel, "bet365", 2.10, datetime(2026, 9, 20, tzinfo=UTC))
    assert quote.implied_probability_raw == pytest.approx(0.47619, abs=1e-5)


def test_competitor_kind_individual_is_supported() -> None:
    player = Competitor(9, SportCode.TENNIS, CompetitorKind.INDIVIDUAL, "Joueur A")
    assert player.kind is CompetitorKind.INDIVIDUAL
