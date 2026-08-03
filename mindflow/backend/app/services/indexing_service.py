"""Keeping the vector index in step with the corpus.

Indexing is split into two steps that fail independently, and that split is the
main design decision here:

1. **Chunking is synchronous and free.** When an entry is written, its chunks
   are written too, in the same transaction, with `embedding` left NULL.
2. **Embedding is asynchronous and costs money.** A worker picks up the NULL
   rows in batches.

Merging the two would put a provider call on the capture path, where an outage
stops people writing notes. Keeping them apart means a provider outage degrades
search for a while and nothing else — the same principle as ADR-026 for quotas:
the product degrades, it does not block.

**Re-indexing is incremental, by content hash.** An entry edited to fix a typo
re-chunks to mostly the same hashes; only what changed is re-embedded. Without
this, every edit re-embeds the whole entry, and a user tidying up their notes on
a Sunday afternoon generates a bill. Chunks whose hash is unchanged are left
completely alone — the row, its embedding, and its `embedded_at` all survive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import chunking
from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import EmbedderPort
from app.infra.db.models.ai import Chunk
from app.infra.db.models.core import Capture, Entry, Transcript
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.index")


@dataclass(slots=True)
class IndexResult:
    """What a single re-index actually did.

    `unchanged` is the interesting number: on a typical edit it should dominate,
    and a deployment where it is always zero has a chunking determinism bug that
    is otherwise invisible.
    """

    created: int = 0
    unchanged: int = 0
    removed: int = 0

    @property
    def touched(self) -> int:
        return self.created + self.removed


@dataclass(slots=True)
class EmbedResult:
    embedded: int = 0
    failed: int = 0
    remaining: int = 0


class IndexingService:
    """Writes and maintains `chunk` rows."""

    def __init__(self, session: AsyncSession, *, embedder: EmbedderPort | None = None) -> None:
        self._session = session
        # Optional: chunking never needs it, only `embed_pending` does. A caller
        # that only writes chunks should not have to construct a provider client.
        self._embedder = embedder

    # -- Writing chunks ----------------------------------------------------- #

    async def index_entry(self, entry: Entry) -> IndexResult:
        """Re-chunk one entry, preserving everything that did not change."""
        text = _entry_text(entry)
        return await self._reconcile(
            account_id=entry.account_id,
            text=text,
            occurred_at=entry.occurred_at,
            entry_id=entry.id,
            capture_id=None,
            source="entry",
        )

    async def index_transcript(self, capture: Capture, transcript: Transcript) -> IndexResult:
        """Index a transcript under its capture.

        Transcripts are indexed *as well as* entries, not instead: extraction
        keeps the actionable items and drops the rest, and « qu'est-ce qui a été
        dit exactement ? » is a question only the transcript can answer.
        """
        return await self._reconcile(
            account_id=capture.account_id,
            text=transcript.text or "",
            occurred_at=capture.captured_at,
            entry_id=None,
            capture_id=capture.id,
            source="transcript",
        )

    async def _reconcile(
        self,
        *,
        account_id: uuid.UUID,
        text: str,
        occurred_at: datetime | None,
        entry_id: uuid.UUID | None,
        capture_id: uuid.UUID | None,
        source: str,
    ) -> IndexResult:
        wanted = chunking.split(text)
        existing = await self._existing(entry_id=entry_id, capture_id=capture_id)
        result = IndexResult()

        # Keyed by (index, hash): a chunk that moved position is a different row
        # even with identical text, because `chunk_index` is part of its
        # identity and of the unique constraint.
        wanted_keys = {(piece.index, piece.content_hash) for piece in wanted}

        for row in existing:
            if (row.chunk_index, row.content_hash) in wanted_keys:
                result.unchanged += 1
                continue
            await self._session.delete(row)
            result.removed += 1

        # Flushed here, before a single insert is queued. SQLAlchemy's unit of
        # work emits inserts before deletes for the same mapper, so without this
        # a chunk replacing one at the same `chunk_index` collides on the unique
        # constraint — which is the ordinary case for an edited note, not an
        # edge case.
        if result.removed:
            await self._session.flush()

        kept = {(row.chunk_index, row.content_hash) for row in existing}
        for piece in wanted:
            if (piece.index, piece.content_hash) in kept:
                continue
            self._session.add(
                Chunk(
                    account_id=account_id,
                    entry_id=entry_id,
                    capture_id=capture_id,
                    chunk_index=piece.index,
                    text=piece.text,
                    content_hash=piece.content_hash,
                    token_estimate=piece.estimated_tokens,
                    occurred_at=occurred_at,
                )
            )
            result.created += 1

        await self._session.flush()

        if result.created:
            metrics.chunks_indexed_total.labels(source).inc(result.created)
        log.debug(
            "index.reconciled",
            source=source,
            created=result.created,
            unchanged=result.unchanged,
            removed=result.removed,
        )
        return result

    async def _existing(
        self, *, entry_id: uuid.UUID | None, capture_id: uuid.UUID | None
    ) -> list[Chunk]:
        stmt = select(Chunk)
        stmt = (
            stmt.where(Chunk.entry_id == entry_id)
            if entry_id is not None
            else stmt.where(Chunk.capture_id == capture_id)
        )
        return list((await self._session.execute(stmt.order_by(Chunk.chunk_index))).scalars())

    async def remove_for_entry(self, entry_id: uuid.UUID) -> int:
        """Drop an entry's chunks.

        Called on soft delete, where the foreign key's CASCADE never fires: the
        row is still there, so without this the deleted note keeps surfacing in
        semantic search — visible only to the person who deleted it, which is
        precisely who will notice.
        """
        chunks = await self._existing(entry_id=entry_id, capture_id=None)
        for chunk in chunks:
            await self._session.delete(chunk)
        await self._session.flush()
        return len(chunks)

    # -- Embedding ---------------------------------------------------------- #

    async def embed_pending(self, *, limit: int = 64) -> EmbedResult:
        """Embed a batch of chunks that have none.

        Ordered by creation so the backlog drains oldest-first: a user who just
        wrote a note is better served by the rest of their corpus being
        searchable than by their newest sentence jumping the queue.
        """
        if self._embedder is None:
            raise RuntimeError("embed_pending requires an embedder")

        pending = list(
            (
                await self._session.execute(
                    select(Chunk)
                    .where(Chunk.embedding.is_(None))
                    .order_by(Chunk.created_at)
                    .limit(limit)
                    # Two workers must not embed the same chunk and pay twice.
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        if not pending:
            return EmbedResult(remaining=await self.backlog())

        try:
            embedding = await self._embedder.embed([chunk.text for chunk in pending])
        except ExtractionUnavailableError:
            # Left NULL deliberately: the rows stay in the backlog and the next
            # tick retries them. Marking them failed would need a reset path
            # that someone has to remember to run.
            metrics.chunks_embedded_total.labels(self._embedder.name, "failed").inc(len(pending))
            log.warning("embed.batch_failed", provider=self._embedder.name, count=len(pending))
            return EmbedResult(failed=len(pending), remaining=await self.backlog())

        now = datetime.now(UTC)
        for chunk, vector in zip(pending, embedding.vectors, strict=True):
            chunk.embedding = list(vector)
            chunk.embedding_model = embedding.model
            chunk.embedded_at = now

        await self._session.flush()
        metrics.chunks_embedded_total.labels(self._embedder.name, "ok").inc(len(pending))
        return EmbedResult(embedded=len(pending), remaining=await self.backlog())

    async def backlog(self) -> int:
        """How many chunks are waiting.

        Exported as a gauge because a backlog that climbs and never falls means
        semantic search is answering from a stale corpus — which is
        indistinguishable, from outside, from answering correctly.
        """
        total = (
            await self._session.execute(
                select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
            )
        ).scalar_one()
        metrics.embedding_backlog.set(total)
        return int(total)


def _entry_text(entry: Entry) -> str:
    """What gets embedded for an entry.

    The title is repeated into the chunk rather than left to the metadata,
    because a chunk is retrieved alone and read alone: a body fragment with no
    title embeds as an anonymous paragraph, and retrieves like one.
    """
    body = entry.body or ""
    return f"{entry.title}\n\n{body}".strip() if body else entry.title


async def reset_embeddings(session: AsyncSession, *, model: str) -> int:
    """Clear every embedding not produced by `model`.

    The migration path for changing embedding provider (ADR-045). Vectors from
    two models occupy different spaces, so a corpus half-embedded by each ranks
    by nothing at all — worse than an empty index, because it looks like it
    works. Clearing puts everything back in the backlog, where the worker
    re-embeds it at the new model's cost.
    """
    result = await session.execute(
        update(Chunk)
        .where(Chunk.embedding_model.is_not(None), Chunk.embedding_model != model)
        .values(embedding=None, embedding_model=None, embedded_at=None)
    )
    await session.flush()
    count = int(result.rowcount or 0)  # type: ignore[attr-defined]
    if count:
        log.warning("embed.model_changed", model=model, cleared=count)
    return count
