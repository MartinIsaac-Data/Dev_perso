"""Frontière multi-sport.

Ajouter un sport consiste à écrire un adaptateur et une table de statistiques.
Le noyau — matchs, cotes, ratings, calibration, backtest — ne bouge pas
(docs/01 §2).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from spp.core.enums import MarketCode, SportCode


@runtime_checkable
class SportAdapter(Protocol):
    """Ce qu'un sport doit fournir pour entrer dans la plateforme.

    Les trois caractéristiques sont déclarées en lecture seule : un adaptateur
    est une constante du domaine, pas un objet configurable à l'exécution.
    Déclarées comme attributs mutables, elles interdiraient aux adaptateurs
    d'être des dataclasses gelées.
    """

    @property
    def sport(self) -> SportCode: ...

    @property
    def allows_draw(self) -> bool: ...

    @property
    def score_model(self) -> str: ...

    def supported_markets(self) -> frozenset[MarketCode]:
        """Marchés que ce sport expose."""
        ...

    def outcome_space(self, market: MarketCode) -> tuple[str, ...]:
        """Issues possibles d'un marché."""
        ...

    def default_half_life_days(self) -> float:
        """Demi-vie de la pondération par récence (docs/02 §B.2)."""
        ...


_REGISTRY: dict[SportCode, SportAdapter] = {}


def register(adapter: SportAdapter) -> SportAdapter:
    _REGISTRY[adapter.sport] = adapter
    return adapter


def get_adapter(sport: SportCode | str) -> SportAdapter:
    key = SportCode(sport)
    if key not in _REGISTRY:
        raise KeyError(f"Aucun adaptateur enregistré pour le sport {key}")
    return _REGISTRY[key]


def registered_sports() -> tuple[SportCode, ...]:
    return tuple(sorted(_REGISTRY, key=lambda s: s.value))
