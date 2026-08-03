"""The assistant: the engine that answers the five questions.

| Question | Route | Model involved |
| --- | --- | --- |
| « Que dois-je faire aujourd'hui ? » | agenda query | none |
| « Quelles sont mes tâches en retard ? » | overdue query | none |
| « Résume mes réunions » | retrieval over meetings → generation | yes |
| « Montre les notes concernant le Forecast Gabon » | retrieval → list | none |
| « Quels sujets reviennent souvent ? » | entity aggregation → narration | yes |

Two of the five never reach a language model and one reaches it only to phrase
numbers that SQL computed. That is the central decision of this service, and it
is not a cost optimisation: « ce qui est dû aujourd'hui » is a fact the database
knows exactly, and a model asked the same question can only approximate it,
more slowly. Routing everything through generation would make the assistant
*worse* at the questions users ask most.

The generative path is retrieval-augmented and cited. Every passage handed to
the model is numbered, the model is instructed to attach those numbers, and the
citations travel with the answer so the client can show what it was built from.
An answer generated with no passages is counted separately
(`assistant_uncited_answers_total`) because it is a sentence the system cannot
back — rare by design, and worth knowing about when it happens.

Memory is loaded into the system prompt, weighted by how recently it was
confirmed (`app.domain.memory`). It is never used to answer factual questions —
only to frame them.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain import chunking
from app.domain.errors import ExtractionUnavailableError, NotFoundError
from app.domain.intent import AssistantPlan, Intent, plan
from app.domain.knowledge import EntityKind
from app.domain.ports import ChatMessage, ChatPort, ChatRequest, EmbedderPort
from app.domain.retrieval import Citation, deduplicate_citations
from app.infra.db.models.ai import Conversation, ConversationMessage
from app.infra.db.models.core import Entry, Task
from app.observability import metrics
from app.observability.logging import get_logger
from app.prompts import answer as answer_prompts
from app.prompts import insights as insight_prompts
from app.services.agenda_service import AgendaService
from app.services.identity_service import Principal
from app.services.knowledge_service import KnowledgeService, ThemeCount
from app.services.memory_service import MemoryService
from app.services.retrieval_service import RetrievalService, to_citations
from app.services.task_service import TaskService

log = get_logger("ai.assistant")

# How many previous turns are replayed to the model. Enough for "et la semaine
# dernière ?" to make sense; short enough that a long conversation does not turn
# every answer into a large bill.
HISTORY_TURNS = 6
NOTHING_FOUND = "Je ne trouve pas cette information dans vos notes."


@dataclass(slots=True)
class Answer:
    text: str
    intent: Intent
    citations: list[Citation] = field(default_factory=list)
    # What the assistant did, in the user's language. Shown under the answer:
    # an assistant that says how it answered is one a user can correct.
    notes: list[str] = field(default_factory=list)
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    latency_ms: int = 0
    used_model: bool = False
    refused: bool = False


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        settings: Settings,
        chat: ChatPort,
        embedder: EmbedderPort | None = None,
    ) -> None:
        self._session = session
        self._principal = principal
        self._settings = settings
        self._chat = chat
        self._embedder = embedder
        self._retrieval = RetrievalService(
            session,
            embedding_model=embedder.model if embedder else None,
            candidate_limit=settings.retrieval_candidate_limit,
        )
        self._knowledge = KnowledgeService(session, chat=chat)
        self._memory = MemoryService(session, principal=principal, chat=chat)
        self._agenda = AgendaService(session, principal=principal)
        self._tasks = TaskService(session, principal=principal)

    # -- Public ------------------------------------------------------------- #

    async def ask(
        self,
        question: str,
        *,
        conversation_id: uuid.UUID | None = None,
        client_message_id: str | None = None,
    ) -> Answer:
        """Answer a question, persisting the exchange."""
        started = time.perf_counter()
        made = plan(question)

        conversation = await self._conversation(conversation_id, question)
        if client_message_id:
            existing = await self._replay(conversation, client_message_id)
            if existing is not None:
                # Same idempotency contract as capture declaration (ADR-009). A
                # phone retrying on a flaky connection must not ask twice, and
                # must not be billed twice.
                return existing

        await self._append(conversation, role="user", content=question, client_id=client_message_id)

        try:
            answer = await self._dispatch(made, question)
        except ExtractionUnavailableError:
            metrics.assistant_questions_total.labels(made.intent.value, "unavailable").inc()
            raise

        answer.latency_ms = int((time.perf_counter() - started) * 1000)
        answer.conversation_id = conversation.id
        message = await self._append(
            conversation,
            role="assistant",
            content=answer.text,
            intent=answer.intent.value,
            citations=answer.citations,
            latency_ms=answer.latency_ms,
        )
        answer.message_id = message.id

        metrics.assistant_questions_total.labels(made.intent.value, "ok").inc()
        metrics.assistant_duration_seconds.labels(made.intent.value).observe(
            answer.latency_ms / 1000
        )
        if answer.used_model and not answer.citations:
            metrics.assistant_uncited_answers_total.inc()
        return answer

    async def stream(
        self,
        question: str,
        *,
        conversation_id: uuid.UUID | None = None,
        client_message_id: str | None = None,
    ) -> AsyncIterator[tuple[str, Answer | None]]:
        """Answer incrementally: `(text_fragment, None)` then `("", answer)`.

        The structured routes have nothing to stream — their answer is computed
        whole — so they yield it in one piece. That asymmetry is deliberate and
        visible to the client, which shows an instant answer for those and a
        typing indicator for the rest.
        """
        made = plan(question)
        if not made.use_generation:
            answer = await self.ask(
                question, conversation_id=conversation_id, client_message_id=client_message_id
            )
            yield answer.text, None
            yield "", answer
            return

        started = time.perf_counter()
        conversation = await self._conversation(conversation_id, question)
        await self._append(conversation, role="user", content=question, client_id=client_message_id)

        request, citations, notes = await self._generation_request(made, question)
        parts: list[str] = []
        refused = False
        async for chunk in self._chat.stream(request):
            if chunk.text:
                parts.append(chunk.text)
                yield chunk.text, None
            if chunk.done and chunk.finish_reason == "refusal":
                refused = True

        text = "".join(parts).strip() or NOTHING_FOUND
        answer = Answer(
            text=text,
            intent=made.intent,
            citations=citations,
            notes=notes,
            conversation_id=conversation.id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            used_model=True,
            refused=refused,
        )
        message = await self._append(
            conversation,
            role="assistant",
            content=answer.text,
            intent=answer.intent.value,
            citations=citations,
            latency_ms=answer.latency_ms,
        )
        answer.message_id = message.id
        metrics.assistant_questions_total.labels(made.intent.value, "ok").inc()
        metrics.assistant_duration_seconds.labels(made.intent.value).observe(
            answer.latency_ms / 1000
        )
        if not citations:
            metrics.assistant_uncited_answers_total.inc()
        yield "", answer

    # -- Routing ------------------------------------------------------------ #

    async def _dispatch(self, made: AssistantPlan, question: str) -> Answer:
        if made.intent is Intent.TODAY:
            return await self._today(made)
        if made.intent is Intent.OVERDUE:
            return await self._overdue(made)
        if made.intent is Intent.UPCOMING:
            return await self._upcoming(made)
        if made.intent is Intent.THEMES:
            return await self._themes(made)
        if made.intent is Intent.RECALL:
            return await self._recall(made, question)
        return await self._generate(made, question)

    # -- Structured routes (no model) --------------------------------------- #

    async def _today(self, made: AssistantPlan) -> Answer:
        """« Que dois-je faire aujourd'hui ? »"""
        today = self._agenda.local_day(datetime.now(UTC))
        agenda = await self._agenda.agenda(
            start=today, end=today + timedelta(days=1), include_done=False
        )
        due = [item for day in agenda.days for item in day.items]
        overdue = agenda.overdue

        lines: list[str] = []
        if not due and not overdue:
            lines.append("Rien de prévu aujourd'hui, et aucune tâche en retard.")
        if due:
            lines.append(f"Aujourd'hui — {len(due)} " + _plural(len(due), "tâche", "tâches") + " :")
            lines.extend(f"• {_describe(item.entry, item.task)}" for item in due[:20])
        if overdue:
            # Deliberately after today's list and explicitly labelled: mixing
            # them would answer a question the user did not ask.
            lines.append("")
            lines.append(
                f"En retard — {len(overdue)} " + _plural(len(overdue), "tâche", "tâches") + " :"
            )
            lines.extend(f"• {_describe(item.entry, item.task)}" for item in overdue[:10])

        return Answer(text="\n".join(lines), intent=made.intent, notes=made.notes)

    async def _overdue(self, made: AssistantPlan) -> Answer:
        """« Quelles sont mes tâches en retard ? »"""
        rows = await self._tasks.overdue(limit=50)
        if not rows:
            return Answer(text="Aucune tâche en retard.", intent=made.intent, notes=made.notes)

        lines = [f"{len(rows)} " + _plural(len(rows), "tâche", "tâches") + " en retard :"]
        lines.extend(f"• {_describe(entry, task, with_lateness=True)}" for entry, task in rows)
        return Answer(text="\n".join(lines), intent=made.intent, notes=made.notes)

    async def _upcoming(self, made: AssistantPlan) -> Answer:
        days = made.window_days or 7
        rows = await self._tasks.upcoming(days=days)
        if not rows:
            return Answer(
                text=f"Rien de prévu dans les {days} prochains jours.",
                intent=made.intent,
                notes=made.notes,
            )
        lines = [f"Les {days} prochains jours — {len(rows)} échéances :"]
        lines.extend(f"• {_describe(entry, task)}" for entry, task in rows[:30])
        return Answer(text="\n".join(lines), intent=made.intent, notes=made.notes)

    async def _recall(self, made: AssistantPlan, question: str) -> Answer:
        """« Montre les notes concernant le Forecast Gabon » — a list, not prose.

        The user asked to be *shown* notes. Rendering them as a paragraph would
        add latency and cost to make the answer harder to scan.
        """
        result = await self._retrieve(made)
        if result.is_empty:
            return Answer(
                text=f"Aucune note trouvée sur « {made.search_query} ».",
                intent=made.intent,
                notes=made.notes + result.notes,
            )

        citations = deduplicate_citations(to_citations(result.passages))
        lines = [f"{len(citations)} " + _plural(len(citations), "note", "notes") + " trouvées :"]
        for citation in citations:
            date_part = f" ({citation.occurred_at})" if citation.occurred_at else ""
            lines.append(f"• {citation.title}{date_part}")
        return Answer(
            text="\n".join(lines),
            intent=made.intent,
            citations=citations,
            notes=made.notes + result.notes,
        )

    # -- Aggregation route -------------------------------------------------- #

    async def _themes(self, made: AssistantPlan) -> Answer:
        """« Quels sujets reviennent souvent ? »

        Counted in SQL, narrated by the model. The counts are handed over as
        established facts precisely so the model cannot recount them and be
        confidently off by two.
        """
        since = datetime.now(UTC) - timedelta(days=90)
        themes = await self._knowledge.recurring_themes(since=since, limit=12)
        if not themes:
            return Answer(
                text=(
                    "Pas encore assez d'éléments pour dégager des sujets récurrents. "
                    "Ils apparaîtront à mesure que vos notes s'accumulent."
                ),
                intent=made.intent,
                notes=made.notes,
            )

        rows = [(theme.kind.label, theme.name, theme.count) for theme in themes]
        request = ChatRequest(
            system=insight_prompts.THEMES_PROMPT.system,
            messages=(
                ChatMessage(
                    role="user",
                    content=insight_prompts.build_counts_block("les 90 derniers jours", rows),
                ),
            ),
            temperature=0.2,
            max_output_tokens=500,
        )
        response = await self._chat.complete(request)
        text = response.text.strip() or _fallback_themes(themes)
        return Answer(
            text=text,
            intent=made.intent,
            notes=made.notes,
            used_model=True,
            refused=response.refused,
        )

    # -- Generative route --------------------------------------------------- #

    async def _generate(self, made: AssistantPlan, question: str) -> Answer:
        request, citations, notes = await self._generation_request(made, question)
        response = await self._chat.complete(request)
        return Answer(
            text=response.text.strip() or NOTHING_FOUND,
            intent=made.intent,
            citations=citations,
            notes=made.notes + notes,
            used_model=True,
            refused=response.refused,
        )

    async def _generation_request(
        self, made: AssistantPlan, question: str
    ) -> tuple[ChatRequest, list[Citation], list[str]]:
        """Assemble the RAG call: memory, history, passages, question."""
        result = await self._retrieve(made)
        passages = result.passages

        # Trimmed to the configured budget rather than sent whole. Past roughly
        # this size recall stops improving and the model starts answering from
        # the middle of the context, which reads as ignoring the question.
        texts = chunking.fit_to_budget(
            [passage.text for passage in passages],
            budget_tokens=self._settings.chat_context_token_budget,
        )
        rendered = [(passage.label, text) for passage, text in zip(passages, texts, strict=False)]
        citations = deduplicate_citations(to_citations(passages[: len(texts)]))

        system = answer_prompts.ANSWER_PROMPT.system
        remembered = await self._memory.system_block()
        if remembered:
            system = f"{system}\n\n{remembered}"

        history = await self._history(made)
        today = self._agenda.local_day(datetime.now(UTC)).isoformat()
        messages = (
            *history,
            ChatMessage(role="user", content=answer_prompts.build_context_block(rendered)),
            ChatMessage(
                role="user", content=answer_prompts.build_question_block(question, today=today)
            ),
        )

        request = ChatRequest(
            system=system,
            messages=messages,
            temperature=0.2,
            max_output_tokens=self._settings.chat_max_output_tokens,
        )
        return request, citations, result.notes

    async def _retrieve(self, made: AssistantPlan):  # type: ignore[no-untyped-def]
        query_vector: list[float] | None = None
        if self._embedder is not None:
            try:
                embedded = await self._embedder.embed([made.search_query], kind="query")
                query_vector = list(embedded.vectors[0])
            except ExtractionUnavailableError:
                # Lexical search alone is a perfectly good answer, and much
                # better than an error page. The degradation is reported.
                log.warning("assistant.embed_failed", provider=self._embedder.name)

        result = await self._retrieval.search(
            made.search_query,
            query_vector=query_vector,
            limit=self._settings.retrieval_context_chunks,
            entry_types=made.entry_types,
        )
        if query_vector is None and self._embedder is not None:
            result.notes.append(
                "Recherche lexicale seule : le service d'embedding est indisponible."
            )
        return result

    # -- Conversation ------------------------------------------------------- #

    async def _conversation(self, conversation_id: uuid.UUID | None, question: str) -> Conversation:
        if conversation_id is not None:
            conversation = await self._session.get(Conversation, conversation_id)
            if conversation is None:
                raise NotFoundError("Conversation introuvable.")
            return conversation

        conversation = Conversation(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            # The first question, trimmed. Good enough to recognise a thread in
            # a list, and replaceable by the user.
            title=question.strip()[:120] or None,
        )
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def _append(
        self,
        conversation: Conversation,
        *,
        role: str,
        content: str,
        client_id: str | None = None,
        intent: str | None = None,
        citations: list[Citation] | None = None,
        latency_ms: int | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            account_id=conversation.account_id,
            conversation_id=conversation.id,
            role=role,
            content=content,
            client_message_id=client_id,
            intent=intent,
            citations=[_citation_json(citation) for citation in (citations or [])],
            latency_ms=latency_ms,
        )
        self._session.add(message)
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(UTC)
        await self._session.flush()
        return message

    async def _replay(self, conversation: Conversation, client_id: str) -> Answer | None:
        """Return the answer already given to this client message, if any."""
        previous = (
            (
                await self._session.execute(
                    select(ConversationMessage)
                    .where(
                        ConversationMessage.conversation_id == conversation.id,
                        ConversationMessage.client_message_id == client_id,
                    )
                    .order_by(ConversationMessage.created_at)
                )
            )
            .scalars()
            .first()
        )
        if previous is None:
            return None

        reply = (
            (
                await self._session.execute(
                    select(ConversationMessage)
                    .where(
                        ConversationMessage.conversation_id == conversation.id,
                        ConversationMessage.role == "assistant",
                        ConversationMessage.created_at >= previous.created_at,
                    )
                    .order_by(ConversationMessage.created_at)
                )
            )
            .scalars()
            .first()
        )
        if reply is None:
            return None

        return Answer(
            text=reply.content,
            intent=Intent(reply.intent) if reply.intent else Intent.OPEN_QUESTION,
            citations=[_citation_from_json(item) for item in reply.citations],
            conversation_id=conversation.id,
            message_id=reply.id,
            notes=["Réponse déjà produite pour cette question."],
        )

    async def _history(self, made: AssistantPlan) -> tuple[ChatMessage, ...]:
        """Recent turns, so follow-up questions resolve.

        Excluded for the structured intents: they are answered from the
        database, and replaying history there would only add cost to a call that
        does not happen.
        """
        if not made.use_generation:
            return ()
        rows = list(
            (
                await self._session.execute(
                    select(ConversationMessage)
                    .order_by(ConversationMessage.created_at.desc())
                    .limit(HISTORY_TURNS * 2)
                )
            ).scalars()
        )
        rows.reverse()
        return tuple(
            ChatMessage(role=row.role, content=row.content)
            for row in rows
            if row.role in ("user", "assistant")
        )

    async def list_conversations(self, *, limit: int = 30) -> list[Conversation]:
        return list(
            (
                await self._session.execute(
                    select(Conversation)
                    .where(Conversation.archived_at.is_(None))
                    .order_by(Conversation.last_message_at.desc().nullslast())
                    .limit(limit)
                )
            ).scalars()
        )

    async def messages(self, conversation_id: uuid.UUID) -> list[ConversationMessage]:
        return list(
            (
                await self._session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation_id)
                    .order_by(ConversationMessage.created_at)
                )
            ).scalars()
        )


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count <= 1 else plural


