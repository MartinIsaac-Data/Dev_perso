from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_local_defaults_are_permissive() -> None:
    """Local development must work with zero configuration."""
    settings = Settings(env="local")
    assert settings.stt_backend == "fake"
    assert settings.llm_backend == "fake"
    assert settings.storage_backend == "local"


def test_production_refuses_fake_backends() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(env="prod", supabase_jwt_secret="s" * 40)
    message = str(exc.value)
    assert "stt_backend" in message
    assert "llm_backend" in message


def test_production_requires_an_auth_verification_method() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            env="prod",
            stt_backend="openai",
            llm_backend="openai",
            openai_api_key="sk-test",
        )
    assert "supabase_jwt_secret or supabase_jwks_url" in str(exc.value)


def test_production_requires_the_provider_key_of_the_chosen_llm() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            env="prod",
            supabase_jwt_secret="s" * 40,
            stt_backend="openai",
            llm_backend="anthropic",
            openai_api_key="sk-test",
        )
    assert "anthropic_api_key" in str(exc.value)


def test_production_accepts_a_complete_configuration() -> None:
    settings = Settings(
        env="prod",
        supabase_jwks_url="https://x.supabase.co/auth/v1/.well-known/jwks.json",
        supabase_service_key="service-key",
        storage_backend="supabase",
        stt_backend="faster_whisper",
        llm_backend="openai",
        openai_api_key="sk-test",
    )
    assert settings.is_production_like


def test_sync_database_url_strips_the_async_driver() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@h:5432/db")
    assert settings.sync_database_url == "postgresql://u:p@h:5432/db"
