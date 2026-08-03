"""Capture endpoints (API.md §5.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Query, Response, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, QueueDep, SessionDep, SettingsDep, StorageDep
from app.api.schemas.captures import (
    AudioView,
    CaptureView,
    DeclareCaptureRequest,
    DeclaredCaptureView,
    EntrySummary,
    TranscriptView,
    UploadInstructions,
)
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope, Problem
from app.domain.enums import CaptureStatus
from app.infra.db.models.core import Capture, Entry
from app.infra.db.session import tenant_session
from app.observability.logging import get_logger
from app.services.capture_service import CaptureService

log = get_logger("api.captures")

router = APIRouter(prefix="/captures", responses=ERROR_RESPONSES)


def _service(session, principal, storage, settings) -> CaptureService:  # type: ignore[no-untyped-def]
    return CaptureService(session, principal=principal, storage=storage, settings=settings)


def _view(capture: Capture) -> CaptureView:
    return CaptureView(
        id=capture.id,
        status=CaptureStatus(capture.status),
        kind=capture.kind,
        duration_ms=capture.duration_ms,
        captured_at=capture.captured_at,
        source=capture.source,
        language_hint=capture.language_hint,
        processing_mode=capture.processing_mode,
        failure_code=capture.failure_code,
        created_at=capture.created_at,
        processing_started_at=capture.processing_started_at,
        processing_finished_at=capture.processing_finished_at,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Déclarer une capture et obtenir une URL d'envoi signée",
    response_model=Envelope[DeclaredCaptureView],
    responses={
        200: {"description": "Capture déjà déclarée — rejeu idempotent"},
        402: {
            "model": Problem,
            "description": "Quota atteint : la capture est acceptée en mode dégradé",
        },
        422: {"model": Problem, "description": "Durée ou format invalide"},
    },
)
async def declare_capture(
    payload: Annotated[DeclareCaptureRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    response: Response,
) -> Envelope[DeclaredCaptureView]:
    """Declare a capture.

    The audio itself never transits this API: the response carries a short-lived
    signed URL the client PUTs to directly (ADR-018).

    Replaying the same `client_capture_id` returns the existing capture with a
    `200` instead of a `201` — that is what makes offline retry safe (ADR-009).

    A capture is **never refused for quota reasons**. Over the limit it is
    accepted with `processing_mode: "degraded"`: stored and transcribed, with AI
    enrichment deferred (ADR-026).
    """
    result = await _service(session, principal, storage, settings).declare(
        client_capture_id=payload.client_capture_id,
        duration_ms=payload.duration_ms,
        audio_format=payload.audio_format.value,
        captured_at=payload.captured_at,
        capture_timezone=payload.capture_timezone,
        kind=payload.kind,
        source=payload.source,
        language_hint=payload.language_hint,
        audio_bytes=payload.audio_bytes,
        audio_sample_rate=payload.audio_sample_rate,
    )

    if not result.created:
        response.status_code = status.HTTP_200_OK

    view = DeclaredCaptureView(
        **_view(result.capture).model_dump(),
        upload=(
            UploadInstructions(
                url=result.upload.url,
                method=result.upload.method,
                headers=result.upload.headers,
                expires_at=result.upload.expires_at,
                object_key=result.upload.object_key,
            )
            if result.upload
            else None
        ),
        quota_warning=(
            "Quota mensuel atteint : la capture est conservée et transcrite, "
            "l'analyse sera effectuée ultérieurement."
            if result.degraded
            else None
        ),
    )
    return Envelope(data=view)


@router.post(
    "/{capture_id}/complete",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Signaler la fin de l'envoi et déclencher le pipeline",
    response_model=Envelope[CaptureView],
)
async def complete_capture(
    capture_id: uuid.UUID,
    principal: PrincipalDep,
    storage: StorageDep,
    settings: SettingsDep,
    queue: QueueDep,
    background: BackgroundTasks,
) -> Envelope[CaptureView]:
    """Mark the upload as finished and start the pipeline.

    Calling this twice is idempotent, not an error: a client that lost the
    response must be able to retry.

    This endpoint deliberately manages **its own transaction** instead of using
    the request-scoped `SessionDep`. The reason is an ordering constraint that is
    easy to get wrong: the job must not be enqueued until the status change is
    committed, or a worker can pick the capture up, read a row still marked
    `pending_upload`, and block on the row lock the open request transaction
    still holds — a deadlock, not a race. Closing the transaction here makes the
    commit boundary explicit and puts the enqueue strictly after it.

    Two mechanisms, on purpose: the outbox row is written inside the same
    transaction as the status change and is the durability guarantee (ADR-010);
    the enqueue is only the fast path. If it is lost, the stuck-capture sweeper
    picks the capture up from the database.
    """
    async with tenant_session(principal.account_id, auth_subject=principal.auth_subject) as session:
        capture = await _service(session, principal, storage, settings).complete_upload(capture_id)
        view = _view(capture)
    # The transaction is committed at this point.

    from app.workers.pipeline.runner import PROCESS_CAPTURE

    background.add_task(queue.enqueue, PROCESS_CAPTURE, str(capture_id), str(principal.account_id))
    return Envelope(data=view)


@router.get(
    "",
    summary="Lister les captures",
    response_model=Collection[CaptureView],
)
async def list_captures(
    principal: PrincipalDep,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[datetime | None, Query()] = None,
) -> Collection[CaptureView]:
    captures = await _service(session, principal, storage, settings).list(
        limit=limit, before=before
    )
    return Collection(data=[_view(c) for c in captures])


@router.get(
    "/{capture_id}",
    summary="Détail d'une capture, avec transcription, audio et entrées dérivées",
    response_model=Envelope[CaptureView],
)
async def get_capture(
    capture_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Envelope[CaptureView]:
    service = _service(session, principal, storage, settings)
    capture = await service.get(capture_id)
    view = _view(capture)

    transcript = await service.transcript(capture_id)
    if transcript is not None:
        view.transcript = TranscriptView(
            id=transcript.id,
            language=transcript.language,
            confidence=float(transcript.confidence) if transcript.confidence else None,
            text=transcript.text,
            word_count=transcript.word_count,
            engine=transcript.engine,
            is_fallback=transcript.is_fallback,
        )

    audio_url = await service.audio_url(capture_id)
    view.audio = AudioView(available=audio_url is not None, url=audio_url)

    entries = await session.execute(
        select(Entry).where(Entry.capture_id == capture_id, Entry.deleted_at.is_(None))
    )
    view.entries = [
        EntrySummary(id=e.id, entry_type=e.entry_type, title=e.title, status=e.status)
        for e in entries.scalars().all()
    ]
    return Envelope(data=view)


@router.delete(
    "/{capture_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une capture",
)
async def delete_capture(
    capture_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    cascade: Annotated[bool, Query(description="Supprimer aussi les entrées dérivées")] = False,
    audio_only: Annotated[bool, Query(description="Ne supprimer que l'audio")] = False,
) -> None:
    """Delete a capture.

    By default the derived entries **survive** (ADR-028): someone deleting a
    recording wants the audio gone, not the tasks they drew from it. Pass
    `cascade=true` to delete both.
    """
    await _service(session, principal, storage, settings).delete(
        capture_id, cascade=cascade, audio_only=audio_only
    )
