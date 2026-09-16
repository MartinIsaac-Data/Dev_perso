"""Erreurs du domaine.

``InsufficientDataError`` est la plus importante : elle matérialise le refus
de produire une probabilité sur des données insuffisantes. L'API la traduit
en HTTP 422 (docs/10 §4).
"""

from __future__ import annotations


class SppError(Exception):
    """Racine de toutes les erreurs de la plateforme."""


class ConfigurationError(SppError):
    """Réglage absent ou incohérent."""


class InsufficientDataError(SppError):
    """Les données disponibles ne permettent pas de produire une prédiction."""

    def __init__(self, detail: str, *, missing: list[str], data_quality: float) -> None:
        super().__init__(detail)
        self.detail = detail
        self.missing = missing
        self.data_quality = data_quality


class LeakageError(SppError):
    """Une donnée postérieure à ``as_of_ts`` a été demandée.

    Cette erreur n'est jamais rattrapée : elle signale un défaut de conception,
    pas une condition d'exécution.
    """


class SettlementError(SppError):
    """Le dénouement d'un pari est impossible ou ambigu."""


class ProviderError(SppError):
    """Un fournisseur de données a échoué."""

    def __init__(self, provider: str, detail: str, *, retryable: bool = True) -> None:
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.retryable = retryable
