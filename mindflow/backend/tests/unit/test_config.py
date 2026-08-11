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
        push_backend="real",
        fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
        token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        public_base_url="https://app.mindflow.ai",
        embedding_backend="openai",
        chat_backend="openai",
    )
    assert settings.is_production_like


def test_production_refuses_a_fake_embedding_backend() -> None:
    """The fake embedder is not inert the way a fake push sender is.

    It returns hash-derived vectors that index and retrieve *successfully* and
    rank nonsense. Semantic search would look like it works while quietly
    returning the wrong notes — the hardest class of bug to notice from outside.
    """
    with pytest.raises(ValidationError, match="embedding_backend"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
            fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
            token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
            public_base_url="https://app.mindflow.ai",
            embedding_backend="fake",
            chat_backend="openai",
        )


def test_production_requires_the_credential_of_whichever_provider_is_chosen() -> None:
    # The point of ADR-043: adding Mistral changed a factory branch and this
    # check, and nothing else.
    with pytest.raises(ValidationError, match="mistral_api_key"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
            fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
            token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
            public_base_url="https://app.mindflow.ai",
            embedding_backend="mistral",
            chat_backend="openai",
        )


def test_a_self_hosted_llama_needs_no_credential() -> None:
    # Requiring a key would make the one provider running entirely on your own
    # hardware the hardest of the five to configure.
    settings = Settings(
        env="prod",
        supabase_jwt_secret="secret",
        stt_backend="faster_whisper",
        llm_backend="openai",
        openai_api_key="sk-test",
        push_backend="real",
        fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
        token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        public_base_url="https://app.mindflow.ai",
        embedding_backend="llama",
        chat_backend="llama",
    )
    assert settings.chat_backend == "llama"


def test_production_refuses_a_fake_push_backend() -> None:
    """A prod build with `push_backend="fake"` would accept reminders, schedule
    them, mark them sent and deliver nothing — a silent failure far worse than a
    refusal to start."""
    with pytest.raises(ValidationError, match="push_backend"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="fake",
        )


def test_production_requires_push_credentials() -> None:
    with pytest.raises(ValidationError, match="fcm_service_account_json"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
        )


def test_sync_database_url_strips_the_async_driver() -> None:
    settings = Settings(database_url="postgresql+asyncpg://u:p@h:5432/db")
    assert settings.sync_database_url == "postgresql://u:p@h:5432/db"


def test_production_requires_a_token_encryption_key() -> None:
    """Without it, OAuth tokens would be stored in plaintext.

    A database backup restored onto a laptop would be a set of live Google
    credentials — and disk encryption does not help, because the backup leaves
    the encrypted disk the moment anyone downloads it.
    """
    with pytest.raises(ValidationError, match="token_encryption_keys"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
            fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
            embedding_backend="openai",
            chat_backend="openai",
            public_base_url="https://app.mindflow.ai",
        )


def test_production_refuses_a_localhost_share_url() -> None:
    # Otherwise every invitation and share link a user sends points at their
    # own machine — a failure nobody notices until a recipient complains.
    with pytest.raises(ValidationError, match="public_base_url"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
            fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
            embedding_backend="openai",
            chat_backend="openai",
            token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        )


def test_local_accepts_any_local_origin_whatever_the_port() -> None:
    """Le client web ne choisit pas toujours son port.

    `flutter run` en prend un au hasard, `tool/serve_web.mjs` sert sur 8080, et
    l'API écoute sur 8000. Épingler un port ferait échouer la moitié des
    démarrages avec, côté navigateur, une erreur que le serveur ne voit pas.
    """
    import re

    pattern = Settings(env="local").cors_origin_regex
    assert pattern is not None
    assert re.match(pattern, "http://localhost:8080")
    assert re.match(pattern, "http://127.0.0.1:54321")
    assert not re.match(pattern, "http://exemple.test")
    # Un sous-domaine qui *contient* localhost n'est pas localhost.
    assert not re.match(pattern, "http://localhost.attaquant.test")


def test_production_does_not_open_local_origins() -> None:
    settings = Settings(
        env="prod",
        supabase_jwks_url="https://x.supabase.co/auth/v1/.well-known/jwks.json",
        stt_backend="faster_whisper",
        llm_backend="openai",
        openai_api_key="sk-test",
        push_backend="real",
        fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
        token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
        public_base_url="https://app.mindflow.ai",
        embedding_backend="openai",
        chat_backend="openai",
        cors_allow_origins="https://app.mindflow.ai, https://beta.mindflow.ai",
    )
    assert settings.cors_origin_regex is None
    assert settings.cors_origins == ["https://app.mindflow.ai", "https://beta.mindflow.ai"]


def test_production_refuses_a_wildcard_origin() -> None:
    with pytest.raises(ValidationError, match="cors_allow_origins"):
        Settings(
            env="prod",
            supabase_jwt_secret="secret",
            stt_backend="faster_whisper",
            llm_backend="openai",
            openai_api_key="sk-test",
            push_backend="real",
            fcm_service_account_json='{"private_key": "x", "client_email": "a@b.c"}',
            embedding_backend="openai",
            chat_backend="openai",
            token_encryption_keys="k1:c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLXh4eHg=",
            public_base_url="https://app.mindflow.ai",
            cors_allow_origins="*",
        )
