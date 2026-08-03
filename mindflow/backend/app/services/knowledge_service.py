"""Extracting entities, and resolving them into a graph.

Two halves with different natures, deliberately kept apart:

* **Extraction is probabilistic.** A model reads a note and proposes people,
  products, companies, projects, decisions, risks and actions. It is allowed to
  be wrong; the confidence threshold and the `source_span` are how that is
  contained.
* **Resolution is deterministic.** Deciding that "Jean-Marc Ondo" in March and
  "jean marc ondo" in July are one person is done by a normalised key computed
  in code (`app.domain.knowledge`). Asking the model would give a different
  answer on a different day, and a knowledge graph that reshuffles itself is
  worse than none.

The operation is **idempotent per entry**. Re-extracting replaces that entry's
mentions rather than adding to them, and `mention_count` is recomputed from the
rows rather than incremented. Incrementing is the obvious implementation and it
is wrong: one re-index doubles every count in the product, « quels sujets
reviennent souvent ? » answers with inflated numbers, and nothing looks broken.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ExtractionUnavailableError
from app.domain.knowledge import (
    EntityKind,
    ExtractedEntity,
    KnowledgeExtraction,
    json_schema_for_llm,
    resolution_key,
)
from app.domain.ports import ChatMessage, ChatPort, ChatRequest
from app.infra.db.models.ai import Entity, EntityMention
from app.infra.db.models.core import Entry
from app.observability import metrics
from app.observability.logging import get_logger
from app.prompts import entities as entity_prompts
from app.prompts.registry import Prompt

log = get_logger("ai.knowledge")

MIN_CONFIDENCE = 0.4


@dataclass(slots=True)
class ExtractionOutcome:
    entities: list[Entity] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    created: int = 0
    linked: int = 0
    # True when the model declined or returned nothing usable. Not an error:
    # most captures name nothing, and treating that as a failure would have the
    # worker retrying half the corpus forever.
    empty: bool = False


@dataclass(slots=True)
class ThemeCount:
    kind: EntityKind
    name: str
    count: int
    last_seen_at: datetime | None


class KnowledgeService:
    def __init__(self, session: AsyncSession, *, chat: ChatPort | None = None) -> None:
        self._session = session
        self._chat = chat

    # -- Extraction --------------------------------------------------------- #

    async def extract_for_entry(self, entry: Entry) -> ExtractionOutcome:
        """Find the entities in one entry and fold them into the graph."""
        if self._chat is None:
            raise RuntimeError("extract_for_entry requires a chat port")

        text = f"{entry.title}\n\n{entry.body or ''}".strip()
        if not text:
            return ExtractionOutcome(empty=True)

        prompt: Prompt = entity_prompts.ENTITY_PROMPT
        request = ChatRequest(
            system=prompt.system,
            messages=(
                ChatMessage(
                    role="user",
                    content=entity_prompts.build_user_block(
                        text,
                        title=entry.title,
                        occurred_at=entry.occurred_at.date().isoformat()
                        if entry.occurred_at
                        else None,
                    ),
                ),
            ),
            temperature=0.0,
            json_schema=json_schema_for_llm() if self._chat.supports_json_schema else None,
        )

        try:
            response = await self._chat.complete(request)
        except ExtractionUnavailableError:
            log.warning("knowledge.unavailable", entry_id=str(entry.id))
            raise

        if response.refused:
            # A decline is a legitimate outcome, not a retry (ADR-030). The
            # entry keeps its content; it simply contributes no entities.
            log.info("knowledge.refused", entry_id=str(entry.id))
            return ExtractionOutcome(empty=True)

        extraction = _parse(response.text, entry_id=entry.id)
        if extraction is None or extraction.is_empty():
            return ExtractionOutcome(empty=True)

        return await self.apply(extraction, entry=entry)

    async def apply(self, extraction: KnowledgeExtraction, *, entry: Entry) -> ExtractionOutcome:
        """Fold an extraction into the graph, idempotently for this entry."""
        candidates = extraction.deduplicated(min_confidence=MIN_CONFIDENCE)
        if not candidates:
            return ExtractionOutcome(topics=extraction.topics, empty=True)

        # Which entities this entry pointed at before. Kept because an entity
        # that is *no longer* named must have its count refreshed too — and it
        # is absent from the new extraction, so nothing else would revisit it.
        # Without this its `mention_count` stays at yesterday's number forever.
        previously_linked = set(
            (
                await self._session.execute(
                    select(EntityMention.entity_id).where(EntityMention.entry_id == entry.id)
                )
            ).scalars()
        )

        # Every mention this entry made previously goes first. Re-extraction
        # must *replace*, never accumulate.
        await self._session.execute(delete(EntityMention).where(EntityMention.entry_id == entry.id))

        outcome = ExtractionOutcome(topics=extraction.topics)
        for candidate in candidates:
            entity, created = await self._resolve(candidate, account_id=entry.account_id)
            outcome.entities.append(entity)
            outcome.created += int(created)

            self._session.add(
                EntityMention(
                    account_id=entry.account_id,
                    entity_id=entity.id,
                    entry_id=entry.id,
                    role=candidate.role,
                    confidence=candidate.confidence,
                    source_span_start=candidate.source_span.start
                    if candidate.source_span
                    else None,
                    source_span_end=candidate.source_span.end if candidate.source_span else None,
                    occurred_at=entry.occurred_at,
                )
            )
            outcome.linked += 1
            metrics.entities_extracted_total.labels(candidate.kind.value).inc()

        await self._session.flush()
        await self._recount(previously_linked | {entity.id for entity in outcome.entities})
        return outcome

    async def _resolve(
        self, candidate: ExtractedEntity, *, account_id: uuid.UUID
    ) -> tuple[Entity, bool]:
        """Find the entity this mention refers to, or create it."""
        key = candidate.resolution_key
        existing = (
            await self._session.execute(
                select(Entity).where(Entity.account_id == account_id, Entity.resolution_key == key)
            )
        ).scalar_one_or_none()

        if existing is not None:
            # A user rename survives re-extraction, exactly as an edited entry
            # survives reprocessing (ADR-027). Without this, the model's
            # spelling silently overwrites the user's on every re-index.
            if existing.edited_by_user_at is None and len(candidate.name) > len(existing.name):
                # Prefer the fuller form: "Sylvie Mba" over "Sylvie".
                existing.name = candidate.name
            if candidate.detail and not existing.detail:
                existing.detail = candidate.detail
            return existing, False

        entity = Entity(
            account_id=account_id,
            kind=candidate.kind.value,
            name=candidate.name,
            resolution_key=key,
            detail=candidate.detail,
        )
        self._session.add(entity)
        await self._session.flush()
        return entity, True

    async def _recount(self, entity_ids: set[uuid.UUID]) -> None:
        """Recompute counts from the mention rows.

        Recomputed rather than incremented, on purpose. An increment is correct
        exactly once per mention and wrong forever after a re-index, and the
        symptom — inflated recurring-topic counts — looks like a working
        feature.
        """
        if not entity_ids:
            return

        rows = (
            await self._session.execute(
                select(
                    EntityMention.entity_id,
                    func.count().label("total"),
                    func.min(EntityMention.occurred_at),
                    func.max(EntityMention.occurred_at),
                )
                .where(EntityMention.entity_id.in_(entity_ids))
                .group_by(EntityMention.entity_id)
            )
        ).all()

        by_id = {row[0]: row for row in rows}
        for entity_id in entity_ids:
            entity = await self._session.get(Entity, entity_id)
            if entity is None:
                continue
            row = by_id.get(entity_id)
            if row is None:
                entity.mention_count = 0
                continue
            entity.mention_count = int(row[1])
            entity.first_seen_at = row[2]
            entity.last_seen_at = row[3]
        await self._session.flush()

    # -- Reading ------------------------------------------------------------ #

    async def recurring_themes(
        self,
        *,
        since: datetime | None = None,
        kinds: tuple[EntityKind, ...] = (),
        limit: int = 12,
        min_mentions: int = 2,
    ) -> list[ThemeCount]:
        """« Quels sujets reviennent souvent ? », answered in SQL.

        A `GROUP BY` is what this question is, and asking a model to rank a
        sample of passages instead produces a plausible ordering that is wrong.
        The model's job is downstream: narrating these numbers, never producing
        them.
        """
        stmt = (
            select(
                Entity.kind,
                Entity.name,
                func.count(EntityMention.id).label("total"),
                func.max(EntityMention.occurred_at).label("last_seen"),
            )
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .where(Entity.archived_at.is_(None))
            .group_by(Entity.id, Entity.kind, Entity.name)
            .having(func.count(EntityMention.id) >= min_mentions)
            .order_by(func.count(EntityMention.id).desc(), Entity.name)
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(EntityMention.occurred_at >= since)
        if kinds:
            stmt = stmt.where(Entity.kind.in_([kind.value for kind in kinds]))

        rows = (await self._session.execute(stmt)).all()
        return [
            ThemeCount(kind=EntityKind(row[0]), name=row[1], count=int(row[2]), last_seen_at=row[3])
            for row in rows
        ]

    async def list_entities(
        self,
        *,
        kind: EntityKind | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[Entity]:
        stmt = (
            select(Entity)
            .where(Entity.archived_at.is_(None))
            .order_by(Entity.mention_count.desc(), Entity.name)
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(Entity.kind == kind.value)
        if query:
            # Matched on the folded form, so searching "theo" finds "Théo".
            folded = resolution_key(kind or EntityKind.PERSON, query).split(":", 1)[1]
            stmt = stmt.where(Entity.resolution_key.contains(folded))
        return list((await self._session.execute(stmt)).scalars())

    async def mentions_for(self, entity_id: uuid.UUID, *, limit: int = 50) -> list[EntityMention]:
        return list(
            (
                await self._session.execute(
                    select(EntityMention)
                    .where(EntityMention.entity_id == entity_id)
                    .order_by(EntityMention.occurred_at.desc().nullslast())
                    .limit(limit)
                )
            ).scalars()
        )


def _parse(payload: str, *, entry_id: uuid.UUID) -> KnowledgeExtraction | None:
    """Validate the model's output, returning None rather than raising.

    Unlike note extraction, where a schema violation fails the capture (AI.md
    I3), a malformed entity extraction is survivable: the entry exists, it is
    searchable, and it simply contributes nothing to the graph until the next
    pass. Raising here would put a background failure in front of a user whose
    note is perfectly fine.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("knowledge.invalid_json", entry_id=str(entry_id))
        return None
    try:
        return KnowledgeExtraction.model_validate(data)
    except ValidationError as exc:
        log.warning("knowledge.schema_violation", entry_id=str(entry_id), errors=exc.error_count())
        return None
