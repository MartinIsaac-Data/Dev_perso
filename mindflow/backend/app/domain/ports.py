"""Ports — the abstract boundaries the domain owns and infrastructure implements.

Every AI boundary goes through a port (AI.md, I1): a model is a replaceable
component, not a foundation. Swapping Whisper for another engine, or OpenAI for
Anthropic, is an adapter change and touches nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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
