"""Fires reminders whose moment has come.

Runs every minute. The design constraints are the ones every scheduler has, and
each is handled explicitly rather than hoped away:

* **Nothing fires twice.** The row is claimed with `FOR UPDATE SKIP LOCKED` and
  its status flipped inside the same transaction, so two workers can run the
  same tick without either waiting on the other or double-sending.
* **Nothing is silently dropped.** A reminder the dispatcher was late for still
  fires, as long as it is inside the grace window; past that it is marked failed
  with a reason rather than left `scheduled` forever.
* **The notification row is written before the push is attempted.** The row is
  the durable record; the push is a courtesy that depends on a third party and a
  device that may be switched off (`services.notification_service`).
* **A failed push is not a failed reminder.** The user finds it in the app.
  Marking the reminder failed because Firebase had a bad minute would hide it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import Settings
from app.domain.enums import (
    ActivityAction,
    NotificationKind,
    ReminderChannel,
    ReminderStatus,
)
from app.domain.ports import PushMessage
from app.infra.db.models.core import ActivityEvent, Entry, Notification, Reminder
from app.infra.db.session import privileged_session, tenant_session
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("worker.reminders")

# A reminder the worker was late for still fires within this window — a phone
# that buzzes four minutes late is useful; one that never buzzes is not.
GRACE = timedelta(hours=6)
BATCH = 100


async def dispatch_due_reminders(settings: Settings, *, now: datetime | None = None) -> int:
    """Send every reminder that has come due. Returns the number delivered."""
    moment = now or datetime.now(UTC)
    claimed = await _claim(moment, limit=min(BATCH, settings.push_batch_size))
    if not claimed:
        return 0

    sent = 0
    for account_id, reminder_id in claimed:
        try:
            if await _fire(settings, account_id=account_id, reminder_id=reminder_id, now=moment):
                sent += 1
        except Exception:
            log.exception("reminder.dispatch_failed", reminder_id=str(reminder_id))
    log.info("reminder.batch", claimed=len(claimed), sent=sent)
    return sent


async def _claim(now: datetime, *, limit: int) -> list[tuple[str, str]]:
    """Atomically take ownership of the reminders that are due.

    `SKIP LOCKED` is what makes more than one worker safe: a row another worker
    is already handling is passed over instead of queued behind it. Without it,
    a second worker would block for the duration of the first one's HTTP calls.

    Runs privileged because it spans every tenant — the one job in the product
    that legitimately does. The per-reminder work below re-enters a tenant-scoped
    session, so RLS still governs everything that touches business rows.
    """
    async with privileged_session() as session:
        rows = (
            await session.execute(
                select(Reminder.id, Reminder.account_id, Reminder.remind_at)
                .where(
                    Reminder.status == ReminderStatus.SCHEDULED.value,
                    Reminder.remind_at <= now,
                )
                .order_by(Reminder.remind_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()

        claimed: list[tuple[str, str]] = []
        for reminder_id, account_id, remind_at in rows:
            reminder = await session.get(Reminder, reminder_id)
            if reminder is None:
                continue
            if now - remind_at > GRACE:
                # Too late to be useful. Recorded as failed with a reason rather
                # than left scheduled, which would make it fire at a random
                # moment weeks later.
                reminder.status = ReminderStatus.FAILED
                reminder.last_error = "missed_window"
                log.warning(
                    "reminder.missed", reminder_id=str(reminder_id), scheduled=remind_at.isoformat()
                )
                continue

            # Claimed here, inside the same transaction as the lock: whatever
            # happens next, this reminder will not be picked up again.
            reminder.status = ReminderStatus.SENT
            reminder.sent_at = now
            reminder.attempts += 1
            metrics.reminder_delivery_lag_seconds.observe((now - remind_at).total_seconds())
            claimed.append((str(account_id), str(reminder_id)))

        return claimed


async def _fire(settings: Settings, *, account_id: str, reminder_id: str, now: datetime) -> bool:
    """Write the notification, then try to push it."""
    from app.services.notification_service import push_to_user

    async with tenant_session(account_id) as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder is None:
            return False

        entry: Entry | None = None
        if reminder.entry_id is not None:
            entry = (
                await session.execute(
                    select(Entry).where(Entry.id == reminder.entry_id, Entry.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            if entry is None:
                # The task was deleted between scheduling and firing. Nothing to
                # remind anyone about.
                log.info("reminder.subject_gone", reminder_id=reminder_id)
                return False

        title = reminder.title or (entry.title if entry else "Rappel MindFlow")
        body = reminder.body or "C'est le moment."

        notification = Notification(
            account_id=reminder.account_id,
            user_id=reminder.user_id,
            entry_id=reminder.entry_id,
            reminder_id=reminder.id,
            kind=NotificationKind.REMINDER,
            title=title[:200],
            body=body[:500],
            payload={
                "entry_id": str(reminder.entry_id) if reminder.entry_id else "",
                "reminder_id": str(reminder.id),
            },
        )
        session.add(notification)
        session.add(
            ActivityEvent(
                account_id=reminder.account_id,
                user_id=reminder.user_id,
                entry_id=reminder.entry_id,
                action=ActivityAction.REMINDER_FIRED.value,
                subject_label=title[:300],
                actor_type="system",
                detail={"channel": reminder.channel},
            )
        )
        await session.flush()

        # A locally scheduled reminder was already delivered by the device
        # itself (ADR-040); pushing it too would show the user the same toast
        # twice.
        if reminder.channel == ReminderChannel.LOCAL.value:
            return True

        delivered = await push_to_user(
            session,
            settings,
            user_id=reminder.user_id,
            message=PushMessage(
                title=title,
                body=body,
                data={
                    "type": "reminder",
                    "entry_id": str(reminder.entry_id) if reminder.entry_id else "",
                    "reminder_id": str(reminder.id),
                },
                # Collapsed per entry: a second reminder about one task replaces
                # the first on the lock screen instead of stacking.
                collapse_key=f"entry-{reminder.entry_id}" if reminder.entry_id else None,
            ),
        )
        if delivered:
            notification.pushed_at = now
        else:
            # Not an error state for the reminder: the notification row exists
            # and the user will find it. Recorded so a systematically
            # undeliverable account is visible in the logs.
            log.info("reminder.not_pushed", reminder_id=reminder_id)
        await session.flush()
        return True


async def sweep_snoozed(settings: Settings) -> int:
    """Wake tasks whose snooze has expired.

    Lives here rather than in the capture sweeper because it belongs to the same
    "time has passed, act on it" concern as reminders, and shares its cadence.
    """
    from app.domain.enums import EntryStatus
    from app.infra.db.models.core import Task

    now = datetime.now(UTC)
    woken = 0
    async with privileged_session() as session:
        rows = (
            await session.execute(
                select(Entry, Task)
                .join(Task, Task.entry_id == Entry.id)
                .where(
                    Entry.status == EntryStatus.SNOOZED.value,
                    Task.snoozed_until.isnot(None),
                    Task.snoozed_until <= now,
                    Entry.deleted_at.is_(None),
                )
                .limit(BATCH)
            )
        ).all()
        for entry, task in rows:
            entry.status = EntryStatus.ACTIVE
            task.snoozed_until = None
            woken += 1
    if woken:
        log.info("reminder.unsnoozed", count=woken)
    return woken
