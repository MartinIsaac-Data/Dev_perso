"""Football : Poisson bivarié corrigé Dixon-Coles, nul possible."""

from __future__ import annotations

from dataclasses import dataclass

from spp.core.enums import MarketCode, SportCode
from spp.core.sports.base import register


@dataclass(frozen=True, slots=True)
class FootballAdapter:
    sport: SportCode = SportCode.FOOTBALL
    allows_draw: bool = True
    score_model: str = "bivariate_poisson"

    def supported_markets(self) -> frozenset[MarketCode]:
        return frozenset(
            {
                MarketCode.ONE_X_TWO,
                MarketCode.DOUBLE_CHANCE,
                MarketCode.OVER_UNDER,
                MarketCode.ASIAN_HANDICAP,
                MarketCode.BTTS,
                MarketCode.CORRECT_SCORE,
            }
        )

    def outcome_space(self, market: MarketCode) -> tuple[str, ...]:
        match market:
            case MarketCode.ONE_X_TWO:
                return ("H", "D", "A")
            case MarketCode.DOUBLE_CHANCE:
                return ("1X", "12", "X2")
            case MarketCode.OVER_UNDER:
                return ("OVER", "UNDER")
            case MarketCode.ASIAN_HANDICAP:
                return ("H", "A")
            case MarketCode.BTTS:
                return ("YES", "NO")
            case _:
                raise KeyError(f"Marché {market} non exposé par le football")

    def default_half_life_days(self) -> float:
        return 90.0


FOOTBALL = register(FootballAdapter())
