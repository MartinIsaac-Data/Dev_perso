from __future__ import annotations

import pytest
from spp.core.enums import MarketCode, SportCode
from spp.core.sports import SportAdapter, get_adapter, registered_sports


def test_three_sports_registered() -> None:
    assert set(registered_sports()) == {
        SportCode.FOOTBALL,
        SportCode.BASKETBALL,
        SportCode.TENNIS,
    }


@pytest.mark.parametrize("sport", list(SportCode))
def test_every_adapter_satisfies_the_protocol(sport: SportCode) -> None:
    assert isinstance(get_adapter(sport), SportAdapter)


def test_only_football_allows_a_draw() -> None:
    assert get_adapter(SportCode.FOOTBALL).allows_draw is True
    assert get_adapter(SportCode.BASKETBALL).allows_draw is False
    assert get_adapter(SportCode.TENNIS).allows_draw is False


def test_draw_absence_is_reflected_in_the_outcome_space() -> None:
    assert get_adapter(SportCode.BASKETBALL).outcome_space(MarketCode.ONE_X_TWO) == (
        "H",
        "A",
    )
    assert get_adapter(SportCode.FOOTBALL).outcome_space(MarketCode.ONE_X_TWO) == (
        "H",
        "D",
        "A",
    )


def test_unknown_sport_raises() -> None:
    with pytest.raises(ValueError, match="hockey"):
        get_adapter("hockey")


def test_unsupported_market_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter(SportCode.TENNIS).outcome_space(MarketCode.BTTS)
