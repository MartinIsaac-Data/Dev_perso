"""The AI layer's endpoints: chat, semantic search, entities, digests, memory
(API.md §5.7).

`POST /assistant/chat/stream` is the only endpoint in the product that does not
return JSON. It streams server-sent events, because the first token is what
tells a user their question was understood, and eight seconds of nothing reads
as broken however fast the total is. The final event carries the complete
`AnswerView` — citations included — so a client that cannot handle SSE can
ignore the fragments and use only the last frame.

Everything else here is ordinary JSON. Note what is *absent*: there is no
endpoint that runs an embedding or an extraction on demand. Those are worker
concerns, and exposing them would let a client turn a request into an unbounded
provider bill.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas.assistant import (
    AnswerView,
    AskRequest,
    CitationView,
    ConversationView,
    DigestView,
    EntityMentionView,
    EntityView,
    GenerateDigestRequest,
    IndexStatusView,
    MemoryView,
    MessageView,
    PassageView,
    SemanticSearchRequest,
    SemanticSearchResponse,
    ThemeView,
)
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.domain.errors import NotFoundError
from app.domain.knowledge import EntityKind
from app.domain.memory import MemoryKind, decayed_weight
from app.domain.retrieval import Citation
from app.infra.ai.factory import build_chat, build_embedder
from app.infra.db.models.ai import Chunk, Conversation, ConversationMessage, Digest, Entity, Memory
from app.prompts.digest import DigestPeriod
from app.services.assistant_service import Answer, AssistantService
from app.services.digest_service import DigestService
from app.services.knowledge_service import KnowledgeService, ThemeCount
from app.services.memory_service import MemoryService
from app.services.retrieval_service import Passage, RetrievalService

router = APIRouter(responses=ERROR_RESPONSES)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def _citation_view(citation: Citation) -> CitationView:
    return CitationView(
        ref=citation.ref,
        entry_id=uuid.UUID(citation.entry_id) if citation.entry_id else None,
        capture_id=uuid.UUID(citation.capture_id) if citation.capture_id else None,
        title=citation.title,
        excerpt=citation.excerpt,
        occurred_at=citation.occurred_at,
        score=citation.score,
    )


def _answer_view(answer: Answer) -> AnswerView:
    return AnswerView(
        text=answer.text,
        intent=answer.intent.value,
        citations=[_citation_view(citation) for citation in answer.citations],
        notes=answer.notes,
        conversation_id=answer.conversation_id,
        message_id=answer.message_id,
        latency_ms=answer.latency_ms,
        used_model=answer.used_model,
        refused=answer.refused,
    )


def _passage_view(passage: Passage) -> PassageView:
    return PassageView(
        chunk_id=passage.chunk_id,
        text=passage.text,
        title=passage.title,
        entry_id=passage.entry_id,
        capture_id=passage.capture_id,
        occurred_at=passage.occurred_at,
        found_by=[retriever.value for retriever in passage.found_by],
        score=passage.score,
    )


def _entity_view(entity: Entity) -> EntityView:
    return EntityView(
        id=entity.id,
        kind=entity.kind,
        label=EntityKind(entity.kind).label,
        name=entity.name,
        detail=entity.detail,
        mention_count=entity.mention_count,
        first_seen_at=entity.first_seen_at,
        last_seen_at=entity.last_seen_at,
    )


def _theme_view(theme: ThemeCount) -> ThemeView:
    return ThemeView(
        kind=theme.kind.value,
        label=theme.kind.label,
        name=theme.name,
        count=theme.count,
        last_seen_at=theme.last_seen_at,
    )


def _digest_view(digest: Digest) -> DigestView:
    return DigestView(
        id=digest.id,
        period=digest.period,
        period_start=digest.period_start,
        period_end=digest.period_end,
        content=digest.content,
        stats=dict(digest.stats or {}),
        entry_count=digest.entry_count,
        read_at=digest.read_at,
        created_at=digest.created_at,
    )


def _memory_view(memory: Memory, *, now: datetime) -> MemoryView:
    return MemoryView(
        id=memory.id,
        kind=memory.kind,
        label=MemoryKind(memory.kind).label,
        statement=memory.statement,
        confidence=float(memory.confidence),
        confirmed_at=memory.confirmed_at,
        weight=decayed_weight(memory.confirmed_at, now=now),
    )


def _message_view(message: ConversationMessage) -> MessageView:
    return MessageView(
        id=message.id,
        role=message.role,
        content=message.content,
        intent=message.intent,
        citations=[CitationView.model_validate(item) for item in (message.citations or [])],
        created_at=message.created_at,
    )


def _assistant(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> AssistantService:
    return AssistantService(
        session,
        principal=principal,
        settings=settings,
        chat=build_chat(settings),
        # None when no embedder is configured. Retrieval then runs lexical-only,
        # which is a working search rather than a failing one.
        embedder=build_embedder(settings) if settings.embedding_backend != "fake" else None,
    )


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #
@router.post(
    "/assistant/chat",
    response_model=Envelope[AnswerView],
    summary="Poser une question à l'assistant",
)
async def ask(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[AskRequest, Body()],
) -> Envelope[AnswerView]:
    service = _assistant(session, principal, settings)
    answer = await service.ask(
        payload.question,
        conversation_id=payload.conversation_id,
        client_message_id=payload.client_message_id,
    )
    return Envelope(data=_answer_view(answer))


@router.post(
    "/assistant/chat/stream",
    summary="Poser une question, réponse en flux",
    response_class=StreamingResponse,
)
async def ask_streaming(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[AskRequest, Body()],
) -> StreamingResponse:
    """Stream an answer as server-sent events.

    Two event types: `delta` carries a text fragment, `answer` carries the
    finished `AnswerView`. A client that only reads `answer` gets exactly what
    the non-streaming endpoint returns, which is what makes this safe to add
    without splitting the client into two code paths.
    """
    service = _assistant(session, principal, settings)

    async def events() -> AsyncIterator[str]:
        async for fragment, answer in service.stream(
            payload.question,
            conversation_id=payload.conversation_id,
            client_message_id=payload.client_message_id,
        ):
            if answer is not None:
                body = _answer_view(answer).model_dump(mode="json")
                yield f"event: answer\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"
            elif fragment:
                delta = json.dumps({"text": fragment}, ensure_ascii=False)
                yield f"event: delta\ndata: {delta}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this an intermediate proxy buffers the whole response and
            # delivers it at once, which turns streaming back into waiting.
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/assistant/conversations",
    response_model=Collection[ConversationView],
    summary="Lister les conversations",
)
async def list_conversations(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Collection[ConversationView]:
    service = _assistant(session, principal, settings)
    rows = await service.list_conversations(limit=limit)
    return Collection(
        data=[
            ConversationView(
                id=row.id,
                title=row.title,
                message_count=row.message_count,
                last_message_at=row.last_message_at,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.get(
    "/assistant/conversations/{conversation_id}",
    response_model=Collection[MessageView],
    summary="Lire une conversation",
)
async def read_conversation(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    conversation_id: uuid.UUID,
) -> Collection[MessageView]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("Conversation introuvable.")
    service = _assistant(session, principal, settings)
    return Collection(
        data=[_message_view(message) for message in await service.messages(conversation_id)]
    )


# --------------------------------------------------------------------------- #
# Semantic search
# --------------------------------------------------------------------------- #
@router.post(
    "/search/semantic",
    response_model=Envelope[SemanticSearchResponse],
    summary="Recherche hybride (lexicale + sémantique)",
)
async def semantic_search(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[SemanticSearchRequest, Body()],
) -> Envelope[SemanticSearchResponse]:
    embedder = build_embedder(settings) if settings.embedding_backend != "fake" else None
    retrieval = RetrievalService(
        session,
        embedding_model=embedder.model if embedder else None,
        candidate_limit=settings.retrieval_candidate_limit,
    )

    query_vector: list[float] | None = None
    if embedder is not None:
        embedded = await embedder.embed([payload.query], kind="query")
        query_vector = list(embedded.vectors[0])

    result = await retrieval.search(
        payload.query,
        query_vector=query_vector,
        limit=payload.limit,
        entry_types=tuple(payload.entry_types),
    )
    return Envelope(
        data=SemanticSearchResponse(
            passages=[_passage_view(passage) for passage in result.passages],
            took_ms=result.took_ms,
            lexical_count=result.lexical_count,
            semantic_count=result.semantic_count,
            notes=result.notes,
        )
    )


@router.get(
    "/search/index-status",
    response_model=Envelope[IndexStatusView],
    summary="État de l'index sémantique",
)
async def index_status(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> Envelope[IndexStatusView]:
    """How much of this account's corpus is searchable by meaning.

    Exposed because a user whose semantic search returns nothing deserves to
    know whether the corpus is still indexing or whether their question simply
    has no answer. Those two look identical otherwise.
    """
    total = (await session.execute(select(func.count()).select_from(Chunk))).scalar_one()
    pending = (
        await session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
        )
    ).scalar_one()
    return Envelope(
        data=IndexStatusView(
            total_chunks=int(total),
            pending_chunks=int(pending),
            embedding_model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            provider=settings.embedding_backend,
        )
    )


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
@router.get("/entities", response_model=Collection[EntityView], summary="Lister les entités")
async def list_entities(
    session: SessionDep,
    principal: PrincipalDep,
    kind: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Collection[EntityView]:
    service = KnowledgeService(session)
    rows = await service.list_entities(
        kind=EntityKind(kind) if kind else None, query=q, limit=limit
    )
    return Collection(data=[_entity_view(entity) for entity in rows])


@router.get(
    "/entities/{entity_id}/mentions",
    response_model=Collection[EntityMentionView],
    summary="Où une entité a été citée",
)
async def entity_mentions(
    session: SessionDep,
    principal: PrincipalDep,
    entity_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Collection[EntityMentionView]:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise NotFoundError("Entité introuvable.")
    service = KnowledgeService(session)
    rows = await service.mentions_for(entity_id, limit=limit)
    return Collection(
        data=[
            EntityMentionView(
                id=row.id,
                entry_id=row.entry_id,
                capture_id=row.capture_id,
                role=row.role,
                confidence=float(row.confidence) if row.confidence is not None else None,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
    )


@router.get("/entities/themes", response_model=Collection[ThemeView], summary="Sujets récurrents")
async def themes(
    session: SessionDep,
    principal: PrincipalDep,
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> Collection[ThemeView]:
    from datetime import timedelta

    service = KnowledgeService(session)
    rows = await service.recurring_themes(
        since=datetime.now(UTC) - timedelta(days=days), limit=limit
    )
    return Collection(data=[_theme_view(theme) for theme in rows])


# --------------------------------------------------------------------------- #
# Digests
# --------------------------------------------------------------------------- #
@router.get("/digests", response_model=Collection[DigestView], summary="Lister les résumés")
async def list_digests(
    session: SessionDep,
    principal: PrincipalDep,
    period: Annotated[str | None, Query(pattern="^(daily|weekly|monthly)$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Collection[DigestView]:
    service = DigestService(session, principal=principal)
    rows = await service.recent(period=DigestPeriod(period) if period else None, limit=limit)
    return Collection(data=[_digest_view(digest) for digest in rows])


@router.post(
    "/digests",
    response_model=Envelope[DigestView],
    status_code=status.HTTP_201_CREATED,
    summary="Générer un résumé",
)
async def generate_digest(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[GenerateDigestRequest, Body()],
) -> Envelope[DigestView]:
    """Produce a digest on demand.

    Idempotent by the same unique constraint the cron relies on: asking twice
    for the same period returns the same row unless `force` is set. The cron
    normally gets there first; this exists for "I want it now" and for a user
    who changed timezone.
    """
    service = DigestService(session, principal=principal, chat=build_chat(settings))
    digest = await service.generate(
        DigestPeriod(payload.period),
        anchor=payload.anchor or date.today(),
        force=payload.force,
    )
    return Envelope(data=_digest_view(digest))


@router.post(
    "/digests/{digest_id}/read",
    response_model=Envelope[DigestView],
    summary="Marquer un résumé comme lu",
)
async def mark_digest_read(
    session: SessionDep, principal: PrincipalDep, digest_id: uuid.UUID
) -> Envelope[DigestView]:
    service = DigestService(session, principal=principal)
    digest = await service.mark_read(digest_id)
    if digest is None:
        raise NotFoundError("Résumé introuvable.")
    return Envelope(data=_digest_view(digest))


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #
@router.get("/memory", response_model=Collection[MemoryView], summary="Ce que l'assistant retient")
async def list_memory(session: SessionDep, principal: PrincipalDep) -> Collection[MemoryView]:
    """Everything the assistant holds about this user.

    Visible in full, always. A memory store the user cannot inspect is one they
    cannot correct, and an assistant confidently wrong about them with no
    explanation is worse than one that remembers nothing.
    """
    service = MemoryService(session, principal=principal)
    now = datetime.now(UTC)
    return Collection(data=[_memory_view(memory, now=now) for memory in await service.active()])


@router.delete(
    "/memory/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Oublier définitivement un fait",
)
async def dismiss_memory(
    session: SessionDep, principal: PrincipalDep, memory_id: uuid.UUID
) -> None:
    """Forget a fact, permanently.

    The row survives as a tombstone so a later conversation cannot re-learn it.
    Re-learning what a user explicitly rejected tells them their correction did
    not stick, which is worse than never having learned it.
    """
    service = MemoryService(session, principal=principal)
    await service.dismiss(memory_id)
