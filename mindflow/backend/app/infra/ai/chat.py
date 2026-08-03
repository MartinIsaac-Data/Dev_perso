"""Conversational adapters: OpenAI, Claude, Gemini, Mistral, Llama (ADR-043).

Five providers, three implementations, one port. OpenAI, Mistral and any
OpenAI-compatible server share a wire format and therefore a class; Anthropic
and Gemini each get their own because their request and stream shapes genuinely
differ.

**Streaming is the primary operation** and `complete()` is derived from it, in
the port. That is the right way round for this product: an assistant that shows
nothing for eight seconds feels broken even when it is fast, and the first token
is what tells the user their question was understood. A provider that could not
stream would get an adapter yielding a single chunk — the interface would not
bend for it.

The awkward part of a multi-provider streaming layer is that **every provider
signals the end differently**, and the end is where the usage numbers live.
OpenAI sends a sentinel line, Anthropic sends typed events, Gemini sends a JSON
array. Each adapter is responsible for emitting exactly one `done=True` chunk
carrying whatever usage it could find; the rest of the system never learns which
provider it was talking to.

Refusals are values, not exceptions (ADR-030). A model declining to answer is a
legitimate outcome the assistant shows as an answer; raising would turn it into
an error page and, worse, into a retry.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import AiUsage, ChatChunk, ChatPort, ChatRequest
from app.infra.ai.analyzers import PRICING_MICRO_EUR_PER_TOKEN
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.chat")


def _cost_micro_eur(model: str, input_tokens: int, output_tokens: int) -> int:
    rate_in, rate_out = PRICING_MICRO_EUR_PER_TOKEN.get(model, (0.0, 0.0))
    return int(input_tokens * rate_in + output_tokens * rate_out)


def _usage(
    model: str, input_tokens: int, output_tokens: int, started: float, **extra: int
) -> AiUsage:
    metrics.llm_tokens_total.labels(model, "chat", "input").inc(input_tokens)
    metrics.llm_tokens_total.labels(model, "chat", "output").inc(output_tokens)
    cost = _cost_micro_eur(model, input_tokens, output_tokens)
    metrics.llm_cost_micro_eur_total.labels(model, "chat").inc(cost)
    return AiUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_micro_eur=cost,
        latency_ms=int((time.perf_counter() - started) * 1000),
        **extra,
    )


def _fail(provider: str, exc: Exception) -> ExtractionUnavailableError:
    log.error("chat.transport_failed", provider=provider, error=type(exc).__name__)
    return ExtractionUnavailableError("Assistant momentanément indisponible.")


async def _check(response: httpx.Response, provider: str) -> None:
    """Raise on an error status, having read the body first.

    `aread()` is required before touching `status_code` on a streamed response
    whose body has not been consumed — without it the error path can hang
    waiting for a body nobody is reading.
    """
    if response.status_code < 400:
        return
    await response.aread()
    log.error("chat.failed", provider=provider, status=response.status_code)
    if response.status_code == 429:
        raise ExtractionUnavailableError("Assistant saturé, réessayez dans un instant.")
    raise ExtractionUnavailableError("Assistant momentanément indisponible.")


class FakeChat(ChatPort):
    """Scripted answers for tests and offline development.

    Streams word by word rather than returning the whole string at once, so the
    tests exercise the same assembly path production uses. A fake that skips
    streaming would leave the only interesting part of this module untested.
    """

    name = "fake"
    supports_json_schema = True

    def __init__(
        self, *, reply: str = "Je ne trouve pas cette information dans vos notes."
    ) -> None:
        self.model = "fake-chat"
        self._reply = reply
        self.last_request: ChatRequest | None = None

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.last_request = request
        for word in self._reply.split(" "):
            yield ChatChunk(text=word + " ")
        yield ChatChunk(
            done=True,
            usage=AiUsage(model=self.model, input_tokens=0, output_tokens=len(self._reply) // 4),
            finish_reason="stop",
        )


class OpenAICompatibleChat(ChatPort):
    """OpenAI, Mistral, and any server speaking `/chat/completions`.

    Llama models arrive through here too: `llama` is not a vendor, it is a
    family served by Ollama, vLLM, llama.cpp and half a dozen hosts, all of
    which implement this route. Pointing `llama_base_url` at one of them is the
    whole integration.
    """

    supports_json_schema = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        name: str = "openai",
        timeout: float = 90.0,
    ) -> None:
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        started = time.perf_counter()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": True,
            # Without this, the terminal chunk carries no usage and every run is
            # recorded as costing nothing.
            "stream_options": {"include_usage": True},
        }
        if request.stop:
            body["stop"] = list(request.stop)
        if request.json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": request.json_schema},
            }

        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        input_tokens = output_tokens = 0
        finish = "stop"
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST", f"{self._base_url}/chat/completions", headers=headers, json=body
                ) as response,
            ):
                await _check(response, self.name)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)

                    # The usage-only frame has an empty `choices`, so this
                    # must be read before indexing into it.
                    if usage := event.get("usage"):
                        input_tokens = int(usage.get("prompt_tokens", 0))
                        output_tokens = int(usage.get("completion_tokens", 0))
                    if not event.get("choices"):
                        continue

                    choice = event["choices"][0]
                    if reason := choice.get("finish_reason"):
                        finish = "refusal" if reason == "content_filter" else reason
                    if text := choice.get("delta", {}).get("content"):
                        yield ChatChunk(text=text)
        except httpx.HTTPError as exc:
            raise _fail(self.name, exc) from exc

        yield ChatChunk(
            done=True,
            usage=_usage(self.model, input_tokens, output_tokens, started),
            finish_reason=finish,
        )


class AnthropicChat(ChatPort):
    """Claude. Typed stream events rather than deltas on a choice."""

    name = "anthropic"
    supports_json_schema = False

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model: str = "claude-opus-5",
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        started = time.perf_counter()
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": True,
        }
        if request.system:
            # Marked cacheable: the system prompt is identical on every turn of
            # every conversation, which is exactly what prefix caching is for.
            body["system"] = [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ]
        if request.stop:
            body["stop_sequences"] = list(request.stop)

        input_tokens = output_tokens = cache_read = cache_write = 0
        finish = "stop"
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                ) as response,
            ):
                await _check(response, self.name)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    kind = event.get("type")

                    if kind == "content_block_delta":
                        if text := event.get("delta", {}).get("text"):
                            yield ChatChunk(text=text)
                    elif kind == "message_start":
                        usage = event.get("message", {}).get("usage", {})
                        input_tokens = int(usage.get("input_tokens", 0))
                        cache_read = int(usage.get("cache_read_input_tokens", 0))
                        cache_write = int(usage.get("cache_creation_input_tokens", 0))
                    elif kind == "message_delta":
                        output_tokens = int(event.get("usage", {}).get("output_tokens", 0))
                        if reason := event.get("delta", {}).get("stop_reason"):
                            finish = reason
                    elif kind == "error":
                        log.error("chat.stream_error", provider=self.name)
                        raise ExtractionUnavailableError("Assistant momentanément indisponible.")
        except httpx.HTTPError as exc:
            raise _fail(self.name, exc) from exc

        yield ChatChunk(
            done=True,
            usage=_usage(
                self.model,
                input_tokens,
                output_tokens,
                started,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            ),
            finish_reason=finish,
        )


class GeminiChat(ChatPort):
    """Google Gemini.

    Its streaming endpoint emits a JSON *array* rather than server-sent events,
    which is why this adapter parses `alt=sse` output the same way as the others
    only after asking for it explicitly. Without `alt=sse` the response is a
    single array that cannot be consumed incrementally — technically streaming,
    practically not.
    """

    name = "gemini"
    supports_json_schema = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "gemini-2.0-flash",
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        started = time.perf_counter()
        generation: dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_output_tokens,
        }
        if request.stop:
            generation["stopSequences"] = list(request.stop)
        if request.json_schema:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = request.json_schema

        body: dict[str, Any] = {
            "contents": [
                {
                    # Gemini names the assistant role "model"; the port's
                    # vocabulary does not bend to one provider's naming.
                    "role": "model" if message.role == "assistant" else "user",
                    "parts": [{"text": message.content}],
                }
                for message in request.messages
            ],
            "generationConfig": generation,
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}

        input_tokens = output_tokens = 0
        finish = "stop"
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/models/{self.model}:streamGenerateContent?alt=sse",
                    headers={"content-type": "application/json", "x-goog-api-key": self._api_key},
                    json=body,
                ) as response,
            ):
                await _check(response, self.name)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])

                    if usage := event.get("usageMetadata"):
                        input_tokens = int(usage.get("promptTokenCount", 0))
                        output_tokens = int(usage.get("candidatesTokenCount", 0))

                    for candidate in event.get("candidates", []):
                        reason = candidate.get("finishReason")
                        if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
                            finish = "refusal"
                        elif reason and reason != "STOP":
                            finish = reason.lower()
                        for part in candidate.get("content", {}).get("parts", []):
                            if text := part.get("text"):
                                yield ChatChunk(text=text)
        except httpx.HTTPError as exc:
            raise _fail(self.name, exc) from exc

        yield ChatChunk(
            done=True,
            usage=_usage(self.model, input_tokens, output_tokens, started),
            finish_reason=finish,
        )
