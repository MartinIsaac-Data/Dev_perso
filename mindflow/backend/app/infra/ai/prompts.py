"""Compatibility shim — the prompts now live in `app.prompts`.

Phase 3 gave every prompt in the product a single home (`app/prompts/`), because
prompts are provider-neutral text and keeping them under one adapter's package
implied that adapter owned them. This module stays so that phase 1 and phase 2
callers keep working unchanged: same names, same text, same fingerprint.

New code should import from `app.prompts.extraction` directly.
"""

from __future__ import annotations

from app.prompts.extraction import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_context_block,
    build_transcript_block,
    prompt_fingerprint,
)

__all__ = [
    "PROMPT_NAME",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "build_context_block",
    "build_transcript_block",
    "prompt_fingerprint",
]
