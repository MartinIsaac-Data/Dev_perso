"""The boundary between this application and a language model.

One protocol, three implementations: the real Anthropic client, a stub that
returns canned responses for tests, and a recording client that captures real
responses so they can be replayed later.

The protocol exists so that everything interesting — assembling the context,
validating the output, persisting the result — is testable without a network
call, a key, or a bill. The only untestable part is the HTTP request itself,
which is exactly the part with no logic in it.

Structured output is obtained through a forced tool call rather than by asking
for JSON in the prompt and parsing the reply. The model then cannot return
prose, an apology or a markdown fence around the object, and the schema is
enforced by the API rather than by a regular expression at this end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_settings


class AgentError(RuntimeError):
    """Anything that stops an agent producing a usable result."""


class AgentNotConfigured(AgentError):
    """No API key. Raised early, with an instruction rather than a stack trace."""


@dataclass(frozen=True)
class LlmResponse:
    data: dict[str, Any]
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 8000,
    ) -> LlmResponse: ...


class AnthropicClient:
    """The real thing. Imported lazily so the application runs without the SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        key = api_key or settings.anthropic_api_key
        if not key:
            raise AgentNotConfigured(
                "No Anthropic API key. Set TOS_ANTHROPIC_API_KEY in .env "
                "(or ANTHROPIC_API_KEY in the environment) to run agents."
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise AgentNotConfigured(
                "The anthropic package is not installed. Run: pip install -e '.[agents]'"
            ) from exc
        self._client = Anthropic(api_key=key)

    def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 8000,
    ) -> LlmResponse:
        tool_name = "record_result"
        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[
                    {
                        "name": tool_name,
                        "description": "Record the structured result. The only way to answer.",
                        "input_schema": json_schema,
                    }
                ],
                # Forcing the tool removes every failure mode where the model
                # replies in prose instead of the schema.
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as AgentError
            raise AgentError(f"the model call failed: {exc}") from exc

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                return LlmResponse(
                    data=dict(block.input),
                    input_tokens=getattr(message.usage, "input_tokens", None),
                    output_tokens=getattr(message.usage, "output_tokens", None),
                )
        raise AgentError("the model returned no tool call despite tool_choice being forced")


class StubClient:
    """Returns prepared responses. The whole test suite runs against this.

    It records every call, so a test can assert on what the agent was actually
    asked — which is where the interesting bugs live. A context assembler that
    silently omits the review rubric produces a plausible but ungrounded
    critique, and no assertion on the *output* would catch it.
    """

    def __init__(self, responses: list[dict[str, Any]] | dict[str, Any]) -> None:
        self._responses = [responses] if isinstance(responses, dict) else list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        model: str,
        max_tokens: int = 8000,
    ) -> LlmResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "json_schema": json_schema,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if not self._responses:
            raise AgentError("StubClient ran out of prepared responses")
        return LlmResponse(data=self._responses.pop(0), input_tokens=100, output_tokens=200)


class FailingClient:
    """Raises. Used to prove the failure path is recorded rather than swallowed."""

    def __init__(self, message: str = "upstream exploded") -> None:
        self._message = message

    def complete(self, **_: Any) -> LlmResponse:
        raise AgentError(self._message)


def default_client() -> LlmClient:
    return AnthropicClient()
