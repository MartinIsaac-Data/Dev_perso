"""Agents: critique, extraction and structuring. Never authoring.

No prompt in this package asks a model to write a business case, an article or
a solution design. The review board attacks a case somebody else wrote; the
extractor turns an advert into rows; the periodic review reports what the
numbers show. A portfolio of work an agent produced is not a portfolio, and
the whole system exists to build one that is.
"""

from app.services.agents.client import (
    AgentError,
    AgentNotConfigured,
    AnthropicClient,
    FailingClient,
    LlmClient,
    LlmResponse,
    StubClient,
    default_client,
)
from app.services.agents.runner import Prompt, load_prompt, run_agent, verify_prompt

__all__ = [
    "AgentError",
    "AgentNotConfigured",
    "AnthropicClient",
    "FailingClient",
    "LlmClient",
    "LlmResponse",
    "Prompt",
    "StubClient",
    "default_client",
    "load_prompt",
    "run_agent",
    "verify_prompt",
]
