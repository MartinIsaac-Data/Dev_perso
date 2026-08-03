"""Entry endpoints (API.md §5.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Header, Query, Response, status
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope, Problem
from app.api.schemas.entries import (
    CreateEntryRequest,
    EntryView,
    SourceView,
    TaskView,
    TransformEntryRequest,
    UpdateEntryRequest,
)
from app.domain.enums import EntryStatus, EntryType
from app.infra.db.models.core import Entry, EntryTag, Tag, Task
from app.services.entry_service import EntryService

router = APIRouter(prefix="/entries", responses=ERROR_RESPONSES)


def entry_view(entry: Entry, task: Task | None = None, tags: list[str] | None = None) -> EntryView:
    return EntryView(
        id=entry.id,
        entry_type=EntryType(entry.entry_type),
        title=entry.title,
        body=entry.body,
        status=EntryStatus(entry.status),
        occurred_at=entry.occurred_at,
        project_id=entry.project_id,
        origin=entry.origin,
        confidence=float(entry.confidence) if entry.confidence is not None else None,
        version=entry.version,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        edited_by_user_at=entry.edited_by_user_at,
        source=SourceView(
            capture_id=entry.capture_id,
            span_start=entry.source_span_start,
            span_end=entry.source_span_end,
        ),
        task=(
            TaskView(
                due_at=task.due_at,
                due_precision=task.due_precision,
                due_raw_expression=task.due_raw_expression,
                priority=task.priority,
                completed_at=task.completed_at,
                snoozed_until=task.snoozed_until,
                assignee_label=task.assignee_label,
                recurrence_rule=task.recurrence_rule,
            )
            if task
            else None
        ),
        tags=tags or [],
    )


async def _hydrate(session, entry: Entry) -> EntryView:  # type: ignore[no-untyped-def]
    task = await session.get(Task, entry.id)
    tags = (
        (
            await session.execute(
                select(Tag.label)
                .join(EntryTag, EntryTag.tag_id == Tag.id)
                .where(EntryTag.entry_id == entry.id)
            )
        )
        .scalars()
        .all()
    )
    return entry_view(entry, task, list(tags))


@router.get(
    "",
    summary="Lister les entrées (notes, tâches, idées, décisions)",
    response_model=Collection[EntryView],
)
async def list_entries(
    principal: PrincipalDep,
    session: SessionDep,
    entry_type: Annotated[
        str | None, Query(description="Types séparés par des virgules : task,idea")
    ] = None,
    entry_status: Annotated[
        str | None, Query(alias="status", description="Statuts séparés par des virgules")
    ] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(description="Recherche plein texte simple")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[datetime | None, Query(description="Curseur : occurred_at")] = None,
) -> Collection[EntryView]:
    entries = await EntryService(session, principal=principal).list_entries(
        entry_types=[EntryType(t) for t in entry_type.split(",")] if entry_type else None,
        statuses=[EntryStatus(s) for s in entry_status.split(",")] if entry_status else None,
        project_id=project_id,
        search=q,
        limit=limit,
        before=before,
    )
    return Collection(data=[await _hydrate(session, entry) for entry in entries])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Créer une entrée manuellement",
    response_model=Envelope[EntryView],
)
async def create_entry(
    payload: Annotated[CreateEntryRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    """`due_expression` takes the wording, not a date ("jeudi", "fin de mois"):
    the same deterministic resolver as the pipeline handles it (ADR-020)."""
    entry = await EntryService(session, principal=principal).create(
        entry_type=payload.entry_type,
        title=payload.title,
        body=payload.body,
        project_id=payload.project_id,
        occurred_at=payload.occurred_at,
        due_expression=payload.due_expression,
        priority=payload.priority,
    )
    return Envelope(data=await _hydrate(session, entry))


@router.get("/{entry_id}", summary="Détail d'une entrée", response_model=Envelope[EntryView])
async def get_entry(
    entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep, response: Response
) -> Envelope[EntryView]:
    entry = await EntryService(session, principal=principal).get(entry_id)
    response.headers["ETag"] = f'"{entry.version}"'
    return Envelope(data=await _hydrate(session, entry))


@router.patch(
    "/{entry_id}",
    summary="Modifier une entrée (verrouillage optimiste)",
    response_model=Envelope[EntryView],
    responses={
        409: {
            "model": Problem,
            "description": (
                "Version obsolète — le corps porte l'état serveur pour permettre une fusion"
            ),
        }
    },
)
async def update_entry(
    entry_id: uuid.UUID,
    payload: Annotated[UpdateEntryRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
    response: Response,
    if_match: Annotated[
        str | None, Header(alias="If-Match", description='Version attendue, ex. "3"')
    ] = None,
) -> Envelope[EntryView]:
    """Modify an entry.

    Correcting an AI-produced `entry_type`, `due_at`, `project_id`, `title` or
    `priority` records a `correction_event`, which feeds **offline** model
    evaluation only — never online training (AI.md §11).

    Any edit sets `edited_by_user_at`, which makes the entry immune to later
    reprocessing: a human correction is never overwritten by the model (ADR-027).
    """
    expected = int(if_match.strip('"')) if if_match and if_match.strip('"').isdigit() else None
    entry = await EntryService(session, principal=principal).update(
        entry_id, expected_version=expected, changes=payload.as_changes()
    )
    response.headers["ETag"] = f'"{entry.version}"'
    return Envelope(data=await _hydrate(session, entry))


@router.post(
    "/{entry_id}/transform",
    summary="Changer le type d'une entrée",
    response_model=Envelope[EntryView],
)
async def transform_entry(
    entry_id: uuid.UUID,
    payload: Annotated[TransformEntryRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    entry = await EntryService(session, principal=principal).transform(
        entry_id, payload.target_type
    )
    return Envelope(data=await _hydrate(session, entry))


@router.post(
    "/{entry_id}/complete", summary="Terminer une tâche", response_model=Envelope[EntryView]
)
async def complete_entry(
    entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[EntryView]:
    entry = await EntryService(session, principal=principal).complete(entry_id)
    return Envelope(data=await _hydrate(session, entry))


@router.delete(
    "/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer une entrée"
)
async def delete_entry(entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> None:
    await EntryService(session, principal=principal).delete(entry_id)
