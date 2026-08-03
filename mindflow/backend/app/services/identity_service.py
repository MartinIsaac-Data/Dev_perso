"""Mapping a Supabase identity onto a MindFlow account (ADR-029).

Supabase owns authentication; MindFlow owns the account. The bridge is
`app_user.auth_subject`. Provisioning is lazy — the account is created on the
first authenticated call rather than through a webhook, because a webhook that
fails leaves a user who can log in but has nowhere to write.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth.supabase import Claims
from app.infra.db.models.core import Account, AppUser, Subscription
from app.infra.db.session import set_tenant_context
from app.observability.logging import get_logger

log = get_logger("identity")

DEFAULT_PLAN = "free"


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller, as the rest of the application sees it."""

    user_id: uuid.UUID
    account_id: uuid.UUID
    auth_subject: str
    email: str
    timezone: str
    locale: str
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, claims: Claims) -> Principal:
        user = await self._find_by_subject(claims.subject)
        if user is None:
            user = await self._provision(claims)
        return Principal(
            user_id=user.id,
            account_id=user.account_id,
            auth_subject=user.auth_subject,
            email=user.email,
            timezone=user.timezone,
            locale=user.locale,
            role=user.role,
        )

    async def _find_by_subject(self, subject: str) -> AppUser | None:
        result = await self._session.execute(
            select(AppUser).where(AppUser.auth_subject == subject, AppUser.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def _provision(self, claims: Claims) -> AppUser:
        """Create the account, user and free subscription in one transaction."""
        email = claims.email or f"{claims.subject}@users.noreply.mindflow.ai"
        now = datetime.now(UTC)

        # Generate the account id first and post it as the tenant context, so the
        # three inserts below satisfy the ordinary RLS WITH CHECK. This is why
        # provisioning needs no privileged connection.
        account_id = uuid.uuid4()
        await set_tenant_context(self._session, account_id=account_id)

        account = Account(id=account_id, kind="personal", display_name=None)
        user = AppUser(
            id=uuid.uuid4(),
            account_id=account_id,
            auth_subject=claims.subject,
            email=email,
            email_verified_at=now if claims.email else None,
            role="owner",
        )
        subscription = Subscription(
            id=uuid.uuid4(),
            account_id=account_id,
            plan_code=DEFAULT_PLAN,
            status="active",
            seats=1,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )

        self._session.add_all([account, user, subscription])
        try:
            await self._session.flush()
        except IntegrityError:
            # Two concurrent first requests from the same new user. The loser
            # rolls back and reads the winner's row.
            await self._session.rollback()
            existing = await self._find_by_subject(claims.subject)
            if existing is None:
                raise
            return existing

        log.info("identity.provisioned", account_id=str(account_id))
        return user
