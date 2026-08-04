"""Live meetings (API.md §18).

Six routes, and the shape of them is the design.

**Audio arrives as blocks, not as a socket.** A WebSocket would be the obvious
choice and is the wrong one here: it needs its own authentication path, its own
reconnection story, and its own proxy configuration, in exchange for latency
this feature does not need — a block every thirty seconds is well inside the
window where a suggestion is still useful in the room. `POST` of a block reuses
the bearer token, the timeouts and the error format the rest of the product
already has, and a dropped connection is a retried request rather than a
resumption protocol.

**Suggestions come back on the same response as the block that produced them**,
*and* on an SSE stream. The response is what makes the recording device's own
panel update without polling; the stream is what lets a second screen — a laptop
open beside the phone — follow along. A client that only ever reads the POST
response is complete.

**Closing is a request, not a timeout.** A meeting that ends because nothing was
posted for five minutes would end during the long silence while somebody reads a
document.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Path, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.domain.errors import ValidationError
from app.domain.meeting import Suggestion
from app.infra.ai.factory import build_chat, build_transcriber
from app.infra.db.models.enterprise import MeetingSession
from app.services.meeting_service import MeetingReport, MeetingService

router = APIRouter(responses=ERROR_RESPONSES)

# One block is a minute of 32 kbps audio with room to spare. Larger blocks are a
# client that has stopped streaming and started uploading a recording, which is
# a different feature with a different cost profile.
MAX_BLOCK_BYTES = 4 * 1024 * 1024

# How often the stream re-reads the session. Two seconds is well under the
# thirty a block takes to arrive, so a suggestion reaches a second screen
# essentially when it is produced, and the query is a primary-key lookup.
STREAM_POLL_SECONDS = 2.0

# Streams are closed rather than left open for ever: an SSE connection nobody
# reads still holds a worker and a database session.
STREAM_MAX_SECONDS = 60 * 90


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class OpenMeetingRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    workspace_id: uuid.UUID | None = None


class AppendTextRequest(BaseModel):
    """For clients that transcribe on the device.

    A browser has the Web Speech API and a phone has an on-device recogniser;
    both are free, private and instant compared with sending audio. Accepting
    text is not a shortcut — it is the cheaper path where it exists.
    """

    text: str = Field(min_length=1, max_length=20000)


class SuggestionView(BaseModel):
    kind: str
    label: str
    text: str
    owner: str | None = None
    confidence: float = 0.5
    at_word: int = 0
    created_at: datetime


class MeetingView(BaseModel):
    id: uuid.UUID
    title: str | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    workspace_id: uuid.UUID | None = None
    transcript: str = ""
    word_count: int = 0
    suggestions: list[SuggestionView] = Field(default_factory=list)


class MeetingBlockView(BaseModel):
    """What one block produced.

    `new_suggestions` is the delta rather than the whole list, so a client can
    animate exactly what appeared. `word_count` lets it show progress without
    re-reading the transcript it already has.
    """

    meeting_id: uuid.UUID
    word_count: int
    new_suggestions: list[SuggestionView] = Field(default_factory=list)


class MeetingReportView(BaseModel):
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    # True when the report is what the live pass had already found rather than a
    # written summary. Stated because a degraded report that looks complete is
    # the failure this whole feature has to avoid.
    degraded: bool = False
    reason: str = ""


class MeetingClosedView(BaseModel):
    meeting: MeetingView
    report: MeetingReportView


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def _suggestion_view(item: Suggestion) -> SuggestionView:
    return SuggestionView(
        kind=item.kind.value,
        label=item.kind.label,
        text=item.text,
        owner=item.owner,
        confidence=item.confidence,
        at_word=item.at_word,
        created_at=item.created_at,
    )


def _meeting_view(session: MeetingSession, suggestions: list[Suggestion]) -> MeetingView:
    transcript = session.live_transcript or ""
    return MeetingView(
        id=session.id,
        title=session.title,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        workspace_id=session.workspace_id,
        transcript=transcript,
        word_count=len(transcript.split()),
        suggestions=[_suggestion_view(item) for item in suggestions],
    )


def _report_view(report: MeetingReport) -> MeetingReportView:
    return MeetingReportView(
        summary=report.summary,
        decisions=report.decisions,
        actions=report.actions,
        open_questions=report.open_questions,
        degraded=report.degraded,
        reason=report.reason,
    )


def _service(session: Any, principal: Any, settings: Any) -> MeetingService:
    return MeetingService(
        session,
        principal=principal,
        settings=settings,
        chat=build_chat(settings),
        transcriber=build_transcriber(settings),
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post(
    "/meetings",
    response_model=Envelope[MeetingView],
    status_code=status.HTTP_201_CREATED,
    summary="Démarrer une réunion",
)
async def open_meeting(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    payload: Annotated[OpenMeetingRequest, Body()],
) -> Envelope[MeetingView]:
    service = _service(session, principal, settings)
    meeting = await service.open(title=payload.title, workspace_id=payload.workspace_id)
    return Envelope(data=_meeting_view(meeting, []))


@router.get(
    "/meetings/live",
    response_model=Envelope[MeetingView | None],
    summary="La réunion en cours, s'il y en a une",
)
async def live_meeting(
    session: SessionDep, principal: PrincipalDep, settings: SettingsDep
) -> Envelope[MeetingView | None]:
    """Asked at every start.

    A meeting survives the application being killed — the transcript is on the
    server, not in the client's memory — so the honest thing on relaunch is to
    offer to resume rather than to silently start over.
    """
    service = _service(session, principal, settings)
    meeting = await service.live()
    if meeting is None:
        return Envelope(data=None)
    return Envelope(data=_meeting_view(meeting, service.suggestions(meeting)))


@router.get("/meetings", response_model=Collection[MeetingView], summary="Réunions récentes")
async def list_meetings(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Collection[MeetingView]:
    service = _service(session, principal, settings)
    rows = await service.list_recent(limit=limit)
    return Collection(data=[_meeting_view(row, service.suggestions(row)) for row in rows])


@router.get(
    "/meetings/{meeting_id}",
    response_model=Envelope[MeetingView],
    summary="Une réunion",
)
async def get_meeting(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
) -> Envelope[MeetingView]:
    service = _service(session, principal, settings)
    meeting = await service.get(meeting_id)
    return Envelope(data=_meeting_view(meeting, service.suggestions(meeting)))


@router.post(
    "/meetings/{meeting_id}/audio",
    response_model=Envelope[MeetingBlockView],
    summary="Envoyer un bloc audio",
)
async def append_audio(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
    block: Annotated[UploadFile, File()],
) -> Envelope[MeetingBlockView]:
    """One block of the live recording.

    A block whose transcription fails still returns `200` with no new
    suggestions: the meeting is not over, and turning a provider hiccup into an
    error would make the client stop sending.
    """
    audio = await block.read()
    if len(audio) > MAX_BLOCK_BYTES:
        raise ValidationError(
            "Bloc audio trop volumineux ; envoyez des blocs plus courts.",
            field="block",
        )

    service = _service(session, principal, settings)
    meeting, added = await service.append_audio(
        meeting_id,
        audio,
        media_type=block.content_type or "audio/webm",
    )
    return Envelope(
        data=MeetingBlockView(
            meeting_id=meeting.id,
            word_count=len((meeting.live_transcript or "").split()),
            new_suggestions=[_suggestion_view(item) for item in added],
        )
    )


@router.post(
    "/meetings/{meeting_id}/text",
    response_model=Envelope[MeetingBlockView],
    summary="Envoyer du texte déjà transcrit",
)
async def append_text(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
    payload: Annotated[AppendTextRequest, Body()],
) -> Envelope[MeetingBlockView]:
    service = _service(session, principal, settings)
    meeting, added = await service.append_text(meeting_id, payload.text)
    return Envelope(
        data=MeetingBlockView(
            meeting_id=meeting.id,
            word_count=len((meeting.live_transcript or "").split()),
            new_suggestions=[_suggestion_view(item) for item in added],
        )
    )


@router.get(
    "/meetings/{meeting_id}/stream",
    summary="Suivre une réunion en direct",
    response_class=StreamingResponse,
)
async def stream_meeting(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
) -> StreamingResponse:
    """Server-sent events for a second screen.

    Polling the row rather than subscribing to a bus, and that is a deliberate
    limit rather than an oversight: a fan-out bus would let this scale to many
    watchers per meeting, and there is no evidence anybody wants that. Two
    seconds against a primary key is cheap; a message broker to save it would be
    a component to run for ever (`Architecture.md` §17.10).

    Events: `suggestion` for each new item, `transcript` when the word count
    moves, `end` when the meeting closes.
    """
    service = _service(session, principal, settings)
    # Fails now rather than inside the generator: an error raised after the
    # response has started is a stream that ends with no explanation.
    await service.get(meeting_id)

    async def events() -> AsyncIterator[str]:
        seen: set[str] = set()
        words = -1
        elapsed = 0.0

        while elapsed < STREAM_MAX_SECONDS:
            meeting = await service.get(meeting_id)
            # Expire so the next read sees another transaction's writes; without
            # it the identity map serves the row this session first loaded and
            # the stream never moves.
            session.expire(meeting)
            meeting = await service.get(meeting_id)

            for item in service.suggestions(meeting):
                if item.key in seen:
                    continue
                seen.add(item.key)
                body = _suggestion_view(item).model_dump(mode="json")
                yield f"event: suggestion\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"

            current = len((meeting.live_transcript or "").split())
            if current != words:
                words = current
                yield (
                    "event: transcript\n"
                    f"data: {json.dumps({'word_count': words}, ensure_ascii=False)}\n\n"
                )

            if meeting.status != "live":
                yield (
                    "event: end\n"
                    f"data: {json.dumps({'status': meeting.status}, ensure_ascii=False)}\n\n"
                )
                return

            await asyncio.sleep(STREAM_POLL_SECONDS)
            elapsed += STREAM_POLL_SECONDS

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this an intermediate proxy buffers the whole response and
            # delivers it at once, which turns a live feed into a transcript.
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/meetings/{meeting_id}/close",
    response_model=Envelope[MeetingClosedView],
    summary="Terminer et produire le compte rendu",
)
async def close_meeting(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
) -> Envelope[MeetingClosedView]:
    service = _service(session, principal, settings)
    meeting, report = await service.close(meeting_id)
    return Envelope(
        data=MeetingClosedView(
            meeting=_meeting_view(meeting, service.suggestions(meeting)),
            report=_report_view(report),
        )
    )


@router.delete(
    "/meetings/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Abandonner une réunion",
)
async def abandon_meeting(
    session: SessionDep,
    principal: PrincipalDep,
    settings: SettingsDep,
    meeting_id: Annotated[uuid.UUID, Path()],
) -> None:
    """Discard without producing anything.

    Distinct from closing, and the distinction is the user's: a meeting that was
    a false start should leave nothing behind, and forcing it through a summary
    would put a report of nothing in their notes.
    """
    service = _service(session, principal, settings)
    await service.abandon(meeting_id)
