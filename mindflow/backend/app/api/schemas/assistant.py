"""Request and response shapes for the AI layer (API.md §5.7).

Every generated answer carries its citations and its plan notes. That is a
product decision expressed in the schema rather than left to the client: a
client *could* choose not to render them, but it cannot be given an answer that
never had them. An assistant whose sources are optional at the protocol level
becomes an assistant with no sources within two releases.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None
    # Client-generated, same contract as `client_capture_id` (ADR-009): a phone
    # retrying on a flaky connection must not ask — or pay — twice.
    client_message_id: str | None = Field(default=None, max_length=64)


class CitationView(BaseModel):
    ref: str
    entry_id: uuid.UUID | None = None
    capture_id: uuid.UUID | None = None
    title: str
    excerpt: str
    occurred_at: str | None = None
    score: float = 0.0


class AnswerView(BaseModel):
    text: str
    intent: str
    citations: list[CitationView] = Field(default_factory=list)
    # How the answer was produced, in French, for display under it.
    notes: list[str] = Field(default_factory=list)
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    latency_ms: int = 0
    # False for the structured routes. The client shows those instantly instead
    # of running a typing animation over an answer that is already complete.
    used_model: bool = False
    refused: bool = False


class ConversationView(BaseModel):
    id: uuid.UUID
    title: str | None = None
    message_count: int = 0
    last_message_at: datetime | None = None
    created_at: datetime


class MessageView(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    intent: str | None = None
    citations: list[CitationView] = Field(default_factory=list)
    created_at: datetime


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    entry_types: list[str] = Field(default_factory=list, max_length=8)


class PassageView(BaseModel):
    chunk_id: uuid.UUID
    text: str
    title: str
    entry_id: uuid.UUID | None = None
    capture_id: uuid.UUID | None = None
    occurred_at: str | None = None
    # Which retrievers found it. Shown in the UI as "trouvé par sens + mots" —
    # agreement between the two is a much stronger signal than either alone, and
    # saying so helps users calibrate their trust.
    found_by: list[str] = Field(default_factory=list)
    score: float = 0.0


class SemanticSearchResponse(BaseModel):
    passages: list[PassageView]
    took_ms: int
    lexical_count: int = 0
    semantic_count: int = 0
    notes: list[str] = Field(default_factory=list)


class EntityView(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    name: str
    detail: str | None = None
    mention_count: int = 0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class EntityMentionView(BaseModel):
    id: uuid.UUID
    entry_id: uuid.UUID | None = None
    capture_id: uuid.UUID | None = None
    role: str | None = None
    confidence: float | None = None
    occurred_at: datetime | None = None


class ThemeView(BaseModel):
    kind: str
    label: str
    name: str
    count: int
    last_seen_at: datetime | None = None


class DigestView(BaseModel):
    id: uuid.UUID
    period: str
    period_start: date
    period_end: date
    content: str
    stats: dict[str, int] = Field(default_factory=dict)
    entry_count: int = 0
    read_at: datetime | None = None
    created_at: datetime


class GenerateDigestRequest(BaseModel):
    period: str = Field(pattern="^(daily|weekly|monthly)$")
    # Any day inside the wanted period; the service snaps to its boundaries.
    anchor: date | None = None
    force: bool = False


class MemoryView(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    statement: str
    confidence: float
    confirmed_at: datetime
    # How much this memory still counts, after decay. Surfaced so a user can
    # see that the assistant treats a fact from March differently from one
    # confirmed yesterday.
    weight: float = 1.0


class IndexStatusView(BaseModel):
    total_chunks: int
    pending_chunks: int
    embedding_model: str | None = None
    dimensions: int = 0
    provider: str = "none"
