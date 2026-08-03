"""What the assistant remembers, and what it refuses to.

The store is small on purpose. Memory competes for the same context window as
retrieved passages, and a memory is read on *every* future turn while a passage
is read once — so a marginal memory is far more expensive than a marginal
passage, and far more likely to mislead.

Three rules, enforced here rather than trusted to the prompt:

* **A high confidence bar** (0.7, higher than anywhere else in the product).
  A doubtful extracted entity shows up once; a doubtful memory shapes every
  future answer, with no error and no way for the user to guess the cause.
* **A dismissal is permanent.** Dismissed rows are kept as tombstones and
  re-learning is refused against them. Deleting instead would let the next
  conversation re-learn exactly what the user just rejected, which reads as the
  product ignoring them.
* **Confidence decays.** Weighting by *last confirmation* rather than original
  confidence means a fact that stopped being true quietly stops being used,
  instead of persisting because it was stated firmly once in March.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import ExtractionUnavailableError, NotFoundError
from app.domain.memory import (
    MemoryCandidate,
    MemoryExtraction,
    MemoryKind,
    decayed_weight,
    json_schema_for_llm,
)
from app.domain.ports import ChatMessage, ChatPort, ChatRequest
from app.infra.db.models.ai import Conversation, ConversationMessage, Memory
from app.observability.logging import get_logger
from app.prompts import memory as memory_prompts
from app.services.identity_service import Principal

log = get_logger("ai.memory")

MIN_CONFIDENCE = 0.7
# How many memories are injected into a prompt. Beyond this the block starts
# crowding out the retrieved passages, which are what actually answer the
# question.
MAX_IN_PROMPT = 12
# Below this decayed weight a memory has gone too long unconfirmed to be worth
# the tokens. It is not deleted — a user asking « qu'est-ce que tu sais de moi ? »
# should still see it, marked as old.
MIN_WEIGHT_IN_PROMPT = 0.25


class MemoryService:
    def __init__(
        self, session: AsyncSession, *, principal: Principal, chat: ChatPort | None = None
    ) -> None:
        self._session = session
        self._principal = principal
        self._chat = chat

    # -- Reading ------------------------------------------------------------ #

    async def active(self, *, limit: int = 100) -> list[Memory]:
        return list(
            (
                await self._session.execute(
                    select(Memory)
                    .where(
                        Memory.user_id == self._principal.user_id,
                        Memory.dismissed_at.is_(None),
                    )
                    .order_by(Memory.confirmed_at.desc())
                    .limit(limit)
                )
            ).scalars()
        )

    async def system_block(self) -> str:
        """The memory block appended to the assistant's system prompt.

        Empty for a new user, and that is the common case — most conversations
        produce no memory at all. An empty block returns an empty string rather
        than a heading with nothing under it, which a model reads as an
        instruction to invent something to put there.
        """
        now = datetime.now(UTC)
        weighted = [
            (memory, decayed_weight(memory.confirmed_at, now=now)) for memory in await self.active()
        ]
        kept = [
            memory
            for memory, weight in sorted(weighted, key=lambda pair: -pair[1])
            if weight >= MIN_WEIGHT_IN_PROMPT
        ][:MAX_IN_PROMPT]
        if not kept:
            return ""

        lines = "\n".join(
            f"- [{MemoryKind(memory.kind).label}] {memory.statement}" for memory in kept
        )
        return (
            "CE QUE TU SAIS DE CETTE PERSONNE\n"
            "Ces faits viennent de conversations précédentes. Utilise-les pour "
            "situer la réponse, jamais comme source d'information factuelle sur "
            "ses notes.\n"
            f"{lines}"
        )

    # -- Writing ------------------------------------------------------------ #

    async def remember(
        self,
        candidate: MemoryCandidate,
        *,
        conversation_id: uuid.UUID | None = None,
    ) -> Memory | None:
        """Store a fact, or confirm one already held.

        Returns None when the fact was previously dismissed. Re-learning what a
        user explicitly rejected is worse than forgetting: it tells them their
        correction did not stick.
        """
        if candidate.confidence < MIN_CONFIDENCE:
            return None

        digest = _hash(candidate)
        existing = (
            await self._session.execute(
                select(Memory).where(
                    Memory.user_id == self._principal.user_id,
                    Memory.statement_hash == digest,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.dismissed_at is not None:
                log.debug("memory.refused_relearn", statement=candidate.statement[:60])
                return None
            # Restating a fact is what makes it survive the decay. This is the
            # only place `confirmed_at` moves.
            existing.confirmed_at = datetime.now(UTC)
            existing.confidence = max(float(existing.confidence), candidate.confidence)
            await self._session.flush()
            return existing

        memory = Memory(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            kind=candidate.kind.value,
            statement=candidate.statement,
            statement_hash=digest,
            confidence=candidate.confidence,
            source_conversation_id=conversation_id,
        )
        self._session.add(memory)
        await self._session.flush()
        log.info("memory.learned", kind=candidate.kind.value)
        return memory

    async def dismiss(self, memory_id: uuid.UUID) -> Memory:
        """Forget a fact, permanently.

        The row survives as a tombstone so the next conversation cannot re-learn
        it. A hard delete would let the assistant rediscover exactly what the
        user just told it to drop.
        """
        memory = await self._session.get(Memory, memory_id)
        if memory is None:
            raise NotFoundError("Mémoire introuvable.")
        memory.dismissed_at = datetime.now(UTC)
        await self._session.flush()
        return memory

    async def harvest(self, conversation_id: uuid.UUID) -> list[Memory]:
        """Review a finished conversation for durable facts.

        Run after the exchange rather than during it, because the interesting
        signal is what the person stated about themselves across several turns,
        and because nothing here should add latency to an answer.
        """
        if self._chat is None:
            raise RuntimeError("harvest requires a chat port")

        conversation = await self._session.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation introuvable.")

        rows = list(
            (
                await self._session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation_id)
                    .order_by(ConversationMessage.created_at)
                )
            ).scalars()
        )
        turns = [(row.role, row.content) for row in rows if row.role in ("user", "assistant")]
        if not turns:
            return []

        known = [memory.statement for memory in await self.active()]
        request = ChatRequest(
            system=memory_prompts.MEMORY_PROMPT.system,
            messages=(
                ChatMessage(role="user", content=memory_prompts.build_known_block(known)),
                ChatMessage(role="user", content=memory_prompts.build_conversation_block(turns)),
            ),
            temperature=0.0,
            max_output_tokens=600,
            json_schema=json_schema_for_llm() if self._chat.supports_json_schema else None,
        )

        try:
            response = await self._chat.complete(request)
        except ExtractionUnavailableError:
            # Harvesting is entirely optional. Losing it costs the assistant a
            # little context next time and nothing else, so it never surfaces.
            log.info("memory.harvest_unavailable", conversation_id=str(conversation_id))
            return []

        if response.refused:
            return []

        extraction = _parse(response.text)
        if extraction is None:
            return []

        stored: list[Memory] = []
        for candidate in extraction.worth_keeping(min_confidence=MIN_CONFIDENCE):
            memory = await self.remember(candidate, conversation_id=conversation_id)
            if memory is not None:
                stored.append(memory)
        return stored


def _hash(candidate: MemoryCandidate) -> str:
    return hashlib.sha256(candidate.dedupe_key.encode()).hexdigest()[:32]


def _parse(payload: str) -> MemoryExtraction | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("memory.invalid_json")
        return None
    try:
        return MemoryExtraction.model_validate(data)
    except ValidationError as exc:
        log.warning("memory.schema_violation", errors=exc.error_count())
        return None
