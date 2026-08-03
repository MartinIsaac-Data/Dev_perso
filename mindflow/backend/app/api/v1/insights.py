"""Search, statistics, history and the library (API.md §5.6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.api.schemas.planning import (
    ActivityView,
    AttachTagsRequest,
    BreakdownView,
    CreateSavedFilterRequest,
    DailyPointView,
    MergeTagRequest,
    ParsedQueryView,
    ProjectDetailView,
    QuickHitView,
    QuickSearchResponse,
    ReorderRequest,
    SavedFilterView,
    SearchHitView,
    SearchResponse,
    StatisticsResponse,
    StreakView,
    TagView,
    UpdateProjectRequest,
    UpdateSavedFilterRequest,
    UpdateTagRequest,
)
from app.api.v1.entries import entry_view
from app.domain.enums import ActivityAction
from app.infra.db.models.core import ActivityEvent, Project, SavedFilter, Tag
from app.services.activity_service import ActivityService
from app.services.analytics_service import AnalyticsService, Breakdown
from app.services.library_service import ProjectDetailService, SavedFilterService, TagService
from app.services.search_service import QuickHit, SearchService

router = APIRouter(responses=ERROR_RESPONSES)


def _breakdown(item: Breakdown) -> BreakdownView:
    return BreakdownView(
        key=item.key,
        label=item.label,
        total=item.total,
        done=item.done,
        completion_rate=item.completion_rate,
        color=item.color,
    )


def _quick(hit: QuickHit) -> QuickHitView:
    return QuickHitView(
        kind=hit.kind, id=hit.id, title=hit.title, subtitle=hit.subtitle, icon=hit.icon
    )


def _tag_view(tag: Tag) -> TagView:
    return TagView(
        id=tag.id,
        label=tag.label,
        normalized=tag.normalized,
        usage_count=tag.usage_count,
        color=tag.color,
        pinned=tag.pinned_at is not None,
    )


def _filter_view(item: SavedFilter) -> SavedFilterView:
    return SavedFilterView(
        id=item.id,
        name=item.name,
        query=item.query,
        icon=item.icon,
        color=item.color,
        position=item.position,
        pinned=item.pinned_at is not None,
    )


def _activity_view(event: ActivityEvent) -> ActivityView:
    return ActivityView(
        id=event.id,
        action=ActivityAction(event.action),
        entry_id=event.entry_id,
        capture_id=event.capture_id,
        project_id=event.project_id,
        subject_label=event.subject_label,
        actor_type=event.actor_type,
        detail=event.detail,
        occurred_at=event.occurred_at,
    )


def _project_view(project: Project, counts: tuple[int, int]) -> ProjectDetailView:
    return ProjectDetailView(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        color=project.color,
        icon=project.icon,
        aliases=list(project.aliases),
        pinned=project.pinned_at is not None,
        archived=project.archived_at is not None,
        open_count=counts[0],
        total_count=counts[1],
    )


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
@router.get(
    "/search",
    summary="Recherche plein texte avec filtres",
    response_model=Envelope[SearchResponse],
)
async def search(
    principal: PrincipalDep,
    session: SessionDep,
    q: Annotated[str, Query(description="Texte libre et filtres : is:task p:high #finance")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> Envelope[SearchResponse]:
    """One box, one grammar (`domain.search_query`).

    Free text is ranked against the `search_vector` generated column, so cost is
    logarithmic in the corpus rather than linear. Filters alone (`is:task
    p:high`) return chronological order: ranking a pure filter by relevance
    would shuffle it for no reason.

    Unrecognised tokens are treated as free text and never rejected — a search
    box that refuses input is a search box people stop using. Filter *values*
    that name nothing are reported back in `query.ignored` so the interface can
    say so instead of silently returning everything.
    """
    results = await SearchService(session, principal=principal).search(
        q, limit=limit, offset=offset
    )
    parsed = results.query
    return Envelope(
        data=SearchResponse(
            query=ParsedQueryView(
                text=parsed.text,
                types=parsed.types,
                statuses=parsed.statuses,
                priorities=parsed.priorities,
                tags=parsed.tags,
                projects=parsed.projects,
                overdue=parsed.overdue,
                recurring=parsed.recurring,
                pinned=parsed.pinned,
                ignored=parsed.ignored,
            ),
            hits=[
                SearchHitView(
                    entry=entry_view(hit.entry, hit.task), rank=hit.rank, snippet=hit.snippet
                )
                for hit in results.hits
            ],
            total=results.total,
            took_ms=results.took_ms,
        )
    )


@router.get(
    "/search/quick",
    summary="Recherche rapide (palette de commandes)",
    response_model=Envelope[QuickSearchResponse],
)
async def quick_search(
    principal: PrincipalDep,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> Envelope[QuickSearchResponse]:
    """The ⌘K palette: a few results across several kinds, fast.

    Prefix matching rather than the full-text index, because a palette has to
    answer while the word is still being typed and `to_tsquery` does not match
    half a word.
    """
    results = await SearchService(session, principal=principal).quick(q)
    return Envelope(
        data=QuickSearchResponse(
            entries=[_quick(hit) for hit in results.entries],
            projects=[_quick(hit) for hit in results.projects],
            tags=[_quick(hit) for hit in results.tags],
            captures=[_quick(hit) for hit in results.captures],
        )
    )


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
@router.get(
    "/stats",
    summary="Tableau de bord analytique",
    response_model=Envelope[StatisticsResponse],
)
async def statistics(
    principal: PrincipalDep,
    session: SessionDep,
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> Envelope[StatisticsResponse]:
    """Report, do not flatter.

    The response deliberately includes the uncomfortable numbers —
    `correction_rate`, `captures_without_entries`, `tasks_overdue` — because
    those are the ones that say whether the product is working. A dashboard that
    counts only successes teaches nothing.
    """
    stats = await AnalyticsService(session, principal=principal).statistics(window_days=window_days)
    return Envelope(
        data=StatisticsResponse(
            window_days=stats.window_days,
            start=stats.start,
            end=stats.end,
            captures=stats.captures,
            entries_created=stats.entries_created,
            tasks_completed=stats.tasks_completed,
            tasks_open=stats.tasks_open,
            tasks_overdue=stats.tasks_overdue,
            completion_rate=stats.completion_rate,
            median_completion_hours=stats.median_completion_hours,
            by_type=[_breakdown(item) for item in stats.by_type],
            by_priority=[_breakdown(item) for item in stats.by_priority],
            by_project=[_breakdown(item) for item in stats.by_project],
            top_tags=[_breakdown(item) for item in stats.top_tags],
            daily=[
                DailyPointView(
                    day=point.day,
                    created=point.created,
                    completed=point.completed,
                    captured=point.captured,
                )
                for point in stats.daily
            ],
            streak=StreakView(
                current=stats.streak.current,
                longest=stats.streak.longest,
                last_active_day=stats.streak.last_active_day,
            ),
            corrections=stats.corrections,
            correction_rate=stats.correction_rate,
            captures_without_entries=stats.captures_without_entries,
            needs_review=stats.needs_review,
            ai_cost_micro_eur=stats.ai_cost_micro_eur,
            busiest_hour=stats.busiest_hour,
        )
    )


# --------------------------------------------------------------------------- #
# History / Timeline
# --------------------------------------------------------------------------- #
@router.get(
    "/activity",
    summary="Historique : ce qui s'est passé, dans les termes de l'utilisateur",
    response_model=Collection[ActivityView],
)
async def activity(
    principal: PrincipalDep,
    session: SessionDep,
    entry_id: Annotated[uuid.UUID | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    before: Annotated[datetime | None, Query(description="Curseur : occurred_at")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Collection[ActivityView]:
    """Distinct from `audit_log`, which answers a security question, and from
    `correction_event`, which measures model quality. This one answers "what
    happened to my task?" and its vocabulary is chosen for that."""
    events = await ActivityService(session, principal=principal).list_events(
        entry_id=entry_id, project_id=project_id, before=before, limit=limit
    )
    return Collection(data=[_activity_view(event) for event in events])


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
@router.get("/tags", summary="Lister les tags", response_model=Collection[TagView])
async def list_tags(principal: PrincipalDep, session: SessionDep) -> Collection[TagView]:
    tags = await TagService(session, principal=principal).list_tags()
    return Collection(data=[_tag_view(tag) for tag in tags])


