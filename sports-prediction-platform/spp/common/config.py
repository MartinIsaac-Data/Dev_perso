"""Configuration applicative.

Une seule source de vérité : les variables d'environnement, validées par
Pydantic au démarrage. Un réglage absent ou aberrant fait échouer le
démarrage plutôt que de produire un comportement silencieusement faux.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "staging", "production"]


class Settings(BaseSettings):
    """Réglages lus depuis l'environnement (préfixe ``SPP_``)."""

    model_config = SettingsConfigDict(
        env_prefix="SPP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "local"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    database_url: str = "postgresql+psycopg://spp:spp@localhost:5433/spp"
    database_pool_size: int = Field(default=5, ge=1, le=50)

    redis_url: str = "redis://localhost:6380/0"

    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_cors_origins: str = "http://localhost:3000"

    odds_api_key: str = ""
    stats_api_key: str = ""
    weather_api_base: str = "https://api.open-meteo.com/v1"

    # Garde-fous de valorisation — voir docs/06-probabilites-et-value.md
    edge_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    uncertainty_k: float = Field(default=1.0, ge=0.0, le=5.0)
    kelly_fraction: float = Field(default=0.25, gt=0.0, le=1.0)
    max_stake_pct: float = Field(default=0.02, gt=0.0, le=0.10)
    min_data_quality: float = Field(default=0.75, ge=0.0, le=1.0)

    @field_validator("kelly_fraction")
    @classmethod
    def _warn_on_full_kelly(cls, v: float) -> float:
        # Kelly complet suppose que la probabilité est exacte. Elle ne l'est
        # jamais. Voir docs/06 §6.2.
        if v > 0.5:
            raise ValueError(
                "kelly_fraction > 0.5 : Kelly quasi complet suppose une "
                "probabilité exacte. Utiliser 0.25 (recommandé) ou 0.5."
            )
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Réglages mémoïsés pour la durée du processus."""
    return Settings()
