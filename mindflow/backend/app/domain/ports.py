"""Ports — the abstract boundaries the domain owns and infrastructure implements.

Every AI boundary goes through a port (AI.md, I1): a model is a replaceable
component, not a foundation. Swapping Whisper for another engine, or OpenAI for
Anthropic, is an adapter change and touches nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.analysis import NoteAnalysis


# --------------------------------------------------------------------------- #
# Transcription
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class TranscriptionSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    speaker_label: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str
    confidence: float | None
    engine: str
    engine_version: str
    duration_ms: int
    segments: tuple[TranscriptionSegment, ...] = ()
    is_fallback: bool = False
    words: list[dict[str, Any]] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class TranscriberPort(ABC):
    """Audio bytes in, text out."""

    name: str = "unknown"

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        *,
        media_type: str,
        language_hint: str | None = None,
    ) -> TranscriptionResult: ...

    async def health(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Analysis (LLM)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Everything the model needs about the user, and nothing more.

    Deliberately excludes identity: no email, no user id, no other user's data
    (AI.md §10.1).
    """

    timezone: str
    locale: str
    captured_at_local: str
    weekday: str
    known_projects: tuple[str, ...] = ()
    known_tags: tuple[str, ...] = ()
    recent_titles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AiUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_micro_eur: int = 0
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis: NoteAnalysis
    usage: AiUsage
    prompt_name: str
    prompt_version: int


class AnalyzerPort(ABC):
    """Transcript in, strongly-typed JSON out."""

    name: str = "unknown"

    @abstractmethod
    async def analyze(self, transcript: str, *, context: AnalysisContext) -> AnalysisResult: ...

    async def health(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Object storage
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class SignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    expires_at: str
    object_key: str


class ObjectStoragePort(ABC):
    """Audio never transits through the API (ADR-018): clients PUT to a signed
    URL and GET from another one."""

    @abstractmethod
    async def signed_upload(
        self, object_key: str, *, media_type: str, max_bytes: int
    ) -> SignedUpload: ...

    @abstractmethod
    async def signed_download(self, object_key: str) -> str: ...

    @abstractmethod
    async def download(self, object_key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, object_key: str) -> None: ...

    @abstractmethod
    async def exists(self, object_key: str) -> bool: ...


# --------------------------------------------------------------------------- #
# Task queue
# --------------------------------------------------------------------------- #
class TaskQueuePort(Protocol):
    """Kept behind a port so tests run the pipeline inline (no Redis) while
    production uses arq (ADR-006)."""

    async def enqueue(self, job: str, *args: Any, **kwargs: Any) -> str | None: ...


# --------------------------------------------------------------------------- #
# Push delivery (Phase 2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class PushMessage:
    """What actually reaches a device.

    Deliberately small. A push is a *pointer* — a title, a line, and enough
    identity to open the right screen — never a copy of the content. Two reasons,
    and both are load-bearing: push payloads transit a third party (ADR-039), and
    a notification that duplicates the data ages badly the moment the user edits
    it.
    """

    title: str
    body: str
    # Opaque to the transport; the client routes on it.
    data: dict[str, str]
    # Used by every provider to replace an earlier notification about the same
    # subject instead of stacking a second one on the lock screen.
    collapse_key: str | None = None
    badge: int | None = None


@dataclass(frozen=True, slots=True)
class PushResult:
    delivered: int
    # Tokens the provider reported as permanently dead. The caller retires them:
    # a token that will never work again must not be retried forever.
    invalid_tokens: tuple[str, ...] = ()
    retryable_tokens: tuple[str, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class PushSenderPort(ABC):
    """One port, several providers (FCM, WNS, and a fake for tests).

    The dispatcher never learns which one it is talking to — that is what makes
    "add Windows support" a new adapter rather than a new branch in the
    scheduler.
    """

    name: str = "push"

    @abstractmethod
    async def send(self, tokens: list[str], message: PushMessage) -> PushResult: ...

    async def health(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Embeddings (Phase 3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors, plus what it cost to make them.

    `dimensions` travels with the result rather than being assumed: a store that
    silently accepts a 768-vector into a 1024-column, or compares vectors made by
    two different models, returns nonsense that looks like a ranking. The caller
    checks.
    """

    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimensions: int
    usage: AiUsage

    def __post_init__(self) -> None:
        for vector in self.vectors:
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"embedding of {len(vector)} dimensions, expected {self.dimensions}"
                )


class EmbedderPort(ABC):
    """Text in, vectors out.

    Batched by construction: every provider charges and rate-limits per request,
    and embedding a hundred chunks one at a time is a hundred round trips for
    work that costs the same in one.
    """

    name: str = "unknown"
    model: str = "unknown"
    dimensions: int = 0

    @abstractmethod
    async def embed(self, texts: list[str], *, kind: str = "document") -> EmbeddingResult:
        """Embed a batch.

        `kind` is `document` or `query`. Several families (E5, BGE, Gemini) score
        materially better when the two are prefixed differently, and a provider
        that ignores the distinction simply ignores the argument.
        """

    async def health(self) -> bool:
        return True


# --------------------------------------------------------------------------- #
# Chat (Phase 3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One turn. `role` is `system`, `user` or `assistant`.

    Deliberately not a provider's message type: OpenAI, Anthropic and Gemini each
    shape this differently — content blocks, `parts`, a separate `system`
    parameter — and letting any one of those shapes reach the service layer is
    how a codebase acquires a favourite vendor.
    """

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: tuple[ChatMessage, ...]
    system: str | None = None
    temperature: float = 0.2
    max_output_tokens: int = 1200
    # A JSON schema when the caller needs a typed answer. Providers that support
    # constrained decoding use it; the others get it appended to the system
    # prompt and their output is validated the same way either side.
    json_schema: dict[str, Any] | None = None
    stop: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatChunk:
    """A streamed fragment. `done` marks the final one, which carries the usage."""

    text: str = ""
    done: bool = False
    usage: AiUsage | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ChatResponse:
    text: str
    usage: AiUsage
    finish_reason: str = "stop"
    # True when the model declined. A refusal is a legitimate outcome, not an
    # error: the caller degrades the answer rather than retrying (ADR-030).
    refused: bool = False


class ChatPort(ABC):
    """A conversation with a model. One interface, five providers.

    Streaming is the primary method and `complete` is derived from it, not the
    other way round: an assistant that shows nothing for eight seconds feels
    broken even when it is fast, and a provider that cannot stream is a provider
    whose adapter yields one chunk.
    """

    name: str = "unknown"
    model: str = "unknown"
    supports_json_schema: bool = False

    @abstractmethod
    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Collect a stream into one response.

        Implemented here rather than per adapter so that five providers cannot
        drift into five subtly different notions of when an answer is finished.
        """
        parts: list[str] = []
        usage = AiUsage(model=self.model)
        finish = "stop"
        async for chunk in self.stream(request):
            parts.append(chunk.text)
            if chunk.done:
                usage = chunk.usage or usage
                finish = chunk.finish_reason or finish
        return ChatResponse(
            text="".join(parts),
            usage=usage,
            finish_reason=finish,
            # Every adapter normalises its provider's decline signal to this one
            # word, so the caller never learns which provider refused.
            refused=finish == "refusal",
        )

    async def health(self) -> bool:
        return True
