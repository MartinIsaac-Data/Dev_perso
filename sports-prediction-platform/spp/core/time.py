"""Temps.

Règle absolue : tout horodatage manipulé par la plateforme est conscient du
fuseau et en UTC. Un ``datetime`` naïf est refusé à la frontière, parce qu'un
décalage d'une heure sur ``as_of_ts`` suffit à laisser entrer une composition
officielle dans une prédiction censée l'ignorer.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalise en UTC, en refusant les datetimes naïfs."""
    if value.tzinfo is None:
        raise ValueError(
            f"datetime naïf refusé : {value!r}. Tout horodatage doit porter "
            "son fuseau (voir docs/04 §2)."
        )
    return value.astimezone(UTC)


def days_between(earlier: datetime, later: datetime) -> float:
    """Écart en jours fractionnaires, positif si ``later`` est postérieur."""
    return (ensure_utc(later) - ensure_utc(earlier)).total_seconds() / 86400.0


def recency_weight(delta_days: float, half_life_days: float) -> float:
    """Poids de décroissance exponentielle.

    ``w = exp(-ln(2) * Δt / H)`` : un match vieux d'exactement une demi-vie
    pèse 0.5. Voir docs/02 §B.2.
    """
    if half_life_days <= 0:
        raise ValueError("half_life_days doit être strictement positif")
    if delta_days < 0:
        raise ValueError("delta_days négatif : un match futur ne pondère pas une forme")
    return math.exp(-math.log(2.0) * delta_days / half_life_days)
