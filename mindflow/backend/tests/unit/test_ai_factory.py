"""Provider selection is configuration, not code (ADR-043).

This file is the executable form of « aucun fournisseur ne doit être couplé au
projet ». If every backend name in `Settings` resolves to a working adapter, and
the only module that mentions a provider's name is the factory, then swapping
provider really is an environment variable.

The negative assertion matters as much as the positive ones:
`test_no_service_imports_a_provider_by_name` is what stops the guarantee from
quietly eroding the first time someone reaches for `OpenAIAnalyzer` directly
because it was convenient.
"""

from __future__ import annotations

import pathlib

import pytest

from app.config import Settings
from app.infra.ai.factory import build_analyzer, build_chat, build_embedder, build_transcriber

BACKEND = "http://localhost:11434/v1"


def _settings(**overrides: object) -> Settings:
    return Settings(env="local", **overrides)  # type: ignore[arg-type]


class TestEmbedders:
    @pytest.mark.parametrize(
        ("backend", "expected"),
        [
            ("openai", "openai"),
            ("mistral", "mistral"),
            ("gemini", "gemini"),
            ("llama", "llama"),
            ("fake", "fake"),
        ],
    )
    def test_every_backend_resolves(self, backend: str, expected: str) -> None:
        embedder = build_embedder(_settings(embedding_backend=backend))
        assert embedder.name == expected

    def test_the_dimension_comes_from_settings_not_from_the_provider(self) -> None:
        # The `chunk.embedding` column has one width; an adapter defaulting to
        # its own would fail at INSERT, on a background worker, silently.
        embedder = build_embedder(_settings(embedding_backend="gemini", embedding_dimensions=1024))
        assert embedder.dimensions == 1024

    def test_the_model_comes_from_settings(self) -> None:
        embedder = build_embedder(
            _settings(embedding_backend="openai", embedding_model="text-embedding-3-large")
        )
        assert embedder.model == "text-embedding-3-large"


class TestChat:
    @pytest.mark.parametrize(
        ("backend", "expected"),
        [
            ("openai", "openai"),
            ("anthropic", "anthropic"),
            ("gemini", "gemini"),
            ("mistral", "mistral"),
            ("llama", "llama"),
            ("fake", "fake"),
        ],
    )
    def test_all_five_required_providers_resolve(self, backend: str, expected: str) -> None:
        # The five named in the phase 3 brief, plus the fake for tests.
        assert build_chat(_settings(chat_backend=backend)).name == expected

    def test_a_self_hosted_llama_is_reached_by_url(self) -> None:
        # "Llama" is a model family, not a vendor. The integration is a URL.
        chat = build_chat(_settings(chat_backend="llama", llama_base_url=BACKEND))
        assert chat.name == "llama"

    def test_the_model_comes_from_settings(self) -> None:
        chat = build_chat(_settings(chat_backend="anthropic", chat_model="claude-haiku-4-5"))
        assert chat.model == "claude-haiku-4-5"


class TestPhaseOneAndTwoStillWork:
    def test_the_transcriber_factory_is_unchanged(self) -> None:
        assert build_transcriber(_settings(stt_backend="fake")).name == "fake"

    def test_the_analyzer_factory_is_unchanged(self) -> None:
        assert build_analyzer(_settings(llm_backend="fake")).name == "fake"


class TestNoProviderCoupling:
    def test_no_service_imports_a_provider_by_name(self) -> None:
        """Only the factory may name a provider.

        Checked by reading the source rather than by convention, because a
        convention that is not enforced is a convention that lasts until the
        first deadline.
        """
        root = pathlib.Path(__file__).resolve().parents[2] / "app"
        allowed = {
            root / "config.py",  # the Literal listing the choices
            root / "infra" / "ai" / "factory.py",
            root / "infra" / "ai" / "analyzers.py",
            root / "infra" / "ai" / "transcribers.py",
            root / "infra" / "ai" / "embedders.py",
            root / "infra" / "ai" / "chat.py",
        }
        vendors = ("openai", "anthropic", "mistral", "gemini", "ollama")

        offenders: list[str] = []
        for path in root.rglob("*.py"):
            if path in allowed:
                continue
            lowered = path.read_text().lower()
            for vendor in vendors:
                # Comments and docstrings may discuss providers; imports and
                # attribute access may not.
                for marker in (f"import {vendor}", f"from {vendor}", f"{vendor}_api_key"):
                    if marker in lowered:
                        offenders.append(f"{path.relative_to(root)}: {marker}")

        assert offenders == []
