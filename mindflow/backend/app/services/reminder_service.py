"""Reminders: scheduling the nudge, separately from the deadline.

`task.due_at` says when the work is owed. A reminder says when to be told. They
are different facts and the product needs both: "due Friday, remind me Thursday
evening" is an ordinary sentence that a single timestamp cannot express.

The scheduling rules are deliberately conservative:

* **A reminder in the past is never created.** Rescheduling a task to tomorrow
  must not fire the "15 minutes before" reminder that is now behind us.
* **Rescheduling a task rewrites its automatic reminders and leaves the manual
  ones alone.** Someone who explicitly asked to be reminded on Tuesday meant
  Tuesday, whatever happens to the due date afterwards.
* **Completing or deleting a task cancels its pending reminders.** A phone
  buzzing about something already done is the fastest way to get notifications
  switched off for good.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ActivityAction, ReminderChannel, ReminderStatus
from app.domain.errors import NotFoundError, ValidationError
from app.infra.db.models.core import Entry, Reminder, Task
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.activity_service import ActivityService
from app.services.identity_service import Principal

log = get_logger("reminder")

# Offsets the product schedules on its own when a task gets a due date. Chosen
# to be useful without being noisy: one the day before to allow planning, one
# shortly before to prompt action.
DEFAULT_OFFSETS: tuple[str, ...] = ("-1d@18:00", "-15m")

MAX_REMINDERS_PER_ENTRY = 10
# A reminder scheduled further out than this is almost always a date-entry
# mistake, and holding a row for three years to find out is not worth it.
MAX_HORIZON = timedelta(days=730)

_OFFSET = re.compile(r"^-(\d+)(m|h|d|w)(?:@(\d{1,2}):(\d{2}))?$")


@dataclass(frozen=True, slots=True)
class ReminderPlan:
    remind_at: datetime
    rule: str


def resolve_offset(rule: str, *, due_at: datetime) -> datetime | None:
    """Turn `-15m` or `-1d@18:00` into an instant.

    The `@HH:MM` form pins a wall-clock time on the offset day, which is what
    "the day before at six" means; a bare `-1d` keeps the deadline's own time.
    An unparseable rule returns None rather than a guessed instant.
    """
    match = _OFFSET.match(rule.strip())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    delta = {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
        "w": timedelta(weeks=amount),
    }[unit]

    moment = due_at - delta
    if match.group(3) is not None:
        hour, minute = int(match.group(3)), int(match.group(4))
        if hour > 23 or minute > 59:
            return None
        moment = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment


class ReminderService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal
        self._activity = ActivityService(session, principal=principal)

    async def list_for_entry(self, entry_id: uuid.UUID) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder).where(Reminder.entry_id == entry_id).order_by(Reminder.remind_at.asc())
        )
        return list(result.scalars().all())

    async def list_upcoming(self, *, limit: int = 50) -> list[Reminder]:
        query: Select[tuple[Reminder]] = (
            select(Reminder)
            .where(
                Reminder.user_id == self._principal.user_id,
                Reminder.status == ReminderStatus.SCHEDULED.value,
            )
            .order_by(Reminder.remind_at.asc())
            .limit(min(limit, 200))
        )
        return list((await self._session.execute(query)).scalars().all())

    async def schedule(
        self,
        *,
        entry_id: uuid.UUID | None,
        remind_at: datetime,
        channel: ReminderChannel = ReminderChannel.PUSH,
        offset_rule: str | None = None,
        title: str | None = None,
        body: str | None = None,
    ) -> Reminder | None:
        """Create one reminder. Returns None when the instant is not schedulable.

        Returning None rather than raising for a past instant is deliberate: the
        common caller is the automatic scheduler reacting to a due date, and
        "that offset is already behind us" is an ordinary outcome there, not an
        error worth aborting a task update for.
        """
        now = datetime.now(UTC)
        if remind_at <= now:
            return None
        if remind_at - now > MAX_HORIZON:
            raise ValidationError(
                "Un rappel ne peut pas être programmé à plus de deux ans.", field="remind_at"
            )

        if entry_id is not None:
            existing = await self.list_for_entry(entry_id)
            pending = [r for r in existing if r.status == ReminderStatus.SCHEDULED.value]
            if len(pending) >= MAX_REMINDERS_PER_ENTRY:
                raise ValidationError(
                    f"Au plus {MAX_REMINDERS_PER_ENTRY} rappels par élément.", field="reminders"
                )

        # The dedupe key is what makes the whole scheduler idempotent: re-running
        # the automatic planner after an update must not stack three copies of
        # the same "15 minutes before".
        key = _dedupe_key(entry_id, remind_at, offset_rule, channel)
        already = (
            await self._session.execute(select(Reminder).where(Reminder.dedupe_key == key))
        ).scalar_one_or_none()
        if already is not None:
            if already.status == ReminderStatus.CANCELLED.value:
                already.status = ReminderStatus.SCHEDULED
                already.remind_at = remind_at
                await self._session.flush()
            return already

        reminder = Reminder(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            entry_id=entry_id,
            remind_at=remind_at,
            channel=channel,
            status=ReminderStatus.SCHEDULED,
            offset_rule=offset_rule,
            title=(title or "")[:200] or None,
            body=(body or "")[:500] or None,
            dedupe_key=key,
        )
        self._session.add(reminder)
        if entry_id is not None:
            self._activity.record(
                ActivityAction.REMINDER_SET,
                entry_id=entry_id,
                label=title,
                detail={"remind_at": remind_at.isoformat(), "rule": offset_rule},
            )
        metrics.reminders_scheduled_total.labels(channel.value).inc()
        await self._session.flush()
        return reminder

    async def cancel(self, reminder_id: uuid.UUID) -> Reminder:
        reminder = await self._session.get(Reminder, reminder_id)
        if reminder is None:
            raise NotFoundError(f"Rappel {reminder_id} introuvable.")
        if reminder.status == ReminderStatus.SCHEDULED.value:
            reminder.status = ReminderStatus.CANCELLED
            await self._session.flush()
        return reminder

    async def dismiss(self, reminder_id: uuid.UUID) -> Reminder:
        reminder = await self._session.get(Reminder, reminder_id)
        if reminder is None:
            raise NotFoundError(f"Rappel {reminder_id} introuvable.")
        reminder.status = ReminderStatus.DISMISSED
        await self._session.flush()
        return reminder

    async def cancel_for_entry(self, entry_id: uuid.UUID, *, automatic_only: bool = False) -> int:
        """Cancel pending reminders on an entry.

        `automatic_only` is what keeps a manual reminder from being wiped out by
        a due-date change: the user asked for Tuesday, and Tuesday is not the
        system's to revise.
        """
        cancelled = 0
        for reminder in await self.list_for_entry(entry_id):
            if reminder.status != ReminderStatus.SCHEDULED.value:
                continue
            if automatic_only and reminder.offset_rule is None:
                continue
            reminder.status = ReminderStatus.CANCELLED
            cancelled += 1
        if cancelled:
            await self._session.flush()
        return cancelled

    async def sync_automatic(
        self,
        entry: Entry,
        task: Task,
        *,
        offsets: tuple[str, ...] = DEFAULT_OFFSETS,
    ) -> list[Reminder]:
        """Re-derive the automatic reminders of a task from its due date.

        Called after anything that moves a deadline. Cancels the previous
        automatic set and recreates it; manual reminders are untouched.
        """
        await self.cancel_for_entry(entry.id, automatic_only=True)
        if task.due_at is None or task.completed_at is not None:
            return []

        created: list[Reminder] = []
        for rule in offsets:
            moment = resolve_offset(rule, due_at=task.due_at)
            if moment is None:
                log.warning("reminder.unparseable_offset", rule=rule)
                continue
            reminder = await self.schedule(
                entry_id=entry.id,
                remind_at=moment,
                offset_rule=rule,
                title=entry.title,
                body=_body_for(rule),
            )
            if reminder is not None:
                created.append(reminder)
        return created


def _body_for(rule: str) -> str:
    if rule.startswith("-1d"):
        return "À faire demain."
    if rule.endswith("m"):
        return "C'est bientôt."
    return "Échéance proche."


def _dedupe_key(
    entry_id: uuid.UUID | None,
    remind_at: datetime,
    offset_rule: str | None,
    channel: ReminderChannel,
) -> str:
    """Stable identity of a reminder.

    Includes the instant, so moving a deadline produces a genuinely new reminder
    rather than resurrecting the old one at the wrong time; and the rule, so the
    two default offsets never collide when they happen to land together.
    """
    stamp = remind_at.astimezone(UTC).strftime("%Y%m%dT%H%M")
    return f"{entry_id or 'standalone'}:{offset_rule or 'manual'}:{channel.value}:{stamp}"[:120]
