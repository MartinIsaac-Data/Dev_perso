"""Audit partition maintenance, against a real partitioned table.

This is the one job in the product whose failure mode is dated: an insert into a
range with no partition raises, so a month arriving unprepared takes the audit
log down entirely, at midnight, with no prior symptom.

`test_an_insert_into_an_unpartitioned_range_fails` is therefore the most
important test in this file. It does not test our code — it pins the PostgreSQL
behaviour the whole design is a reaction to. If a future PostgreSQL silently
routed such a row somewhere, half of ADR-059 would be unnecessary, and we would
want a test to tell us rather than discover it by reading release notes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.config import Settings
from app.infra.db.session import dispose_engine, init_engine, privileged_session
from app.observability import metrics
from app.workers.scheduled.partitioner import _retention_cutoff, maintain_audit_partitions
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

_PARTITIONS = (
    "SELECT c.relname FROM pg_class c "
    "JOIN pg_inherits i ON i.inhrelid = c.oid "
    "JOIN pg_class p ON p.oid = i.inhparent "
    "WHERE p.relname = 'audit_log' ORDER BY c.relname"
)


@pytest_asyncio.fixture
async def worker(api_settings: Settings) -> AsyncIterator[Settings]:
    """The engine a scheduled job runs on — no HTTP client, no tenant context."""
    await dispose_engine()
    init_engine(api_settings)
    yield api_settings
    await dispose_engine()


async def _partitions() -> list[str]:
    async with privileged_session() as session:
        return list((await session.execute(text(_PARTITIONS))).scalars())


async def _drop(name: str) -> None:
    async with privileged_session() as session:
        await session.execute(text(f"DROP TABLE IF EXISTS {name}"))
        await session.commit()


async def _create_ancient_partition() -> None:
    async with privileged_session() as session:
        await session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS audit_log_201801 PARTITION OF audit_log "
                "FOR VALUES FROM ('2018-01-01') TO ('2018-02-01')"
            )
        )
        await session.commit()


def _month_key(offset_months: int) -> str:
    cursor = datetime.now(UTC).replace(day=1)
    for _ in range(offset_months):
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return cursor.strftime("%Y%m")


class TestCreation:
    async def test_the_job_creates_the_months_ahead_that_are_configured(
        self, worker: Settings
    ) -> None:
        await maintain_audit_partitions(
            worker.model_copy(update={"audit_partition_months_ahead": 4})
        )

        names = await _partitions()
        # Month 0 through month 4 inclusive: the function's loop is `0..n`.
        for offset in range(5):
            assert f"audit_log_{_month_key(offset)}" in names

    async def test_running_it_twice_creates_nothing_the_second_time(self, worker: Settings) -> None:
        await maintain_audit_partitions(worker)
        before = await _partitions()

        created = await maintain_audit_partitions(worker)

        assert created == 0
        assert await _partitions() == before

    async def test_it_closes_a_gap_left_by_a_worker_that_was_down(self, worker: Settings) -> None:
        """The case the job exists for: nobody ran it across a month boundary."""
        await maintain_audit_partitions(worker)
        missing = f"audit_log_{_month_key(1)}"
        await _drop(missing)
        assert missing not in await _partitions()

        created = await maintain_audit_partitions(worker)

        assert created >= 1
        assert missing in await _partitions()


class TestTheFailureItPrevents:
    async def test_an_insert_into_an_unpartitioned_range_fails(self, worker: Settings) -> None:
        """Pins the PostgreSQL behaviour that makes this job load-bearing."""
        async with privileged_session() as session:
            # Broad on purpose: the driver wraps the PostgreSQL error, and pinning the
            # asyncpg class here would make the test about the driver.
            with pytest.raises(Exception) as caught:
                await session.execute(
                    text(
                        "INSERT INTO audit_log (actor_type, action, occurred_at) "
                        "VALUES ('system', 'test.probe', :when)"
                    ),
                    {"when": datetime(2019, 1, 15, tzinfo=UTC)},
                )
            await session.rollback()

        assert "partition" in str(caught.value).lower()

    async def test_an_insert_into_a_prepared_range_succeeds(self, worker: Settings) -> None:
        await maintain_audit_partitions(worker)

        async with privileged_session() as session:
            await session.execute(
                text(
                    "INSERT INTO audit_log (actor_type, action, occurred_at) "
                    "VALUES ('system', 'test.probe', :when)"
                ),
                {"when": datetime.now(UTC)},
            )
            await session.rollback()


class TestRetention:
    async def test_retention_is_off_by_default(self, worker: Settings) -> None:
        """Dropping audit history because nobody configured it is the worse failure."""
        assert worker.audit_retention_months == 0
        await maintain_audit_partitions(worker)
        await _create_ancient_partition()

        await maintain_audit_partitions(worker)

        assert "audit_log_201801" in await _partitions()
        await _drop("audit_log_201801")

    async def test_configured_retention_drops_older_partitions(self, worker: Settings) -> None:
        settings = worker.model_copy(update={"audit_retention_months": 12})
        await maintain_audit_partitions(settings)
        await _create_ancient_partition()

        await maintain_audit_partitions(settings)

        assert "audit_log_201801" not in await _partitions()

    async def test_retention_never_drops_the_current_month(self, worker: Settings) -> None:
        await maintain_audit_partitions(worker.model_copy(update={"audit_retention_months": 1}))

        assert f"audit_log_{_month_key(0)}" in await _partitions()


class TestTheGauges:
    async def test_the_gap_gauge_is_zero_once_the_job_has_run(self, worker: Settings) -> None:
        await maintain_audit_partitions(worker)

        assert metrics.audit_partition_gap._value.get() == 0
        assert metrics.audit_partitions._value.get() >= 1

    async def test_the_gap_gauge_reports_the_database_not_the_job(self, worker: Settings) -> None:
        """Read back from pg_class, so a creation that silently did nothing shows."""
        await maintain_audit_partitions(worker)
        await _drop(f"audit_log_{_month_key(1)}")

        # Zero months ahead: only the current month is created, so the gap
        # survives the run and the gauge must report it rather than the intent.
        await maintain_audit_partitions(
            worker.model_copy(update={"audit_partition_months_ahead": 0})
        )
        assert metrics.audit_partition_gap._value.get() == 1

        await maintain_audit_partitions(worker)
        assert metrics.audit_partition_gap._value.get() == 0


class TestRetentionCutoff:
    """Walking months rather than subtracting days. For a DROP, drift is not rounding."""

    @pytest.mark.parametrize(
        ("today", "months", "expected"),
        [
            (date(2026, 8, 3), 12, date(2025, 8, 1)),
            (date(2026, 1, 31), 1, date(2025, 12, 1)),
            (date(2026, 3, 15), 3, date(2025, 12, 1)),
            (date(2026, 1, 1), 24, date(2024, 1, 1)),
            (date(2026, 12, 31), 6, date(2026, 6, 1)),
        ],
    )
    def test_the_cutoff_lands_on_the_first_of_the_right_month(
        self, today: date, months: int, expected: date
    ) -> None:
        assert _retention_cutoff(today, months) == expected

    def test_a_year_of_retention_never_lands_early(self) -> None:
        """`timedelta(days=365)` would; this is the reason the helper exists."""
        for month in range(1, 13):
            assert _retention_cutoff(date(2026, month, 1), 12) == date(2025, month, 1)
