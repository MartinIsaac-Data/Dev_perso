"""Tables for the AI layer (Phase 3): chunks, entities, conversations, memory,
digests.

A separate module from `core.py` for one reason worth stating: these tables are
*derived*. Every row here can be rebuilt from the captures and entries in
`core.py`, and none of them is a source of truth. That distinction matters
operationally — a corrupt chunk table is a re-index, a corrupt entry table is a
restore — and putting them in the same file would blur it.

Two decisions here shape everything downstream:

**Chunks belong to exactly one source.** A chunk either comes from an entry or
from a transcript, never both, enforced by a check constraint. The alternative —
one nullable pair with no constraint — makes every citation query a case
analysis, and makes "which rows does deleting a capture remove?" unanswerable
without reading the application.

**Embeddings from different models are not comparable.** `chunk.embedding` is a
fixed-width `vector(N)`, so the column's width is a deployment decision
(ADR-045). Recording `embedding_model` on the row is not bookkeeping: queries
filter on it, because mixing two models' vectors in one search returns results
ranked by nothing at all.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

# Aliased: `Chunk.text` is a column, and an unaliased import would be shadowed
# by it inside the class body.
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.infra.db.models.base import Base, TimestampMixin, uuid_pk

# Read once at import. The column width and the migration must agree, and both
# read the same setting — a mismatch is caught at startup by the readiness check
# rather than at the first INSERT.
EMBEDDING_DIMENSIONS = get_settings().embedding_dimensions


class Chunk(Base, TimestampMixin):
    """A retrievable piece of text and its embedding."""

    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    # CASCADE on both, unlike `entry.capture_id` (ADR-028). A chunk is not
    # content the user would miss; it is a copy of content that has just been
    # deleted, and keeping it would let deleted text keep surfacing in search.
    entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"))
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capture.id", ondelete="CASCADE")
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256[:32] of the normalised text. The whole point of re-index economy:
    # unchanged text is never sent to a provider twice.
    content_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    token_estimate: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Nullable: a chunk exists as soon as its entry is written, and is embedded
    # afterwards by a worker. Making it NOT NULL would force the embedding call
    # onto the capture path, where a provider outage becomes data loss.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Denormalised from the source so retrieval can filter and order by date
    # without joining. Retrieval is the hottest query in the product.
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "(entry_id IS NOT NULL) <> (capture_id IS NOT NULL)",
            name="one_source_only",
        ),
        UniqueConstraint("entry_id", "chunk_index", name="chunk_entry_id_chunk_index_unique"),
        UniqueConstraint("capture_id", "chunk_index", name="chunk_capture_id_chunk_index_unique"),
        Index("chunk_account_id_idx", "account_id"),
        Index("chunk_content_hash_idx", "content_hash"),
        # The embedding backlog. Partial, because the interesting rows are a
        # vanishing fraction of the table in steady state — a full index here
        # would be almost entirely rows the worker never wants to see.
        Index(
            "chunk_pending_embedding_idx",
            "account_id",
            postgresql_where=sql_text("embedding IS NULL"),
        ),
    )


class Entity(Base, TimestampMixin):
    """A person, product, company, project, decision, risk or action.

    One table for all seven kinds — see `app.domain.knowledge` for why. The
    resolution key is what makes a person recur across months instead of
    appearing once per capture.
    """

    __tablename__ = "entity"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # As the user said it, for display.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Folded for comparison. Computed in Python, not by the model.
    resolution_key: Mapped[str] = mapped_column(String(240), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(600))

    # Maintained by the extraction service rather than counted on read: « quels
    # sujets reviennent souvent ? » is a ranking query over the whole corpus, and
    # a COUNT(*) join per entity makes it O(mentions) on every ask.
    mention_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # A user rename must survive re-extraction, same principle as ADR-027.
    edited_by_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "kind IN ('person','product','company','project','decision','risk','action')",
            name="kind_valid",
        ),
        UniqueConstraint(
            "account_id", "resolution_key", name="entity_account_id_resolution_key_unique"
        ),
        Index("entity_account_id_kind_idx", "account_id", "kind"),
        Index("entity_account_id_mention_count_idx", "account_id", "mention_count"),
    )


class EntityMention(Base):
    """Where an entity was named. The evidence behind every count."""

    __tablename__ = "entity_mention"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entity.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entry.id", ondelete="CASCADE"))
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("capture.id", ondelete="CASCADE")
    )

    role: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    source_span_start: Mapped[int | None] = mapped_column(Integer)
    source_span_end: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Re-extracting an entry must update its mentions, not add a second set.
        # Without this, a single re-index doubles every count in the product.
        UniqueConstraint("entity_id", "entry_id", name="entity_mention_entity_id_entry_id_unique"),
        Index("entity_mention_account_id_entity_id_idx", "account_id", "entity_id"),
        Index("entity_mention_entry_id_idx", "entry_id"),
    )


class Conversation(Base, TimestampMixin):
    """A thread with the assistant."""

    __tablename__ = "conversation"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )

    # Derived from the first question, editable. Null until the first message.
    title: Mapped[str | None] = mapped_column(String(200))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("conversation_account_id_last_message_at_idx", "account_id", "last_message_at"),
    )


class ConversationMessage(Base):
    """One turn. Immutable once written."""

    __tablename__ = "conversation_message"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Client-generated, same idempotency contract as `capture.client_capture_id`
    # (ADR-009). A phone that retries a question on a flaky connection must not
    # ask it twice — and must not be billed twice.
    client_message_id: Mapped[str | None] = mapped_column(String(64))

    # How the answer was produced, so the UI can show it and support can debug
    # it: which intent fired, what was cited, which run it came from.
    intent: Mapped[str | None] = mapped_column(String(24))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="role_valid"),
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="conversation_message_conversation_id_client_message_id_unique",
        ),
        Index(
            "conversation_message_conversation_id_created_at_idx", "conversation_id", "created_at"
        ),
    )


class Memory(Base, TimestampMixin):
    """A durable fact the assistant carries between conversations."""

    __tablename__ = "memory"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    statement: Mapped[str] = mapped_column(String(300), nullable=False)
    # Lower-cased statement, hashed. Stops a long conversation storing the same
    # fact once per turn.
    statement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)

    # SET NULL rather than CASCADE: deleting a conversation must not silently
    # revoke what the assistant learned from it. The provenance is lost; the
    # fact is not.
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL")
    )
    # Drives the decay in `app.domain.memory`. Re-confirmation moves it forward.
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # A user dismissal is permanent and must never be re-learned, so the row
    # stays as a tombstone rather than being deleted.
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('profile','preference','relation','routine')", name="kind_valid"),
        UniqueConstraint(
            "account_id",
            "user_id",
            "statement_hash",
            name="memory_account_id_user_id_statement_hash_unique",
        ),
        Index("memory_account_id_user_id_idx", "account_id", "user_id"),
    )


class Digest(Base, TimestampMixin):
    """A generated daily, weekly or monthly summary."""

    __tablename__ = "digest"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )

    period: Mapped[str] = mapped_column(String(8), nullable=False)
    # Dates, not instants: "the week of 1 June" in the user's timezone. Storing
    # the boundary as a timestamptz would make the same week two different rows
    # for a user who travels.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # The counts handed to the model as facts, kept so the digest can be
    # rendered without re-querying and audited without re-running.
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("period IN ('daily','weekly','monthly')", name="period_valid"),
        CheckConstraint("period_end >= period_start", name="period_ordered"),
        # Regenerating a period replaces it. Two summaries of the same week are
        # not a richer history, they are a contradiction shown to the user.
        UniqueConstraint(
            "account_id", "user_id", "period", "period_start", name="digest_period_unique"
        ),
        Index("digest_account_id_period_period_start_idx", "account_id", "period", "period_start"),
    )


# Tenant tables added by Phase 3. Appended to `TENANT_TABLES` in `core.py`, which
# the RLS migration and the isolation test both iterate over.
AI_TENANT_TABLES: tuple[str, ...] = (
    "chunk",
    "entity",
    "entity_mention",
    "conversation",
    "conversation_message",
    "memory",
    "digest",
)
