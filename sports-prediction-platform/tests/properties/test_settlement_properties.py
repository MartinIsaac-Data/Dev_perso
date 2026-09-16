"""Invariants du dénouement, vérifiés par génération.

Les formules financières ont des invariants clairs, et c'est exactement là
qu'une erreur de signe passe inaperçue à la relecture (docs/12 §7).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from spp.core.entities import MatchResult
from spp.core.enums import BetStatus, MarketCode, Side
from spp.core.settlement import settle

scores = st.integers(min_value=0, max_value=9)
odds = st.floats(min_value=1.01, max_value=50.0, allow_nan=False, allow_infinity=False)
whole_or_half_lines = st.sampled_from([x / 2 for x in range(0, 13)])
asian_lines = st.sampled_from([x / 4 for x in range(-12, 13)])


@given(h=scores, a=scores, o=odds)
def test_1x2_is_exhaustive_and_exclusive(h: int, a: int, o: float) -> None:
    """Exactement une des trois issues gagne, toujours."""
    result = MatchResult(1, h, a)
    won = [
        s
        for s in (Side.HOME, Side.DRAW, Side.AWAY)
        if settle(MarketCode.ONE_X_TWO, s, result, odds=o).status is BetStatus.WON
    ]
    assert len(won) == 1


@given(h=scores, a=scores, o=odds, line=whole_or_half_lines)
def test_over_and_under_are_complementary(h: int, a: int, o: float, line: float) -> None:
    """Over et Under se remboursent ensemble, ou l'un gagne et l'autre perd."""
    result = MatchResult(1, h, a)
    over = settle(MarketCode.OVER_UNDER, Side.OVER, result, odds=o, line=line)
    under = settle(MarketCode.OVER_UNDER, Side.UNDER, result, odds=o, line=line)

    if over.status is BetStatus.VOID:
        assert under.status is BetStatus.VOID
    else:
        assert {over.status, under.status} == {BetStatus.WON, BetStatus.LOST}


@given(h=scores, a=scores, line=asian_lines)
def test_asian_handicap_is_zero_sum_at_even_odds(h: int, a: int, line: float) -> None:
    """À cote 2.00, parier une unité sur chaque côté d'un handicap asiatique
    restitue exactement les deux unités misées — quelle que soit la ligne.

    C'est la signature d'un handicap correctement réglé : victoire/défaite
    (2 + 0), remboursement des deux côtés (1 + 1) et demi-gain/demi-perte
    (1.5 + 0.5) satisfont tous l'égalité. Toute erreur sur la décomposition
    des lignes en quarts la casse immédiatement.
    """
    result = MatchResult(1, h, a)
    home = settle(MarketCode.ASIAN_HANDICAP, Side.HOME, result, odds=2.0, line=line)
    away = settle(MarketCode.ASIAN_HANDICAP, Side.AWAY, result, odds=2.0, line=-line)
    assert home.return_multiplier + away.return_multiplier == pytest.approx(2.0)


@given(h=scores, a=scores, line=asian_lines)
def test_over_under_is_zero_sum_at_even_odds(h: int, a: int, line: float) -> None:
    """Même invariant sur les totaux, lignes en quarts comprises."""
    result = MatchResult(1, h, max(a, 0))
    over = settle(MarketCode.OVER_UNDER, Side.OVER, result, odds=2.0, line=abs(line))
    under = settle(MarketCode.OVER_UNDER, Side.UNDER, result, odds=2.0, line=abs(line))
    assert over.return_multiplier + under.return_multiplier == pytest.approx(2.0)


@given(h=scores, a=scores, o=odds, line=asian_lines, stake=st.floats(1.0, 10_000.0))
def test_return_multiplier_is_bounded(h: int, a: int, o: float, line: float, stake: float) -> None:
    """Un pari ne peut jamais rapporter plus que la cote ni moins que zéro."""
    s = settle(MarketCode.ASIAN_HANDICAP, Side.HOME, MatchResult(1, h, a), odds=o, line=line)
    assert 0.0 <= s.return_multiplier <= o
    # Tolérance flottante : stake*mult - stake et stake*(o-1) ne s'arrondissent
    # pas identiquement, bien qu'algébriquement égaux à la borne.
    assert s.profit(stake) >= -stake - 1e-9
    assert s.profit(stake) <= stake * (o - 1) + 1e-9


@given(h=scores, a=scores, o=odds)
def test_btts_is_complementary(h: int, a: int, o: float) -> None:
    result = MatchResult(1, h, a)
    yes = settle(MarketCode.BTTS, Side.YES, result, odds=o)
    no = settle(MarketCode.BTTS, Side.NO, result, odds=o)
    assert {yes.status, no.status} == {BetStatus.WON, BetStatus.LOST}


@given(h=scores, a=scores, o=odds)
def test_double_chance_covers_exactly_two_of_three(h: int, a: int, o: float) -> None:
    """Sur trois doubles chances, exactement deux gagnent."""
    result = MatchResult(1, h, a)
    won = [
        s
        for s in (Side.HOME_DRAW, Side.HOME_AWAY, Side.DRAW_AWAY)
        if settle(MarketCode.DOUBLE_CHANCE, s, result, odds=o).status is BetStatus.WON
    ]
    assert len(won) == 2
