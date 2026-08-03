"""Every prompt in the product, in one place, with an identity.

A prompt is not a string literal buried in the adapter that happens to use it.
It is a **versioned artefact** with the same status as a database migration, for
one blunt reason: when an answer is wrong six weeks from now, the first question
is "what exactly did we send?", and the only honest answer comes from a stored
fingerprint that maps back to text nobody can quietly edit.

So each prompt declares:

* a `name` — stable, referenced by `ai_run.prompt_name`;
* a `version` — bumped whenever the text changes in a way that changes output;
* a `fingerprint` — the hash actually written to every run row.

The registry also makes one safety property *testable rather than hoped for*:
every prompt that interpolates user content must state that the content is data
and not instructions. `tests/unit/test_prompts.py` asserts it for all of them, so
a new prompt cannot be added without an injection guard.

Prompts live outside `app.infra` on purpose. They are provider-neutral text —
the same extraction prompt goes to OpenAI, Claude, Gemini, Llama or Mistral
unchanged. Putting them under an adapter would imply one owns them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# Every prompt handling user text must carry this marker. The phrasing varies —
# the guarantee does not.
INJECTION_GUARD_MARKER = "jamais une instruction"


@dataclass(frozen=True, slots=True)
class Prompt:
    """A versioned instruction block."""

    name: str
    version: int
    system: str
    description: str = ""
    # Prompts that never see user-authored text (there are few) opt out
    # explicitly, so the omission is a decision rather than an oversight.
    handles_user_content: bool = True
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def fingerprint(self) -> str:
        """Hash of the exact text sent, stored on each `ai_run`."""
        return hashlib.sha256(self.system.encode()).hexdigest()[:16]

    @property
    def reference(self) -> str:
        """Human-readable identity for logs: `extract_entities@2`."""
        return f"{self.name}@{self.version}"

    @property
    def has_injection_guard(self) -> bool:
        return INJECTION_GUARD_MARKER in self.system


_REGISTRY: dict[str, Prompt] = {}


def register(prompt: Prompt) -> Prompt:
    """Add a prompt to the registry, refusing duplicates.

    A silently overwritten prompt name is the kind of bug that shows up as
    "the summaries got worse last Tuesday" and takes a day to find.
    """
    if prompt.name in _REGISTRY:
        raise ValueError(f"prompt {prompt.name!r} is already registered")
    _REGISTRY[prompt.name] = prompt
    return prompt


def get(name: str) -> Prompt:
    try:
        return _REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"unknown prompt {name!r}; known: {sorted(_REGISTRY)}") from exc


def all_prompts() -> tuple[Prompt, ...]:
    return tuple(_REGISTRY[name] for name in sorted(_REGISTRY))


def fingerprints() -> dict[str, str]:
    """Name → fingerprint, exposed on the readiness endpoint for support."""
    return {prompt.name: prompt.fingerprint for prompt in all_prompts()}
