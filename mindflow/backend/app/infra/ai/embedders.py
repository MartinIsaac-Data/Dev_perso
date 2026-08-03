"""Embedding adapters (ADR-043, ADR-045).

Four providers, two implementations. OpenAI, Mistral and any OpenAI-compatible
server — Ollama, vLLM, llama.cpp, Together — speak the same `/embeddings` wire
format, so they share one class parameterised by base URL and credential. That
is not a shortcut: it is the observation that made phase 3's provider-neutrality
requirement cheap to satisfy. Gemini uses a different request shape and gets its
own adapter.

Three properties every adapter here must hold, because the store depends on them:

* **Order is preserved.** `embed(["a", "b"])` returns the vector for "a" first.
  Providers return indexed results and at least one returns them out of order
  under load; the adapter sorts. Getting this wrong attaches every embedding to
  the wrong chunk, and nothing crashes — search simply becomes random.
* **Dimensions are asserted, not assumed.** A vector of the wrong width is a
  configuration error that must surface at the adapter, not as a Postgres type
  error three layers down, and certainly not as a silently truncated vector.
* **Failure is a refusal to store.** There is no partial batch: a batch either
  yields one vector per input or raises. A short batch silently misaligned with
  its inputs is the same bug as unordered results.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, ClassVar

import httpx

from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import AiUsage, EmbedderPort, EmbeddingResult
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.embed")

# Euro-micros per token, list prices. Embedding is cheap enough that the point of
# tracking it is spotting a runaway re-index, not accounting.
PRICING_MICRO_EUR_PER_TOKEN: dict[str, float] = {
    "text-embedding-3-small": 0.019,
    "text-embedding-3-large": 0.12,
    "mistral-embed": 0.09,
    "text-embedding-004": 0.0,
}


def _cost_micro_eur(model: str, tokens: int) -> int:
    return int(tokens * PRICING_MICRO_EUR_PER_TOKEN.get(model, 0.0))


def _record(model: str, tokens: int) -> int:
    metrics.llm_tokens_total.labels(model, "embed", "input").inc(tokens)
    cost = _cost_micro_eur(model, tokens)
    metrics.llm_cost_micro_eur_total.labels(model, "embed").inc(cost)
    return cost


class FakeEmbedder(EmbedderPort):
    """Deterministic vectors derived from the text's hash.

    Useful for tests and offline work, and **dangerous in production** — which is
    why `Settings` refuses to start with it outside development. The vectors are
    stable and well-formed, so indexing and retrieval both succeed; they simply
    encode nothing. Semantic search would appear to work and return arbitrary
    notes, and nobody would see an error.

    The one real property it has: identical text embeds identically, so tests can
    assert that re-indexing is a no-op.
    """

    name = "fake"

    def __init__(self, *, model: str = "fake-embed", dimensions: int = 1536) -> None:
        self.model = model
        self.dimensions = dimensions

    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        vectors = tuple(self._vector(text) for text in texts)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            dimensions=self.dimensions,
            usage=AiUsage(model=self.model, input_tokens=sum(len(t) // 4 for t in texts)),
        )

    def _vector(self, text: str) -> tuple[float, ...]:
        seed = hashlib.sha256(text.encode()).digest()
        raw = [
            math.sin((seed[index % len(seed)] + index) * 0.017) for index in range(self.dimensions)
        ]
        # Normalised, so cosine distance behaves like a real embedding space and
        # a test asserting "similar things are closer" is at least well-posed.
        norm = math.sqrt(sum(value * value for value in raw)) or 1.0
        return tuple(value / norm for value in raw)


class OpenAICompatibleEmbedder(EmbedderPort):
    """OpenAI, Mistral, and anything serving the same `/embeddings` route.

    The provider name is a label here, not a behaviour switch. If a future
    provider needs different handling, it gets its own class rather than a branch
    inside this one — a class with five `if self.name ==` branches is a coupling
    with extra steps.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
        name: str = "openai",
        timeout: float = 30.0,
        send_dimensions: bool = True,
    ) -> None:
        self.name = name
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # OpenAI's v3 models accept a `dimensions` parameter (Matryoshka
        # truncation); Mistral and most self-hosted servers reject the unknown
        # field outright, so it is opt-in.
        self._send_dimensions = send_dimensions

    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                vectors=(),
                model=self.model,
                dimensions=self.dimensions,
                usage=AiUsage(model=self.model),
            )

        started = time.perf_counter()
        body: dict[str, Any] = {"model": self.model, "input": texts}
        if self._send_dimensions:
            body["dimensions"] = self.dimensions

        headers = {"content-type": "application/json"}
        # A self-hosted server usually has no key; sending `Bearer ` with an
        # empty credential makes some of them reject the request outright.
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = await _post(
            f"{self._base_url}/embeddings", headers, body, self._timeout, self.name
        )

        # Sorted by index, never by arrival: a provider returning results out of
        # order would attach every vector to the wrong chunk, silently.
        items = sorted(payload.get("data", []), key=lambda item: int(item.get("index", 0)))
        vectors = tuple(tuple(float(value) for value in item["embedding"]) for item in items)
        _assert_batch(vectors, expected=len(texts), provider=self.name)

        tokens = int(payload.get("usage", {}).get("prompt_tokens", 0))
        cost = _record(self.model, tokens)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            dimensions=self.dimensions,
            usage=AiUsage(
                model=self.model,
                input_tokens=tokens,
                cost_micro_eur=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )


