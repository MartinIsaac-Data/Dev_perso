"""The scheduled synchronisation pass, across tenants.

The unit tests cover *when* a connection is due. These cover the part that only
a real database can show: that the job crosses tenants to find the work, enters
a tenant session to do it, records the outcome on the row, and does not attempt
what it must not attempt.

`test_the_job_writes_under_a_tenant_context` is the one worth keeping if the
others were deleted. The job is the only place in the product that iterates over
every account, so it is the only place where a missing tenant context would go
unnoticed: a privileged session reading and a privileged session *writing* look
identical right up until somebody's calendar event lands in somebody else's
account.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.config import Settings
from app.domain.sync import (
    MAX_CONSECUTIVE_FAILURES,
    Direction,
    Provider,
    PullResult,
    SyncConnectorPort,
)
from app.infra.crypto import KeyRing, encrypt
from app.infra.db.models.core import Account, AppUser
from app.infra.db.models.enterprise import IntegrationConnection
from app.infra.db.session import dispose_engine, init_engine, privileged_session
from app.infra.sync.connectors import ConnectorAuthError, ConnectorUnavailableError
from app.workers.scheduled import synchroniser
from app.workers.scheduled.synchroniser import sync_due_connections
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


class StubConnector(SyncConnectorPort):
    """A connector that does what the test tells it to, and records the calls."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.pulls = 0

    async def pull(self, *, cursor: str | None = None) -> PullResult:
        self.pulls += 1
        if self.error is not None:
            raise self.error
        return PullResult(items=[], cursor="cursor-1", incremental=True)

    async def push(self, *, entry, link=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError


@pytest_asyncio.fixture
async def worker(api_settings: Settings, clean_db) -> AsyncIterator[Settings]:  # type: ignore[no-untyped-def]
    await dispose_engine()
    init_engine(api_settings)
    yield api_settings
    await dispose_engine()


async def _tenant(
    settings: Settings,
    *,
    provider: Provider = Provider.GOOGLE_CALENDAR,
    status: str = "active",
    last_sync_at: datetime | None = None,
    failures: int = 0,
    direction: Direction = Direction.PULL,
    last_attempt_ago: timedelta | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """An account with one user and one connection. Returns their identifiers.

    `last_attempt_ago` backdates `updated_at`, which is what the backoff reads
    for a failing connection. It has to be written in raw SQL: the ORM's
    `onupdate` would overwrite any value the mapper set.
    """
    ring = KeyRing.from_settings(settings.token_encryption_keys)
    account_id = uuid.uuid4()
    user_id = uuid.uuid4()
    connection_id = uuid.uuid4()

    async with privileged_session() as session:
        session.add(Account(id=account_id, display_name="Test"))
        session.add(
            AppUser(
                id=user_id,
                account_id=account_id,
                auth_subject=f"stub|{user_id}",
                email=f"{user_id}@example.test",
                timezone="Europe/Paris",
                locale="fr-FR",
                role="owner",
            )
        )
        session.add(
            IntegrationConnection(
                id=connection_id,
                account_id=account_id,
                user_id=user_id,
                provider=provider.value,
                access_token_encrypted=encrypt("token", ring=ring),
                status=status,
                direction=direction.value,
                last_sync_at=last_sync_at,
                consecutive_failures=failures,
            )
        )
        await session.commit()

    if last_attempt_ago is not None:
        async with privileged_session() as session:
            await session.execute(
                text("UPDATE integration_connection SET updated_at = :moment WHERE id = :id"),
                {"moment": datetime.now(UTC) - last_attempt_ago, "id": connection_id},
            )
            await session.commit()
    return account_id, user_id, connection_id


async def _connection(connection_id: uuid.UUID) -> IntegrationConnection:
    async with privileged_session() as session:
        row = (
            await session.execute(
                select(IntegrationConnection).where(IntegrationConnection.id == connection_id)
            )
        ).scalar_one()
        return row


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubConnector:
    """Replaces the real connector so no test ever reaches a provider."""
    connector = StubConnector()
    monkeypatch.setattr(
        "app.services.integration_service.build_connector",
        lambda connection, *, access_token: connector,
    )
    return connector


class TestTheTick:
    async def test_a_never_synced_connection_is_attempted(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        _, _, connection_id = await _tenant(worker)

        attempted = await sync_due_connections(worker)

        assert attempted == 1
        assert stub.pulls == 1
        assert (await _connection(connection_id)).last_sync_at is not None

    async def test_a_recently_synced_connection_is_skipped(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        await _tenant(worker, last_sync_at=datetime.now(UTC))

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0

    async def test_it_crosses_tenants(self, worker: Settings, stub: StubConnector) -> None:
        # The point of the privileged lookup. Three accounts, one tick.
        for _ in range(3):
            await _tenant(worker)

        assert await sync_due_connections(worker) == 3
        assert stub.pulls == 3

    async def test_obsidian_is_never_scheduled(self, worker: Settings, stub: StubConnector) -> None:
        # Not merely refused once attempted — never selected. A pass that exists
        # only to refuse itself is wasted work and a confusing log line.
        await _tenant(worker, provider=Provider.OBSIDIAN, direction=Direction.PUSH)

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0

    async def test_an_expired_grant_is_never_retried(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        # Retrying a revoked grant cannot succeed. Doing it forever burns quota
        # and buries the only fix, which is asking the user to reconnect.
        await _tenant(worker, status="expired")

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0

    async def test_a_connection_past_the_failure_ceiling_is_left_alone(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        await _tenant(worker, failures=MAX_CONSECUTIVE_FAILURES)

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0

    async def test_a_deleted_user_stops_syncing(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        # An OAuth grant is personal. A connection made by somebody who has left
        # must stop working rather than keep syncing on their behalf.
        _, user_id, _ = await _tenant(worker)
        async with privileged_session() as session:
            user = await session.get(AppUser, user_id)
            assert user is not None
            user.deleted_at = datetime.now(UTC)
            await session.commit()

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0


class TestTheTenantContext:
    def test_the_job_writes_under_a_tenant_context(self) -> None:
        """The privileged session may select identifiers; it must not do the work.

        Inspecting source is unusual, and justified for the same reason as
        `test_the_api_always_sets_the_user_context`: the property is one precise
        line, and no functional test distinguishes a job that writes through a
        tenant session from one that writes privileged — both produce the right
        rows on a single-tenant fixture.
        """
        source = inspect.getsource(synchroniser)

        assert "async with tenant_session(str(account_id), user_id=str(user_id))" in source
        # The privileged block exists, and its only statement is the SELECT.
        privileged = source.split("async with privileged_session() as session:")[1]
        assert "session.add" not in privileged
        assert "commit" not in privileged


class TestFailureHandling:
    async def test_a_provider_outage_is_recorded_not_raised(
        self, worker: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = StubConnector(error=ConnectorUnavailableError("service indisponible"))
        monkeypatch.setattr(
            "app.services.integration_service.build_connector",
            lambda connection, *, access_token: connector,
        )
        _, _, connection_id = await _tenant(worker)

        attempted = await sync_due_connections(worker)

        assert attempted == 1
        row = await _connection(connection_id)
        assert row.consecutive_failures == 1
        assert row.status == "active"
        # Not touched: `last_sync_at` means "last time we were in step with the
        # provider", and a failure did not put us there.
        assert row.last_sync_at is None

    async def test_a_revoked_grant_marks_the_connection_expired(
        self, worker: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = StubConnector(error=ConnectorAuthError("jeton révoqué"))
        monkeypatch.setattr(
            "app.services.integration_service.build_connector",
            lambda connection, *, access_token: connector,
        )
        _, _, connection_id = await _tenant(worker)

        await sync_due_connections(worker)

        row = await _connection(connection_id)
        assert row.status == "expired"
        # And the next tick will not pick it up.
        assert await sync_due_connections(worker) == 0

    async def test_repeated_outages_eventually_give_up(
        self, worker: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = StubConnector(error=ConnectorUnavailableError("toujours en panne"))
        monkeypatch.setattr(
            "app.services.integration_service.build_connector",
            lambda connection, *, access_token: connector,
        )
        _, _, connection_id = await _tenant(
            worker,
            failures=MAX_CONSECUTIVE_FAILURES - 1,
            # Past the backoff for five failures, so this tick attempts it.
            last_attempt_ago=timedelta(hours=2),
        )

        # One more failure reaches the ceiling.
        await sync_due_connections(worker)

        row = await _connection(connection_id)
        assert row.consecutive_failures == MAX_CONSECUTIVE_FAILURES
        assert row.status == "error"

    async def test_a_freshly_failed_connection_is_held_back_by_the_backoff(
        self, worker: Settings, stub: StubConnector
    ) -> None:
        # The backoff, seen end to end rather than through `is_due`: a
        # connection that failed a moment ago is not attempted again on the
        # next tick, which is what keeps a bad minute from becoming a ban.
        await _tenant(worker, failures=1, last_attempt_ago=timedelta(seconds=5))

        assert await sync_due_connections(worker) == 0
        assert stub.pulls == 0

    async def test_one_connection_failing_does_not_end_the_tick(
        self, worker: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        healthy = StubConnector()
        calls = {"n": 0}

        def _build(connection, *, access_token):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:
                # A bug in one adapter, not a provider outage: `sync` does not
                # catch this, so only the job's own guard keeps the tick alive.
                raise RuntimeError("adapter exploded")
            return healthy

        monkeypatch.setattr("app.services.integration_service.build_connector", _build)
        await _tenant(worker)
        await _tenant(worker)
        await _tenant(worker)

        attempted = await sync_due_connections(worker)

        # Two of three completed; the broken one did not take the others down.
        assert attempted == 2
        assert healthy.pulls == 2


class TestBounds:
    async def test_a_tick_is_bounded(
        self, worker: Settings, stub: StubConnector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One account with a large backlog must not starve everyone else, and a
        # tick must have a predictable worst case.
        monkeypatch.setattr(synchroniser, "MAX_CONNECTIONS_PER_TICK", 2)
        for _ in range(5):
            await _tenant(worker)

        assert await sync_due_connections(worker) == 2

    async def test_the_stalest_connection_is_served_first(
        self, worker: Settings, stub: StubConnector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(synchroniser, "MAX_CONNECTIONS_PER_TICK", 1)
        now = datetime.now(UTC)
        await _tenant(worker, last_sync_at=now - timedelta(hours=1))
        _, _, stalest = await _tenant(worker, last_sync_at=now - timedelta(days=3))

        await sync_due_connections(worker)

        # A backlog drains in the order that hurts least.
        assert (await _connection(stalest)).last_sync_at > now - timedelta(minutes=1)
