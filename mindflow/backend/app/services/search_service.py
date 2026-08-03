"""Search: full text, and the command palette.

Two modes, one grammar (`domain.search_query`):

* **Full text** ranks entries by relevance across a corpus that may be large.
  Backed by the `search_vector` generated column and a GIN index (ADR-037), so
  the cost is logarithmic in the corpus rather than linear.
* **Quick search** is the ⌘K palette: a handful of results across *several*
  kinds — entries, projects, tags, captures — returned fast enough to feel like
  filtering, not searching. It runs on prefix matching, not on the FTS index,
  because a palette must answer while the word is still being typed and
  `to_tsquery` does not match half a word.

`websearch_to_tsquery` is used rather than `to_tsquery` for one reason that
outranks its slightly poorer expressiveness: it cannot raise on malformed input.
A search box must not be able to return a 500.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntryStatus, EntryType
from app.domain.search_query import ParsedQuery, parse_query, to_websearch
from app.infra.db.models.core import Capture, Entry, EntryTag, Project, Tag, Task
from app.observability import metrics
from app.services.identity_service import Principal

# The text search configuration the generated column was built with. Changing it
# means rebuilding `entry.search_vector`, so it lives in one place.
FTS_CONFIG = "french"


def _config() -> ColumnElement[str]:
    """The configuration name, cast to `regconfig`.

    Without the cast PostgreSQL sees `websearch_to_tsquery(varchar, varchar)`,
    which does not exist, and answers with an `UndefinedFunction` that reads like
    a missing extension. The overload takes `regconfig`.
    """
    return cast(literal(FTS_CONFIG), REGCONFIG)


MAX_RESULTS = 100
QUICK_LIMIT_PER_KIND = 5
# Below this the palette is answering on one or two letters, where prefix
# matching returns everything and helps nobody.
MIN_QUICK_LENGTH = 2


@dataclass(slots=True)
class SearchHit:
    entry: Entry
    task: Task | None
    rank: float
    # Server-side highlight, so the client does not re-implement the tokeniser
    # and disagree with the ranking about what matched.
    snippet: str | None = None


@dataclass(slots=True)
class SearchResults:
    query: ParsedQuery
    hits: list[SearchHit]
    total: int
    took_ms: int


@dataclass(slots=True)
class QuickHit:
    kind: str
    id: str
    title: str
    subtitle: str | None = None
    icon: str | None = None


@dataclass(slots=True)
class QuickResults:
    entries: list[QuickHit] = field(default_factory=list)
    projects: list[QuickHit] = field(default_factory=list)
    tags: list[QuickHit] = field(default_factory=list)
    captures: list[QuickHit] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.entries or self.projects or self.tags or self.captures)


class SearchService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def search(
        self,
        raw: str,
        *,
        limit: int = 50,
        offset: int = 0,
        now: datetime | None = None,
    ) -> SearchResults:
        started = time.perf_counter()
        parsed = parse_query(raw, now=now or datetime.now(UTC), timezone=self._principal.timezone)

        if parsed.is_empty:
            metrics.search_queries_total.labels("full", "empty").inc()
            return SearchResults(query=parsed, hits=[], total=0, took_ms=0)

        query, rank = self._base_query(parsed)
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(query.order_by(None).subquery())
                )
            ).scalar_one()
        )

        query = (
            query.order_by(rank.desc(), Entry.occurred_at.desc())
            .limit(min(limit, MAX_RESULTS))
            .offset(max(offset, 0))
        )

        rows = (await self._session.execute(query)).all()
        hits = [
            SearchHit(
                entry=row[0],
                task=row[1],
                rank=float(row[2] or 0.0),
                snippet=row[3] if len(row) > 3 else None,
            )
            for row in rows
        ]

        took_ms = int((time.perf_counter() - started) * 1000)
        metrics.search_queries_total.labels("full", "hit" if hits else "miss").inc()
        metrics.search_duration_seconds.labels("full").observe(took_ms / 1000)
        return SearchResults(query=parsed, hits=hits, total=total, took_ms=took_ms)

    def _base_query(self, parsed: ParsedQuery) -> tuple[Select[Any], ColumnElement[float]]:
        """Build the filtered, ranked query.

        Rank is a constant when there is no free text: `is:task p:high` is a
        *filter*, and ordering a filter by relevance would shuffle it randomly.
        Chronological order is the honest answer there.
        """
        if parsed.text:
            tsquery = func.websearch_to_tsquery(_config(), literal(to_websearch(parsed.text)))
            rank: ColumnElement[float] = func.ts_rank_cd(Entry.search_vector, tsquery)
            snippet = func.ts_headline(
                _config(),
                func.coalesce(Entry.body, Entry.title),
                tsquery,
                literal("StartSel=«,StopSel=»,MaxWords=24,MinWords=8,ShortWord=2"),
            )
            query = select(Entry, Task, rank.label("rank"), snippet.label("snippet"))
        else:
            rank = literal(0.0)
            query = select(Entry, Task, rank.label("rank"))

        query = query.outerjoin(Task, Task.entry_id == Entry.id).where(Entry.deleted_at.is_(None))
        if parsed.text:
            query = query.where(
                Entry.search_vector.op("@@")(
                    func.websearch_to_tsquery(_config(), literal(to_websearch(parsed.text)))
                )
            )

        if parsed.types:
            query = query.where(Entry.entry_type.in_([t.value for t in parsed.types]))
        if parsed.statuses:
            query = query.where(Entry.status.in_([s.value for s in parsed.statuses]))
        else:
            # Archived entries are excluded unless asked for by name. They are
            # the user's own "put this away" gesture and a search that ignores it
            # undoes the gesture.
            query = query.where(Entry.status != EntryStatus.ARCHIVED.value)
        if parsed.priorities:
            query = query.where(Task.priority.in_([p.value for p in parsed.priorities]))
        if parsed.pinned:
            query = query.where(Entry.pinned_at.isnot(None))
        if parsed.recurring:
            query = query.where(Task.recurrence_rule.isnot(None))
        if parsed.overdue:
            query = query.where(
                and_(
                    Task.due_at.isnot(None),
                    Task.due_at < datetime.now(UTC),
                    Task.completed_at.is_(None),
                )
            )
        if parsed.due is not None:
            if parsed.due.bounded:
                if parsed.due.start is not None:
                    query = query.where(Task.due_at >= parsed.due.start)
                if parsed.due.end is not None:
                    query = query.where(Task.due_at < parsed.due.end)
            else:
                # `due:none` — the explicitly unbounded window means "no due date".
                query = query.where(Task.due_at.is_(None))
        if parsed.created is not None and parsed.created.bounded:
            if parsed.created.start is not None:
                query = query.where(Entry.created_at >= parsed.created.start)
            if parsed.created.end is not None:
                query = query.where(Entry.created_at < parsed.created.end)

        for tag in parsed.tags:
            # One EXISTS per tag: several `#tag` terms mean "carries all of
            # them", which a single IN cannot express.
            query = query.where(
                select(literal(1))
                .select_from(EntryTag)
                .join(Tag, Tag.id == EntryTag.tag_id)
                .where(EntryTag.entry_id == Entry.id, Tag.normalized == tag)
                .exists()
            )

        if parsed.projects:
            conditions = [
                or_(
                    func.lower(Project.slug) == name,
                    func.lower(Project.name).like(f"{name}%"),
                )
                for name in parsed.projects
            ]
            query = query.where(
                select(literal(1))
                .select_from(Project)
                .where(Project.id == Entry.project_id, or_(*conditions))
                .exists()
            )

        return query, rank

    async def quick(self, raw: str, *, limit: int = QUICK_LIMIT_PER_KIND) -> QuickResults:
        """The command palette.

        Prefix matching, capped per kind. `ILIKE 'term%'` rather than `%term%`
        so the trigram/btree indexes can be used and the palette stays under the
        threshold where typing feels laggy.
        """
        started = time.perf_counter()
        term = raw.strip()
        if len(term) < MIN_QUICK_LENGTH:
            return QuickResults()

        pattern = f"{term.lower()}%"
        contains = f"%{term.lower()}%"

        entries = (
            (
                await self._session.execute(
                    select(Entry)
                    .where(
                        Entry.deleted_at.is_(None),
                        func.lower(Entry.title).like(contains),
                    )
                    .order_by(
                        # Prefix matches first — what the user is typing is usually
                        # the start of what they are looking for.
                        (func.lower(Entry.title).like(pattern)).desc(),
                        Entry.pinned_at.desc().nullslast(),
                        Entry.occurred_at.desc(),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        projects = (
            (
                await self._session.execute(
                    select(Project)
                    .where(Project.archived_at.is_(None), func.lower(Project.name).like(contains))
                    .order_by(Project.name)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        tags = (
            (
                await self._session.execute(
                    select(Tag)
                    .where(Tag.normalized.like(pattern))
                    .order_by(Tag.usage_count.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        captures = (
            (
                await self._session.execute(
                    select(Capture)
                    .join(Entry, Entry.capture_id == Capture.id)
                    .where(Capture.deleted_at.is_(None), func.lower(Entry.title).like(contains))
                    .order_by(Capture.captured_at.desc())
                    .limit(limit)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        metrics.search_duration_seconds.labels("quick").observe(time.perf_counter() - started)
        return QuickResults(
            entries=[
                QuickHit(
                    kind="entry",
                    id=str(entry.id),
                    title=entry.title,
                    subtitle=entry.entry_type,
                    icon=entry.entry_type,
                )
                for entry in entries
            ],
            projects=[
                QuickHit(
                    kind="project",
                    id=str(project.id),
                    title=project.name,
                    subtitle=project.description,
                    icon=project.icon,
                )
                for project in projects
            ],
            tags=[
                QuickHit(
                    kind="tag",
                    id=str(tag.id),
                    title=f"#{tag.label}",
                    subtitle=f"{tag.usage_count} élément(s)",
                )
                for tag in tags
            ],
            captures=[
                QuickHit(
                    kind="capture",
                    id=str(capture.id),
                    title=capture.captured_at.strftime("Enregistrement du %d/%m à %H:%M"),
                    subtitle=f"{capture.duration_ms // 1000} s",
                )
                for capture in captures
            ],
        )

    async def suggest_tags(self, prefix: str, *, limit: int = 8) -> list[Tag]:
        result = await self._session.execute(
            select(Tag)
            .where(Tag.normalized.like(f"{prefix.strip().lower()}%"))
            .order_by(Tag.usage_count.desc(), Tag.label)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def by_type(self, entry_type: EntryType, *, limit: int = 50) -> list[Entry]:
        result = await self._session.execute(
            select(Entry)
            .where(Entry.deleted_at.is_(None), Entry.entry_type == entry_type.value)
            .order_by(Entry.occurred_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def entry_ids_for_project(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(Entry.id).where(Entry.project_id == project_id, Entry.deleted_at.is_(None))
        )
        return [row[0] for row in result.all()]
