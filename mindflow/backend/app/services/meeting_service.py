"""A meeting, while it is still happening.

The shape of this service follows one constraint that is easy to state and easy
to violate: **a live feature must degrade to a recording, never to a failure.**
Somebody is in a room with other people. If the speech provider hiccups, or the
model is slow, or the network drops for twenty seconds, the meeting does not
pause to wait for us. So every path here either succeeds or leaves the
transcript intact and moves on — there is no state in which a provider problem
loses what was said.

That is why:

* a failed transcription of one block returns without raising, and the next
  block still lands;
* a failed analysis leaves `analysed_words` where it was, so the same window is
  retried at the next cue rather than skipped;
* closing a meeting whose summary could not be produced still writes the
  transcript and still creates the entries the live pass had already found.

The cost discipline is the other half. Analysis happens on a *cue*
(`domain.meeting.should_analyse`), not on a timer, because a forty-five minute
meeting on a timer is two hundred model calls for a handful of commitments
(ADR-047, ADR-062).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.errors import NotFoundError
from app.domain.errors import ValidationError as DomainValidationError
from app.domain.meeting import (
    MeetingStatus,
    MeetingWindow,
    Suggestion,
    SuggestionKind,
    merge_suggestions,
)
from app.domain.permissions import Action
from app.domain.ports import ChatMessage, ChatPort, ChatRequest, TranscriberPort
from app.infra.db.models.enterprise import MeetingSession
from app.observability import metrics
from app.observability.logging import get_logger
from app.prompts import meeting as prompts
from app.services.identity_service import Principal
from app.services.workspace_service import WorkspaceService

log = get_logger("meeting")

# Long enough for a live window, short enough that a runaway answer cannot cost
# what a whole summary costs.
LIVE_MAX_TOKENS = 500
SUMMARY_MAX_TOKENS = 1400

# A meeting nobody has closed after this long was abandoned — a phone that died,
# a browser tab closed. Swept rather than left `live` for ever, because a `live`
# row is what the client offers to resume.
ABANDON_AFTER_HOURS = 12


# --------------------------------------------------------------------------- #
# Model output
# --------------------------------------------------------------------------- #
class _LiveItem(BaseModel):
    kind: str = "question"
    text: str = ""
    owner: str | None = None
    confidence: float = 0.5


class _LiveOutput(BaseModel):
    suggestions: list[_LiveItem] = Field(default_factory=list)


class _SummaryAction(BaseModel):
    text: str = ""
    owner: str | None = None
    due: str | None = None


class _SummaryOutput(BaseModel):
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    actions: list[_SummaryAction] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class MeetingReport:
    """What closing a meeting produced."""

    summary: str
    decisions: list[str]
    actions: list[dict[str, Any]]
    open_questions: list[str]
    degraded: bool = False
    reason: str = ""


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class MeetingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        principal: Principal,
        settings: Settings,
        chat: ChatPort | None = None,
        transcriber: TranscriberPort | None = None,
    ) -> None:
        self._session = session
        self._principal = principal
        self._settings = settings
        self._chat = chat
        self._transcriber = transcriber
        self._workspaces = WorkspaceService(session, principal=principal)

    # -- Lifecycle ---------------------------------------------------------- #

    async def open(
        self,
        *,
        title: str | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> MeetingSession:
        """Start a session. Refuses a second live one for the same person.

        One microphone, one meeting. Allowing two would produce two half
        transcripts of the same room, which is worse than refusing.
        """
        await self._workspaces.require(Action.ENTRY_WRITE)

        existing = await self._live_session()
        if existing is not None:
            raise DomainValidationError(
                "Une réunion est déjà en cours. Terminez-la avant d'en ouvrir une autre.",
                field="meeting",
            )

        session = MeetingSession(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            workspace_id=workspace_id,
            title=(title or "").strip() or None,
            status=MeetingStatus.LIVE.value,
            started_at=datetime.now(UTC),
            live_transcript="",
            live_suggestions=[],
        )
        self._session.add(session)
        await self._session.flush()
        metrics.meetings_total.labels("opened").inc()
        log.info("meeting.opened", meeting_id=str(session.id))
        return session

    async def get(self, meeting_id: uuid.UUID) -> MeetingSession:
        row = await self._session.get(MeetingSession, meeting_id)
        if row is None or row.user_id != self._principal.user_id:
            # A meeting is personal to the person recording it, so somebody
            # else's is not merely forbidden — it is not theirs to see.
            raise NotFoundError("Réunion introuvable.")
        return row

    async def list_recent(self, *, limit: int = 20) -> list[MeetingSession]:
        rows = await self._session.execute(
            select(MeetingSession)
            .where(MeetingSession.user_id == self._principal.user_id)
            .order_by(MeetingSession.started_at.desc())
            .limit(limit)
        )
        return list(rows.scalars())

    async def live(self) -> MeetingSession | None:
        return await self._live_session()

    # -- Ingest ------------------------------------------------------------- #

    async def append_audio(
        self,
        meeting_id: uuid.UUID,
        audio: bytes,
        *,
        media_type: str,
    ) -> tuple[MeetingSession, list[Suggestion]]:
        """Transcribe one block and fold it into the running transcript.

        Returns the session and any *new* suggestions, so the caller can push
        exactly the delta rather than the whole list.
        """
        session = await self._require_live(meeting_id)

        transcriber = self._transcriber
        if transcriber is None:
            raise DomainValidationError("Transcription indisponible.", field="audio")

        try:
            result = await transcriber.transcribe(audio, media_type=media_type)
            text = result.text
        except Exception:
            # The room did not stop talking. Losing one block is a gap in the
            # transcript; raising here would end the meeting.
            metrics.meeting_blocks_total.labels("failed").inc()
            log.warning("meeting.block_failed", meeting_id=str(meeting_id))
            return session, []

        metrics.meeting_blocks_total.labels("ok").inc()
        return await self.append_text(meeting_id, text, _session=session)

    async def append_text(
        self,
        meeting_id: uuid.UUID,
        text: str,
        *,
        _session: MeetingSession | None = None,
    ) -> tuple[MeetingSession, list[Suggestion]]:
        """Fold already-transcribed text in. Used by clients that do their own STT."""
        session = _session or await self._require_live(meeting_id)
        if not text.strip():
            return session, []

        window = self._window(session).append(text)
        session.live_transcript = window.transcript

        if not window.due():
            await self._session.flush()
            return session, []

        added = await self._analyse(session, window)
        return session, added

    # -- Analysis ----------------------------------------------------------- #

    async def _analyse(
        self,
        session: MeetingSession,
        window: MeetingWindow,
        *,
        closing: bool = False,
    ) -> list[Suggestion]:
        """One live pass over the pending window. Never raises."""
        chat = self._chat
        pending = window.pending
        if chat is None or not pending.strip():
            return []

        existing = self.suggestions(session)
        block = prompts.build_live_block(
            pending,
            [item.text for item in existing[-12:]],
        )

        try:
            response = await chat.complete(
                ChatRequest(
                    messages=(ChatMessage(role="user", content=block),),
                    system=prompts.LIVE_SYSTEM_PROMPT,
                    max_output_tokens=LIVE_MAX_TOKENS,
                    json_schema=_LIVE_SCHEMA,
                    temperature=0.1,
                )
            )
        except Exception:
            # `analysed_words` is deliberately not advanced: the same window is
            # retried at the next cue. A window silently skipped is a commitment
            # silently lost.
            metrics.meeting_analyses_total.labels("failed").inc()
            log.warning("meeting.analysis_failed", meeting_id=str(session.id))
            await self._session.flush()
            return []

        if response.refused:
            metrics.meeting_analyses_total.labels("refused").inc()
            await self._advance(session, window)
            return []

        parsed = _parse_live(response.text)
        added = [
            Suggestion(
                kind=SuggestionKind.parse(item.kind),
                text=item.text.strip(),
                owner=(item.owner or None),
                confidence=item.confidence,
                at_word=window.total_words,
            )
            for item in parsed
            if item.text.strip()
        ]

        merged = merge_suggestions(existing, added)
        new_keys = {item.key for item in merged} - {item.key for item in existing}
        session.live_suggestions = [item.to_json() for item in merged]
        await self._advance(session, window)

        metrics.meeting_analyses_total.labels("ok").inc()
        metrics.meeting_suggestions_total.inc(len(new_keys))
        if closing:
            log.info("meeting.closing_pass", meeting_id=str(session.id), added=len(new_keys))
        return [item for item in merged if item.key in new_keys]

    async def _advance(self, session: MeetingSession, window: MeetingWindow) -> None:
        marked = window.mark_analysed()
        session.live_transcript = marked.transcript
        session.analysed_words = marked.analysed_words
        await self._session.flush()

    # -- Closing ------------------------------------------------------------ #

    async def close(self, meeting_id: uuid.UUID) -> tuple[MeetingSession, MeetingReport]:
        """End the meeting and produce its report.

        Runs one last live pass first: the most likely moment for a commitment
        is the last thirty seconds, when people agree what happens next.
        """
        session = await self._require_live(meeting_id)
        window = self._window(session)

        if window.due(closing=True):
            await self._analyse(session, window, closing=True)
            window = self._window(session)

        report = await self._summarise(session, window)

        session.status = MeetingStatus.ENDED.value
        session.ended_at = datetime.now(UTC)
        await self._session.flush()

        metrics.meetings_total.labels("closed").inc()
        log.info(
            "meeting.closed",
            meeting_id=str(meeting_id),
            words=window.total_words,
            degraded=report.degraded,
        )
        return session, report

    async def abandon(self, meeting_id: uuid.UUID) -> MeetingSession:
        """Discard a meeting without producing anything."""
        session = await self._require_live(meeting_id)
        session.status = MeetingStatus.ABANDONED.value
        session.ended_at = datetime.now(UTC)
        await self._session.flush()
        metrics.meetings_total.labels("abandoned").inc()
        return session

    async def _summarise(self, session: MeetingSession, window: MeetingWindow) -> MeetingReport:
        """The closing pass. Degrades to what the live pass found."""
        suggestions = self.suggestions(session)
        fallback = _fallback_report(suggestions, window)

        chat = self._chat
        if chat is None or window.total_words < 30:
            # Too short to summarise. Saying so beats three sentences of prose
            # about a meeting that produced nothing.
            fallback.degraded = True
            fallback.reason = (
                "Réunion trop courte pour un compte rendu."
                if chat is not None
                else "Service d'analyse indisponible."
            )
            return fallback

        minutes = None
        if session.started_at is not None:
            elapsed = datetime.now(UTC) - session.started_at
            minutes = max(1, int(elapsed.total_seconds() // 60))

        block = prompts.build_summary_block(
            window.transcript,
            [item.text for item in suggestions],
            title=session.title,
            duration_minutes=minutes,
        )

        try:
            response = await chat.complete(
                ChatRequest(
                    messages=(ChatMessage(role="user", content=block),),
                    system=prompts.SUMMARY_SYSTEM_PROMPT,
                    max_output_tokens=SUMMARY_MAX_TOKENS,
                    json_schema=_SUMMARY_SCHEMA,
                    temperature=0.2,
                )
            )
        except Exception:
            log.warning("meeting.summary_failed", meeting_id=str(session.id))
            fallback.degraded = True
            fallback.reason = (
                "Le compte rendu n'a pas pu être produit. "
                "La transcription et les éléments relevés sont conservés."
            )
            return fallback

        if response.refused:
            fallback.degraded = True
            fallback.reason = "Le modèle a refusé de produire un compte rendu."
            return fallback

        parsed = _parse_summary(response.text)
        if parsed is None:
            fallback.degraded = True
            fallback.reason = "Compte rendu illisible ; éléments relevés conservés."
            return fallback

        return MeetingReport(
            summary=parsed.summary.strip(),
            decisions=[item.strip() for item in parsed.decisions if item.strip()],
            actions=[
                {"text": action.text.strip(), "owner": action.owner, "due": action.due}
                for action in parsed.actions
                if action.text.strip()
            ],
            open_questions=[item.strip() for item in parsed.open_questions if item.strip()],
        )

    # -- Helpers ------------------------------------------------------------ #

    async def _require_live(self, meeting_id: uuid.UUID) -> MeetingSession:
        session = await self.get(meeting_id)
        if session.status != MeetingStatus.LIVE.value:
            raise DomainValidationError("Cette réunion est terminée.", field="meeting")
        return session

    async def _live_session(self) -> MeetingSession | None:
        rows = await self._session.execute(
            select(MeetingSession).where(
                MeetingSession.user_id == self._principal.user_id,
                MeetingSession.status == MeetingStatus.LIVE.value,
            )
        )
        return rows.scalars().first()

    def _window(self, session: MeetingSession) -> MeetingWindow:
        return MeetingWindow(
            transcript=session.live_transcript or "",
            analysed_words=session.analysed_words or 0,
        )

    def suggestions(self, session: MeetingSession) -> list[Suggestion]:
        """The stored suggestions, decoded. Public because every view needs them."""
        items = [Suggestion.from_json(row) for row in (session.live_suggestions or [])]
        return [item for item in items if item is not None]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
_LIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["action", "decision", "question"]},
                    "text": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["kind", "text"],
            },
        }
    },
    "required": ["suggestions"],
}

_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "due": {"type": ["string", "null"]},
                },
                "required": ["text"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
}


def _parse_live(payload: str) -> list[_LiveItem]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("meeting.invalid_live_json")
        return []
    try:
        return _LiveOutput.model_validate(data).suggestions
    except ValidationError as exc:
        log.warning("meeting.live_schema_violation", errors=exc.error_count())
        return []


def _parse_summary(payload: str) -> _SummaryOutput | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("meeting.invalid_summary_json")
        return None
    try:
        return _SummaryOutput.model_validate(data)
    except ValidationError as exc:
        log.warning("meeting.summary_schema_violation", errors=exc.error_count())
        return None


def _fallback_report(suggestions: list[Suggestion], window: MeetingWindow) -> MeetingReport:
    """What to show when no summary could be produced.

    Not empty: the live pass already found things, and they are real. A degraded
    report that lists them is far more useful than an apology.
    """
    return MeetingReport(
        summary="",
        decisions=[s.text for s in suggestions if s.kind is SuggestionKind.DECISION],
        actions=[
            {"text": s.text, "owner": s.owner, "due": None}
            for s in suggestions
            if s.kind is SuggestionKind.ACTION
        ],
        open_questions=[s.text for s in suggestions if s.kind is SuggestionKind.QUESTION],
    )
