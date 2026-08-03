"""Hybrid retrieval: full text, vectors, and the fusion of the two.

Neither retriever is reliably better, which is the whole reason for running
both. Vector search finds « le patron » when the note says « le directeur ».
Lexical search finds an exact reference number that no embedding will ever place
nearby, and finds a proper noun the embedding model has never seen — which, in a
product about *your* colleagues and *your* projects, is most of them.

Their scores are not comparable, so they are fused by rank
(`app.domain.retrieval`) rather than by score. That module explains why; this
one is about the two queries and the properties they must have:

* **Semantic search filters on `embedding_model`.** Vectors made by two models
  live in different spaces, so a corpus mid-migration would otherwise rank by
  nothing. Filtering means a migration degrades recall rather than corrupting it.
* **The vector query uses `<=>`** — cosine — to match the HNSW operator class
  built in migration 0006. A different operator silently ignores the index and
  sequential-scans, which appears months later as "search got slow".
* **Neither query can raise on user input.** `websearch_to_tsquery` cannot
  (ADR-037's reason for choosing it), and the vector side takes no user text at
  all — only a vector. A search box must not be able to return a 500.
* **An unembedded corpus is not an error.** Before the first embedding worker
  tick, semantic search returns nothing and lexical search answers alone. That
  is a normal state, not a degraded one, and it must not be reported as failure.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, Select, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntryStatus
from app.domain.retrieval import (
    Candidate,
    Citation,
    Retriever,
    attach_scores,
    reciprocal_rank_fusion,
)
from app.infra.db.models.ai import Chunk
from app.infra.db.models.core import Capture, Entry
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("ai.retrieve")

FTS_CONFIG = "french"

# How deep each retriever goes before fusion. Fusion needs depth to find
# consensus; the user never sees it.
CANDIDATE_LIMIT = 40
# Cosine *distance*, so smaller is closer. Past this the match is noise, and a
# confident answer built on noise is worse than no answer.
MAX_COSINE_DISTANCE = 0.85


def _config() -> ColumnElement[str]:
    """`french`, cast to `regconfig` — see `search_service._config`."""
    return cast(literal(FTS_CONFIG), REGCONFIG)


# Question words and connectives. Present in every question and in almost no
# note, so ANDing them guarantees zero results.
_QUESTION_NOISE = frozenset(
    {
        "que",
        "quoi",
        "qui",
        "quel",
        "quels",
        "quelle",
        "quelles",
        "quand",
        "comment",
        "pourquoi",
        "est",
        "sont",
        "les",
        "des",
        "une",
        "mes",
        "mon",
        "ma",
        "sur",
        "pour",
        "dans",
        "avec",
        "cette",
        "resume",
        "résume",
        "montre",
        "affiche",
        "liste",
        "trouve",
        "dis",
        "moi",
        "faire",
        "dois",
        "peux",
        "tu",
        "je",
        "ce",
        "cet",
        "aux",
        "par",
        "notes",
        "note",
        "propos",
        "concernant",
        "sujet",
        "chez",
        "plus",
        "tout",
        "tous",
    }
)
_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
# Enough terms to describe a question; more only dilutes the ranking.
MAX_QUERY_TERMS = 12


def _to_or_query(query: str) -> str:
    """Turn a natural-language question into a disjunctive search.

    `websearch_to_tsquery` ANDs bare terms, which is right for a search box and
    catastrophic for a question: « Pourquoi le fournisseur a-t-il changé ses
    conditions ? » would require the word "pourquoi" to appear in the note, so
    it matches nothing at all.

    Explicit `OR` keeps the guarantee that made `websearch_to_tsquery` the right
    choice in the first place (ADR-037): whatever the user types, it still
    cannot raise. Building a `to_tsquery` string by hand would hand that
    guarantee back.
    """
    words = [
        word
        for word in (match.group(0).lower() for match in _WORD.finditer(query))
        if word not in _QUESTION_NOISE
    ]
    # Deduplicated, keeping order: a repeated word adds nothing to a disjunction.
    unique = list(dict.fromkeys(words))[:MAX_QUERY_TERMS]
    return " OR ".join(unique)


@dataclass(slots=True)
class Passage:
    """A retrieved chunk with everything needed to cite it."""

    chunk_id: uuid.UUID
    text: str
    entry_id: uuid.UUID | None
    capture_id: uuid.UUID | None
    title: str
    occurred_at: str | None
    found_by: tuple[Retriever, ...] = ()
    score: float = 0.0

    @property
    def ref(self) -> str:
        return str(self.chunk_id)

    @property
    def label(self) -> str:
        """The header the model sees above the text.

        Carries the date so the answer can say « le 3 mars, en réunion » rather
        than « dans une de vos notes », which is the difference between an
        answer a user can check and one they have to trust.
        """
        return f"{self.title} — {self.occurred_at}" if self.occurred_at else self.title


@dataclass(slots=True)
class RetrievalResult:
    passages: list[Passage]
    took_ms: int
    lexical_count: int = 0
    semantic_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.passages


class RetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding_model: str | None = None,
        candidate_limit: int = CANDIDATE_LIMIT,
    ) -> None:
        self._session = session
        # None means "do not run semantic search" — the honest state before any
        # embedder is configured, and the one that keeps lexical search working
        # on its own rather than failing together.
        self._embedding_model = embedding_model
        self._candidate_limit = candidate_limit

    async def search(
        self,
        query: str,
        *,
        query_vector: list[float] | None = None,
        limit: int = 8,
        entry_types: tuple[str, ...] = (),
        since: str | None = None,
    ) -> RetrievalResult:
        """Retrieve passages for a question."""
        started = time.perf_counter()
        notes: list[str] = []

        lexical = await self._lexical(query, entry_types=entry_types)
        semantic: list[tuple[uuid.UUID, float]] = []
        if query_vector and self._embedding_model:
            semantic = await self._semantic(query_vector, entry_types=entry_types)
            if not semantic:
                notes.append("Aucun résultat sémantique : le corpus n'est pas encore indexé.")
        elif query_vector:
            notes.append("Recherche sémantique désactivée (aucun modèle d'embedding configuré).")

        rankings = {
            Retriever.LEXICAL: [str(chunk_id) for chunk_id, _ in lexical],
            Retriever.SEMANTIC: [str(chunk_id) for chunk_id, _ in semantic],
        }

        # « Résume mes réunions » shares no keyword with any meeting note and no
        # embedding with a *set* of them: it is a request to browse a filtered
        # slice, not to match one. Falling back to recency is what makes that
        # question answerable at all — and it is only a fallback, so a question
        # that does match keeps its ranking.
        if not lexical and not semantic:
            recent = await self._recent(entry_types=entry_types, limit=limit)
            rankings[Retriever.RECENCY] = [str(chunk_id) for chunk_id in recent]
            if recent:
                notes.append("Aucun mot-clé correspondant : les éléments les plus récents.")

        fused = reciprocal_rank_fusion(
            rankings,
            weights={
                Retriever.LEXICAL: 1.0,
                Retriever.SEMANTIC: 1.0,
                Retriever.RECENCY: 1.0,
            },
            limit=limit,
        )
        attach_scores(fused, Retriever.LEXICAL, {str(k): v for k, v in lexical})
        attach_scores(fused, Retriever.SEMANTIC, {str(k): v for k, v in semantic})

        passages = await self._hydrate(fused)
        took_ms = int((time.perf_counter() - started) * 1000)

        metrics.search_duration_seconds.labels("hybrid").observe(took_ms / 1000)
        metrics.search_queries_total.labels("hybrid", "hit" if passages else "empty").inc()
        log.debug(
            "retrieve.done",
            lexical=len(lexical),
            semantic=len(semantic),
            fused=len(passages),
            took_ms=took_ms,
        )
        return RetrievalResult(
            passages=passages,
            took_ms=took_ms,
            lexical_count=len(lexical),
            semantic_count=len(semantic),
            notes=notes,
        )

    async def _lexical(
        self, query: str, *, entry_types: tuple[str, ...]
    ) -> list[tuple[uuid.UUID, float]]:
        """Rank chunks by full-text relevance.

        Chunks have no `search_vector` column of their own — building one would
        double the storage of the largest table in the schema for a gain the
        entry-level index already provides. `to_tsvector` is computed on the fly
        instead, over a candidate set the WHERE clause has already narrowed.
        """
        cleaned = _to_or_query(query)
        if not cleaned:
            return []

        tsquery = func.websearch_to_tsquery(_config(), cleaned)
        vector = func.to_tsvector(_config(), Chunk.text)

        stmt = (
            select(Chunk.id, func.ts_rank_cd(vector, tsquery).label("rank"))
            .where(vector.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(vector, tsquery).desc(), Chunk.occurred_at.desc())
            .limit(self._candidate_limit)
        )
        stmt = self._scope(stmt, entry_types)
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]

    async def _semantic(
        self, query_vector: list[float], *, entry_types: tuple[str, ...]
    ) -> list[tuple[uuid.UUID, float]]:
        """Rank chunks by cosine distance to the question."""
        distance = Chunk.embedding.cosine_distance(query_vector)
        stmt = (
            select(Chunk.id, distance.label("distance"))
            .where(
                Chunk.embedding.is_not(None),
                # Mixing two models' vectors ranks by nothing at all. Filtering
                # makes a provider migration degrade recall, not corrupt it.
                Chunk.embedding_model == self._embedding_model,
                distance < MAX_COSINE_DISTANCE,
            )
            .order_by(distance)
            .limit(self._candidate_limit)
        )
        stmt = self._scope(stmt, entry_types)
        rows = (await self._session.execute(stmt)).all()
        # Returned as similarity, so a bigger number is a better match in the
        # explanation shown to the user. It plays no part in the ranking.
        return [(row[0], 1.0 - float(row[1])) for row in rows]

    async def _recent(self, *, entry_types: tuple[str, ...], limit: int) -> list[uuid.UUID]:
        """The newest chunks in scope, used only when nothing matched.

        Restricted to the first chunk of each source: a browse should show the
        opening of ten meetings, not ten fragments of the same long one.
        """
        stmt = (
            select(Chunk.id)
            .where(Chunk.chunk_index == 0)
            .order_by(Chunk.occurred_at.desc().nullslast(), Chunk.created_at.desc())
            .limit(limit)
        )
        stmt = self._scope(stmt, entry_types)
        return [row[0] for row in (await self._session.execute(stmt)).all()]

    def _scope(self, stmt: Select, entry_types: tuple[str, ...]) -> Select:  # type: ignore[type-arg]
        """Restrict to live content, and optionally to a kind of entry.

        A soft-deleted or archived entry must never surface in an answer. RLS
        already handles the tenant; this handles the lifecycle, which RLS knows
        nothing about.
        """
        stmt = stmt.outerjoin(Entry, Chunk.entry_id == Entry.id).where(
            or_(
                Chunk.entry_id.is_(None),
                (Entry.deleted_at.is_(None)) & (Entry.status != EntryStatus.ARCHIVED),
            )
        )
        if entry_types:
            # Narrowing to a kind means dropping transcript chunks: « résume mes
            # réunions » is about meetings, and a transcript chunk has no type.
            stmt = stmt.where(Entry.entry_type.in_(entry_types))
        return stmt

    async def _hydrate(self, candidates: list[Candidate]) -> list[Passage]:
        """Load the text and titles for the fused ranking, in one query."""
        if not candidates:
            return []

        ids = [uuid.UUID(candidate.ref) for candidate in candidates]
        rows = (
            await self._session.execute(
                select(Chunk, Entry.title, Capture.captured_at)
                .outerjoin(Entry, Chunk.entry_id == Entry.id)
                .outerjoin(Capture, Chunk.capture_id == Capture.id)
                .where(Chunk.id.in_(ids))
            )
        ).all()

        by_id = {row[0].id: row for row in rows}
        passages: list[Passage] = []
        for candidate in candidates:
            row = by_id.get(uuid.UUID(candidate.ref))
            if row is None:
                # Deleted between ranking and hydration. Skipping is correct:
                # citing a row that no longer exists is worse than one fewer
                # citation.
                continue
            chunk, entry_title, captured_at = row
            occurred = chunk.occurred_at or captured_at
            passages.append(
                Passage(
                    chunk_id=chunk.id,
                    text=chunk.text,
                    entry_id=chunk.entry_id,
                    capture_id=chunk.capture_id,
                    title=entry_title or "Transcription",
                    occurred_at=occurred.date().isoformat() if occurred else None,
                    found_by=candidate.found_by,
                    score=candidate.fused,
                )
            )
        return passages


def to_citations(passages: list[Passage]) -> list[Citation]:
    """Turn passages into what the client renders under an answer."""
    return [
        Citation(
            ref=passage.ref,
            entry_id=str(passage.entry_id) if passage.entry_id else None,
            capture_id=str(passage.capture_id) if passage.capture_id else None,
            title=passage.title,
            # Enough to recognise the source without reproducing it. A citation
            # is a pointer, not a second copy of the note.
            excerpt=passage.text[:280],
            occurred_at=passage.occurred_at,
            score=passage.score,
        )
        for passage in passages
    ]
