"""Dénouement : les cas nominaux et surtout les cas limites.

Les handicaps en quarts et les lignes entières remboursées sont exactement les
endroits où une implémentation dupliquée diverge (docs/14 §2.3).
"""

from __future__ import annotations

import pytest
from spp.common.errors import SettlementError
from spp.core.entities import MatchResult
from spp.core.enums import BetStatus, MarketCode, Side
from spp.core.settlement import settle

R21 = MatchResult(1, 2, 1)  # total 3, marge +1
R11 = MatchResult(1, 1, 1)  # total 2, marge  0
R30 = MatchResult(1, 3, 0)  # total 3, marge +3
R02 = MatchResult(1, 0, 2)  # total 2, marge -2


# --------------------------------------------------------------------------
#  1X2 et double chance
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("side", "result", "status"),
    [
        (Side.HOME, R21, BetStatus.WON),
        (Side.DRAW, R21, BetStatus.LOST),
        (Side.AWAY, R21, BetStatus.LOST),
        (Side.DRAW, R11, BetStatus.WON),
        (Side.AWAY, R02, BetStatus.WON),
    ],
)
def test_1x2(side: Side, result: MatchResult, status: BetStatus) -> None:
    assert settle(MarketCode.ONE_X_TWO, side, result, odds=2.10).status is status


def test_1x2_won_returns_the_odds() -> None:
    s = settle(MarketCode.ONE_X_TWO, Side.HOME, R21, odds=2.10)
    assert s.return_multiplier == pytest.approx(2.10)
    assert s.profit(100.0) == pytest.approx(110.0)


def test_1x2_lost_returns_nothing() -> None:
    s = settle(MarketCode.ONE_X_TWO, Side.AWAY, R21, odds=3.60)
    assert s.return_multiplier == 0.0
    assert s.profit(100.0) == pytest.approx(-100.0)


@pytest.mark.parametrize(
    ("side", "result", "status"),
    [
        (Side.HOME_DRAW, R21, BetStatus.WON),
        (Side.HOME_DRAW, R02, BetStatus.LOST),
        (Side.DRAW_AWAY, R11, BetStatus.WON),
        (Side.HOME_AWAY, R11, BetStatus.LOST),
    ],
)
def test_double_chance(side: Side, result: MatchResult, status: BetStatus) -> None:
    assert settle(MarketCode.DOUBLE_CHANCE, side, result, odds=1.30).status is status


# --------------------------------------------------------------------------
#  BTTS
# --------------------------------------------------------------------------
def test_btts() -> None:
    assert settle(MarketCode.BTTS, Side.YES, R21, odds=1.85).status is BetStatus.WON
    assert settle(MarketCode.BTTS, Side.NO, R21, odds=1.95).status is BetStatus.LOST
    assert settle(MarketCode.BTTS, Side.NO, R30, odds=1.95).status is BetStatus.WON


# --------------------------------------------------------------------------
#  Totaux, y compris la ligne entière remboursée
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("side", "line", "result", "status"),
    [
        (Side.OVER, 2.5, R21, BetStatus.WON),
        (Side.UNDER, 2.5, R21, BetStatus.LOST),
        (Side.OVER, 3.5, R21, BetStatus.LOST),
        (Side.UNDER, 2.5, R11, BetStatus.WON),
        # ligne entière atteinte exactement : remboursement
        (Side.OVER, 3.0, R21, BetStatus.VOID),
        (Side.UNDER, 3.0, R21, BetStatus.VOID),
        (Side.OVER, 2.0, R11, BetStatus.VOID),
    ],
)
def test_over_under(side: Side, line: float, result: MatchResult, status: BetStatus) -> None:
    assert settle(MarketCode.OVER_UNDER, side, result, odds=1.92, line=line).status is status


def test_void_total_returns_the_stake_exactly() -> None:
    s = settle(MarketCode.OVER_UNDER, Side.OVER, R21, odds=1.92, line=3.0)
    assert s.return_multiplier == pytest.approx(1.0)
    assert s.profit(100.0) == pytest.approx(0.0)


