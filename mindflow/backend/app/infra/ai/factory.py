"""AI adapter selection — configuration, not code (ADR-031, AI.md I1)."""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import AnalyzerPort, TranscriberPort


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