def _describe(entry: Entry, task: Task | None, *, with_lateness: bool = False) -> str:
    parts = [entry.title]
    if task is not None and task.due_at is not None:
        parts.append(f"— {task.due_at.date().isoformat()}")
        if with_lateness:
            late = (datetime.now(UTC) - task.due_at).days
            if late >= 1:
                parts.append(f"({late} " + _plural(late, "jour", "jours") + " de retard)")
    return " ".join(parts)


def _fallback_themes(themes: list[ThemeCount]) -> str:
    """A plain listing, used when the model returns nothing.

    The counts are the answer; the narration is a nicety. Losing the model must
    not lose the information it was asked to phrase.
    """
    lines = ["Sujets les plus présents :"]
    lines.extend(f"• {theme.name} — {theme.count} mentions" for theme in themes)
    return "\n".join(lines)


def _citation_json(citation: Citation) -> dict[str, object]:
    return {
        "ref": citation.ref,
        "entry_id": citation.entry_id,
        "capture_id": citation.capture_id,
        "title": citation.title,
        "excerpt": citation.excerpt,
        "occurred_at": citation.occurred_at,
        "score": citation.score,
    }


def _citation_from_json(data: dict[str, object]) -> Citation:
    return Citation(
        ref=str(data.get("ref", "")),
        entry_id=str(data["entry_id"]) if data.get("entry_id") else None,
        capture_id=str(data["capture_id"]) if data.get("capture_id") else None,
        title=str(data.get("title", "")),
        excerpt=str(data.get("excerpt", "")),
        occurred_at=str(data["occurred_at"]) if data.get("occurred_at") else None,
        score=float(str(data.get("score") or 0.0)),
    )


__all__ = ["Answer", "AssistantService", "EntityKind"]
