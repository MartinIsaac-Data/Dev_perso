"""Application settings.

Validated at import time so a missing or incoherent value fails the process at
startup rather than on the first request (Architecture.md §7.4).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MINDFLOW_",
        extra="ignore",
    )

    # -- Runtime -----------------------------------------------------------
    env: Literal["local", "test", "staging", "prod"] = "local"
    debug: bool = False
    version: str = "0.1.0"
    api_prefix: str = "/v1"

    # -- Data --------------------------------------------------------------
    # Typed as `str` rather than PostgresDsn: the URL is handed to SQLAlchemy,
    # which does its own parsing, and a validated-URL type forces a `str()`
    # conversion at every call site for no added safety. The scheme check below
    # keeps the useful part of the validation.
    database_url: str = "postgresql+asyncpg://postgres@localhost:5432/mindflow"
    database_pool_size: int = 10
    database_max_overflow: int = 5
    redis_url: str = "redis://localhost:6379/0"

    # -- Auth (Supabase) ---------------------------------------------------
    # Supabase issues either HS256 tokens signed with the project JWT secret
    # (legacy) or asymmetric tokens verified through JWKS. Both are supported;
    # exactly one must be configured outside the local/test environments.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwks_url: str = ""
    supabase_service_key: str = ""
    jwt_audience: str = "authenticated"
    jwt_leeway_seconds: int = 10

    # -- Storage -----------------------------------------------------------
    storage_backend: Literal["supabase", "local"] = "local"
    storage_bucket: str = "captures"
    storage_local_root: str = "/var/lib/mindflow/objects"
    storage_signed_url_ttl_seconds: int = 300
    storage_max_audio_bytes: int = 100 * 1024 * 1024

    # -- Speech to text ----------------------------------------------------
    stt_backend: Literal["faster_whisper", "openai", "fake"] = "fake"
    stt_model: str = "large-v3"
    stt_device: str = "auto"
    stt_compute_type: str = "int8_float16"
    stt_timeout_seconds: float = 300.0

    # -- LLM ---------------------------------------------------------------
    llm_backend: Literal["openai", "anthropic", "fake"] = "fake"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 4000

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    # -- Pipeline ----------------------------------------------------------
    # A capture longer than this is rejected at declaration time; the plan's own
    # limit is applied on top of it (Database.md, plan.max_capture_duration_ms).
    max_capture_duration_ms: int = 60 * 60 * 1000
    pipeline_max_retries: int = 5
    queue_backend: Literal["arq", "inline"] = "arq"

    # -- Observability -----------------------------------------------------
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "console"] = "json"

    @field_validator("database_url")
    @classmethod
    def _check_database_scheme(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError("database_url must be a postgresql:// URL")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_scheme(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("redis_url must be a redis:// URL")
        return value

    @property
    def sync_database_url(self) -> str:
        """Alembic runs synchronously; strip the asyncpg driver."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def is_production_like(self) -> bool:
        return self.env in ("staging", "prod")

    @model_validator(mode="after")
    def _check_production_requirements(self) -> Settings:
        if not self.is_production_like:
            return self

        missing: list[str] = []
        if not (self.supabase_jwt_secret or self.supabase_jwks_url):
            missing.append("supabase_jwt_secret or supabase_jwks_url")
        if self.storage_backend == "supabase" and not self.supabase_service_key:
            missing.append("supabase_service_key")
        if self.stt_backend == "fake":
            missing.append("stt_backend (must not be 'fake')")
        if self.llm_backend == "fake":
            missing.append("llm_backend (must not be 'fake')")
        if self.llm_backend == "openai" and not self.openai_api_key:
            missing.append("openai_api_key")
        if self.llm_backend == "anthropic" and not self.anthropic_api_key:
            missing.append("anthropic_api_key")

        if missing:
            raise ValueError(
                f"environment '{self.env}' requires: {', '.join(missing)}. "
                "Refusing to start with an incomplete configuration."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
