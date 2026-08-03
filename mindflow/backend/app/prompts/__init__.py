"""Every prompt the product sends to a language model.

One folder, deliberately. Prompts used to live next to the adapter that sent
them, which quietly implied that the OpenAI adapter *owned* the extraction
prompt — untrue, and actively misleading once phase 3 made the provider
interchangeable (ADR-043). The same text goes to OpenAI, Claude, Gemini, Llama
and Mistral without modification; it belongs to the product, not to a vendor.

Importing this package registers all prompts, so `registry.all_prompts()` is
complete and the safety tests in `tests/unit/test_prompts.py` see every one of
them. That is the reason for the eager imports below: a prompt that is only
imported lazily is a prompt that never gets checked for an injection guard.
"""

from __future__ import annotations

from app.prompts import answer, digest, entities, extraction, insights, memory
from app.prompts.registry import Prompt, all_prompts, fingerprints, get, register

__all__ = [
    "Prompt",
    "all_prompts",
    "answer",
    "digest",
    "entities",
    "extraction",
    "fingerprints",
    "get",
    "insights",
    "memory",
    "register",
]
