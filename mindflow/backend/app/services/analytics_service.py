"""Statistics for the analytical dashboard.

A principle runs through all of it: **report, do not flatter**. A dashboard that
only counts what went well teaches nothing. So the numbers here include the
uncomfortable ones — how many extractions the user had to correct, how much of
the backlog is overdue, how many captures never produced anything — because
those are the ones that say whether the product is actually working.

Every figure is computed in SQL. Fetching rows to count them in Python is fine
at a hundred entries and quietly catastrophic at fifty thousand, which is the
volume a two-year-old account reaches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Float, Select, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntryStatus, EntryType
from app.infra.db.models.core import (
    AiRun,
    Capture,
    CorrectionEvent,
    Entry,
    EntryTag,
    Project,
    Tag,
    Task,
)
from app.services.identity_service import Principal

MAX_WINDOW_DAYS = 365
DEFAULT_WINDOW_DAYS = 30


@dataclass(slots=True)
class DailyPoint:
    day: date
    created: int = 0
    completed: int = 0
    captured: int = 0


@dataclass(slots=True)
class Breakdown:
    key: str
    label: str
    total: int
    done: int = 0
    color: str | None = None

    @property
    def completion_rate(self) -> float:
        return round(self.done / self.total, 3) if self.total else 0.0


@dataclass(slots=True)
class Streak:
    current: int
    longest: int
    last_active_day: date | None


@dataclass(slots=True)
class Statistics:
    window_days: int
    start: date
    end: date

    captures: int
    entries_created: int
    tasks_completed: int
    tasks_open: int
    tasks_overdue: int

    completion_rate: float
    # Median, not mean: one task left open for eight months would drag an average
    # into meaninglessness while the typical experience stayed unchanged.
    median_completion_hours: float | None

    by_type: list[Breakdown]
    by_priority: list[Breakdown]
    by_project: list[Breakdown]
    top_tags: list[Breakdown]
    daily: list[DailyPoint]
    streak: Streak

    # The honest half.
    corrections: int
    correction_rate: float
    captures_without_entries: int
    needs_review: int
    ai_cost_micro_eur: int

    busiest_hour: int | None = None
    peak_day: date | None = None
    notes: list[str] = field(default_factory=list)


class AnalyticsService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal
        self._zone = _zone(principal.timezone)

    async def statistics(self, *, window_days: int = DEFAULT_WINDOW_DAYS) -> Statistics:
        window = max(1, min(window_days, MAX_WINDOW_DAYS))
        now = datetime.now(UTC)
        end_day = now.astimezone(self._zone).date() + timedelta(days=1)
        start_day = end_day - timedelta(days=window)
        start = datetime.combine(start_day, datetime.min.time(), tzinfo=self._zone).astimezone(UTC)
        end = datetime.combine(end_day, datetime.min.time(), tzinfo=self._zone).astimezone(UTC)

        captures = await self._count(
            select(func.count())
            .select_from(Capture)
            .where(
                Capture.deleted_at.is_(None),
                Capture.captured_at >= start,
                Capture.captured_at < end,
            )
        )
        entries_created = await self._count(
            select(func.count())
            .select_from(Entry)
            .where(
                Entry.deleted_at.is_(None),
                Entry.created_at >= start,
                Entry.created_at < end,
            )
        )
        tasks_completed = await self._count(
            select(func.count())
            .select_from(Task)
            .join(Entry, Entry.id == Task.entry_id)
            .where(
                Entry.deleted_at.is_(None),
                Task.completed_at.isnot(None),
                Task.completed_at >= start,
                Task.completed_at < end,
            )
        )
        tasks_open = await self._count(
            select(func.count())
            .select_from(Task)
            .join(Entry, Entry.id == Task.entry_id)
            .where(
                Entry.deleted_at.is_(None),
                Task.completed_at.is_(None),
                Entry.status.notin_((EntryStatus.ARCHIVED.value, EntryStatus.DONE.value)),
            )
        )
        tasks_overdue = await self._count(
            select(func.count())
            .select_from(Task)
            .join(Entry, Entry.id == Task.entry_id)
            .where(
                Entry.deleted_at.is_(None),
                Task.completed_at.is_(None),
                Task.due_at.isnot(None),
                Task.due_at < now,
            )
        )

        total_tasks = tasks_open + tasks_completed
        completion_rate = round(tasks_completed / total_tasks, 3) if total_tasks else 0.0

        return Statistics(
            window_days=window,
            start=start_day,
            end=end_day,
            captures=captures,
            entries_created=entries_created,
            tasks_completed=tasks_completed,
            tasks_open=tasks_open,
            tasks_overdue=tasks_overdue,
            completion_rate=completion_rate,
            median_completion_hours=await self._median_completion_hours(start, end),
            by_type=await self._by_type(start, end),
            by_priority=await self._by_priority(),
            by_project=await self._by_project(),
            top_tags=await self._top_tags(),
            daily=await self._daily(start_day, end_day, start, end),
            streak=await self._streak(),
            corrections=await self._count(
                select(func.count())
                .select_from(CorrectionEvent)
                .where(CorrectionEvent.corrected_at >= start)
            ),
            correction_rate=await self._correction_rate(start, end),
            captures_without_entries=await self._captures_without_entries(start, end),
            needs_review=await self._count(
                select(func.count())
                .select_from(Entry)
                .where(
                    Entry.deleted_at.is_(None),
                    Entry.status == EntryStatus.NEEDS_REVIEW.value,
                )
            ),
            ai_cost_micro_eur=await self._ai_cost(start, end),
            busiest_hour=await self._busiest_hour(start, end),
        )

    # -- building blocks ----------------------------------------------------
    async def _count(self, query: Select[tuple[int]]) -> int:
        result = await self._session.execute(query)
        return int(result.scalar_one() or 0)

    async def _median_completion_hours(self, start: datetime, end: datetime) -> float | None:
        """Time from creation to completion, median.

        `percentile_cont` does it in the database. Computing a median in Python
        means fetching every completed task, which is exactly the query that gets
        slow first on a busy account.
        """
        expression = func.percentile_cont(0.5).within_group(
            func.extract("epoch", Task.completed_at - Entry.created_at)
        )
        result = await self._session.execute(
            select(expression)
            .select_from(Task)
            .join(Entry, Entry.id == Task.entry_id)
            .where(
                Entry.deleted_at.is_(None),
                Task.completed_at.isnot(None),
                Task.completed_at >= start,
                Task.completed_at < end,
            )
        )
        seconds = result.scalar_one_or_none()
        return round(float(seconds) / 3600, 1) if seconds else None

    async def _by_type(self, start: datetime, end: datetime) -> list[Breakdown]:
        rows = (
            await self._session.execute(
                select(
                    Entry.entry_type,
                    func.count().label("total"),
                    func.count(case((Entry.status == EntryStatus.DONE.value, 1))).label("done"),
                )
                .where(
                    Entry.deleted_at.is_(None),
                    Entry.created_at >= start,
                    Entry.created_at < end,
                )
                .group_by(Entry.entry_type)
                .order_by(func.count().desc())
            )
        ).all()
        return [
            Breakdown(
                key=row.entry_type,
                label=_TYPE_LABELS.get(row.entry_type, row.entry_type),
                total=int(row.total),
                done=int(row.done),
            )
            for row in rows
        ]

    async def _by_priority(self) -> list[Breakdown]:
        rows = (
            await self._session.execute(
                select(
                    Task.priority,
                    func.count().label("total"),
                    func.count(Task.completed_at).label("done"),
                )
                .select_from(Task)
                .join(Entry, Entry.id == Task.entry_id)
                .where(Entry.deleted_at.is_(None))
                .group_by(Task.priority)
            )
        ).all()
        order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        breakdowns = [
            Breakdown(
                key=row.priority,
                label=_PRIORITY_LABELS.get(row.priority, row.priority),
                total=int(row.total),
                done=int(row.done),
            )
            for row in rows
        ]
        breakdowns.sort(key=lambda item: order.get(item.key, 9))
        return breakdowns

    async def _by_project(self, *, limit: int = 8) -> list[Breakdown]:
        rows = (
            await self._session.execute(
                select(
                    Project.id,
                    Project.name,
                    Project.color,
                    func.count(Entry.id).label("total"),
                    func.count(case((Entry.status == EntryStatus.DONE.value, 1))).label("done"),
                )
                .select_from(Project)
                .join(Entry, Entry.project_id == Project.id)
                .where(Entry.deleted_at.is_(None), Project.archived_at.is_(None))
                .group_by(Project.id, Project.name, Project.color)
                .order_by(func.count(Entry.id).desc())
                .limit(limit)
            )
        ).all()
        return [
            Breakdown(
                key=str(row.id),
                label=row.name,
                total=int(row.total),
                done=int(row.done),
                color=row.color,
            )
            for row in rows
        ]

    async def _top_tags(self, *, limit: int = 10) -> list[Breakdown]:
        rows = (
            await self._session.execute(
                select(Tag.label, Tag.color, func.count(EntryTag.entry_id).label("total"))
                .select_from(Tag)
                .join(EntryTag, EntryTag.tag_id == Tag.id)
                .join(Entry, Entry.id == EntryTag.entry_id)
                .where(Entry.deleted_at.is_(None))
                .group_by(Tag.label, Tag.color)
                .order_by(func.count(EntryTag.entry_id).desc())
                .limit(limit)
            )
        ).all()
        return [
            Breakdown(key=row.label, label=f"#{row.label}", total=int(row.total), color=row.color)
            for row in rows
        ]

    async def _daily(
        self, start_day: date, end_day: date, start: datetime, end: datetime
    ) -> list[DailyPoint]:
        zone = self._principal.timezone
        points: dict[date, DailyPoint] = {}
        cursor = start_day
        while cursor < end_day:
            points[cursor] = DailyPoint(day=cursor)
            cursor += timedelta(days=1)

        created_day = func.date(func.timezone(zone, Entry.created_at))
        for row in (
            await self._session.execute(
                select(created_day.label("day"), func.count().label("n"))
                .select_from(Entry)
                .where(
                    Entry.deleted_at.is_(None),
                    Entry.created_at >= start,
                    Entry.created_at < end,
                )
                .group_by(created_day)
            )
        ).all():
            if row.day in points:
                points[row.day].created = int(row.n)

        done_day = func.date(func.timezone(zone, Task.completed_at))
        for row in (
            await self._session.execute(
                select(done_day.label("day"), func.count().label("n"))
                .select_from(Task)
                .join(Entry, Entry.id == Task.entry_id)
                .where(
                    Entry.deleted_at.is_(None),
                    Task.completed_at.isnot(None),
                    Task.completed_at >= start,
                    Task.completed_at < end,
                )
                .group_by(done_day)
            )
        ).all():
            if row.day in points:
                points[row.day].completed = int(row.n)

        captured_day = func.date(func.timezone(zone, Capture.captured_at))
        for row in (
            await self._session.execute(
                select(captured_day.label("day"), func.count().label("n"))
                .select_from(Capture)
                .where(
                    Capture.deleted_at.is_(None),
                    Capture.captured_at >= start,
                    Capture.captured_at < end,
                )
                .group_by(captured_day)
            )
        ).all():
            if row.day in points:
                points[row.day].captured = int(row.n)

        return [points[key] for key in sorted(points)]

    async def _streak(self, *, lookback_days: int = 365) -> Streak:
        """Consecutive days with at least one capture.

        Counted on *capture*, not on completion: the habit this product is
        trying to build is "say it out loud straight away". Rewarding task
        completion instead would celebrate a different behaviour entirely.
        """
        zone = self._principal.timezone
        day = func.date(func.timezone(zone, Capture.captured_at))
        since = datetime.now(UTC) - timedelta(days=lookback_days)
        rows = (
            await self._session.execute(
                select(day.label("day"))
                .select_from(Capture)
                .where(Capture.deleted_at.is_(None), Capture.captured_at >= since)
                .group_by(day)
                .order_by(day.desc())
            )
        ).all()

        days = [row.day for row in rows]
        if not days:
            return Streak(current=0, longest=0, last_active_day=None)

        today = datetime.now(UTC).astimezone(self._zone).date()
        current = 0
        # Yesterday still counts: a streak should not break because the day is
        # not over yet.
        if days[0] in (today, today - timedelta(days=1)):
            expected = days[0]
            for value in days:
                if value == expected:
                    current += 1
                    expected -= timedelta(days=1)
                else:
                    break

        longest = 1
        run = 1
        for previous, value in pairwise(days):
            if previous - value == timedelta(days=1):
                run += 1
                longest = max(longest, run)
            else:
                run = 1
        return Streak(current=current, longest=max(longest, current), last_active_day=days[0])

    async def _correction_rate(self, start: datetime, end: datetime) -> float:
        """Share of AI-produced entries the user had to fix.

        The single most useful number on this dashboard, and the least
        flattering. If it climbs, the extraction prompt is drifting away from
        how this particular user speaks.
        """
        ai_entries = await self._count(
            select(func.count())
            .select_from(Entry)
            .where(
                Entry.deleted_at.is_(None),
                Entry.origin == "ai",
                Entry.created_at >= start,
                Entry.created_at < end,
            )
        )
        if not ai_entries:
            return 0.0
        corrected = await self._count(
            select(func.count(func.distinct(CorrectionEvent.entry_id)))
            .select_from(CorrectionEvent)
            .where(CorrectionEvent.corrected_at >= start, CorrectionEvent.corrected_at < end)
        )
        return round(corrected / ai_entries, 3)

    async def _captures_without_entries(self, start: datetime, end: datetime) -> int:
        """Recordings that produced nothing.

        Either the user said something unstructurable, or the extraction failed.
        Both are worth surfacing; a dashboard that hides them makes the pipeline
        look perfect.
        """
        return await self._count(
            select(func.count())
            .select_from(Capture)
            .where(
                Capture.deleted_at.is_(None),
                Capture.captured_at >= start,
                Capture.captured_at < end,
                ~select(Entry.id).where(Entry.capture_id == Capture.id).exists(),
            )
        )

    async def _ai_cost(self, start: datetime, end: datetime) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.sum(AiRun.cost_micro_eur), 0)).where(
                AiRun.created_at >= start, AiRun.created_at < end
            )
        )
        return int(result.scalar_one() or 0)

    async def _busiest_hour(self, start: datetime, end: datetime) -> int | None:
        """The hour of day this person captures most. Local, obviously."""
        hour = func.extract("hour", func.timezone(self._principal.timezone, Capture.captured_at))
        result = await self._session.execute(
            select(hour.label("hour"), func.count().label("n"))
            .select_from(Capture)
            .where(
                Capture.deleted_at.is_(None),
                Capture.captured_at >= start,
                Capture.captured_at < end,
            )
            .group_by(hour)
            .order_by(func.count().desc())
            .limit(1)
        )
        row = result.first()
        return int(row.hour) if row else None

    async def project_summary(self, project_id: uuid.UUID) -> dict[str, object]:
        rows = (
            await self._session.execute(
                select(
                    func.count().label("total"),
                    func.count(case((Entry.status == EntryStatus.DONE.value, 1))).label("done"),
                    func.count(case((Entry.entry_type == EntryType.TASK.value, 1))).label("tasks"),
                    cast(func.count(Entry.pinned_at), Float).label("pinned"),
                )
                .select_from(Entry)
                .where(Entry.project_id == project_id, Entry.deleted_at.is_(None))
            )
        ).one()
        overdue = await self._count(
            select(func.count())
            .select_from(Task)
            .join(Entry, Entry.id == Task.entry_id)
            .where(
                Entry.project_id == project_id,
                Entry.deleted_at.is_(None),
                Task.completed_at.is_(None),
                Task.due_at.isnot(None),
                Task.due_at < datetime.now(UTC),
            )
        )
        total = int(rows.total)
        return {
            "total": total,
            "done": int(rows.done),
            "tasks": int(rows.tasks),
            "overdue": overdue,
            "completion_rate": round(int(rows.done) / total, 3) if total else 0.0,
        }


_TYPE_LABELS = {
    "task": "Tâches",
    "idea": "Idées",
    "note": "Notes",
    "decision": "Décisions",
    "question": "Questions",
    "meeting": "Réunions",
    "reminder": "Rappels",
}

_PRIORITY_LABELS = {
    "urgent": "Urgent",
    "high": "Important",
    "normal": "Normal",
    "low": "Basse",
}


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")
