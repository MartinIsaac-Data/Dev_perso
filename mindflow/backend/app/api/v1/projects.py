"""Project endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, status

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas.common import ERROR_RESPONSES, Collection, Envelope
from app.api.schemas.entries import CreateProjectRequest, ProjectView
from app.infra.db.models.core import Project
from app.services.entry_service import ProjectService

router = APIRouter(prefix="/projects", responses=ERROR_RESPONSES)


def _view(project: Project) -> ProjectView:
    return ProjectView(
        id=project.id,
        name=project.name,
        slug=project.slug,
        color=project.color,
        aliases=list(project.aliases),
    )


@router.get("", summary="Lister les projets", response_model=Collection[ProjectView])
async def list_projects(principal: PrincipalDep, session: SessionDep) -> Collection[ProjectView]:
    projects = await ProjectService(session, principal=principal).list_projects()
    return Collection(data=[_view(p) for p in projects])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Créer un projet",
    response_model=Envelope[ProjectView],
)
async def create_project(
    payload: Annotated[CreateProjectRequest, Body()],
    principal: PrincipalDep,
    session: SessionDep,
) -> Envelope[ProjectView]:
    """`aliases` carries the spoken forms ("le client Vinci", "VNC"); the
    extraction pipeline matches project hints against them (AI.md §5.2)."""
    project = await ProjectService(session, principal=principal).create(
        name=payload.name, color=payload.color, aliases=payload.aliases
    )
    return Envelope(data=_view(project))


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Archiver un projet"
)
async def delete_project(
    project_id: uuid.UUID, principal: PrincipalDep, session: SessionDep
) -> None:
    await ProjectService(session, principal=principal).delete(project_id)