def test_quarter_total_can_be_half_won() -> None:
    # Total 3, ligne 2.75 -> moitiés sur 2.5 (gagnée) et 3.0 (remboursée)
    s = settle(MarketCode.OVER_UNDER, Side.OVER, R21, odds=2.00, line=2.75)
    assert s.status is BetStatus.HALF_WON
    assert s.return_multiplier == pytest.approx(1.5)


def test_quarter_total_can_be_half_lost() -> None:
    # Total 3, ligne 3.25 côté OVER -> moitiés sur 3.0 (remboursée) et 3.5 (perdue)
    s = settle(MarketCode.OVER_UNDER, Side.OVER, R21, odds=2.00, line=3.25)
    assert s.status is BetStatus.HALF_LOST
    assert s.return_multiplier == pytest.approx(0.5)


# --------------------------------------------------------------------------
#  Handicap asiatique — le cas qui casse les implémentations naïves
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("side", "line", "result", "status"),
    [
        (Side.HOME, -0.5, R21, BetStatus.WON),  # gagne par 1 > 0.5
        (Side.HOME, -1.0, R21, BetStatus.VOID),  # gagne par exactement 1
        (Side.HOME, -1.5, R21, BetStatus.LOST),
        (Side.AWAY, +1.0, R21, BetStatus.VOID),
        (Side.AWAY, +1.5, R21, BetStatus.WON),
        (Side.HOME, -2.5, R30, BetStatus.WON),
        (Side.HOME, 0.0, R11, BetStatus.VOID),  # nul, handicap nul
    ],
)
def test_asian_handicap(side: Side, line: float, result: MatchResult, status: BetStatus) -> None:
    got = settle(MarketCode.ASIAN_HANDICAP, side, result, odds=1.95, line=line)
    assert got.status is status


def test_quarter_handicap_half_won() -> None:
    # -0.75 -> moitiés sur -0.5 (gagnée) et -1.0 (remboursée), victoire par 1
    s = settle(MarketCode.ASIAN_HANDICAP, Side.HOME, R21, odds=2.00, line=-0.75)
    assert s.status is BetStatus.HALF_WON
    assert s.return_multiplier == pytest.approx(1.5)


def test_quarter_handicap_half_lost() -> None:
    # -1.25 -> moitiés sur -1.0 (remboursée) et -1.5 (perdue), victoire par 1
    s = settle(MarketCode.ASIAN_HANDICAP, Side.HOME, R21, odds=2.00, line=-1.25)
    assert s.status is BetStatus.HALF_LOST
    assert s.return_multiplier == pytest.approx(0.5)


def test_quarter_handicap_fully_won_when_both_halves_win() -> None:
    s = settle(MarketCode.ASIAN_HANDICAP, Side.HOME, R30, odds=2.00, line=-0.75)
    assert s.status is BetStatus.WON
    assert s.return_multiplier == pytest.approx(2.00)


# --------------------------------------------------------------------------
#  Erreurs
# --------------------------------------------------------------------------
def test_missing_line_is_an_error() -> None:
    with pytest.raises(SettlementError, match="ligne"):
        settle(MarketCode.OVER_UNDER, Side.OVER, R21, odds=1.92)


def test_incompatible_side_is_an_error() -> None:
    with pytest.raises(SettlementError, match="incompatible"):
        settle(MarketCode.ONE_X_TWO, Side.OVER, R21, odds=1.92)


def test_invalid_odds_is_an_error() -> None:
    with pytest.raises(SettlementError, match="invalide"):
        settle(MarketCode.ONE_X_TWO, Side.HOME, R21, odds=1.0)


def test_unsupported_market_is_an_error() -> None:
    with pytest.raises(SettlementError, match="non pris en charge"):
        settle(MarketCode.CORRECT_SCORE, Side.HOME, R21, odds=8.0)
