"""The notification centre, and the fan-out to devices.

Ordering here is the whole design:

    write the notification row → then try to push

Not the other way round. The row is the durable record the user can find in the
app tomorrow; the push is a best-effort courtesy that depends on a third party,
a network and a device that may be off. Pushing first and recording on success
loses every notification for anyone whose phone happened to be unreachable —
which is precisely the population a reminder is for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.enums import NotificationKind, PushProvider
from app.domain.errors import NotFoundError
from app.domain.ports import PushMessage
from app.infra.db.models.core import Device, Notification
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.identity_service import Principal

log = get_logger("notification")

MAX_PAGE = 100
# Beyond this a device is almost certainly gone for good; keeping it in the
# fan-out wastes a request per reminder, forever.
MAX_PUSH_FAILURES = 5


class NotificationService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def list_notifications(
        self,
        *,
        unread_only: bool = False,
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        query: Select[tuple[Notification]] = (
            select(Notification)
            .where(Notification.user_id == self._principal.user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(min(limit, MAX_PAGE))
        )
        if unread_only:
            query = query.where(Notification.read_at.is_(None))
        if before is not None:
            query = query.where(Notification.created_at < before)
        return list((await self._session.execute(query)).scalars().all())

    async def unread_count(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == self._principal.user_id,
                Notification.read_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def create(
        self,
        *,
        kind: NotificationKind,
        title: str,
        body: str | None = None,
        entry_id: uuid.UUID | None = None,
        capture_id: uuid.UUID | None = None,
        reminder_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            entry_id=entry_id,
            capture_id=capture_id,
            reminder_id=reminder_id,
            kind=kind,
            title=title[:200],
            body=(body or "")[:500] or None,
            payload=payload or {},
        )
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def mark_read(self, notification_id: uuid.UUID) -> Notification:
        notification = await self._session.get(Notification, notification_id)
        if notification is None:
            raise NotFoundError(f"Notification {notification_id} introuvable.")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await self._session.flush()
        return notification

    async def mark_all_read(self) -> int:
        unread = await self.list_notifications(unread_only=True, limit=MAX_PAGE)
        now = datetime.now(UTC)
        for notification in unread:
            notification.read_at = now
        if unread:
            await self._session.flush()
        return len(unread)

    # -- devices ------------------------------------------------------------
    async def register_device(
        self,
        *,
        install_id: str,
        platform: str,
        push_token: str | None,
        push_provider: PushProvider,
        name: str | None = None,
        app_version: str | None = None,
        os_version: str | None = None,
    ) -> Device:
        """Register or refresh a device.

        Keyed on `install_id`, not on the push token: tokens rotate, sometimes
        weekly. Keying on the token would create a new row per rotation and send
        the same reminder five times to one phone.
        """
        existing = (
            await self._session.execute(
                select(Device).where(
                    Device.user_id == self._principal.user_id,
                    Device.install_id == install_id,
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if existing is not None:
            if existing.push_token != push_token:
                existing.push_token_updated_at = now
                # A fresh token clears the failure history: whatever was wrong
                # with the previous one is not this one's fault.
                existing.push_failed_at = None
                existing.push_failure_count = 0
            existing.push_token = push_token
            existing.push_provider = push_provider
            existing.platform = platform
            existing.name = name or existing.name
            existing.app_version = app_version or existing.app_version
            existing.os_version = os_version or existing.os_version
            existing.last_seen_at = now
            existing.revoked_at = None
            await self._session.flush()
            return existing

        device = Device(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            install_id=install_id,
            platform=platform,
            push_token=push_token,
            push_provider=push_provider,
            push_token_updated_at=now if push_token else None,
            name=name,
            app_version=app_version,
            os_version=os_version,
            last_seen_at=now,
        )
        self._session.add(device)
        await self._session.flush()
        log.info("device.registered", platform=platform, provider=push_provider.value)
        return device

    async def revoke_device(self, install_id: str) -> None:
        device = (
            await self._session.execute(
                select(Device).where(
                    Device.user_id == self._principal.user_id,
                    Device.install_id == install_id,
                )
            )
        ).scalar_one_or_none()
        if device is None:
            raise NotFoundError("Appareil introuvable.")
        device.revoked_at = datetime.now(UTC)
        device.push_token = None
        await self._session.flush()

    async def list_devices(self) -> list[Device]:
        result = await self._session.execute(
            select(Device)
            .where(Device.user_id == self._principal.user_id, Device.revoked_at.is_(None))
            .order_by(Device.last_seen_at.desc().nullslast())
        )
        return list(result.scalars().all())


async def push_to_user(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    message: PushMessage,
) -> int:
    """Fan a message out to every live device of one user.

    Grouped by provider so each adapter gets one batch, and dead tokens are
    retired as the providers report them — a token nobody retires is a request
    the dispatcher repeats every minute until the end of time.
    """
    from app.infra.push.factory import build_push_sender

    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.user_id == user_id,
                    Device.revoked_at.is_(None),
                    Device.push_token.isnot(None),
                    Device.push_failure_count < MAX_PUSH_FAILURES,
                )
            )
        )
        .scalars()
        .all()
    )
    if not devices:
        return 0

    by_provider: dict[str, list[Device]] = {}
    for device in devices:
        by_provider.setdefault(device.push_provider, []).append(device)

    delivered = 0
    for provider_value, group in by_provider.items():
        try:
            provider = PushProvider(provider_value)
        except ValueError:
            continue
        sender = build_push_sender(settings, provider)
        if sender is None:
            continue

        tokens = [device.push_token for device in group if device.push_token]
        result = await sender.send(tokens, message)
        delivered += result.delivered
        metrics.reminders_delivered_total.labels(
            provider.value, "ok" if result.ok else "error"
        ).inc(max(result.delivered, 1) if result.ok else 1)

        now = datetime.now(UTC)
        invalid = set(result.invalid_tokens)
        retryable = set(result.retryable_tokens)
        for device in group:
            if device.push_token in invalid:
                # Permanently dead: revoke rather than merely count. The app was
                # uninstalled or the channel is gone.
                device.revoked_at = now
                device.push_failed_at = now
                log.info("push.token_retired", device_id=str(device.id))
            elif device.push_token in retryable:
                device.push_failed_at = now
                device.push_failure_count += 1

    await session.flush()
    return delivered
