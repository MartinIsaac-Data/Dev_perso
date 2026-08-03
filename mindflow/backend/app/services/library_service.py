"""Tags, projects and saved filters — the user's own filing system.

Grouped into one service because they answer the same question ("how do I
organise my own material?") and share one non-obvious operation: **merge**.
Renaming a tag to one that already exists, or moving every entry off a project
before archiving it, are the operations that make a filing system survivable.
Without them people accumulate `#finance`, `#Finance` and `#financier` and stop
using tags altogether.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ActivityAction
from app.domain.errors import NotFoundError, ValidationError
from app.infra.db.models.core import Entry, EntryTag, Project, SavedFilter, Tag
from app.observability.logging import get_logger
from app.services.activity_service import ActivityService
from app.services.identity_service import Principal

log = get_logger("library")

MAX_SAVED_FILTERS = 30
POSITION_STEP = 100


class TagService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def list_tags(self, *, limit: int = 200, with_counts: bool = True) -> list[Tag]:
        """Tags, most used first.

        `usage_count` is denormalised on the row and recomputed on write rather
        than counted here: the tag list is rendered on every filter bar, and a
        `GROUP BY` over the join table on each render is a needless cost.
        """
        result = await self._session.execute(
            select(Tag)
            .order_by(Tag.pinned_at.desc().nullslast(), Tag.usage_count.desc(), Tag.label)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, tag_id: uuid.UUID) -> Tag:
        tag = await self._session.get(Tag, tag_id)
        if tag is None:
            raise NotFoundError(f"Tag {tag_id} introuvable.")
        return tag

    async def update(
        self,
        tag_id: uuid.UUID,
        *,
        label: str | None = None,
        color: str | None = None,
        pinned: bool | None = None,
    ) -> Tag:
        """Rename or restyle a tag.

        Renaming onto an existing tag *merges* rather than failing on the unique
        constraint. That is what the user means: they are fixing a duplicate.
        """
        from app.services.analysis_mapper import normalise_tag

        tag = await self.get(tag_id)

        if label is not None:
            clean = label.strip().lstrip("#")
            if not clean:
                raise ValidationError("Le libellé ne peut pas être vide.", field="label")
            normalized = normalise_tag(clean)
            existing = (
                await self._session.execute(
                    select(Tag).where(Tag.normalized == normalized, Tag.id != tag.id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return await self.merge(source_id=tag.id, target_id=existing.id)
            tag.label = clean[:60]
            tag.normalized = normalized

        if color is not None:
            tag.color = color or None
        if pinned is not None:
            tag.pinned_at = datetime.now(UTC) if pinned else None

        await self._session.flush()
        return tag

    async def merge(self, *, source_id: uuid.UUID, target_id: uuid.UUID) -> Tag:
        """Move every association from one tag to another, then delete the source.

        The `ON CONFLICT DO NOTHING` matters: an entry carrying *both* tags would
        otherwise violate the composite primary key half-way through the move and
        leave the merge partially applied.
        """
        if source_id == target_id:
            return await self.get(target_id)
        source = await self.get(source_id)
        target = await self.get(target_id)

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        rows = (
            await self._session.execute(
                select(EntryTag.entry_id, EntryTag.account_id, EntryTag.origin).where(
                    EntryTag.tag_id == source.id
                )
            )
        ).all()
        for row in rows:
            await self._session.execute(
                pg_insert(EntryTag)
                .values(
                    entry_id=row.entry_id,
                    tag_id=target.id,
                    account_id=row.account_id,
                    origin=row.origin,
                )
                .on_conflict_do_nothing(index_elements=["entry_id", "tag_id"])
            )

        await self._session.execute(delete(EntryTag).where(EntryTag.tag_id == source.id))
        await self._session.delete(source)
        await self._session.flush()
        await self.recount(target.id)
        log.info("tag.merged", source=str(source_id), target=str(target_id))
        return target

    async def delete(self, tag_id: uuid.UUID) -> None:
        tag = await self.get(tag_id)
        await self._session.execute(delete(EntryTag).where(EntryTag.tag_id == tag.id))
        await self._session.delete(tag)
        await self._session.flush()

    async def recount(self, tag_id: uuid.UUID) -> int:
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(EntryTag)
                    .join(Entry, Entry.id == EntryTag.entry_id)
                    .where(EntryTag.tag_id == tag_id, Entry.deleted_at.is_(None))
                )
            ).scalar_one()
        )
        await self._session.execute(update(Tag).where(Tag.id == tag_id).values(usage_count=total))
        await self._session.flush()
        return total

    async def attach(self, entry_id: uuid.UUID, labels: list[str]) -> list[Tag]:
        """Tag an entry, creating tags as needed."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.services.analysis_mapper import normalise_tag

        attached: list[Tag] = []
        for raw in labels[:20]:
            clean = raw.strip().lstrip("#")
            if not clean:
                continue
            normalized = normalise_tag(clean)
            tag = (
                await self._session.execute(select(Tag).where(Tag.normalized == normalized))
            ).scalar_one_or_none()
            if tag is None:
                tag = Tag(
                    id=uuid.uuid4(),
                    account_id=self._principal.account_id,
                    label=clean[:60],
                    normalized=normalized,
                )
                self._session.add(tag)
                await self._session.flush()
            await self._session.execute(
                pg_insert(EntryTag)
                .values(
                    entry_id=entry_id,
                    tag_id=tag.id,
                    account_id=self._principal.account_id,
                    origin="user",
                )
                .on_conflict_do_nothing(index_elements=["entry_id", "tag_id"])
            )
            attached.append(tag)

        await self._session.flush()
        for tag in attached:
            await self.recount(tag.id)
        return attached

    async def detach(self, entry_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(EntryTag).where(EntryTag.entry_id == entry_id, EntryTag.tag_id == tag_id)
        )
        await self._session.flush()
        await self.recount(tag_id)

    async def labels_for(self, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Tags for many entries in one query — the list screen's N+1 killer."""
        if not entry_ids:
            return {}
        rows = (
            await self._session.execute(
                select(EntryTag.entry_id, Tag.label)
                .join(Tag, Tag.id == EntryTag.tag_id)
                .where(EntryTag.entry_id.in_(entry_ids))
                .order_by(Tag.label)
            )
        ).all()
        grouped: dict[uuid.UUID, list[str]] = {}
        for entry_id, label in rows:
            grouped.setdefault(entry_id, []).append(label)
        return grouped


class SavedFilterService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    async def list_filters(self) -> list[SavedFilter]:
        result = await self._session.execute(
            select(SavedFilter)
            .where(SavedFilter.user_id == self._principal.user_id)
            .order_by(SavedFilter.pinned_at.desc().nullslast(), SavedFilter.position)
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        name: str,
        query: str,
        icon: str | None = None,
        color: str | None = None,
        pinned: bool = False,
    ) -> SavedFilter:
        from app.domain.search_query import parse_query

        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Le nom est obligatoire.", field="name")

        parsed = parse_query(query, timezone=self._principal.timezone)
        if parsed.is_empty:
            # Saving an empty filter creates a shortcut that means "everything",
            # which the user already has.
            raise ValidationError("Ce filtre ne sélectionne rien.", field="query")

        existing = await self.list_filters()
        if len(existing) >= MAX_SAVED_FILTERS:
            raise ValidationError(
                f"Au plus {MAX_SAVED_FILTERS} filtres enregistrés.", field="filters"
            )
        if any(item.name.lower() == clean_name.lower() for item in existing):
            raise ValidationError("Un filtre porte déjà ce nom.", field="name")

        saved = SavedFilter(
            id=uuid.uuid4(),
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            name=clean_name[:60],
            query=query.strip()[:500],
            icon=icon,
            color=color,
            position=(existing[-1].position + POSITION_STEP) if existing else POSITION_STEP,
            pinned_at=datetime.now(UTC) if pinned else None,
        )
        self._session.add(saved)
        await self._session.flush()
        return saved

    async def update(
        self,
        filter_id: uuid.UUID,
        *,
        name: str | None = None,
        query: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        pinned: bool | None = None,
    ) -> SavedFilter:
        saved = await self._session.get(SavedFilter, filter_id)
        if saved is None:
            raise NotFoundError(f"Filtre {filter_id} introuvable.")
        if name is not None:
            clean = name.strip()
            if not clean:
                raise ValidationError("Le nom est obligatoire.", field="name")
            saved.name = clean[:60]
        if query is not None:
            saved.query = query.strip()[:500]
        if icon is not None:
            saved.icon = icon or None
        if color is not None:
            saved.color = color or None
        if pinned is not None:
            saved.pinned_at = datetime.now(UTC) if pinned else None
        await self._session.flush()
        return saved

    async def delete(self, filter_id: uuid.UUID) -> None:
        saved = await self._session.get(SavedFilter, filter_id)
        if saved is None:
            raise NotFoundError(f"Filtre {filter_id} introuvable.")
        await self._session.delete(saved)
        await self._session.flush()

    async def reorder(self, ordered_ids: list[uuid.UUID]) -> list[SavedFilter]:
        filters = {item.id: item for item in await self.list_filters()}
        position = POSITION_STEP
        for filter_id in ordered_ids:
            item = filters.get(filter_id)
            if item is None:
                continue
            item.position = position
            position += POSITION_STEP
        await self._session.flush()
        return await self.list_filters()


class ProjectDetailService:
    """Project operations beyond the create/list/archive of phase 1."""

    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal
        self._activity = ActivityService(session, principal=principal)

    async def get(self, project_id: uuid.UUID) -> Project:
        project = await self._session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"Projet {project_id} introuvable.")
        return project

    async def update(
        self,
        project_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        aliases: list[str] | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> Project:
        from app.services.analysis_mapper import slugify

        project = await self.get(project_id)
        if name is not None:
            clean = name.strip()
            if not clean:
                raise ValidationError("Le nom est obligatoire.", field="name")
            project.name = clean[:120]
            # The slug follows the name: a project renamed "Refonte 2027" whose
            # slug still reads "refonte-2026" breaks `@refonte-2027` in search.
            project.slug = slugify(clean)
        if description is not None:
            project.description = description[:500] or None
        if color is not None:
            project.color = color or None
        if icon is not None:
            project.icon = icon or None
        if aliases is not None:
            project.aliases = [alias.strip() for alias in aliases if alias.strip()][:10]
        if pinned is not None:
            project.pinned_at = datetime.now(UTC) if pinned else None
        if archived is not None:
            project.archived_at = datetime.now(UTC) if archived else None
            self._activity.record(
                ActivityAction.ARCHIVED if archived else ActivityAction.RESTORED,
                project_id=project.id,
                label=project.name,
            )
        await self._session.flush()
        return project

    async def list_projects(self, *, include_archived: bool = False) -> list[Project]:
        query = select(Project).order_by(
            Project.pinned_at.desc().nullslast(), Project.position, Project.name
        )
        if not include_archived:
            query = query.where(Project.archived_at.is_(None))
        return list((await self._session.execute(query)).scalars().all())

    async def entry_counts(self) -> dict[uuid.UUID, tuple[int, int]]:
        """(open, total) per project, in one query."""
        rows = (
            await self._session.execute(
                select(
                    Entry.project_id,
                    func.count().label("total"),
                    func.count(func.nullif(Entry.status, "done")).label("open"),
                )
                .where(Entry.deleted_at.is_(None), Entry.project_id.isnot(None))
                .group_by(Entry.project_id)
            )
        ).all()
        return {row.project_id: (int(row.open), int(row.total)) for row in rows}
