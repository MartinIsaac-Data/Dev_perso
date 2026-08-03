"""LLM analysers (ADR-031, AI.md §4).

Three adapters behind one port. Swapping provider is a configuration change —
`MINDFLOW_LLM_BACKEND` — not a code change, which is what "architecture
interchangeable" has to mean to be worth anything.

Both real adapters use **constrained decoding against the same JSON schema**.
That is the load-bearing part: a non-conforming output is rejected, never
best-effort parsed (AI.md, I3).
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.analysis import AnalysisNote, NoteAnalysis, json_schema_for_llm
from app.domain.errors import (
    ExtractionUnavailableError,
    LlmRefusalError,
    LlmSchemaViolationError,
)
from app.domain.ports import AiUsage, AnalysisContext, AnalysisResult, AnalyzerPort
from app.infra.ai.prompts import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_context_block,
    build_transcript_block,
)
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.llm")

# Public list prices, euro-cents per million tokens, used to record a cost per
# run. Approximate by construction (USD→EUR); the point is relative tracking and
# anomaly detection, not accounting.
PRICING_MICRO_EUR_PER_TOKEN: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.14, 0.55),
    "gpt-4o": (2.3, 9.2),
    "claude-opus-5": (4.6, 23.0),
    "claude-haiku-4-5": (0.92, 4.6),
    "claude-sonnet-5": (2.8, 13.8),
}


def _cost_micro_eur(model: str, input_tokens: int, output_tokens: int) -> int:
    rate_in, rate_out = PRICING_MICRO_EUR_PER_TOKEN.get(model, (0.0, 0.0))
    return int(input_tokens * rate_in + output_tokens * rate_out)


def _validate(payload: str, *, model: str) -> NoteAnalysis:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        log.error("llm.invalid_json", model=model)
        raise LlmSchemaViolationError("Le modèle n'a pas renvoyé de JSON valide.") from exc
    try:
        return NoteAnalysis.model_validate(data)
    except ValidationError as exc:
        log.error("llm.schema_violation", model=model, error_count=exc.error_count())
        raise LlmSchemaViolationError("Réponse du modèle non conforme au schéma.") from exc


class FakeAnalyzer(AnalyzerPort):
    """Deterministic analyser for tests and offline development."""

    name = "fake"

    def __init__(self, analysis: NoteAnalysis | None = None) -> None:
        self._analysis = analysis

    async def analyze(self, transcript: str, *, context: AnalysisContext) -> AnalysisResult:
        if self._analysis is not None:
            analysis = self._analysis
        else:
            analysis = NoteAnalysis(
                language="fr",
                summary=transcript[:200] or "Capture vide",
                tasks=[],
                ideas=[],
                notes=[
                    AnalysisNote.model_validate(
                        {
                            "title": (transcript[:100] or "Note"),
                            "body": None,
                            "entry_type": "note",
                            "confidence": 0.8,
                            "source_span": {"start": 0, "end": max(1, min(len(transcript), 100))},
                        }
                    )
                ],
                overall_confidence=0.8,
            )
        return AnalysisResult(
            analysis=analysis,
            usage=AiUsage(model="fake", input_tokens=0, output_tokens=0),
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
        )


class OpenAIAnalyzer(AnalyzerPort):
    """OpenAI adapter using Structured Outputs (`json_schema`, `strict: true`)."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_output_tokens: int = 4000,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens

    async def analyze(self, transcript: str, *, context: AnalysisContext) -> AnalysisResult:
        started = time.perf_counter()
        body = {
            "model": self._model,
            "max_tokens": self._max_output_tokens,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": build_context_block(context)},
                {"role": "user", "content": build_transcript_block(transcript, context)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "note_analysis",
                    "strict": True,
                    "schema": json_schema_for_llm(),
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx.HTTPError as exc:
            log.error("llm.transport_failed", provider=self.name, error=type(exc).__name__)
            raise ExtractionUnavailableError("Service d'analyse injoignable.") from exc

        if response.status_code == 429:
            raise ExtractionUnavailableError("Limite de débit atteinte sur le modèle.")
        if response.status_code >= 400:
            log.error("llm.failed", provider=self.name, status=response.status_code)
            raise ExtractionUnavailableError("Échec de l'analyse.")

        payload = response.json()
        choice = payload["choices"][0]

        # A content filter refusal is not an error to retry: retrying would be
        # circumvention. The capture degrades with its transcript intact.
        if choice.get("finish_reason") == "content_filter" or choice["message"].get("refusal"):
            log.info("llm.refusal", provider=self.name)
            raise LlmRefusalError("Le modèle a refusé de traiter ce contenu.")

        analysis = _validate(choice["message"]["content"], model=self._model)
        usage = payload.get("usage", {})
        return self._result(analysis, usage, started)

    def _result(
        self, analysis: NoteAnalysis, usage: dict[str, Any], started: float
    ) -> AnalysisResult:
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        cached = int(usage.get("prompt_tokens_details", {}).get("cached_tokens", 0))
        latency_ms = int((time.perf_counter() - started) * 1000)

        metrics.llm_tokens_total.labels(self._model, "extract", "input").inc(input_tokens)
        metrics.llm_tokens_total.labels(self._model, "extract", "output").inc(output_tokens)
        cost = _cost_micro_eur(self._model, input_tokens, output_tokens)
        metrics.llm_cost_micro_eur_total.labels(self._model, "extract").inc(cost)

        return AnalysisResult(
            analysis=analysis,
            usage=AiUsage(
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cached,
                cost_micro_eur=cost,
                latency_ms=latency_ms,
            ),
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
        )


class AnthropicAnalyzer(AnalyzerPort):
    """Claude adapter — the ADR-008 choice, kept implemented so the evaluation
    harness can compare the two providers on the same dataset (ADR-031)."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model: str = "claude-opus-5",
        timeout: float = 60.0,
        max_output_tokens: int = 4000,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_output_tokens = max_output_tokens

    async def analyze(self, transcript: str, *, context: AnalysisContext) -> AnalysisResult:
        started = time.perf_counter()
        body = {
            "model": self._model,
            "max_tokens": self._max_output_tokens,
            "system": [
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": build_context_block(context)},
            ],
            "messages": [{"role": "user", "content": build_transcript_block(transcript, context)}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": json_schema_for_llm(),
                }
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            log.error("llm.transport_failed", provider=self.name, error=type(exc).__name__)
            raise ExtractionUnavailableError("Service d'analyse injoignable.") from exc

        if response.status_code == 429:
            raise ExtractionUnavailableError("Limite de débit atteinte sur le modèle.")
        if response.status_code >= 400:
            log.error("llm.failed", provider=self.name, status=response.status_code)
            raise ExtractionUnavailableError("Échec de l'analyse.")

        payload = response.json()

        # Claude signals a policy decline with stop_reason, not an HTTP error —
        # check it before reading content.
        if payload.get("stop_reason") == "refusal":
            log.info("llm.refusal", provider=self.name)
            raise LlmRefusalError("Le modèle a refusé de traiter ce contenu.")

        text = next(
            (block["text"] for block in payload.get("content", []) if block.get("type") == "text"),
            "",
        )
        analysis = _validate(text, model=self._model)

        usage = payload.get("usage", {})
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        latency_ms = int((time.perf_counter() - started) * 1000)

        metrics.llm_tokens_total.labels(self._model, "extract", "input").inc(input_tokens)
        metrics.llm_tokens_total.labels(self._model, "extract", "output").inc(output_tokens)
        cost = _cost_micro_eur(self._model, input_tokens, output_tokens)
        metrics.llm_cost_micro_eur_total.labels(self._model, "extract").inc(cost)

        return AnalysisResult(
            analysis=analysis,
            usage=AiUsage(
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
                cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
                cost_micro_eur=cost,
                latency_ms=latency_ms,
            ),
            prompt_name=PROMPT_NAME,
            prompt_version=PROMPT_VERSION,
        )
