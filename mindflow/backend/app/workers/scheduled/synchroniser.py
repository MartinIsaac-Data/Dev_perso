"""Running integration synchronisations on a schedule, across every tenant.

Until this job existed, « synchronisation automatique » meant a button. The
connectors, the port, the conflict classification and the screen all worked;
nothing pulled the trigger.

Four properties it must have, and each of them is easy to get wrong:

* **It spans tenants, so it runs privileged** (ADR-042) to *find* the work, then
  re-enters a tenant session per account to *do* it. Every write therefore still
  goes through an RLS policy — the privileged connection selects identifiers and
  nothing else.

* **A failing connection must not be retried on every tick.** The delay grows
  exponentially, capped at an hour (`domain.sync.backoff_seconds`), and the
  scheduler gives up entirely after `MAX_CONSECUTIVE_FAILURES`. A provider
  having a bad minute must not be hammered; one having a bad day must not be
  abandoned within it.

* **`expired` is never retried at all.** A revoked OAuth grant cannot recover on
  its own, so retrying it forever burns provider quota and buries the one thing
  that would fix it: asking the user to reconnect (ADR-056).

* **One connection's failure must not end the tick.** `IntegrationService.sync`
  already refuses to raise for provider trouble, but a bug in one adapter must
  not stop the other six.

**On what "due" means for a failing connection.** A successful pass sets
`last_sync_at`; a failed one deliberately does not, because `last_sync_at` means
*last time we were in step with the provider* and a failure did not put us
there. The backoff therefore keys on `updated_at`, which a failed attempt always
writes (it increments `consecutive_failures`). The imprecision is real and worth
stating: any other write to the row — a user changing the direction — also
touches `updated_at` and can delay one retry by up to an hour. That is a
tolerable cost for not adding a column whose only reader would be this line.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import Settings
from app.domain.sync import MAX_CONSECUTIVE_FAILURES, Provider, backoff_seconds
from app.infra.db.models.core import AppUser
from app.infra.db.models.enterprise import IntegrationConnection
from app.infra.db.session import privileged_session, tenant_session
from app.observability.logging import get_logger
from app.services.identity_service import Principal
from app.services.integration_service import IntegrationService

log = get_logger("worker.sync")

# Connections attempted per tick. Bounded so one account with seven providers
# cannot starve everyone else's calendar, and so a tick has a predictable
# worst-case duration.
MAX_CONNECTIONS_PER_TICK = 40

# Providers the server can actually talk to. Obsidian declares
# `is_server_side = False` — it is a folder on somebody's disk — so it is
# filtered out here rather than being scheduled and then refused.
SERVER_SIDE_PROVIDERS: tuple[str, ...] = tuple(
    provider.value for provider in Provider if provider.is_server_side
)


def is_due(
    *,
    last_sync_at: datetime | None,
    updated_at: datetime | None,
    consecutive_failures: int,
    interval_seconds: int,
    now: datetime,
) -> bool:
    """Whether a connection should be attempted on this tick.

    Never synchronised is always due — that is the first pass after connecting,
    and making the user wait five minutes to see anything happen would read as a
    connection that did not work.
    """
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        # The scheduler has given up. Only reconnecting clears this, which
        # resets the counter (`IntegrationService.connect`).
        return False
    if consecutive_failures > 0:
        reference = updated_at or last_sync_at
        if reference is None:
            return True
        return now - reference >= timedelta(seconds=backoff_seconds(consecutive_failures))
    if last_sync_at is None:
        return True
    return now - last_sync_at >= timedelta(seconds=interval_seconds)


async def sync_due_connections(settings: Settings, *, now: datetime | None = None) -> int:
    """Run one pass over every connection that is due. Returns the count attempted."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    candidates = await _due_connections(settings, moment)
    if not candidates:
        return 0

    attempted = 0
    failed = 0

    for account_id, user_id, connection_id, timezone_name, locale, email, role in candidates:
        try:
            # The tenant context carries the user as well as the account: the
            # phase-4 policies read `app.user_id`, and a sync that writes an
            # entry must land under the same visibility rules as the API
            # (ADR-054).
            async with tenant_session(str(account_id), user_id=str(user_id)) as session:
                service = IntegrationService(
                    session,
                    principal=Principal(
                        user_id=user_id,
                        account_id=account_id,
                        auth_subject="",
                        email=email,
                        timezone=timezone_name,
                        locale=locale,
                        role=role,
                    ),
                    settings=settings,
                )
                report = await service.sync(connection_id)
                attempted += 1
                if report.failed:
                    failed += 1
        except Exception:
            # `sync` does not raise for provider trouble, so reaching here is a
            # bug rather than an outage — and one adapter's bug must not cost
            # the other six their tick.
            failed += 1
            log.exception("sync.connection_failed", connection_id=str(connection_id))

    if attempted:
        log.info("sync.tick", attempted=attempted, failed=failed)
    return attempted


async def _due_connections(
    settings: Settings, now: datetime
) -> Sequence[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str, str, str]]:
    """Identifiers of the connections to attempt, newest-stalest first.

    Runs on the privileged connection because it crosses tenants, and selects
    identifiers only: the work itself happens in a tenant session.
    """
    async with privileged_session() as session:
        rows = (
            await session.execute(
                select(
                    IntegrationConnection.account_id,
                    IntegrationConnection.user_id,
                    IntegrationConnection.id,
                    IntegrationConnection.last_sync_at,
                    IntegrationConnection.updated_at,
                    IntegrationConnection.consecutive_failures,
                    AppUser.timezone,
                    AppUser.locale,
                    AppUser.email,
                    AppUser.role,
                )
                .join(AppUser, AppUser.id == IntegrationConnection.user_id)
                .where(
                    # `active` only. `expired` is excluded on purpose: a revoked
                    # grant will never recover on a retry, and retrying it
                    # forever is how an integration generates support load.
                    IntegrationConnection.status == "active",
                    IntegrationConnection.provider.in_(SERVER_SIDE_PROVIDERS),
                    AppUser.deleted_at.is_(None),
                )
                # Stalest first, so a backlog drains in the order that hurts
                # least. NULLs — never synchronised — come first.
                .order_by(IntegrationConnection.last_sync_at.asc().nullsfirst())
                # Fetched wider than the cap because dueness is decided in
                # Python: the backoff depends on the failure count, which SQL
                # would have to express as a CASE nobody could read.
                .limit(MAX_CONNECTIONS_PER_TICK * 4)
            )
        ).all()

    due: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str, str, str]] = []
    for row in rows:
        if not is_due(
            last_sync_at=row.last_sync_at,
            updated_at=row.updated_at,
            consecutive_failures=row.consecutive_failures,
            interval_seconds=settings.sync_interval_seconds,
            now=now,
        ):
            continue
        due.append(
            (row.account_id, row.user_id, row.id, row.timezone, row.locale, row.email, row.role)
        )
        if len(due) >= MAX_CONNECTIONS_PER_TICK:
            break
    return due
