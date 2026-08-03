"""Entry lifecycle (API.md §5.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EntryOrigin, EntryStatus, EntryType, Priority
from app.domain.errors import NotFoundError, ValidationError, VersionConflictError
from app.domain.temporal import resolve
from app.infra.db.models.core import CorrectionEvent, Entry, Project, Task
from app.observability import metrics
from app.observability.logging import get_logger
from app.services.identity_service import Principal

log = get_logger("entry")

# Fields whose correction is a signal about model quality (AI.md §11).
TRACKED_FIELDS = frozenset({"entry_type", "title", "project_id", "due_at", "priority"})


class EntryService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def list_entries(
        self,
        *,
        entry_types: list[EntryType] | None = None,
        statuses: list[EntryStatus] | None = None,
        project_id: uuid.UUID | None = None,
        search: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[Entry]:
        query: Select[tuple[Entry]] = (
            select(Entry)
            .where(Entry.deleted_at.is_(None))
            .order_by(Entry.occurred_at.desc(), Entry.id.desc())
            .limit(min(limit, 200))
        )
        if entry_types:
            query = query.where(Entry.entry_type.in_([t.value for t in entry_types]))
        if statuses:
            query = query.where(Entry.status.in_([s.value for s in statuses]))
        if project_id is not None:
            query = query.where(Entry.project_id == project_id)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(Entry.title.ilike(pattern) | Entry.body.ilike(pattern))
        if before is not None:
            query = query.where(Entry.occurred_at < before)
        return list((await self._session.execute(query)).scalars().all())

    async def get(self, entry_id: uuid.UUID) -> Entry:
        result = await self._session.execute(
            select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None))
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise NotFoundError(f"Entrée {entry_id} introuvable.")
        return entry

    async def create(
        self,
        *,
        entry_type: EntryType,
        title: str,
        body: str | None = None,
        project_id: uuid.UUID | None = None,
        occurred_at: datetime | None = None,
        due_expression: str | None = None,
        priority: Priority = Priority.NORMAL,
    ) -> Entry:
        now = datetime.now(UTC)
        entry = Entry(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            project_id=project_id,
            entry_type=entry_type,
            title=title.strip()[:300],
            body=body,
            status=EntryStatus.ACTIVE,
            occurred_at=occurred_at or now,
            origin=EntryOrigin.USER,
            # Typed by a human: never overwritten by a reprocessing run (ADR-027).
            edited_by_user_at=now,
        )
        self._session.add(entry)
        await self._session.flush()

        if entry_type is EntryType.TASK:
            resolved = resolve(
                due_expression or "", captured_at=now, timezone=self._principal.timezone
            )
            self._session.add(
                Task(
                    entry_id=entry.id,
                    account_id=self._principal.account_id,
                    due_at=resolved.due_at,
                    due_precision=resolved.precision.value if resolved.precision else None,
                    due_raw_expression=due_expression,
                    priority=priority,
                    recurrence_rule=resolved.recurrence_rule,
                )
            )
            await self._session.flush()

        await self._reindex(entry)
        return entry

    async def update(
        self,
        entry_id: uuid.UUID,
        *,
        expected_version: int | None,
        changes: dict[str, object],
    ) -> Entry:
        entry = await self.get(entry_id)

        # Optimistic locking (API.md §8.2). The 409 body carries the server state
        # so the client can merge field by field rather than pick a winner.
        if expected_version is not None and entry.version != expected_version:
            raise VersionConflictError(current_version=entry.version)

        task = await self._session.get(Task, entry_id)
        touched_by_user = False

        for field, value in changes.items():
            if value is None and field not in ("project_id", "body", "due_at"):
                continue

            if field in ("title", "body", "status", "project_id", "entry_type"):
                old = getattr(entry, field)
                if old == value:
                    continue
                if field == "entry_type":
                    self._assert_type_change(EntryType(entry.entry_type), EntryType(str(value)))
                setattr(entry, field, value)
                await self._record_correction(entry, field, old, value)
                touched_by_user = True

            elif field in ("due_expression", "priority", "completed_at", "snoozed_until"):
                if task is None:
                    if EntryType(entry.entry_type) is not EntryType.TASK:
                        raise ValidationError("Ce champ ne s'applique qu'aux tâches.", field=field)
                    task = Task(entry_id=entry.id, account_id=entry.account_id)
                    self._session.add(task)
                if field == "due_expression":
                    resolved = resolve(
                        str(value),
                        captured_at=datetime.now(UTC),
                        timezone=self._principal.timezone,
                    )
                    old_due = task.due_at
                    task.due_at = resolved.due_at
                    task.due_precision = resolved.precision.value if resolved.precision else None
                    task.due_raw_expression = str(value)
                    await self._record_correction(entry, "due_at", old_due, resolved.due_at)
                else:
                    setattr(task, field, value)
                touched_by_user = True

        if touched_by_user:
            entry.edited_by_user_at = datetime.now(UTC)
            if entry.status == EntryStatus.NEEDS_REVIEW:
                entry.status = EntryStatus.ACTIVE

        await self._session.flush()
        await self._session.refresh(entry)
        await self._reindex(entry)
        return entry

    def _assert_type_change(self, current: EntryType, target: EntryType) -> None:
        if current is EntryType.MEETING and target is not EntryType.MEETING:
            raise ValidationError(
                "Un compte-rendu de réunion ne peut pas changer de type.",
                field="entry_type",
            )

    async def transform(self, entry_id: uuid.UUID, target: EntryType) -> Entry:
        entry = await self.get(entry_id)
        if EntryType(entry.entry_type) is target:
            return entry
        return await self.update(
            entry_id, expected_version=None, changes={"entry_type": target.value}
        )

    async def complete(self, entry_id: uuid.UUID) -> Entry:
        entry = await self.get(entry_id)
        if EntryType(entry.entry_type) is not EntryType.TASK:
            raise ValidationError("Seule une tâche peut être terminée.")
        task = await self._session.get(Task, entry_id)
        if task is not None:
            task.completed_at = datetime.now(UTC)
        entry.status = EntryStatus.DONE
        await self._session.flush()
        return entry

    async def delete(self, entry_id: uuid.UUID) -> None:
        entry = await self.get(entry_id)
        entry.deleted_at = datetime.now(UTC)
        await self._session.flush()
        # Soft delete, so the foreign key's CASCADE never fires. Without
        # this the deleted note keeps surfacing in semantic search —
        # visible only to the person who deleted it, which is exactly who
        # will notice.
        from app.services.indexing_service import IndexingService

        await IndexingService(self._session).remove_for_entry(entry_id)

    async def counts_by_status(self) -> dict[str, int]:
        result = await self._session.execute(
            select(Entry.status, func.count())
            .where(Entry.deleted_at.is_(None))
            .group_by(Entry.status)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def counts_by_type(self) -> dict[str, int]:
        result = await self._session.execute(
            select(Entry.entry_type, func.count())
            .where(Entry.deleted_at.is_(None))
            .group_by(Entry.entry_type)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def due_soon(self, *, limit: int = 20) -> list[tuple[Entry, Task]]:
        result = await self._session.execute(
            select(Entry, Task)
            .join(Task, Task.entry_id == Entry.id)
            .where(
                Entry.deleted_at.is_(None),
                Task.completed_at.is_(None),
                Task.due_at.isnot(None),
            )
            .order_by(Task.due_at.asc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def _reindex(self, entry: Entry) -> None:
        """Keep the retrieval index in step with a hand-written entry.

        Chunking only — no provider call, so this is safe on a request path
        (`services.indexing_service` explains the split). Failures are swallowed:
        an entry that saved correctly is a success, and losing its chunks means
        it is missing from semantic search until the next re-index rather than
        losing the note itself.
        """
        from app.services.indexing_service import IndexingService

        try:
            await IndexingService(self._session).index_entry(entry)
        except Exception:
            log.warning("entry.indexing_failed", entry_id=str(entry.id))

    async def _record_correction(self, entry: Entry, field: str, old: object, new: object) -> None:
        """A correction on an AI-produced entry is a quality signal (AI.md §11).

        It feeds offline evaluation only — never online training (I7).
        """
        if field not in TRACKED_FIELDS or entry.origin != EntryOrigin.AI:
            return
        self._session.add(
            CorrectionEvent(
                id=uuid.uuid4(),
                account_id=entry.account_id,
                entry_id=entry.id,
                ai_run_id=entry.ai_run_id,
                field=field,
                old_value=str(old)[:500] if old is not None else None,
                new_value=str(new)[:500] if new is not None else None,
            )
        )
        metrics.entries_corrected_total.labels(field).inc()


class ProjectService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def list_projects(self) -> list[Project]:
        result = await self._session.execute(
            select(Project).where(Project.archived_at.is_(None)).order_by(Project.name)
        )
        return list(result.scalars().all())

    async def create(
        self, *, name: str, color: str | None = None, aliases: list[str] | None = None
    ) -> Project:
        from app.services.analysis_mapper import slugify

        project = Project(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            name=name.strip()[:120],
            slug=slugify(name),
            color=color,
            aliases=aliases or [],
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def delete(self, project_id: uuid.UUID) -> None:
        project = await self._session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"Projet {project_id} introuvable.")
        project.archived_at = datetime.now(UTC)
        await self._session.flush()
