"""Entités du domaine.

Immuables et sans dépendance à l'infrastructure : elles ne savent ni comment
elles sont stockées, ni comment elles sont exposées.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from spp.core.enums import CompetitorKind, MatchStatus, Outcome1X2, SportCode
from spp.core.time import ensure_utc


@dataclass(frozen=True, slots=True)
class Competitor:
    """Une équipe ou un joueur individuel.

    Le noyau ne distingue pas les deux : un match de tennis est un match entre
    deux compétiteurs de type ``INDIVIDUAL``.
    """

    competitor_id: int
    sport: SportCode
    kind: CompetitorKind
    name: str
    short_name: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    match_id: int
    sport: SportCode
    competition_id: int
    season_id: int
    kickoff_utc: datetime
    home: Competitor
    away: Competitor
    status: MatchStatus = MatchStatus.SCHEDULED
    venue_id: int | None = None
    is_neutral_venue: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", ensure_utc(self.kickoff_utc))
        if self.home.competitor_id == self.away.competitor_id:
            raise ValueError("Une équipe ne peut pas se rencontrer elle-même")

    def is_known_at(self, as_of: datetime) -> bool:
        """Le match est-il encore à venir à l'instant donné ?"""
        return ensure_utc(as_of) < self.kickoff_utc


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Résultat final. Les scores de période sont portés séparément."""

    match_id: int
    home_score: int
    away_score: int
    went_extra_time: bool = False
    went_penalties: bool = False

    def __post_init__(self) -> None:
        if self.home_score < 0 or self.away_score < 0:
            raise ValueError("Un score ne peut pas être négatif")

    @property
    def total(self) -> int:
        return self.home_score + self.away_score

    @property
    def margin(self) -> int:
        """Différence de buts du point de vue de l'équipe à domicile."""
        return self.home_score - self.away_score

    @property
    def outcome_1x2(self) -> Outcome1X2:
        if self.margin > 0:
            return Outcome1X2.HOME
        if self.margin < 0:
            return Outcome1X2.AWAY
        return Outcome1X2.DRAW

    @property
    def both_teams_scored(self) -> bool:
        return self.home_score > 0 and self.away_score > 0


@dataclass(frozen=True, slots=True)
class Selection:
    """Une issue pariable d'un marché, pour un match donné."""

    match_id: int
    market: str
    side: str
    line: float | None = None
    period: str = "FT"


@dataclass(frozen=True, slots=True)
class OddsQuote:
    selection: Selection
    bookmaker: str
    odds: float
    captured_at: datetime
    max_stake: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", ensure_utc(self.captured_at))
        if self.odds <= 1.0:
            raise ValueError(f"Cote décimale invalide : {self.odds}")

    @property
    def implied_probability_raw(self) -> float:
        """Probabilité implicite **brute**, marge comprise.

        Ce n'est pas une probabilité : voir docs/06 §1.
        """
        return 1.0 / self.odds
