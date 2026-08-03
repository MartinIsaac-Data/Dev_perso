"""Turn a `NoteAnalysis` into rows (AI.md §5).

This is the deterministic half of the pipeline: everything the model was asked
*not* to decide gets decided here — dates, project attachment, tag normalisation,
and whether an entry is confident enough to publish.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analysis import AnalysisIdea, AnalysisNote, AnalysisTask, NoteAnalysis
from app.domain.enums import EntryOrigin, EntryStatus, EntryType, Priority
from app.domain.temporal import ResolvedDate, resolve
from app.infra.db.models.core import Entry, EntryTag, Project, Tag, Task
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("pipeline.mapper")

# Below this, the entry lands in needs_review instead of active. Deliberately a
# product setting, not a constant of nature: too high and the user is asked to
# check everything, too low and they never see the mistakes (AI.md §8.3).
NEEDS_REVIEW_THRESHOLD = 0.65

# Fuzzy project matching. Above this ratio a hint is attached but flagged as a
# suggestion; below it, nothing is attached — guessing is worse than not knowing.
PROJECT_MATCH_THRESHOLD = 0.72


def normalise_tag(label: str) -> str:
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", label.lower().strip())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", stripped).strip("-")[:60]


def slugify(name: str) -> str:
    return normalise_tag(name) or "projet"


@dataclass(slots=True)
class MappedEntries:
    entries: list[Entry]
    tasks: list[Task]
    entry_tags: list[EntryTag]
    needs_review_count: int
    unresolved_dates: list[str]


class AnalysisMapper:
    def __init__(self, session: AsyncSession, *, account_id: uuid.UUID, user_id: uuid.UUID):
        self._session = session
        self._account_id = account_id
        self._user_id = user_id

    async def map(
        self,
        analysis: NoteAnalysis,
        *,
        capture_id: uuid.UUID,
        captured_at: datetime,
        timezone: str,
        ai_run_id: uuid.UUID | None,
    ) -> MappedEntries:
        projects = await self._load_projects()
        tags = await self._ensure_tags(analysis.tags + analysis.categories)

        result = MappedEntries([], [], [], 0, [])

        for item in analysis.tasks:
            entry, task = self._build_task(
                item, capture_id, captured_at, timezone, ai_run_id, projects, result
            )
            result.entries.append(entry)
            result.tasks.append(task)

        for idea in analysis.ideas:
            result.entries.append(
                self._build_simple(
                    idea, EntryType.IDEA, capture_id, captured_at, ai_run_id, projects, result
                )
            )

        for note in analysis.notes:
            result.entries.append(
                self._build_simple(
                    note, note.entry_type, capture_id, captured_at, ai_run_id, projects, result
                )
            )

        # If the model found nothing actionable, the summary still becomes a note:
        # a capture must never vanish into an empty inbox.
        if not result.entries:
            result.entries.append(
                Entry(
                    id=uuid.uuid4(),
                    account_id=self._account_id,
                    user_id=self._user_id,
                    capture_id=capture_id,
                    entry_type=EntryType.NOTE,
                    title=analysis.summary[:300],
                    body=None,
                    status=EntryStatus.ACTIVE,
                    occurred_at=captured_at,
                    origin=EntryOrigin.AI,
                    ai_run_id=ai_run_id,
                    confidence=analysis.overall_confidence,
                )
            )

        for entry in result.entries:
            for tag in tags:
                result.entry_tags.append(
                    EntryTag(
                        entry_id=entry.id,
                        tag_id=tag.id,
                        account_id=self._account_id,
                        origin="ai",
                    )
                )
            metrics.entries_created_total.labels(entry.entry_type, entry.origin).inc()

        return result

    # -- builders ----------------------------------------------------------
    def _build_task(
        self,
        item: AnalysisTask,
        capture_id: uuid.UUID,
        captured_at: datetime,
        timezone: str,
        ai_run_id: uuid.UUID | None,
        projects: list[Project],
        result: MappedEntries,
    ) -> tuple[Entry, Task]:
        entry = self._base_entry(
            title=item.title,
            body=item.body,
            entry_type=EntryType.TASK,
            confidence=item.confidence,
            span=item.source_span,
            capture_id=capture_id,
            captured_at=captured_at,
            ai_run_id=ai_run_id,
            project=self._match_project(item.project_hint, projects),
            result=result,
        )

        resolved = ResolvedDate(expression="")
        if item.due is not None:
            resolved = resolve(item.due.expression, captured_at=captured_at, timezone=timezone)
            if not resolved.resolved:
                result.unresolved_dates.append(item.due.expression)
                log.info(
                    "temporal.unresolved",
                    reason=resolved.unresolved_reason,
                    entry_id=str(entry.id),
                )

        task = Task(
            entry_id=entry.id,
            account_id=self._account_id,
            due_at=resolved.due_at,
            due_precision=resolved.precision.value if resolved.precision else None,
            due_raw_expression=item.due.expression if item.due else None,
            priority=item.priority,
            assignee_label=item.assignee,
            recurrence_rule=resolved.recurrence_rule,
        )
        return entry, task

    def _build_simple(
        self,
        item: AnalysisIdea | AnalysisNote,
        entry_type: EntryType | str,
        capture_id: uuid.UUID,
        captured_at: datetime,
        ai_run_id: uuid.UUID | None,
        projects: list[Project],
        result: MappedEntries,
    ) -> Entry:
        hint = getattr(item, "project_hint", None)
        return self._base_entry(
            title=item.title,
            body=item.body,
            entry_type=EntryType(entry_type),
            confidence=item.confidence,
            span=item.source_span,
            capture_id=capture_id,
            captured_at=captured_at,
            ai_run_id=ai_run_id,
            project=self._match_project(hint, projects),
            result=result,
        )

    def _base_entry(
        self,
        *,
        title: str,
        body: str | None,
        entry_type: EntryType,
        confidence: float,
        span: object,
        capture_id: uuid.UUID,
        captured_at: datetime,
        ai_run_id: uuid.UUID | None,
        project: Project | None,
        result: MappedEntries,
    ) -> Entry:
        needs_review = confidence < NEEDS_REVIEW_THRESHOLD
        if needs_review:
            result.needs_review_count += 1

        return Entry(
            id=uuid.uuid4(),
            account_id=self._account_id,
            user_id=self._user_id,
            capture_id=capture_id,
            project_id=project.id if project else None,
            entry_type=entry_type,
            title=title[:300],
            body=body,
            status=EntryStatus.NEEDS_REVIEW if needs_review else EntryStatus.ACTIVE,
            occurred_at=captured_at,
            origin=EntryOrigin.AI,
            ai_run_id=ai_run_id,
            confidence=confidence,
            source_span_start=getattr(span, "start", None),
            source_span_end=getattr(span, "end", None),
        )

    # -- lookups -----------------------------------------------------------
    async def _load_projects(self) -> list[Project]:
        result = await self._session.execute(select(Project).where(Project.archived_at.is_(None)))
        return list(result.scalars().all())

    def _match_project(self, hint: str | None, projects: list[Project]) -> Project | None:
        """Exact name, then alias, then fuzzy. No match means no attachment —
        a wrong project is worse than none (AI.md §5.2)."""
        if not hint:
            return None
        needle = normalise_tag(hint)
        if not needle:
            return None

        for project in projects:
            if normalise_tag(project.name) == needle:
                return project
        for project in projects:
            if any(normalise_tag(alias) == needle for alias in project.aliases):
                return project

        from difflib import SequenceMatcher

        best: tuple[float, Project | None] = (0.0, None)
        for project in projects:
            ratio = SequenceMatcher(None, needle, normalise_tag(project.name)).ratio()
            if ratio > best[0]:
                best = (ratio, project)
        if best[0] >= PROJECT_MATCH_THRESHOLD:
            return best[1]
        return None

    async def _ensure_tags(self, labels: list[str]) -> list[Tag]:
        wanted = {normalise_tag(label): label.strip() for label in labels if label.strip()}
        wanted.pop("", None)
        if not wanted:
            return []

        existing = await self._session.execute(select(Tag).where(Tag.normalized.in_(list(wanted))))
        tags = {tag.normalized: tag for tag in existing.scalars().all()}

        for normalized, label in wanted.items():
            if normalized in tags:
                tags[normalized].usage_count += 1
                continue
            tag = Tag(
                id=uuid.uuid4(),
                account_id=self._account_id,
                label=label[:60],
                normalized=normalized,
                usage_count=1,
            )
            self._session.add(tag)
            tags[normalized] = tag

        await self._session.flush()
        return list(tags.values())


def overall_priority(analysis: NoteAnalysis) -> Priority:
    """The capture's priority is the highest of its tasks, else what the model
    reported for the capture as a whole."""
    order = [Priority.LOW, Priority.NORMAL, Priority.HIGH, Priority.URGENT]
    priorities = [Priority(task.priority) for task in analysis.tasks]
    if not priorities:
        return Priority(analysis.priority)
    return max(priorities, key=order.index)