class GeminiEmbedder(EmbedderPort):
    """Google Gemini. Different request shape, same contract.

    Gemini distinguishes the *task* a vector is for: a passage being stored and a
    question being asked are embedded differently, and using the wrong one
    measurably hurts recall. `kind` carries that through the port, which is why
    the port has a parameter that three of the four adapters ignore.
    """

    name = "gemini"

    _TASK_TYPES: ClassVar[dict[str, str]] = {
        "document": "RETRIEVAL_DOCUMENT",
        "query": "RETRIEVAL_QUERY",
    }

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        model: str = "text-embedding-004",
        dimensions: int = 768,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                vectors=(),
                model=self.model,
                dimensions=self.dimensions,
                usage=AiUsage(model=self.model),
            )

        started = time.perf_counter()
        task_type = self._TASK_TYPES.get(kind, "RETRIEVAL_DOCUMENT")
        body = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                    "outputDimensionality": self.dimensions,
                }
                for text in texts
            ]
        }

        payload = await _post(
            f"{self._base_url}/models/{self.model}:batchEmbedContents",
            {"content-type": "application/json", "x-goog-api-key": self._api_key},
            body,
            self._timeout,
            self.name,
        )

        # Gemini returns embeddings positionally, with no index field to sort on.
        # The length check below is therefore the only guard against
        # misalignment, which makes it load-bearing rather than defensive.
        vectors = tuple(
            tuple(float(value) for value in item["values"])
            for item in payload.get("embeddings", [])
        )
        _assert_batch(vectors, expected=len(texts), provider=self.name)

        # No usage block in the batch response; estimated so cost tracking is
        # not silently zero for one provider out of four.
        tokens = sum(len(text) // 4 for text in texts)
        cost = _record(self.model, tokens)
        return EmbeddingResult(
            vectors=vectors,
            model=self.model,
            dimensions=self.dimensions,
            usage=AiUsage(
                model=self.model,
                input_tokens=tokens,
                cost_micro_eur=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
            ),
        )


async def _post(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_seconds: float,
    provider: str,
) -> dict[str, Any]:
    """One HTTP call, with the failure taxonomy every adapter shares."""
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        log.error("embed.transport_failed", provider=provider, error=type(exc).__name__)
        raise ExtractionUnavailableError("Service d'embedding injoignable.") from exc

    if response.status_code == 429:
        # Retryable, and the worker's backoff is what handles it. Embedding is
        # never on the user's critical path, so waiting costs nothing visible.
        raise ExtractionUnavailableError("Limite de débit atteinte sur l'embedding.")
    if response.status_code >= 400:
        log.error("embed.failed", provider=provider, status=response.status_code)
        raise ExtractionUnavailableError("Échec de l'embedding.")

    result: dict[str, Any] = response.json()
    return result


def _assert_batch(vectors: tuple[tuple[float, ...], ...], *, expected: int, provider: str) -> None:
    """A batch is all or nothing.

    A short batch is not a partial success to salvage: the caller pairs vectors
    with inputs by position, so `n-1` vectors for `n` texts means every pairing
    after the gap is wrong. Raising here turns a silent corruption into a retry.
    """
    if len(vectors) != expected:
        log.error("embed.batch_mismatch", provider=provider, expected=expected, got=len(vectors))
        raise ExtractionUnavailableError("Réponse d'embedding incomplète.")
