"""Agenda and calendar.

The hard part of an agenda is not the query, it is the *timezone*. A day is a
range in the user's local calendar, and "this week" spans 167, 168 or 169 hours
depending on where the daylight-saving boundary falls. Doing this arithmetic in
UTC produces an agenda that is subtly wrong twice a year — one hour of tasks
appearing on the wrong day, which is exactly the kind of bug users report as
"the app lost my task".

So every boundary here is built in the user's zone and converted to UTC once, at
the edge, for the query.

Overdue items get their own bucket rather than being pinned to the day they were
due. A task from three weeks ago at the bottom of a scrolled-away day is a task
nobody will ever see again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import AgendaView, EntryStatus
from app.infra.db.models.core import Capture, Entry, Task
from app.services.identity_service import Principal

# A month view asking for a year of days would be a denial of service with a
# friendly face.
MAX_RANGE_DAYS = 400


@dataclass(slots=True)
class AgendaItem:
    entry: Entry
    task: Task | None
    # The local day this item belongs on. Computed once here so the interface
    # never has to redo timezone arithmetic per row.
    day: date


@dataclass(slots=True)
class AgendaDay:
    day: date
    items: list[AgendaItem] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.items


@dataclass(slots=True)
class Agenda:
    start: date
    end: date
    timezone: str
    days: list[AgendaDay]
    overdue: list[AgendaItem]
    # Undated items are not shown in the grid but are offered beside it, so a
    # task with no deadline is not invisible in the one screen about planning.
    unscheduled: list[AgendaItem] = field(default_factory=list)


@dataclass(slots=True)
class CalendarCell:
    day: date
    total: int
    done: int
    overdue: int
    captures: int

    @property
    def pending(self) -> int:
        return max(self.total - self.done, 0)


class AgendaService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal
        self._zone = _zone(principal.timezone)

    # -- range helpers ------------------------------------------------------
    def range_for(self, view: AgendaView, anchor: date) -> tuple[date, date]:
        """Half-open [start, end) in local days."""
        if view is AgendaView.DAY:
            return anchor, anchor + timedelta(days=1)
        if view is AgendaView.WEEK:
            monday = anchor - timedelta(days=anchor.weekday())
            return monday, monday + timedelta(days=7)
        first = anchor.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        # The grid shows whole weeks, so a month view spans from the Monday
        # before the 1st to the Sunday after the last day. Anything else leaves
        # holes at the corners of the calendar.
        return first - timedelta(days=first.weekday()), following + timedelta(
            days=(7 - following.weekday()) % 7
        )

    def _instant(self, day: date, at: time = time.min) -> datetime:
        return datetime.combine(day, at, tzinfo=self._zone).astimezone(UTC)

    def local_day(self, moment: datetime) -> date:
        return moment.astimezone(self._zone).date()

    # -- agenda -------------------------------------------------------------
    async def agenda(
        self,
        *,
        start: date,
        end: date,
        include_done: bool = True,
        include_unscheduled: bool = False,
        project_id: uuid.UUID | None = None,
    ) -> Agenda:
        if (end - start).days > MAX_RANGE_DAYS:
            end = start + timedelta(days=MAX_RANGE_DAYS)

        query = (
            select(Entry, Task)
            .join(Task, Task.entry_id == Entry.id)
            .where(
                Entry.deleted_at.is_(None),
                Task.due_at >= self._instant(start),
                Task.due_at < self._instant(end),
            )
            .order_by(Task.due_at.asc(), Entry.id.asc())
        )
        if not include_done:
            query = query.where(Task.completed_at.is_(None))
        if project_id is not None:
            query = query.where(Entry.project_id == project_id)

        rows = (await self._session.execute(query)).all()

        buckets: dict[date, AgendaDay] = {}
        cursor = start
        while cursor < end:
            buckets[cursor] = AgendaDay(day=cursor)
            cursor += timedelta(days=1)

        for entry, task in rows:
            day = self.local_day(task.due_at)
            bucket = buckets.get(day)
            if bucket is None:
                # A due date that lands outside the requested window after
                # timezone conversion. Rare, but dropping it silently would be a
                # disappearing task.
                bucket = buckets.setdefault(day, AgendaDay(day=day))
            bucket.items.append(AgendaItem(entry=entry, task=task, day=day))

        overdue_rows = await self._overdue()
        unscheduled: list[AgendaItem] = []
        if include_unscheduled:
            unscheduled = await self._unscheduled(project_id=project_id)

        return Agenda(
            start=start,
            end=end,
            timezone=self._principal.timezone,
            days=[buckets[key] for key in sorted(buckets)],
            overdue=overdue_rows,
            unscheduled=unscheduled,
        )

    async def _overdue(self) -> list[AgendaItem]:
        now = datetime.now(UTC)
        rows = (
            await self._session.execute(
                select(Entry, Task)
                .join(Task, Task.entry_id == Entry.id)
                .where(
                    Entry.deleted_at.is_(None),
                    Entry.status.notin_((EntryStatus.DONE.value, EntryStatus.ARCHIVED.value)),
                    Task.completed_at.is_(None),
                    Task.due_at.isnot(None),
                    Task.due_at < now,
                )
                .order_by(Task.due_at.asc())
                .limit(100)
            )
        ).all()
        return [
            AgendaItem(entry=entry, task=task, day=self.local_day(task.due_at))
            for entry, task in rows
        ]

    async def _unscheduled(self, *, project_id: uuid.UUID | None) -> list[AgendaItem]:
        query = (
            select(Entry, Task)
            .outerjoin(Task, Task.entry_id == Entry.id)
            .where(
                Entry.deleted_at.is_(None),
                Entry.status.notin_((EntryStatus.DONE.value, EntryStatus.ARCHIVED.value)),
                Task.due_at.is_(None),
            )
            .order_by(Entry.occurred_at.desc())
            .limit(50)
        )
        if project_id is not None:
            query = query.where(Entry.project_id == project_id)
        rows = (await self._session.execute(query)).all()
        today = self.local_day(datetime.now(UTC))
        return [AgendaItem(entry=entry, task=task, day=today) for entry, task in rows]

    # -- calendar -----------------------------------------------------------
    async def calendar(self, *, start: date, end: date) -> list[CalendarCell]:
        """Per-day density, for the month grid.

        Aggregated in the database rather than by counting the agenda in Python:
        a month grid needs six weeks of counts and nothing else, and shipping
        every row to compute a number is how a calendar screen becomes slow.
        The `AT TIME ZONE` cast groups by the *user's* day, not by UTC.
        """
        zone = self._principal.timezone
        local_day = func.date(func.timezone(zone, Task.due_at))

        task_rows = (
            await self._session.execute(
                select(
                    local_day.label("day"),
                    func.count().label("total"),
                    func.count(Task.completed_at).label("done"),
                )
                .select_from(Entry)
                .join(Task, Task.entry_id == Entry.id)
                .where(
                    Entry.deleted_at.is_(None),
                    Task.due_at >= self._instant(start),
                    Task.due_at < self._instant(end),
                )
                .group_by(local_day)
            )
        ).all()

        capture_day = func.date(func.timezone(zone, Capture.captured_at))
        capture_rows = (
            await self._session.execute(
                select(capture_day.label("day"), func.count().label("total"))
                .select_from(Capture)
                .where(
                    Capture.deleted_at.is_(None),
                    Capture.captured_at >= self._instant(start),
                    Capture.captured_at < self._instant(end),
                )
                .group_by(capture_day)
            )
        ).all()

        now = datetime.now(UTC)
        today = self.local_day(now)
        captures_by_day = {row.day: int(row.total) for row in capture_rows}

        cells: dict[date, CalendarCell] = {}
        cursor = start
        while cursor < end:
            cells[cursor] = CalendarCell(
                day=cursor, total=0, done=0, overdue=0, captures=captures_by_day.get(cursor, 0)
            )
            cursor += timedelta(days=1)

        for row in task_rows:
            cell = cells.get(row.day)
            if cell is None:
                continue
            cell.total = int(row.total)
            cell.done = int(row.done)
            if row.day < today:
                cell.overdue = max(cell.total - cell.done, 0)

        return [cells[key] for key in sorted(cells)]


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")
