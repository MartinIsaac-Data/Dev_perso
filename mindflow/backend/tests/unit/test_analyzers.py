"""LLM adapters (ADR-031, AI.md §4).

The point of these tests is that both providers are held to the *same* contract:
same schema, same refusal handling, same rejection of malformed output.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.domain.analysis import NoteAnalysis, json_schema_for_llm
from app.domain.errors import ExtractionUnavailableError, LlmRefusalError, LlmSchemaViolationError
from app.domain.ports import AnalysisContext
from app.infra.ai.analyzers import AnthropicAnalyzer, FakeAnalyzer, OpenAIAnalyzer

CONTEXT = AnalysisContext(
    timezone="Europe/Paris",
    locale="fr-FR",
    captured_at_local="2026-06-09 11:47",
    weekday="mardi",
    known_projects=("Vinci",),
    known_tags=("budget",),
)

VALID_ANALYSIS = {
    "language": "fr",
    "summary": "Deux actions à mener pour le client Vinci.",
    "tasks": [
        {
            "title": "Rappeler le DAF de Vinci",
            "body": None,
            "due": {"expression": "jeudi", "kind": "due"},
            "priority": "normal",
            "assignee": None,
            "project_hint": "Vinci",
            "confidence": 0.93,
            "source_span": {"start": 0, "end": 45},
        }
    ],
    "ideas": [],
    "notes": [],
    "categories": ["client"],
    "people": ["DAF"],
    "projects": ["Vinci"],
    "tags": ["budget"],
    "dates": [{"expression": "jeudi", "kind": "due"}],
    "priority": "normal",
    "overall_confidence": 0.9,
    "unprocessed_remainder": None,
}


def openai_response(content: dict, *, refusal: bool = False) -> dict:
    message: dict = {"role": "assistant", "content": json.dumps(content)}
    if refusal:
        message = {"role": "assistant", "content": None, "refusal": "I cannot help with that."}
    return {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 350},
    }


def anthropic_response(content: dict, *, stop_reason: str = "end_turn") -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(content)}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 1200, "output_tokens": 350},
    }


# --------------------------------------------------------------------------- #
# Schema — the actual contract
# --------------------------------------------------------------------------- #
def test_schema_is_strict_everywhere() -> None:
    """Providers reject a strict-mode schema that allows extra properties."""

    def check(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(json_schema_for_llm())


def test_the_contract_holds_all_requested_fields() -> None:
    fields = set(NoteAnalysis.model_fields)
    for required in (
        "summary",
        "tasks",
        "ideas",
        "categories",
        "people",
        "projects",
        "tags",
        "dates",
        "priority",
    ):
        assert required in fields


def test_the_model_never_returns_a_resolved_date() -> None:
    """ADR-020: the model reports the wording, the code resolves it."""
    hint = NoteAnalysis.model_validate(VALID_ANALYSIS).tasks[0].due
    assert hint is not None
    assert hint.expression == "jeudi"
    assert not hasattr(hint, "due_at")


# --------------------------------------------------------------------------- #
# OpenAI adapter
# --------------------------------------------------------------------------- #
@respx.mock
async def test_openai_happy_path() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_response(VALID_ANALYSIS))
    )
    analyzer = OpenAIAnalyzer(api_key="sk-test")
    result = await analyzer.analyze("Faut que je rappelle le DAF jeudi", context=CONTEXT)

    assert result.analysis.tasks[0].title == "Rappeler le DAF de Vinci"
    assert result.usage.input_tokens == 1200
    assert result.usage.cost_micro_eur > 0


@respx.mock
async def test_openai_sends_a_strict_json_schema() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_response(VALID_ANALYSIS))
    )
    await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)

    body = json.loads(route.calls[0].request.content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


@respx.mock
async def test_openai_refusal_is_not_retried_and_is_not_an_error_to_the_user() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_response({}, refusal=True))
    )
    with pytest.raises(LlmRefusalError) as exc:
        await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)
    assert exc.value.code == "content_not_processed"


@respx.mock
async def test_openai_malformed_json_is_rejected_not_salvaged() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{not json"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )
    )
    with pytest.raises(LlmSchemaViolationError):
        await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)


@respx.mock
async def test_openai_schema_violation_is_rejected() -> None:
    broken = {**VALID_ANALYSIS, "overall_confidence": 5.0}  # out of range
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_response(broken))
    )
    with pytest.raises(LlmSchemaViolationError):
        await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)


@respx.mock
async def test_openai_rate_limit_maps_to_a_retryable_error() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": "rate limit"})
    )
    with pytest.raises(ExtractionUnavailableError):
        await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)


@respx.mock
async def test_network_failure_maps_to_a_retryable_error() -> None:
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    with pytest.raises(ExtractionUnavailableError):
        await OpenAIAnalyzer(api_key="sk-test").analyze("x", context=CONTEXT)


# --------------------------------------------------------------------------- #
# Anthropic adapter — same contract, different wire format
# --------------------------------------------------------------------------- #
@respx.mock
async def test_anthropic_happy_path() -> None:
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=anthropic_response(VALID_ANALYSIS))
    )
    result = await AnthropicAnalyzer(api_key="sk-ant").analyze("x", context=CONTEXT)
    assert result.analysis.tasks[0].project_hint == "Vinci"


@respx.mock
async def test_anthropic_refusal_is_read_from_stop_reason_not_the_status_code() -> None:
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200, json=anthropic_response(VALID_ANALYSIS, stop_reason="refusal")
        )
    )
    with pytest.raises(LlmRefusalError):
        await AnthropicAnalyzer(api_key="sk-ant").analyze("x", context=CONTEXT)


@respx.mock
async def test_both_providers_produce_the_same_domain_object() -> None:
    """The whole point of the port: the caller cannot tell them apart."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=openai_response(VALID_ANALYSIS))
    )
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json=anthropic_response(VALID_ANALYSIS))
    )
    a = await OpenAIAnalyzer(api_key="k").analyze("x", context=CONTEXT)
    b = await AnthropicAnalyzer(api_key="k").analyze("x", context=CONTEXT)
    assert a.analysis == b.analysis


async def test_fake_analyzer_is_usable_without_network() -> None:
    result = await FakeAnalyzer().analyze("une note quelconque", context=CONTEXT)
    assert result.analysis.summary
    assert result.usage.model == "fake"
