"""AI adapter selection — configuration, not code (ADR-031, ADR-043, AI.md I1).

This module is the *only* place in the codebase that knows a provider's name.
Everything above it holds a port. That is what « aucun fournisseur ne doit être
couplé au projet » has to mean to be worth anything: adding Mistral in phase 3
touched this file, a settings block and a production-validation check, and
nothing else — no service, no route, no test of behaviour.

Imports are deliberately local to each branch. A top-level import of every
adapter would load five HTTP clients' worth of module to build one, and would
make a broken optional dependency break startup for deployments that never use
it.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import AnalyzerPort, ChatPort, EmbedderPort, TranscriberPort


def build_transcriber(settings: Settings) -> TranscriberPort:
    if settings.stt_backend == "faster_whisper":
        from app.infra.ai.transcribers import FasterWhisperTranscriber

        return FasterWhisperTranscriber(
            model=settings.stt_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            timeout=settings.stt_timeout_seconds,
        )
    if settings.stt_backend == "openai":
        from app.infra.ai.transcribers import OpenAIWhisperTranscriber

        return OpenAIWhisperTranscriber(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.stt_timeout_seconds,
        )

    from app.infra.ai.transcribers import FakeTranscriber

    return FakeTranscriber()


def build_analyzer(settings: Settings) -> AnalyzerPort:
    if settings.llm_backend == "openai":
        from app.infra.ai.analyzers import OpenAIAnalyzer

        return OpenAIAnalyzer(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    if settings.llm_backend == "anthropic":
        from app.infra.ai.analyzers import AnthropicAnalyzer

        return AnthropicAnalyzer(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    from app.infra.ai.analyzers import FakeAnalyzer

    return FakeAnalyzer()


def build_embedder(settings: Settings) -> EmbedderPort:
    """Pick an embedder. The dimension always comes from settings, never from
    the provider's default — the `chunk.embedding` column has one width and the
    adapter must produce it (ADR-045)."""
    from app.infra.ai.embedders import GeminiEmbedder, OpenAICompatibleEmbedder

    dimensions = settings.embedding_dimensions

    if settings.embedding_backend == "openai":
        return OpenAICompatibleEmbedder(
            name="openai",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.embedding_model,
            dimensions=dimensions,
            timeout=settings.embedding_timeout_seconds,
        )
    if settings.embedding_backend == "mistral":
        return OpenAICompatibleEmbedder(
            name="mistral",
            api_key=settings.mistral_api_key,
            base_url=settings.mistral_base_url,
            model=settings.embedding_model,
            dimensions=dimensions,
            timeout=settings.embedding_timeout_seconds,
            # Mistral rejects the unknown `dimensions` field rather than
            # ignoring it, so the request must not carry it.
            send_dimensions=False,
        )
    if settings.embedding_backend == "gemini":
        return GeminiEmbedder(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model=settings.embedding_model,
            dimensions=dimensions,
            timeout=settings.embedding_timeout_seconds,
        )
    if settings.embedding_backend == "llama":
        return OpenAICompatibleEmbedder(
            name="llama",
            api_key=settings.llama_api_key,
            base_url=settings.llama_base_url,
            model=settings.embedding_model,
            dimensions=dimensions,
            timeout=settings.embedding_timeout_seconds,
            send_dimensions=False,
        )

    from app.infra.ai.embedders import FakeEmbedder

    return FakeEmbedder(dimensions=dimensions)


def build_chat(settings: Settings) -> ChatPort:
    """Pick a conversational model."""
    if settings.chat_backend == "openai":
        from app.infra.ai.chat import OpenAICompatibleChat

        return OpenAICompatibleChat(
            name="openai",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.chat_model,
            timeout=settings.chat_timeout_seconds,
        )
    if settings.chat_backend == "mistral":
        from app.infra.ai.chat import OpenAICompatibleChat

        return OpenAICompatibleChat(
            name="mistral",
            api_key=settings.mistral_api_key,
            base_url=settings.mistral_base_url,
            model=settings.chat_model,
            timeout=settings.chat_timeout_seconds,
        )
    if settings.chat_backend == "llama":
        from app.infra.ai.chat import OpenAICompatibleChat

        # Not a vendor: any OpenAI-compatible host — Ollama, vLLM, llama.cpp —
        # serving a Llama-family model. The URL is the integration.
        return OpenAICompatibleChat(
            name="llama",
            api_key=settings.llama_api_key,
            base_url=settings.llama_base_url,
            model=settings.chat_model,
            timeout=settings.chat_timeout_seconds,
        )
    if settings.chat_backend == "anthropic":
        from app.infra.ai.chat import AnthropicChat

        return AnthropicChat(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=settings.chat_model,
            timeout=settings.chat_timeout_seconds,
        )
    if settings.chat_backend == "gemini":
        from app.infra.ai.chat import GeminiChat

        return GeminiChat(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model=settings.chat_model,
            timeout=settings.chat_timeout_seconds,
        )

    from app.infra.ai.chat import FakeChat

    return FakeChat()
