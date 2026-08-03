"""Reminders, the notification centre, and device registration (API.md §5.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope, Problem
from app.api.schemas.planning import (
    CreateReminderRequest,
    DeviceView,
    NotificationSummary,
    NotificationView,
    RegisterDeviceRequest,
    ReminderView,
)
from app.domain.errors import ValidationError
from app.infra.db.models.core import Device, Notification, Reminder, Task
from app.services.notification_service import NotificationService
from app.services.reminder_service import ReminderService, resolve_offset

router = APIRouter(responses=ERROR_RESPONSES)


def _reminder_view(reminder: Reminder) -> ReminderView:
    return ReminderView(
        id=reminder.id,
        entry_id=reminder.entry_id,
        remind_at=reminder.remind_at,
        channel=reminder.channel,
        status=reminder.status,
        offset_rule=reminder.offset_rule,
        title=reminder.title,
        body=reminder.body,
        sent_at=reminder.sent_at,
    )


def _notification_view(notification: Notification) -> NotificationView:
    return NotificationView(
        id=notification.id,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        entry_id=notification.entry_id,
        capture_id=notification.capture_id,
        payload=notification.payload,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _device_view(device: Device) -> DeviceView:
    return DeviceView(
        id=device.id,
        install_id=device.install_id,
        platform=device.platform,
        push_provider=device.push_provider,
        name=device.name,
        app_version=device.app_version,
        last_seen_at=device.last_seen_at,
        # The token itself is never echoed: it is a delivery credential, and an
        # endpoint that returns it turns a read-only leak into a spoofing
        # capability.
        push_enabled=bool(device.push_token) and device.push_failed_at is None,
    )


# --------------------------------------------------------------------------- #
# Reminders
# --------------------------------------------------------------------------- #
@router.get(
    "/reminders",
    summary="Rappels programmés à venir",
    response_model=Collection[ReminderView],
)
async def list_reminders(
    principal: PrincipalDep,
    session: SessionDep,
    entry_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Collection[ReminderView]:
    """Also the source of truth the desktop client syncs from.

    An unpackaged Windows build has no WNS channel and schedules its own toasts
    from this list (ADR-040), which is why a locally scheduled reminder is still
    stored server-side: two views of "what is scheduled" that cannot be compared
    will drift.
    """
    service = ReminderService(session, principal=principal)
    reminders = (
        await service.list_for_entry(entry_id)
        if entry_id is not None
        else await service.list_upcoming(limit=limit)
    )
    return Collection(data=[_reminder_view(item) for item in reminders])


@router.post(
    "/reminders",
    status_code=status.HTTP_201_CREATED,
    summary="Programmer un rappel",
    response_model=Envelope[ReminderView],
    responses={422: {"model": Problem, "description": "Instant invalide ou déjà passé"}},
)
async def create_reminder(
    payload: Annotated[CreateReminderRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[ReminderView]:
    """Either an absolute instant or an offset from the task's due date.

    A manual reminder is never rewritten by a later due-date change: the user
    asked for that moment, and the scheduler does not get to revise it.
    """
    remind_at: datetime | None = payload.remind_at

    if remind_at is None:
        if payload.offset_rule is None or payload.entry_id is None:
            raise ValidationError(
                "Fournissez soit `remind_at`, soit `offset_rule` avec un `entry_id`.",
                field="remind_at",
            )
        task = await session.get(Task, payload.entry_id)
        if task is None or task.due_at is None:
            raise ValidationError(
                "Cette tâche n'a pas d'échéance : un décalage ne peut pas être calculé.",
                field="offset_rule",
            )
        remind_at = resolve_offset(payload.offset_rule, due_at=task.due_at)
        if remind_at is None:
            raise ValidationError("Décalage non reconnu.", field="offset_rule")

    reminder = await ReminderService(session, principal=principal).schedule(
        entry_id=payload.entry_id,
        remind_at=remind_at,
        channel=payload.channel,
        # Manual: no offset rule recorded, which is exactly what protects it
        # from being rewritten when the deadline moves.
        offset_rule=None,
        title=payload.title,
        body=payload.body,
    )
    if reminder is None:
        raise ValidationError("Cet instant est déjà passé.", field="remind_at")
    return Envelope(data=_reminder_view(reminder))


@router.delete(
    "/reminders/{reminder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Annuler un rappel",
)
async def cancel_reminder(
    reminder_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> None:
    await ReminderService(session, principal=principal).cancel(reminder_id)


@router.post(
    "/reminders/{reminder_id}/dismiss",
    summary="Marquer un rappel comme traité",
    response_model=Envelope[ReminderView],
)
async def dismiss_reminder(
    reminder_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[ReminderView]:
    reminder = await ReminderService(session, principal=principal).dismiss(reminder_id)
    return Envelope(data=_reminder_view(reminder))


# --------------------------------------------------------------------------- #
# Notification centre
# --------------------------------------------------------------------------- #
@router.get(
    "/notifications",
    summary="Centre de notifications",
    response_model=Envelope[NotificationSummary],
)
async def list_notifications(
    principal: PrincipalDep,
    session: SessionDep,
    unread_only: Annotated[bool, Query()] = False,
    before: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[NotificationSummary]:
    """The durable record.

    A notification row is written **before** any push is attempted, so a user
    whose phone was unreachable still finds it here. Pushing first and recording
    on success loses exactly the notifications that mattered most.
    """
    service = NotificationService(session, principal=principal)
    items = await service.list_notifications(unread_only=unread_only, before=before, limit=limit)
    return Envelope(
        data=NotificationSummary(
            unread=await service.unread_count(),
            items=[_notification_view(item) for item in items],
        )
    )


@router.post(
    "/notifications/{notification_id}/read",
    summary="Marquer une notification comme lue",
    response_model=Envelope[NotificationView],
)
async def mark_read(
    notification_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[NotificationView]:
    notification = await NotificationService(session, principal=principal).mark_read(
        notification_id
    )
    return Envelope(data=_notification_view(notification))


@router.post(
    "/notifications/read-all",
    summary="Tout marquer comme lu",
    response_model=Envelope[NotificationSummary],
)
async def mark_all_read(
    principal: PrincipalDep, session: SessionDep
) -> Envelope[NotificationSummary]:
    service = NotificationService(session, principal=principal)
    await service.mark_all_read()
    return Envelope(data=NotificationSummary(unread=0, items=[]))


# --------------------------------------------------------------------------- #
# Devices
# --------------------------------------------------------------------------- #
@router.put(
    "/devices",
    summary="Enregistrer ou rafraîchir un appareil pour les notifications",
    response_model=Envelope[DeviceView],
)
async def register_device(
    payload: Annotated[RegisterDeviceRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[DeviceView]:
    """Idempotent on `install_id`.

    Keyed on the installation rather than on the push token because tokens
    rotate — sometimes weekly. Keying on the token creates a new row per
    rotation and ends up sending one reminder five times to the same phone.
    """
    device = await NotificationService(session, principal=principal).register_device(
        install_id=payload.install_id,
        platform=payload.platform.value,
        push_token=payload.push_token,
        push_provider=payload.push_provider,
        name=payload.name,
        app_version=payload.app_version,
        os_version=payload.os_version,
    )
    return Envelope(data=_device_view(device))


@router.get("/devices", summary="Appareils enregistrés", response_model=Collection[DeviceView])
async def list_devices(principal: PrincipalDep, session: SessionDep) -> Collection[DeviceView]:
    devices = await NotificationService(session, principal=principal).list_devices()
    return Collection(data=[_device_view(device) for device in devices])


@router.delete(
    "/devices/{install_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Révoquer un appareil",
)
async def revoke_device(install_id: str, principal: PrincipalDep, session: SessionDep) -> None:
    await NotificationService(session, principal=principal).revoke_device(install_id)
