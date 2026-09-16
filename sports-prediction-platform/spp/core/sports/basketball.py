"""Basketball : normale sur le différentiel, pas de nul, pace déterminant."""

from __future__ import annotations

from dataclasses import dataclass

from spp.core.enums import MarketCode, SportCode
from spp.core.sports.base import register


@dataclass(frozen=True, slots=True)
class BasketballAdapter:
    sport: SportCode = SportCode.BASKETBALL
    allows_draw: bool = False
    score_model: str = "normal_diff"

    def supported_markets(self) -> frozenset[MarketCode]:
        return frozenset({MarketCode.ONE_X_TWO, MarketCode.OVER_UNDER, MarketCode.ASIAN_HANDICAP})

    def outcome_space(self, market: MarketCode) -> tuple[str, ...]:
        match market:
            case MarketCode.ONE_X_TWO:
                return ("H", "A")  # la prolongation supprime le nul
            case MarketCode.OVER_UNDER:
                return ("OVER", "UNDER")
            case MarketCode.ASIAN_HANDICAP:
                return ("H", "A")
            case _:
                raise KeyError(f"Marché {market} non exposé par le basketball")

    def default_half_life_days(self) -> float:
        return 35.0


BASKETBALL = register(BasketballAdapter())
