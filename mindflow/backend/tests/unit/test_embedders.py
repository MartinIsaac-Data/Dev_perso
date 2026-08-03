"""Embedding adapters, held to one contract across four providers.

Two tests here are worth more than the rest combined.

`test_results_are_ordered_by_index_not_by_arrival` protects against the failure
that has no symptom: a provider returning results out of order attaches every
vector to the wrong chunk. Nothing raises, nothing logs, and search becomes
random in a way that looks like "the model isn't very good".

`test_a_short_batch_is_refused` protects against the same corruption arriving by
a different route. Both are silent, both are permanent until re-indexed, and
both are invisible in staging with small data.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.domain.errors import ExtractionUnavailableError
from app.infra.ai.embedders import FakeEmbedder, GeminiEmbedder, OpenAICompatibleEmbedder

OPENAI_URL = "https://api.openai.com/v1/embeddings"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents"
)


def _openai_embedder(dimensions: int = 4, **kwargs: object) -> OpenAICompatibleEmbedder:
    return OpenAICompatibleEmbedder(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="text-embedding-3-small",
        dimensions=dimensions,
        **kwargs,  # type: ignore[arg-type]
    )


def _openai_payload(*vectors: list[float]) -> dict[str, object]:
    return {
        "data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)],
        "usage": {"prompt_tokens": 12},
    }


class TestFakeEmbedder:
    @pytest.mark.asyncio
    async def test_identical_text_embeds_identically(self) -> None:
        # What makes "re-indexing unchanged text is a no-op" testable.
        embedder = FakeEmbedder(dimensions=8)
        first = await embedder.embed(["Rappeler le DAF"])
        second = await embedder.embed(["Rappeler le DAF"])
        assert first.vectors == second.vectors

    @pytest.mark.asyncio
    async def test_different_text_embeds_differently(self) -> None:
        embedder = FakeEmbedder(dimensions=8)
        result = await embedder.embed(["Rappeler le DAF", "Acheter du café"])
        assert result.vectors[0] != result.vectors[1]

    @pytest.mark.asyncio
    async def test_vectors_have_the_declared_width(self) -> None:
        result = await FakeEmbedder(dimensions=32).embed(["x"])
        assert len(result.vectors[0]) == 32

    @pytest.mark.asyncio
    async def test_vectors_are_normalised(self) -> None:
        result = await FakeEmbedder(dimensions=16).embed(["x"])
        norm = sum(value * value for value in result.vectors[0]) ** 0.5
        assert norm == pytest.approx(1.0)


class TestOpenAICompatible:
    @pytest.mark.asyncio
    @respx.mock
    async def test_embeds_a_batch(self) -> None:
        route = respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0, 0, 0], [0, 1.0, 0, 0]))
        )
        result = await _openai_embedder().embed(["a", "b"])

        assert len(result.vectors) == 2
        assert result.vectors[0] == (1.0, 0.0, 0.0, 0.0)
        assert result.model == "text-embedding-3-small"
        assert result.usage.input_tokens == 12
        assert route.calls[0].request.read().decode().count('"input"') == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_results_are_ordered_by_index_not_by_arrival(self) -> None:
        # The corruption with no symptom: every vector attached to the wrong
        # chunk, no error, search silently randomised.
        respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0, 1.0, 0, 0]},
                        {"index": 0, "embedding": [1.0, 0, 0, 0]},
                    ],
                    "usage": {"prompt_tokens": 4},
                },
            )
        )
        result = await _openai_embedder().embed(["first", "second"])
        assert result.vectors[0] == (1.0, 0.0, 0.0, 0.0)

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_short_batch_is_refused(self) -> None:
        respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0, 0, 0]))
        )
        with pytest.raises(ExtractionUnavailableError):
            await _openai_embedder().embed(["a", "b"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_wrong_width_is_refused(self) -> None:
        # A configuration error must surface here, not as a Postgres type error
        # three layers down.
        respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0]))
        )
        with pytest.raises(ValueError, match="dimensions"):
            await _openai_embedder().embed(["a"])

    @pytest.mark.asyncio
    async def test_an_empty_batch_costs_nothing_and_calls_nobody(self) -> None:
        # The indexing worker legitimately finds nothing to do.
        result = await _openai_embedder().embed([])
        assert result.vectors == ()
        assert result.usage.input_tokens == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_rate_limiting_is_reported_as_unavailable_so_the_worker_retries(self) -> None:
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(429, json={}))
        with pytest.raises(ExtractionUnavailableError):
            await _openai_embedder().embed(["a"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_transport_failure_is_reported_as_unavailable(self) -> None:
        respx.post(OPENAI_URL).mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(ExtractionUnavailableError):
            await _openai_embedder().embed(["a"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_dimensions_parameter_is_sent_when_supported(self) -> None:
        route = respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0, 0, 0]))
        )
        await _openai_embedder().embed(["a"])
        assert b'"dimensions"' in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_dimensions_parameter_is_omitted_when_not(self) -> None:
        # Mistral rejects the unknown field rather than ignoring it, so sending
        # it would make every request fail.
        route = respx.post("https://api.mistral.ai/v1/embeddings").mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0, 0, 0]))
        )
        embedder = OpenAICompatibleEmbedder(
            name="mistral",
            api_key="k",
            base_url="https://api.mistral.ai/v1",
            model="mistral-embed",
            dimensions=4,
            send_dimensions=False,
        )
        await embedder.embed(["a"])
        assert b'"dimensions"' not in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_self_hosted_server_gets_no_authorization_header(self) -> None:
        # Sending `Bearer ` with an empty credential makes some local servers
        # reject the request outright.
        route = respx.post("http://localhost:11434/v1/embeddings").mock(
            return_value=httpx.Response(200, json=_openai_payload([1.0, 0, 0, 0]))
        )
        embedder = OpenAICompatibleEmbedder(
            name="llama",
            api_key="",
            base_url="http://localhost:11434/v1",
            model="nomic-embed-text",
            dimensions=4,
            send_dimensions=False,
        )
        await embedder.embed(["a"])
        assert "authorization" not in route.calls[0].request.headers


class TestGemini:
    def _embedder(self) -> GeminiEmbedder:
        return GeminiEmbedder(api_key="key", model="text-embedding-004", dimensions=4)

    @pytest.mark.asyncio
    @respx.mock
    async def test_embeds_a_batch(self) -> None:
        respx.post(GEMINI_URL).mock(
            return_value=httpx.Response(
                200,
                json={"embeddings": [{"values": [1.0, 0, 0, 0]}, {"values": [0, 1.0, 0, 0]}]},
            )
        )
        result = await self._embedder().embed(["a", "b"])
        assert result.vectors[0] == (1.0, 0.0, 0.0, 0.0)
        assert result.dimensions == 4

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_query_is_embedded_for_the_query_task(self) -> None:
        # Gemini embeds a stored passage and an asked question differently, and
        # using the wrong task type measurably hurts recall.
        route = respx.post(GEMINI_URL).mock(
            return_value=httpx.Response(200, json={"embeddings": [{"values": [1.0, 0, 0, 0]}]})
        )
        await self._embedder().embed(["a"], kind="query")
        assert b"RETRIEVAL_QUERY" in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_document_is_embedded_for_the_document_task(self) -> None:
        route = respx.post(GEMINI_URL).mock(
            return_value=httpx.Response(200, json={"embeddings": [{"values": [1.0, 0, 0, 0]}]})
        )
        await self._embedder().embed(["a"])
        assert b"RETRIEVAL_DOCUMENT" in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_short_batch_is_refused(self) -> None:
        # Gemini returns embeddings positionally with no index to sort on, so
        # the length check is the only guard against misalignment.
        respx.post(GEMINI_URL).mock(
            return_value=httpx.Response(200, json={"embeddings": [{"values": [1.0, 0, 0, 0]}]})
        )
        with pytest.raises(ExtractionUnavailableError):
            await self._embedder().embed(["a", "b"])

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_failure_is_reported_as_unavailable(self) -> None:
        respx.post(GEMINI_URL).mock(return_value=httpx.Response(500, json={}))
        with pytest.raises(ExtractionUnavailableError):
            await self._embedder().embed(["a"])

    @pytest.mark.asyncio
    async def test_an_empty_batch_calls_nobody(self) -> None:
        assert (await self._embedder().embed([])).vectors == ()
