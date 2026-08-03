"""Current user and dashboard (API.md §5)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import PrincipalDep, SessionDep, SettingsDep, StorageDep
from app.api.schemas.common import ERROR_RESPONSES, Envelope
from app.api.schemas.entries import DashboardView, MeView
from app.api.v1.entries import entry_view
from app.domain.enums import EntryStatus
from app.services.capture_service import CaptureService
from app.services.entry_service import EntryService

router = APIRouter(responses=ERROR_RESPONSES)


@router.get("/me", summary="Utilisateur courant", response_model=Envelope[MeView])
async def me(principal: PrincipalDep) -> Envelope[MeView]:
    return Envelope(
        data=MeView(
            id=principal.user_id,
            account_id=principal.account_id,
            email=principal.email,
            timezone=principal.timezone,
            locale=principal.locale,
            role=principal.role,
        )
    )


@router.get(
    "/dashboard",
    summary="Tableau de bord : compteurs, échéances proches, quota",
    response_model=Envelope[DashboardView],
)
async def dashboard(
    principal: PrincipalDep,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Envelope[DashboardView]:
    entries = EntryService(session, principal=principal)
    captures = CaptureService(session, principal=principal, storage=storage, settings=settings)

    by_status = await entries.counts_by_status()
    due = await entries.due_soon(limit=10)

    return Envelope(
        data=DashboardView(
            capture_count=await captures.count(),
            entries_by_type=await entries.counts_by_type(),
            entries_by_status=by_status,
            needs_review=by_status.get(EntryStatus.NEEDS_REVIEW.value, 0),
            due_soon=[entry_view(entry, task) for entry, task in due],
            quota=await captures.usage_summary(),
        )
    )
