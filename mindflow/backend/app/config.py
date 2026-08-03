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
    # Cross-tenant jobs (the sweeper, the outbox dispatcher, the reminder
    # dispatcher) need a connection that RLS does not filter. The application
    # role deliberately cannot do that — it is `NOBYPASSRLS`, which is the whole
    # point of ADR-033 — so those jobs use a second DSN pointing at
    # `mindflow_maintenance` (ADR-042). Empty means "same as database_url",
    # which is right for local development where the app owns the schema.
    maintenance_database_url: str = ""
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

    # -- Additional providers (Phase 3) ------------------------------------
    # Mistral, Gemini and Llama arrive here rather than in a plugin because the
    # ports they implement already existed; adding a provider is a factory
    # branch and a credential, never a change to a caller (ADR-043).
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # Llama has no single vendor. Anything speaking the OpenAI wire format —
    # Ollama, vLLM, llama.cpp's server, Together, Groq — is reached by pointing
    # this at it, which is why there is a URL and no product name.
    llama_base_url: str = "http://localhost:11434/v1"
    llama_api_key: str = ""

    # -- Embeddings (Phase 3) ----------------------------------------------
    embedding_backend: Literal["openai", "mistral", "gemini", "llama", "fake"] = "fake"
    embedding_model: str = "text-embedding-3-small"
    # This is a *schema* decision, not merely a client one: the `chunk.embedding`
    # column is `vector(N)` and N is fixed at migration time. Changing provider
    # to one with a different width therefore means a migration plus a full
    # re-embed — which is required anyway, since two models' vectors live in
    # different spaces and comparing them is meaningless (ADR-045).
    embedding_dimensions: int = 1536
    embedding_timeout_seconds: float = 30.0
    # Providers cap request size; 64 chunks is comfortably inside every cap we
    # target and keeps a failed batch cheap to retry.
    embedding_batch_size: int = 64

    # -- Assistant (Phase 3) -----------------------------------------------
    chat_backend: Literal["openai", "anthropic", "gemini", "mistral", "llama", "fake"] = "fake"
    chat_model: str = "gpt-4o-mini"
    chat_timeout_seconds: float = 90.0
    chat_max_output_tokens: int = 1200
    # How much retrieved text the answer prompt may carry. Larger is not better:
    # past roughly this size, recall stops improving and the model starts
    # answering from the middle of the context, which reads as ignoring the
    # question.
    chat_context_token_budget: int = 6000

    # -- Enterprise (Phase 4) ----------------------------------------------
    # `id:base64[,id:base64…]`, active key first. One string because it must
    # survive being an environment variable in every deployment target, and
    # because a secret manager hands back one value (ADR-058).
    token_encryption_keys: str = ""
    # How often the scheduler considers a connection due. Five minutes is well
    # inside every provider's rate limit and well under a user's patience.
    sync_interval_seconds: int = 300
    sync_batch_size: int = 25
    # Public base for share links and invitations. Wrong here means every link
    # a user sends points at localhost.
    public_base_url: str = "http://localhost:3000"

    # -- Retrieval (Phase 3) -----------------------------------------------
    # Candidates pulled from *each* retriever before fusion. Fusion needs depth
    # to find consensus; showing depth to the user does not.
    retrieval_candidate_limit: int = 40
    retrieval_context_chunks: int = 8
    retrieval_min_similarity: float = 0.15

    # -- Push notifications (Phase 2) --------------------------------------
    # `fake` records instead of sending, which is what lets the whole reminder
    # path be exercised in tests and in `docker compose up` without a Firebase
    # project or a Microsoft Partner Center account.
    push_backend: Literal["real", "fake"] = "fake"
    push_timeout_seconds: float = 10.0
    # Batch ceiling per dispatcher tick. Keeps one very active account from
    # monopolising the worker for a minute.
    push_batch_size: int = 200

    # Firebase: the service account JSON, verbatim. Kept as a string rather than
    # a file path so it can come from a secret manager without touching disk.
    fcm_service_account_json: str = ""
    fcm_project_id: str = ""

    # Windows Notification Service, for packaged (MSIX) builds. Unpackaged
    # Windows builds schedule their toasts locally instead (ADR-040).
    wns_client_id: str = ""
    wns_client_secret: str = ""

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
    def effective_maintenance_url(self) -> str:
        return self.maintenance_database_url or self.database_url

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
        # A production build with `push_backend="fake"` would accept reminders,
        # schedule them, mark them sent and deliver nothing — a silent failure
        # far worse than a refusal to start.
        if self.push_backend == "fake":
            missing.append("push_backend (must not be 'fake')")
        if self.push_backend == "real" and not (
            self.fcm_service_account_json or self.wns_client_id
        ):
            missing.append("fcm_service_account_json or wns_client_id")

        # Phase 4. Without a key, OAuth tokens would be stored in plaintext —
        # and a database backup would be a set of live Google credentials.
        if not self.token_encryption_keys:
            missing.append("token_encryption_keys")
        if self.public_base_url.startswith("http://localhost"):
            missing.append("public_base_url (les liens de partage pointeraient sur localhost)")

        # Phase 3. `fake` here is not inert like a fake push: the fake embedder
        # produces hash-derived vectors that index and retrieve *successfully*
        # and rank nonsense. Semantic search would appear to work and quietly
        # return the wrong notes, which is the hardest class of bug to notice.
        if self.embedding_backend == "fake":
            missing.append("embedding_backend (must not be 'fake')")
        if self.chat_backend == "fake":
            missing.append("chat_backend (must not be 'fake')")
        for backend in dict.fromkeys((self.embedding_backend, self.chat_backend)):
            key = _missing_provider_key(backend, self)
            if key and key not in missing:
                missing.append(key)

        if missing:
            raise ValueError(
                f"environment '{self.env}' requires: {', '.join(missing)}. "
                "Refusing to start with an incomplete configuration."
            )
        return self


def _missing_provider_key(backend: str, settings: Settings) -> str:
    """The credential a backend needs but does not have, if any.

    `llama` is deliberately absent: it points at a self-hosted OpenAI-compatible
    server, which normally needs no key. Requiring one would make the one
    provider that runs entirely on your own hardware the hardest to configure.
    """
    required: dict[str, str] = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "mistral": settings.mistral_api_key,
        "gemini": settings.gemini_api_key,
    }
    if backend in required and not required[backend]:
        return f"{backend}_api_key"
    return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
