"""Empreintes déterministes.

``feature_hash`` est le détecteur de révision rétroactive : si le recalcul
d'une prédiction passée produit un hash différent, un fournisseur a modifié
son historique (docs/03 §7, docs/07 §2).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    """Sérialisation canonique : clés triées, séparateurs fixes, UTF-8."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_of(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def feature_hash(features: dict[str, Any], *, precision: int = 6) -> str:
    """Empreinte d'un vecteur de features.

    Les flottants sont arrondis avant hachage : sans cela, une différence au
    quinzième chiffre décimal — due à l'ordre des sommations — produirait une
    fausse alerte de révision.
    """
    rounded: dict[str, Any] = {}
    for key, value in features.items():
        rounded[key] = round(value, precision) if isinstance(value, float) else value
    return sha256_of(rounded)
