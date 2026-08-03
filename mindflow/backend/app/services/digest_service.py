"""Daily, weekly and monthly summaries.

A digest is read passively — often on a phone notification, by someone who will
not open the source to check it. That single fact drives every decision here:

* **The counts are computed in SQL and handed to the model as established
  facts.** « 14 tâches terminées » is something the database knows; a model
  counting a list is a well-documented way to be confidently off by two, and a
  wrong number in a summary is believed.
* **Periods are days in the user's timezone, not UTC instants.** "The week of
  1 June" must mean the same thing for someone in Libreville and someone in
  Paris, and must not shift when they travel. `period_start` is a `date` for
  exactly this reason.
* **Regenerating replaces.** The unique constraint on
  (account, user, period, period_start) means a re-run overwrites. Two
  summaries of the same week are not a richer history — they are a
  contradiction shown to the user.

An empty period produces a one-line digest rather than nothing. Silence is
ambiguous: the user cannot tell "you did nothing" from "the job failed".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntryStatus, EntryType
from app.domain.errors import ExtractionUnavailableError
from app.domain.ports import ChatMessage, ChatPort, ChatRequest
from app.infra.db.models.ai import Digest
from app.infra.db.models.core import Entry, Task
from app.observability import metrics
from app.observability.logging import get_logger
from app.prompts.digest import DigestPeriod, build_material_block, for_period
from app.services.identity_service import Principal

log = get_logger("ai.digest")

# Enough material for the model to see the shape of a period without paying to
# send a whole month of notes.
MAX_ITEMS = {
    DigestPeriod.DAILY: 40,
    DigestPeriod.WEEKLY: 90,
    DigestPeriod.MONTHLY: 150,
}


@dataclass(slots=True)
class DigestStats:
    entries_created: int = 0
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_overdue: int = 0
    meetings: int = 0
    decisions: int = 0

    def as_lines(self) -> list[str]:
        """Rendered for the prompt, omitting zeros.

        A list of zeros reads as an instruction to explain them, and the model
        obliges with a paragraph about a quiet week nobody asked for.
        """
        pairs = [
            (self.entries_created, "note créée", "notes créées"),
            (self.tasks_created, "tâche créée", "tâches créées"),
            (self.tasks_completed, "tâche terminée", "tâches terminées"),
            (self.tasks_overdue, "tâche en retard", "tâches en retard"),
            (self.meetings, "réunion", "réunions"),
            (self.decisions, "décision", "décisions"),
        ]
        return [
            f"{count} {singular if count == 1 else plural}"
            for count, singular, plural in pairs
            if count
        ]

    def as_json(self) -> dict[str, int]:
        return {
            "entries_created": self.entries_created,
            "tasks_completed": self.tasks_completed,
            "tasks_created": self.tasks_created,
            "tasks_overdue": self.tasks_overdue,
            "meetings": self.meetings,
            "decisions": self.decisions,
        }

    @property
    def is_empty(self) -> bool:
        return not any(self.as_json().values())


class DigestService:
    def __init__(
        self, session: AsyncSession, *, principal: Principal, chat: ChatPort | None = None
    ) -> None:
        self._session = session
        self._principal = principal
        self._chat = chat
        self._zone = _zone(principal.timezone)

    # -- Periods ------------------------------------------------------------ #

    def period_bounds(self, period: DigestPeriod, anchor: date) -> tuple[date, date]:
        """The inclusive day range a digest covers.

        Weeks start Monday (ISO), which is what "la semaine" means to a French
        user. Months are calendar months, not rolling thirty days — a monthly
        digest that covers 12 May to 11 June is not a month to anybody.
        """
        if period is DigestPeriod.DAILY:
            return anchor, anchor
        if period is DigestPeriod.WEEKLY:
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        start = anchor.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)

    def _instant(self, day: date, at: time = time.min) -> datetime:
        return datetime.combine(day, at, tzinfo=self._zone).astimezone(UTC)

    # -- Generation --------------------------------------------------------- #

    async def generate(self, period: DigestPeriod, *, anchor: date, force: bool = False) -> Digest:
        """Produce (or replace) the digest for the period containing `anchor`."""
        start, end = self.period_bounds(period, anchor)
        existing = await self.find(period, start)
        if existing is not None and not force:
            return existing

        stats = await self._stats(start, end)
        items = await self._material(start, end, limit=MAX_ITEMS[period])
        content = await self._write(period, start, end, stats, items)

        digest = existing or Digest(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            period=period.value,
            period_start=start,
            period_end=end,
            content="",
        )
        digest.period_end = end
        digest.content = content
        digest.stats = dict(stats.as_json())
        digest.entry_count = stats.entries_created
        if existing is None:
            self._session.add(digest)
        await self._session.flush()

        metrics.digests_generated_total.labels(period.value, "ok").inc()
        return digest

    async def _write(
        self,
        period: DigestPeriod,
        start: date,
        end: date,
        stats: DigestStats,
        items: list[str],
    ) -> str:
        """Ask the model to phrase the period, falling back to the facts.

        The fallback matters: a digest is generated by a cron with nobody
        watching, and a provider outage must not leave an empty row that looks
        like an empty week.
        """
        if stats.is_empty and not items:
            return _empty_text(period, start, end)
        if self._chat is None:
            return _factual_text(period, start, end, stats, items)

        label = _period_label(period, start, end)
        request = ChatRequest(
            system=for_period(period).system,
            messages=(
                ChatMessage(
                    role="user",
                    content=build_material_block(label, items, stats=stats.as_lines()),
                ),
            ),
            temperature=0.3,
            max_output_tokens=900,
        )

        try:
            response = await self._chat.complete(request)
        except ExtractionUnavailableError:
            metrics.digests_generated_total.labels(period.value, "degraded").inc()
            log.warning("digest.unavailable", period=period.value, start=start.isoformat())
            return _factual_text(period, start, end, stats, items)

        if response.refused or not response.text.strip():
            metrics.digests_generated_total.labels(period.value, "degraded").inc()
            return _factual_text(period, start, end, stats, items)
        return response.text.strip()

    # -- Material ----------------------------------------------------------- #

    async def _stats(self, start: date, end: date) -> DigestStats:
        """Counts, in one round trip per aspect.

        Aggregated in SQL rather than by loading the period and counting in
        Python: a monthly digest for an active user would otherwise pull
        thousands of rows to produce six integers.
        """
        begin = self._instant(start)
        finish = self._instant(end + timedelta(days=1))

        created = (
            await self._session.execute(
                select(
                    func.count(Entry.id),
                    func.count(Entry.id).filter(Entry.entry_type == EntryType.MEETING.value),
                    func.count(Entry.id).filter(Entry.entry_type == EntryType.DECISION.value),
                    func.count(Entry.id).filter(Entry.entry_type == EntryType.TASK.value),
                ).where(
                    Entry.deleted_at.is_(None),
                    Entry.occurred_at >= begin,
                    Entry.occurred_at < finish,
                )
            )
        ).one()

        completed = (
            await self._session.execute(
                select(func.count(Task.entry_id))
                .join(Entry, Task.entry_id == Entry.id)
                .where(
                    Entry.deleted_at.is_(None),
                    Task.completed_at.is_not(None),
                    Task.completed_at >= begin,
                    Task.completed_at < finish,
                )
            )
        ).scalar_one()

        overdue = (
            await self._session.execute(
                select(func.count(Task.entry_id))
                .join(Entry, Task.entry_id == Entry.id)
                .where(
                    Entry.deleted_at.is_(None),
                    Entry.status.notin_((EntryStatus.DONE.value, EntryStatus.ARCHIVED.value)),
                    Task.completed_at.is_(None),
                    Task.due_at.is_not(None),
                    Task.due_at < finish,
                )
            )
        ).scalar_one()

        return DigestStats(
            entries_created=int(created[0]),
            meetings=int(created[1]),
            decisions=int(created[2]),
            tasks_created=int(created[3]),
            tasks_completed=int(completed),
            tasks_overdue=int(overdue),
        )

    async def _material(self, start: date, end: date, *, limit: int) -> list[str]:
        """The entries the model reads, newest first."""
        rows = list(
            (
                await self._session.execute(
                    select(Entry)
                    .where(
                        Entry.deleted_at.is_(None),
                        Entry.status != EntryStatus.ARCHIVED.value,
                        Entry.occurred_at >= self._instant(start),
                        Entry.occurred_at < self._instant(end + timedelta(days=1)),
                    )
                    .order_by(Entry.occurred_at.desc())
                    .limit(limit)
                )
            ).scalars()
        )
        return [_render(entry) for entry in rows]

    # -- Reading ------------------------------------------------------------ #

    async def find(self, period: DigestPeriod, start: date) -> Digest | None:
        return (
            await self._session.execute(
                select(Digest).where(
                    Digest.user_id == self._principal.user_id,
                    Digest.period == period.value,
                    Digest.period_start == start,
                )
            )
        ).scalar_one_or_none()

    async def recent(self, *, period: DigestPeriod | None = None, limit: int = 20) -> list[Digest]:
        stmt = (
            select(Digest)
            .where(Digest.user_id == self._principal.user_id)
            .order_by(Digest.period_start.desc())
            .limit(limit)
        )
        if period is not None:
            stmt = stmt.where(Digest.period == period.value)
        return list((await self._session.execute(stmt)).scalars())

    async def mark_read(self, digest_id: uuid.UUID) -> Digest | None:
        digest = await self._session.get(Digest, digest_id)
        if digest is None:
            return None
        digest.read_at = datetime.now(UTC)
        await self._session.flush()
        return digest


def _render(entry: Entry) -> str:
    day = entry.occurred_at.date().isoformat() if entry.occurred_at else "?"
    body = (entry.body or "").strip().replace("\n", " ")
    suffix = f" — {body[:160]}" if body else ""
    return f"[{day}] ({entry.entry_type}) {entry.title}{suffix}"


def _period_label(period: DigestPeriod, start: date, end: date) -> str:
    if period is DigestPeriod.DAILY:
        return start.isoformat()
    return f"du {start.isoformat()} au {end.isoformat()}"


def _empty_text(period: DigestPeriod, start: date, end: date) -> str:
    """Explicit rather than blank.

    A blank digest is ambiguous: the user cannot tell "nothing happened" from
    "the job failed", and will assume the latter.
    """
    return f"Aucune activité enregistrée sur la période ({_period_label(period, start, end)})."


def _factual_text(
    period: DigestPeriod, start: date, end: date, stats: DigestStats, items: list[str]
) -> str:
    """The digest without the prose.

    Every number here was computed in SQL, so this is not a degraded *answer* —
    it is the same information without the phrasing. That is the right thing to
    fall back to when a provider is down.
    """
    lines = [f"Résumé {period.label} ({_period_label(period, start, end)})", ""]
    lines.extend(f"• {line}" for line in stats.as_lines())
    if items:
        lines.append("")
        lines.append("Éléments de la période :")
        lines.extend(f"• {item}" for item in items[:15])
    return "\n".join(lines)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # pragma: no cover - defensive
        return ZoneInfo("UTC")
