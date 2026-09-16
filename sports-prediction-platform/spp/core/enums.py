"""Énumérations du domaine.

Elles reflètent exactement les contraintes ``CHECK`` de ``sql/schema.sql`` :
toute divergence entre les deux est un bug.
"""

from __future__ import annotations

from enum import StrEnum


class SportCode(StrEnum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    TENNIS = "tennis"


class CompetitorKind(StrEnum):
    TEAM = "team"
    INDIVIDUAL = "individual"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    WALKOVER = "walkover"

    @property
    def is_usable_for_training(self) -> bool:
        """Un match reporté n'est pas un nul : il sort du jeu de données."""
        return self is MatchStatus.FINISHED


class Outcome1X2(StrEnum):
    HOME = "H"
    DRAW = "D"
    AWAY = "A"


class MarketCode(StrEnum):
    ONE_X_TWO = "1X2"
    DOUBLE_CHANCE = "DC"
    OVER_UNDER = "OU"
    ASIAN_HANDICAP = "AH"
    BTTS = "BTTS"
    CORRECT_SCORE = "CS"


class Side(StrEnum):
    HOME = "H"
    DRAW = "D"
    AWAY = "A"
    HOME_DRAW = "1X"
    HOME_AWAY = "12"
    DRAW_AWAY = "X2"
    OVER = "OVER"
    UNDER = "UNDER"
    YES = "YES"
    NO = "NO"


class BetStatus(StrEnum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    HALF_WON = "half_won"
    HALF_LOST = "half_lost"
    CASHED_OUT = "cashed_out"


class LineupSource(StrEnum):
    PREDICTED = "predicted"
    OFFICIAL = "official"


class LeakageClass(StrEnum):
    """Classe de fuite d'une feature — voir docs/03 §1."""

    SAFE = "safe"
    NEEDS_LAG = "needs_lag"
    FORBIDDEN = "forbidden"


class RunMode(StrEnum):
    """Mode d'exécution — voir docs/01 §6."""

    LIVE = "live"
    REPLAY = "replay"
    SHADOW = "shadow"
    BACKTEST = "backtest"


class DevigMethod(StrEnum):
    PROPORTIONAL = "proportional"
    ADDITIVE = "additive"
    ODDS_RATIO = "odds_ratio"
    SHIN = "shin"
    POWER = "power"