@router.patch(
    "/tags/{tag_id}", summary="Renommer ou styliser un tag", response_model=Envelope[TagView]
)
async def update_tag(
    tag_id: uuid.UUID,
    payload: Annotated[UpdateTagRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[TagView]:
    """Renaming onto an existing tag **merges** into it rather than failing on
    the unique constraint — that is what the user means when they are fixing a
    duplicate like `#Finance` next to `#finance`."""
    tag = await TagService(session, principal=principal).update(
        tag_id, label=payload.label, color=payload.color, pinned=payload.pinned
    )
    return Envelope(data=_tag_view(tag))


@router.post(
    "/tags/{tag_id}/merge", summary="Fusionner deux tags", response_model=Envelope[TagView]
)
async def merge_tags(
    tag_id: uuid.UUID,
    payload: Annotated[MergeTagRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[TagView]:
    tag = await TagService(session, principal=principal).merge(
        source_id=tag_id, target_id=payload.target_id
    )
    return Envelope(data=_tag_view(tag))


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Supprimer un tag")
async def delete_tag(tag_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> None:
    await TagService(session, principal=principal).delete(tag_id)


@router.post(
    "/entries/{entry_id}/tags",
    summary="Ajouter des tags à une entrée",
    response_model=Collection[TagView],
)
async def attach_tags(
    entry_id: uuid.UUID,
    payload: Annotated[AttachTagsRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Collection[TagView]:
    tags = await TagService(session, principal=principal).attach(entry_id, payload.labels)
    return Collection(data=[_tag_view(tag) for tag in tags])


@router.delete(
    "/entries/{entry_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retirer un tag d'une entrée",
)
async def detach_tag(
    entry_id: uuid.UUID, tag_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> None:
    await TagService(session, principal=principal).detach(entry_id, tag_id)


# --------------------------------------------------------------------------- #
# Saved filters
# --------------------------------------------------------------------------- #
@router.get("/filters", summary="Filtres enregistrés", response_model=Collection[SavedFilterView])
async def list_filters(principal: PrincipalDep, session: SessionDep) -> Collection[SavedFilterView]:
    """Stores the *query string*, not a compiled predicate: the grammar is the
    contract, so a filter saved today keeps working when the parser gains a
    keyword tomorrow."""
    filters = await SavedFilterService(session, principal=principal).list_filters()
    return Collection(data=[_filter_view(item) for item in filters])


@router.post(
    "/filters",
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer un filtre",
    response_model=Envelope[SavedFilterView],
)
async def create_filter(
    payload: Annotated[CreateSavedFilterRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[SavedFilterView]:
    saved = await SavedFilterService(session, principal=principal).create(
        name=payload.name,
        query=payload.query,
        icon=payload.icon,
        color=payload.color,
        pinned=payload.pinned,
    )
    return Envelope(data=_filter_view(saved))


@router.patch(
    "/filters/{filter_id}",
    summary="Modifier un filtre enregistré",
    response_model=Envelope[SavedFilterView],
)
async def update_filter(
    filter_id: uuid.UUID,
    payload: Annotated[UpdateSavedFilterRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[SavedFilterView]:
    saved = await SavedFilterService(session, principal=principal).update(
        filter_id,
        name=payload.name,
        query=payload.query,
        icon=payload.icon,
        color=payload.color,
        pinned=payload.pinned,
    )
    return Envelope(data=_filter_view(saved))


@router.delete(
    "/filters/{filter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un filtre enregistré",
)
async def delete_filter(filter_id: uuid.UUID, principal: PrincipalDep, session: SessionDep) -> None:
    await SavedFilterService(session, principal=principal).delete(filter_id)


@router.post(
    "/filters/reorder",
    summary="Réordonner les filtres",
    response_model=Collection[SavedFilterView],
)
async def reorder_filters(
    payload: Annotated[ReorderRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Collection[SavedFilterView]:
    filters = await SavedFilterService(session, principal=principal).reorder(payload.ordered_ids)
    return Collection(data=[_filter_view(item) for item in filters])


# --------------------------------------------------------------------------- #
# Projects (detail beyond phase 1's create/list/archive)
# --------------------------------------------------------------------------- #
@router.get(
    "/projects/detailed",
    summary="Projets avec compteurs",
    response_model=Collection[ProjectDetailView],
)
async def list_projects_detailed(
    principal: PrincipalDep,
    session: SessionDep,
    include_archived: Annotated[bool, Query()] = False,
) -> Collection[ProjectDetailView]:
    service = ProjectDetailService(session, principal=principal)
    projects = await service.list_projects(include_archived=include_archived)
    counts = await service.entry_counts()
    return Collection(
        data=[_project_view(project, counts.get(project.id, (0, 0))) for project in projects]
    )


@router.patch(
    "/projects/{project_id}",
    summary="Modifier un projet",
    response_model=Envelope[ProjectDetailView],
)
async def update_project(
    project_id: uuid.UUID,
    payload: Annotated[UpdateProjectRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[ProjectDetailView]:
    """The slug follows the name. A project renamed "Refonte 2027" whose slug
    still reads `refonte-2026` silently breaks `@refonte-2027` in search."""
    service = ProjectDetailService(session, principal=principal)
    project = await service.update(
        project_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        aliases=payload.aliases,
        pinned=payload.pinned,
        archived=payload.archived,
    )
    counts = await service.entry_counts()
    return Envelope(data=_project_view(project, counts.get(project.id, (0, 0))))


@router.get(
    "/projects/{project_id}/stats",
    summary="Statistiques d'un projet",
    response_model=Envelope[dict[str, object]],
)
async def project_stats(
    project_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> Envelope[dict[str, object]]:
    summary = await AnalyticsService(session, principal=principal).project_summary(project_id)
    return Envelope(data=summary)
