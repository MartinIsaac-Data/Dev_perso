"""The Timeline: recording what happened, in the user's own terms.

Every feature in phase 2 writes here, which is exactly why it is one small
service rather than an `INSERT` scattered across six others. Two properties are
worth holding on to:

* **Recording never fails a mutation.** If the timeline write raised, completing
  a task would fail because its *history* could not be written — an absurd
  trade. The recorder is best-effort by construction: it adds to the session and
  lets the caller's transaction carry it.
* **The label is denormalised at write time.** A timeline that goes blank when
  its subject is deleted is not a history; "you deleted *Rappeler le DAF*" has
  to survive the row it refers to.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ActivityAction
from app.infra.db.models.core import ActivityEvent
from app.services.identity_service import Principal

MAX_PAGE = 200


class ActivityService:
    def __init__(self, session: AsyncSession, *, principal: Principal) -> None:
        self._session = session
        self._principal = principal

    def record(
        self,
        action: ActivityAction,
        *,
        entry_id: uuid.UUID | None = None,
        capture_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        label: str | None = None,
        actor_type: str = "user",
        detail: dict[str, Any] | None = None,
    ) -> ActivityEvent:
        """Add an event to the current transaction.

        Synchronous on purpose: it must commit or roll back with the change it
        describes. A timeline that records a completion the transaction later
        abandoned is worse than no timeline.
        """
        event = ActivityEvent(
            account_id=self._principal.account_id,
            user_id=self._principal.user_id,
            entry_id=entry_id,
            capture_id=capture_id,
            project_id=project_id,
            action=action.value,
            subject_label=(label or "")[:300] or None,
            actor_type=actor_type,
            detail=detail or {},
        )
        self._session.add(event)
        return event

    async def list_events(
        self,
        *,
        entry_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        actions: list[ActivityAction] | None = None,
        since: datetime | None = None,
        before: datetime | None = None,
        limit: int = 50,
    ) -> list[ActivityEvent]:
        query: Select[tuple[ActivityEvent]] = (
            select(ActivityEvent)
            .order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
            .limit(min(limit, MAX_PAGE))
        )
        if entry_id is not None:
            query = query.where(ActivityEvent.entry_id == entry_id)
        if project_id is not None:
            query = query.where(ActivityEvent.project_id == project_id)
        if actions:
            query = query.where(ActivityEvent.action.in_([a.value for a in actions]))
        if since is not None:
            query = query.where(ActivityEvent.occurred_at >= since)
        if before is not None:
            query = query.where(ActivityEvent.occurred_at < before)
        return list((await self._session.execute(query)).scalars().all())
