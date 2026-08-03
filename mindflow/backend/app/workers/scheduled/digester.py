"""Generating digests on a schedule, in each user's own evening.

The scheduling problem here is the whole job. A daily digest is worth reading at
21:00 *local* time; a cron running at 21:00 UTC delivers it at midnight in
Libreville and at 14:00 in Los Angeles. So the cron ticks hourly and each tick
asks a different question: **which users are, right now, at their digest hour in
their own timezone?**

That makes the job idempotent by construction rather than by bookkeeping — the
unique constraint on (account, user, period, period_start) means a tick that
fires twice for the same user produces the same row. There is no "already sent"
flag to keep in step with reality.

Weekly digests go out Monday morning, looking back at the week that ended;
monthly on the first of the month. Both use the same local-hour logic, because
"Monday morning" has the same timezone problem as "this evening".
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import Settings
from app.infra.ai.factory import build_chat
from app.infra.db.models.core import AppUser
from app.infra.db.session import privileged_session, tenant_session
from app.observability import metrics
from app.observability.logging import get_logger
from app.prompts.digest import DigestPeriod
from app.services.digest_service import DigestService
from app.services.identity_service import Principal

log = get_logger("worker.digest")

# Local hours at which each digest is produced. The daily one lands in the
# evening, when the day is over and there is something to summarise; the
# periodic ones land in the morning, when the reader is planning.
DAILY_HOUR = 21
WEEKLY_HOUR = 8
MONTHLY_HOUR = 8

MAX_USERS_PER_TICK = 200


async def generate_due_digests(settings: Settings, *, now: datetime | None = None) -> int:
    """Generate every digest whose local hour has just arrived."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    users = await _users()
    if not users:
        return 0

    chat = build_chat(settings)
    produced = 0

    for account_id, user_id, timezone_name in users:
        local = moment.astimezone(_zone(timezone_name))
        due = _due_periods(local)
        if not due:
            continue

        principal = Principal(
            user_id=user_id,
            account_id=account_id,
            auth_subject="",
            email="",
            timezone=timezone_name,
            locale="fr-FR",
            role="owner",
        )
        for period, anchor in due:
            try:
                async with tenant_session(str(account_id)) as session:
                    service = DigestService(session, principal=principal, chat=chat)
                    await service.generate(period, anchor=anchor)
                    produced += 1
            except Exception:
                # One user's failure must not stop the rest of the tick.
                metrics.digests_generated_total.labels(period.value, "failed").inc()
                log.exception("digest.failed", user_id=str(user_id), period=period.value)

    if produced:
        log.info("digest.tick", produced=produced)
    return produced


def _due_periods(local: datetime) -> list[tuple[DigestPeriod, date]]:
    """Which digests this local time calls for.

    Anchors point *backwards*: the daily digest at 21:00 summarises today, while
    Monday's weekly digest summarises the week that just ended, not the one
    starting in an hour.
    """
    due: list[tuple[DigestPeriod, date]] = []
    today = local.date()

    if local.hour == DAILY_HOUR:
        due.append((DigestPeriod.DAILY, today))
    if local.hour == WEEKLY_HOUR and local.weekday() == 0:
        due.append((DigestPeriod.WEEKLY, today - timedelta(days=1)))
    if local.hour == MONTHLY_HOUR and local.day == 1:
        # Any day of the previous month anchors it; the service snaps to the
        # calendar month around it.
        due.append((DigestPeriod.MONTHLY, today - timedelta(days=1)))
    return due


async def _users() -> list[tuple[uuid.UUID, uuid.UUID, str]]:
    """Every active user, with the timezone the schedule is computed in.

    Cross-tenant, so privileged (ADR-042). Note that this is a table the
    `mindflow_maintenance` role could not read before migration 0006 fixed its
    default privileges — the job would have returned zero users, silently, and
    nobody would have received a digest.
    """
    async with privileged_session() as session:
        rows = (
            await session.execute(
                select(AppUser.account_id, AppUser.id, AppUser.timezone)
                .where(AppUser.deleted_at.is_(None))
                .limit(MAX_USERS_PER_TICK)
            )
        ).all()
        return [(row[0], row[1], row[2] or "UTC") for row in rows]


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        # An unknown timezone must not stop the tick for everyone else. UTC is
        # a wrong hour for that user, not a missing digest.
        log.warning("digest.unknown_timezone", timezone=name)
        return ZoneInfo("UTC")
