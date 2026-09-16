"""Dénouement des paris.

Ce module est **partagé par le backtest et la production**. Deux
implémentations divergeraient sur les cas limites — handicaps en quarts,
lignes entières remboursées, matchs abandonnés — et produiraient un backtest
faussement positif (docs/14 §2.3).

Le résultat d'un dénouement est un **multiplicateur de retour** : ce que
rapporte une mise unitaire, mise comprise.

    perdu           -> 0.0
    demi-perdu      -> 0.5
    remboursé       -> 1.0
    demi-gagné      -> 1 + (cote - 1) / 2
    gagné           -> cote

Cette représentation unique gère naturellement les lignes asiatiques en
quarts, où la mise est scindée en deux moitiés réglées séparément.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from spp.common.errors import SettlementError
from spp.core.entities import MatchResult
from spp.core.enums import BetStatus, MarketCode, Side


class _Leg(Enum):
    """Issue d'une demi-mise réglée sur une ligne entière ou demie."""

    WIN = "win"
    VOID = "void"
    LOSE = "lose"


@dataclass(frozen=True, slots=True)
class Settlement:
    status: BetStatus
    return_multiplier: float
    """Retour pour une mise de 1 à la cote donnée, mise comprise."""

    def profit(self, stake: float) -> float:
        return stake * self.return_multiplier - stake


def _leg_from_margin(margin: float) -> _Leg:
    """Règle une demi-mise : marge > 0 gagne, < 0 perd, = 0 est remboursée."""
    if margin > 0:
        return _Leg.WIN
    if margin < 0:
        return _Leg.LOSE
    return _Leg.VOID


def _combine(legs: list[_Leg], odds: float) -> Settlement:
    """Combine une ou deux demi-mises en un multiplicateur de retour."""
    per_leg = 1.0 / len(legs)
    multiplier = 0.0
    for leg in legs:
        if leg is _Leg.WIN:
            multiplier += per_leg * odds
        elif leg is _Leg.VOID:
            multiplier += per_leg * 1.0
        # LOSE n'ajoute rien

    return Settlement(status=_status_for(multiplier, odds), return_multiplier=multiplier)


def _status_for(multiplier: float, odds: float) -> BetStatus:
    eps = 1e-9
    if multiplier <= eps:
        return BetStatus.LOST
    if abs(multiplier - odds) < eps:
        return BetStatus.WON
    if abs(multiplier - 1.0) < eps:
        return BetStatus.VOID
    if multiplier < 1.0:
        return BetStatus.HALF_LOST
    return BetStatus.HALF_WON


def _split_line(line: float) -> list[float]:
    """Décompose une ligne asiatique en quarts en ses deux lignes adjacentes.

    ``-0.75`` devient ``[-0.5, -1.0]`` : la mise est scindée en deux moitiés.
    Une ligne entière ou demie reste seule.
    """
    quarter = abs(line * 4) % 2
    if abs(quarter - 1.0) < 1e-9:  # ...25 ou ...75
        return [line - 0.25, line + 0.25]
    return [line]


def settle(
    market: MarketCode | str,
    side: Side | str,
    result: MatchResult,
    *,
    odds: float,
    line: float | None = None,
) -> Settlement:
    """Règle un pari à partir du résultat du match.

    Args:
        market: code du marché.
        side: issue pariée.
        result: résultat final du match.
        odds: cote décimale prise.
        line: ligne (total ou handicap), requise pour ``OU`` et ``AH``.

    Raises:
        SettlementError: marché inconnu, issue incompatible, ligne manquante.
    """
    if odds <= 1.0:
        raise SettlementError(f"Cote décimale invalide : {odds}")

    market = MarketCode(market)
    side = Side(side)

    if market is MarketCode.ONE_X_TWO:
        return _settle_1x2(side, result, odds)
    if market is MarketCode.DOUBLE_CHANCE:
        return _settle_double_chance(side, result, odds)
    if market is MarketCode.BTTS:
        return _settle_btts(side, result, odds)
    if market is MarketCode.OVER_UNDER:
        return _settle_over_under(side, result, odds, _require_line(market, line))
    if market is MarketCode.ASIAN_HANDICAP:
        return _settle_asian_handicap(side, result, odds, _require_line(market, line))

    raise SettlementError(f"Marché non pris en charge : {market}")


def _require_line(market: MarketCode, line: float | None) -> float:
    if line is None:
        raise SettlementError(f"Le marché {market} exige une ligne")
    return line


def _settle_1x2(side: Side, result: MatchResult, odds: float) -> Settlement:
    mapping = {Side.HOME: "H", Side.DRAW: "D", Side.AWAY: "A"}
    if side not in mapping:
        raise SettlementError(f"Issue {side} incompatible avec le marché 1X2")
    won = result.outcome_1x2.value == mapping[side]
    return _combine([_Leg.WIN if won else _Leg.LOSE], odds)


def _settle_double_chance(side: Side, result: MatchResult, odds: float) -> Settlement:
    covered = {
        Side.HOME_DRAW: {"H", "D"},
        Side.HOME_AWAY: {"H", "A"},
        Side.DRAW_AWAY: {"D", "A"},
    }
    if side not in covered:
        raise SettlementError(f"Issue {side} incompatible avec la double chance")
    won = result.outcome_1x2.value in covered[side]
    return _combine([_Leg.WIN if won else _Leg.LOSE], odds)


def _settle_btts(side: Side, result: MatchResult, odds: float) -> Settlement:
    if side not in (Side.YES, Side.NO):
        raise SettlementError(f"Issue {side} incompatible avec BTTS")
    won = result.both_teams_scored if side is Side.YES else not result.both_teams_scored
    return _combine([_Leg.WIN if won else _Leg.LOSE], odds)


def _settle_over_under(side: Side, result: MatchResult, odds: float, line: float) -> Settlement:
    if side not in (Side.OVER, Side.UNDER):
        raise SettlementError(f"Issue {side} incompatible avec un total")

    legs: list[_Leg] = []
    for sub_line in _split_line(line):
        margin = result.total - sub_line
        if side is Side.UNDER:
            margin = -margin
        legs.append(_leg_from_margin(margin))
    return _combine(legs, odds)


def _settle_asian_handicap(side: Side, result: MatchResult, odds: float, line: float) -> Settlement:
    """Handicap asiatique.

    ``line`` s'applique **à l'équipe pariée**. Un pari sur l'équipe à domicile
    avec ``line = -0.5`` gagne si elle l'emporte par au moins un but.
    """
    if side not in (Side.HOME, Side.AWAY):
        raise SettlementError(f"Issue {side} incompatible avec un handicap asiatique")

    raw_margin = result.margin if side is Side.HOME else -result.margin
    legs = [_leg_from_margin(raw_margin + sub_line) for sub_line in _split_line(line)]
    return _combine(legs, odds)
