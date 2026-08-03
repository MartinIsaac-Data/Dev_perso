"""Chat adapters: five providers, one contract.

Each provider gets the same three questions asked of it — does it stream text,
does it report usage, does it normalise a refusal — because the point of the
port is that the assistant above it cannot tell which one it is talking to. If
one adapter reports a refusal as an exception and another as a finish reason,
the assistant has to know the difference, and the abstraction has bought
nothing.

`TestTheSameContract` is the file's real subject: it runs the same assertions
against every adapter rather than trusting three separate near-identical tests
to stay in step.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import ChatMessage, ChatRequest
from app.infra.ai.chat import AnthropicChat, FakeChat, GeminiChat, OpenAICompatibleChat

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent"
)

REQUEST = ChatRequest(
    messages=(ChatMessage(role="user", content="Que dois-je faire aujourd'hui ?"),),
    system="Tu es un assistant.",
)


def _sse(*frames: str) -> str:
    return "".join(f"data: {frame}\n\n" for frame in frames)


def _openai_stream(*, finish: str = "stop") -> str:
    return _sse(
        '{"choices":[{"delta":{"content":"Deux "},"finish_reason":null}]}',
        '{"choices":[{"delta":{"content":"tâches."},"finish_reason":null}]}',
        f'{{"choices":[{{"delta":{{}},"finish_reason":"{finish}"}}]}}',
        '{"choices":[],"usage":{"prompt_tokens":120,"completion_tokens":8}}',
        "[DONE]",
    )


def _anthropic_stream(*, stop_reason: str = "end_turn") -> str:
    return _sse(
        '{"type":"message_start","message":{"usage":{"input_tokens":120,'
        '"cache_read_input_tokens":90,"cache_creation_input_tokens":30}}}',
        '{"type":"content_block_delta","delta":{"text":"Deux "}}',
        '{"type":"content_block_delta","delta":{"text":"tâches."}}',
        f'{{"type":"message_delta","delta":{{"stop_reason":"{stop_reason}"}},'
        f'"usage":{{"output_tokens":8}}}}',
    )


def _gemini_stream(*, finish: str = "STOP") -> str:
    return _sse(
        '{"candidates":[{"content":{"parts":[{"text":"Deux "}]}}]}',
        '{"candidates":[{"content":{"parts":[{"text":"tâches."}]}}]}',
        f'{{"candidates":[{{"finishReason":"{finish}","content":{{"parts":[]}}}}],'
        f'"usageMetadata":{{"promptTokenCount":120,"candidatesTokenCount":8}}}}',
    )


def _openai() -> OpenAICompatibleChat:
    return OpenAICompatibleChat(
        api_key="sk-test", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    )


def _anthropic() -> AnthropicChat:
    return AnthropicChat(api_key="key", model="claude-opus-5")


def _gemini() -> GeminiChat:
    return GeminiChat(api_key="key", model="gemini-2.0-flash")


class TestFakeChat:
    @pytest.mark.asyncio
    async def test_streams_word_by_word(self) -> None:
        # The fake exercises the same assembly path production uses; one that
        # returned the whole string would leave that path untested.
        chunks = [chunk async for chunk in FakeChat(reply="un deux trois").stream(REQUEST)]
        assert len([chunk for chunk in chunks if chunk.text]) == 3

    @pytest.mark.asyncio
    async def test_complete_reassembles_the_stream(self) -> None:
        response = await FakeChat(reply="un deux trois").complete(REQUEST)
        assert response.text.strip() == "un deux trois"

    @pytest.mark.asyncio
    async def test_records_the_request_for_assertions(self) -> None:
        chat = FakeChat()
        await chat.complete(REQUEST)
        assert chat.last_request is not None
        assert chat.last_request.system == "Tu es un assistant."


class TestOpenAICompatible:
    @pytest.mark.asyncio
    @respx.mock
    async def test_streams_and_reports_usage(self) -> None:
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text=_openai_stream()))
        response = await _openai().complete(REQUEST)

        assert response.text == "Deux tâches."
        assert response.usage.input_tokens == 120
        assert response.usage.output_tokens == 8
        assert not response.refused

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_usage_only_frame_does_not_crash_on_empty_choices(self) -> None:
        # The terminal frame carries usage and an empty `choices`; indexing into
        # it before checking would fail on every single call.
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text=_openai_stream()))
        assert (await _openai().complete(REQUEST)).usage.input_tokens == 120

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_system_prompt_is_sent_as_a_system_message(self) -> None:
        route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text=_openai_stream()))
        await _openai().complete(REQUEST)
        assert b'{"role":"system","content":"Tu es un assistant."}' in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_usage_is_requested_explicitly(self) -> None:
        # Without `stream_options`, every run records as costing nothing.
        route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text=_openai_stream()))
        await _openai().complete(REQUEST)
        assert b"stream_options" in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_content_filter_is_a_refusal_not_an_error(self) -> None:
        respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, text=_openai_stream(finish="content_filter"))
        )
        response = await _openai().complete(REQUEST)
        assert response.refused

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_self_hosted_server_gets_no_authorization_header(self) -> None:
        route = respx.post("http://localhost:11434/v1/chat/completions").mock(
            return_value=httpx.Response(200, text=_openai_stream())
        )
        chat = OpenAICompatibleChat(
            name="llama", api_key="", base_url="http://localhost:11434/v1", model="llama3.1"
        )
        await chat.complete(REQUEST)
        assert "authorization" not in route.calls[0].request.headers


class TestAnthropic:
    @pytest.mark.asyncio
    @respx.mock
    async def test_streams_and_reports_usage_including_cache(self) -> None:
        respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(200, text=_anthropic_stream()))
        response = await _anthropic().complete(REQUEST)

        assert response.text == "Deux tâches."
        assert response.usage.input_tokens == 120
        assert response.usage.output_tokens == 8
        assert response.usage.cache_read_tokens == 90
        assert response.usage.cache_write_tokens == 30

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_system_prompt_is_marked_cacheable(self) -> None:
        # It is identical on every turn of every conversation — exactly what
        # prefix caching exists for.
        route = respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, text=_anthropic_stream())
        )
        await _anthropic().complete(REQUEST)
        assert b"cache_control" in route.calls[0].request.read()

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_refusal_stop_reason_is_normalised(self) -> None:
        respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, text=_anthropic_stream(stop_reason="refusal"))
        )
        assert (await _anthropic().complete(REQUEST)).refused

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_mid_stream_error_event_fails_loudly(self) -> None:
        respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, text=_sse('{"type":"error","error":{}}'))
        )
        with pytest.raises(ExtractionUnavailableError):
            await _anthropic().complete(REQUEST)


class TestGemini:
    @pytest.mark.asyncio
    @respx.mock
    async def test_streams_and_reports_usage(self) -> None:
        respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream())
        )
        response = await _gemini().complete(REQUEST)

        assert response.text == "Deux tâches."
        assert response.usage.input_tokens == 120
        assert response.usage.output_tokens == 8

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_sent_events_are_requested_explicitly(self) -> None:
        # Without `alt=sse` the response is one JSON array that cannot be
        # consumed incrementally — technically streaming, practically not.
        route = respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream())
        )
        await _gemini().complete(REQUEST)
        assert "alt=sse" in str(route.calls[0].request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_the_assistant_role_is_translated_to_gemini_vocabulary(self) -> None:
        # Gemini calls it "model"; the port's vocabulary does not bend to one
        # provider's naming.
        route = respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream())
        )
        await _gemini().complete(
            ChatRequest(
                messages=(
                    ChatMessage(role="user", content="a"),
                    ChatMessage(role="assistant", content="b"),
                )
            )
        )
        body = route.calls[0].request.read()
        assert b'"model"' in body
        assert b'"assistant"' not in body

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_safety_block_is_normalised_to_a_refusal(self) -> None:
        respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream(finish="SAFETY"))
        )
        assert (await _gemini().complete(REQUEST)).refused


class TestTheSameContract:
    """The point of the port: three adapters, indistinguishable from above."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_every_provider_produces_the_same_answer_and_usage(self) -> None:
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, text=_openai_stream()))
        respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(200, text=_anthropic_stream()))
        respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream())
        )

        for chat in (_openai(), _anthropic(), _gemini()):
            response = await chat.complete(REQUEST)
            assert response.text == "Deux tâches.", chat.name
            assert response.usage.input_tokens == 120, chat.name
            assert response.usage.output_tokens == 8, chat.name
            assert response.finish_reason, chat.name

    @pytest.mark.asyncio
    @respx.mock
    async def test_every_provider_reports_a_refusal_the_same_way(self) -> None:
        respx.post(OPENAI_URL).mock(
            return_value=httpx.Response(200, text=_openai_stream(finish="content_filter"))
        )
        respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, text=_anthropic_stream(stop_reason="refusal"))
        )
        respx.post(url__startswith=GEMINI_URL).mock(
            return_value=httpx.Response(200, text=_gemini_stream(finish="SAFETY"))
        )

        for chat in (_openai(), _anthropic(), _gemini()):
            # A value, never an exception: the assistant shows the decline as an
            # answer rather than turning it into an error page and a retry.
            assert (await chat.complete(REQUEST)).refused, chat.name

    @pytest.mark.asyncio
    @respx.mock
    async def test_every_provider_reports_rate_limiting_the_same_way(self) -> None:
        respx.post(OPENAI_URL).mock(return_value=httpx.Response(429, json={}))
        respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(429, json={}))
        respx.post(url__startswith=GEMINI_URL).mock(return_value=httpx.Response(429, json={}))

        for chat in (_openai(), _anthropic(), _gemini()):
            with pytest.raises(ExtractionUnavailableError):
                await chat.complete(REQUEST)

    @pytest.mark.asyncio
    @respx.mock
    async def test_every_provider_reports_a_transport_failure_the_same_way(self) -> None:
        respx.post(OPENAI_URL).mock(side_effect=httpx.ConnectError("down"))
        respx.post(ANTHROPIC_URL).mock(side_effect=httpx.ConnectError("down"))
        respx.post(url__startswith=GEMINI_URL).mock(side_effect=httpx.ConnectError("down"))

        for chat in (_openai(), _anthropic(), _gemini()):
            with pytest.raises(ExtractionUnavailableError):
                await chat.complete(REQUEST)
