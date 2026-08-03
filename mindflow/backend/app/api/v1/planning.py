"""Agenda, calendar and advanced task endpoints (API.md §5.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope, Problem
from app.api.schemas.entries import EntryView
from app.api.schemas.planning import (
    AgendaDayView,
    AgendaItemView,
    AgendaResponse,
    BulkResult,
    BulkUpdateRequest,
    CalendarCellView,
    CalendarResponse,
    CompletionView,
    CreateSubtaskRequest,
    PinRequest,
    RecurrenceRequest,
    ReorderRequest,
    RescheduleRequest,
    SnoozeRequest,
    SubtaskView,
    TaskProgress,
    UpdateSubtaskRequest,
)
from app.api.v1.entries import entry_view
from app.domain.enums import AgendaView
from app.infra.db.models.core import Entry, Subtask, Task
from app.services.agenda_service import AgendaItem, AgendaService
from app.services.reminder_service import ReminderService
from app.services.task_service import TaskService

router = APIRouter(responses=ERROR_RESPONSES)


def _subtask_view(subtask: Subtask) -> SubtaskView:
    return SubtaskView(
        id=subtask.id,
        entry_id=subtask.entry_id,
        title=subtask.title,
        position=subtask.position,
        completed_at=subtask.completed_at,
        origin=subtask.origin,
    )


async def _hydrate_entry(session: SessionDep, entry: Entry) -> EntryView:
    """Build the view of an entry a mutation just changed.

    The explicit `refresh` is required, not defensive. A `flush()` expires the
    attributes SQLAlchemy expects the database to have recomputed — `updated_at`
    among them — and reading an expired attribute triggers a lazy load. Under
    asyncio that lazy load has no greenlet to run in and raises `MissingGreenlet`
    at response-building time, which surfaces as a 500 on an operation that
    actually succeeded.
    """
    await session.refresh(entry)
    task = await session.get(Task, entry.id)
    return entry_view(entry, task)


def _item_view(item: AgendaItem, progress: tuple[int, int] | None) -> AgendaItemView:
    return AgendaItemView(
        entry=entry_view(item.entry, item.task),
        day=item.day,
        subtasks=(TaskProgress(done=progress[0], total=progress[1]) if progress else None),
    )


# --------------------------------------------------------------------------- #
# Agenda
# --------------------------------------------------------------------------- #
@router.get(
    "/agenda",
    summary="Agenda : les échéances d'une journée, d'une semaine ou d'un mois",
    response_model=Envelope[AgendaResponse],
)
async def get_agenda(
    principal: PrincipalDep,
    session: SessionDep,
    view: Annotated[AgendaView, Query()] = AgendaView.WEEK,
    anchor: Annotated[date | None, Query(description="Jour de référence")] = None,
    include_done: Annotated[bool, Query()] = True,
    include_unscheduled: Annotated[bool, Query()] = False,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Envelope[AgendaResponse]:
    """Return the agenda for a window.

    All boundaries are computed in the **user's** timezone and converted to UTC
    once, at the query edge. Doing the arithmetic in UTC produces an agenda that
    is subtly wrong twice a year, with an hour of tasks landing on the wrong day
    — which users report as "the app lost my task".

    Overdue items are returned in their own bucket rather than pinned to the day
    they were due: at the bottom of a scrolled-away day, nobody ever sees them.
    """
    service = AgendaService(session, principal=principal)
    tasks = TaskService(session, principal=principal)

    reference = anchor or service.local_day(datetime.now(UTC))
    start, end = service.range_for(view, reference)

    agenda = await service.agenda(
        start=start,
        end=end,
        include_done=include_done,
        include_unscheduled=include_unscheduled,
        project_id=project_id,
    )

    every_id = [item.entry.id for day in agenda.days for item in day.items]
    every_id += [item.entry.id for item in agenda.overdue]
    every_id += [item.entry.id for item in agenda.unscheduled]
    progress = await tasks.subtask_progress(every_id)

    return Envelope(
        data=AgendaResponse(
            view=view,
            start=agenda.start,
            end=agenda.end,
            timezone=agenda.timezone,
            days=[
                AgendaDayView(
                    day=day.day,
                    items=[_item_view(item, progress.get(item.entry.id)) for item in day.items],
                )
                for day in agenda.days
            ],
            overdue=[_item_view(item, progress.get(item.entry.id)) for item in agenda.overdue],
            unscheduled=[
                _item_view(item, progress.get(item.entry.id)) for item in agenda.unscheduled
            ],
        )
    )


@router.get(
    "/calendar",
    summary="Calendrier : densité par jour, pour la grille mensuelle",
    response_model=Envelope[CalendarResponse],
)
async def get_calendar(
    principal: PrincipalDep,
    session: SessionDep,
    month: Annotated[date | None, Query(description="N'importe quel jour du mois")] = None,
) -> Envelope[CalendarResponse]:
    """Counts per day, aggregated in the database.

    A month grid needs six weeks of numbers and nothing else; shipping every row
    to count them in the client is how a calendar screen becomes slow on an
    account with a year of history.
    """
    service = AgendaService(session, principal=principal)
    reference = month or service.local_day(datetime.now(UTC))
    start, end = service.range_for(AgendaView.MONTH, reference)
    cells = await service.calendar(start=start, end=end)

    return Envelope(
        data=CalendarResponse(
            start=start,
            end=end,
            timezone=principal.timezone,
            cells=[
                CalendarCellView(
                    day=cell.day,
                    total=cell.total,
                    done=cell.done,
                    pending=cell.pending,
                    overdue=cell.overdue,
                    captures=cell.captures,
                )
                for cell in cells
            ],
        )
    )


# --------------------------------------------------------------------------- #
# Subtasks
# --------------------------------------------------------------------------- #
@router.get(
    "/entries/{entry_id}/subtasks",
    summary="Lister les sous-tâches",
    response_model=Collection[SubtaskView],
)
async def list_subtasks(
    entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Collection[SubtaskView]:
    subtasks = await TaskService(session, principal=principal).list_subtasks(entry_id)
    return Collection(data=[_subtask_view(item) for item in subtasks])


@router.post(
    "/entries/{entry_id}/subtasks",
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter une sous-tâche",
    response_model=Envelope[SubtaskView],
    responses={422: {"model": Problem, "description": "Titre vide ou liste saturée"}},
)
async def add_subtask(
    entry_id: uuid.UUID,
    payload: Annotated[CreateSubtaskRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[SubtaskView]:
    """One flat level only. Two levels of nesting is a project, and projects
    already exist."""
    subtask = await TaskService(session, principal=principal).add_subtask(
        entry_id, title=payload.title
    )
    return Envelope(data=_subtask_view(subtask))


@router.patch(
    "/subtasks/{subtask_id}",
    summary="Modifier ou cocher une sous-tâche",
    response_model=Envelope[SubtaskView],
)
async def update_subtask(
    subtask_id: uuid.UUID,
    payload: Annotated[UpdateSubtaskRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[SubtaskView]:
    subtask = await TaskService(session, principal=principal).update_subtask(
        subtask_id, title=payload.title, completed=payload.completed
    )
    return Envelope(data=_subtask_view(subtask))


@router.delete(
    "/subtasks/{subtask_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer une sous-tâche",
)
async def delete_subtask(
    subtask_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> None:
    await TaskService(session, principal=principal).delete_subtask(subtask_id)


@router.post(
    "/entries/{entry_id}/subtasks/reorder",
    summary="Réordonner les sous-tâches",
    response_model=Collection[SubtaskView],
)
async def reorder_subtasks(
    entry_id: uuid.UUID,
    payload: Annotated[ReorderRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Collection[SubtaskView]:
    """Takes the full ordered list, which makes the call idempotent — the point
    of the design, since drag-and-drop on a flaky link emits deltas out of
    order."""
    subtasks = await TaskService(session, principal=principal).reorder_subtasks(
        entry_id, payload.ordered_ids
    )
    return Collection(data=[_subtask_view(item) for item in subtasks])


# --------------------------------------------------------------------------- #
# Task lifecycle
# --------------------------------------------------------------------------- #
@router.post(
    "/entries/{entry_id}/complete-task",
    summary="Terminer une tâche, en générant l'occurrence suivante si elle est récurrente",
    response_model=Envelope[CompletionView],
)
async def complete_task(
    entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[CompletionView]:
    """Complete a task.

    A recurring task produces its next occurrence here, computed from the
    *previous due date* rather than from now: a Monday task completed on
    Wednesday is still due next Monday (`domain.recurrence`).
    """
    service = TaskService(session, principal=principal)
    result = await service.complete(entry_id)
    reminders = ReminderService(session, principal=principal)
    # A phone buzzing about something already done is the fastest way to get
    # notifications switched off for good.
    await reminders.cancel_for_entry(entry_id)

    next_view: EntryView | None = None
    if result.next_occurrence is not None:
        next_task = await session.get(Task, result.next_occurrence.id)
        next_view = entry_view(result.next_occurrence, next_task)
        if next_task is not None:
            await reminders.sync_automatic(result.next_occurrence, next_task)

    return Envelope(
        data=CompletionView(
            entry=await _hydrate_entry(session, result.entry),
            next_occurrence=next_view,
        )
    )


@router.post(
    "/entries/{entry_id}/reopen", summary="Rouvrir une tâche", response_model=Envelope[EntryView]
)
async def reopen_task(
    entry_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[EntryView]:
    entry = await TaskService(session, principal=principal).reopen(entry_id)
    return Envelope(data=await _hydrate_entry(session, entry))


@router.post(
    "/entries/{entry_id}/snooze",
    summary="Reporter l'affichage d'une tâche",
    response_model=Envelope[EntryView],
)
async def snooze_task(
    entry_id: uuid.UUID,
    payload: Annotated[SnoozeRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    """Snoozing hides a task; it does **not** move its deadline.

    "I do not want to see this until Thursday" and "this is due Thursday" are
    different statements, and a tool that conflates them quietly rewrites the
    user's commitments.
    """
    entry = await TaskService(session, principal=principal).snooze(entry_id, until=payload.until)
    return Envelope(data=await _hydrate_entry(session, entry))


@router.post(
    "/entries/{entry_id}/reschedule",
    summary="Déplacer une échéance",
    response_model=Envelope[EntryView],
)
async def reschedule_task(
    entry_id: uuid.UUID,
    payload: Annotated[RescheduleRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    service = TaskService(session, principal=principal)
    entry = await service.reschedule(entry_id, due_at=payload.due_at)
    task = await session.get(Task, entry.id)
    if task is not None:
        # Automatic reminders follow the deadline; manual ones do not (the user
        # asked for Tuesday, and Tuesday is not the system's to revise).
        await ReminderService(session, principal=principal).sync_automatic(entry, task)
    return Envelope(data=await _hydrate_entry(session, entry))


@router.post(
    "/entries/{entry_id}/recurrence",
    summary="Définir ou retirer une récurrence",
    response_model=Envelope[EntryView],
    responses={422: {"model": Problem, "description": "Règle non prise en charge"}},
)
async def set_recurrence(
    entry_id: uuid.UUID,
    payload: Annotated[RecurrenceRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    """A subset of RFC 5545: `FREQ`, `INTERVAL`, `BYDAY`, `COUNT`, `UNTIL`.

    A rule outside that subset is **rejected**, not approximated — a task
    appearing on a day nobody asked for is worse than a rule that does not
    apply.
    """
    entry = await TaskService(session, principal=principal).set_recurrence(
        entry_id, rule=payload.rule
    )
    return Envelope(data=await _hydrate_entry(session, entry))


@router.post(
    "/entries/{entry_id}/pin", summary="Épingler une entrée", response_model=Envelope[EntryView]
)
async def pin_entry(
    entry_id: uuid.UUID,
    payload: Annotated[PinRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[EntryView]:
    entry = await TaskService(session, principal=principal).pin(entry_id, pinned=payload.pinned)
    return Envelope(data=await _hydrate_entry(session, entry))


@router.post(
    "/entries/bulk",
    summary="Modifier plusieurs entrées en une fois",
    response_model=Envelope[BulkResult],
)
async def bulk_update(
    payload: Annotated[BulkUpdateRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[BulkResult]:
    """Apply one change to many entries.

    Rows are loaded rather than updated set-wise: RLS scopes the read, the
    timeline needs each title, and completing a recurring task in bulk must
    still roll it forward. A bare `UPDATE … WHERE id IN` would skip all three.
    """
    matched = await TaskService(session, principal=principal).bulk_update(
        payload.ids,
        status=payload.status,
        priority=payload.priority,
        project_id=payload.project_id,
        clear_project=payload.clear_project,
    )
    return Envelope(data=BulkResult(matched=matched, requested=len(payload.ids)))
