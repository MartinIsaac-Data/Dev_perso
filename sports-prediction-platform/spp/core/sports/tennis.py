"""Tennis : chaîne de Markov sur le point servi, compétiteurs individuels."""

from __future__ import annotations

from dataclasses import dataclass

from spp.core.enums import MarketCode, SportCode
from spp.core.sports.base import register


@dataclass(frozen=True, slots=True)
class TennisAdapter:
    sport: SportCode = SportCode.TENNIS
    allows_draw: bool = False
    score_model: str = "markov_point"

    def supported_markets(self) -> frozenset[MarketCode]:
        return frozenset({MarketCode.ONE_X_TWO, MarketCode.OVER_UNDER, MarketCode.ASIAN_HANDICAP})

    def outcome_space(self, market: MarketCode) -> tuple[str, ...]:
        match market:
            case MarketCode.ONE_X_TWO:
                return ("H", "A")
            case MarketCode.OVER_UNDER:
                return ("OVER", "UNDER")  # total de jeux
            case MarketCode.ASIAN_HANDICAP:
                return ("H", "A")  # handicap de jeux
            case _:
                raise KeyError(f"Marché {market} non exposé par le tennis")

    def default_half_life_days(self) -> float:
        return 120.0


TENNIS = register(TennisAdapter())
