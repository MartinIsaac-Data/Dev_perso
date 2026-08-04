"""Audit partition maintenance (ADR-059).

`audit_log` is partitioned by month, and an insert into a range with no
partition **fails**. That makes this the only job in the product whose absence
has a *date* rather than a gradual degradation: everything works until the first
of a month, then every audit write raises at once.

The SQL functions live in the database precisely so that they work when this
worker is down. This job is the thing that calls them on a schedule — the two
are complementary, not redundant: a function nobody calls protects nothing.

**Why it re-checks rather than tracking state.** `ensure_audit_partitions` is
idempotent and cheap, so the job simply asks every day. A job that remembered
what it had already created would be wrong the first time somebody restored a
backup from before those partitions existed.

**Retention is opt-in.** `audit_retention_months` defaults to zero and the drop
is skipped. Deleting audit history because nobody set a retention policy is a
worse failure than a table that grows: the second is visible on a dashboard, the
first is discovered when an auditor asks for last year.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

from app.config import Settings
from app.infra.db.session import privileged_session
from app.observability import metrics
from app.observability.logging import get_logger

log = get_logger("worker.partitioner")


def _retention_cutoff(today: date, months: int) -> date:
    """First day of the month `months` before `today`'s month.

    Computed by walking months rather than subtracting days, because
    `timedelta(days=30 * n)` drifts and would eventually drop a month early —
    which, for a `DROP TABLE`, is not a rounding error.
    """
    year, month = today.year, today.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


async def maintain_audit_partitions(settings: Settings) -> int:
    """Create upcoming partitions, then apply retention. Returns partitions created."""
    created = 0
    dropped = 0

    async with privileged_session() as session:
        created = int(
            (
                await session.execute(
                    text("SELECT ensure_audit_partitions(:months)"),
                    {"months": settings.audit_partition_months_ahead},
                )
            ).scalar_one()
        )

        if settings.audit_retention_months > 0:
            cutoff = _retention_cutoff(datetime.now(UTC).date(), settings.audit_retention_months)
            dropped = int(
                (
                    await session.execute(
                        text("SELECT drop_audit_partitions_before(:cutoff)"),
                        {"cutoff": cutoff},
                    )
                ).scalar_one()
            )

        # Read back rather than trust the return value. The gauge is what an
        # alert fires on, and it should reflect the database, not this job's
        # opinion of it.
        total = int(
            (
                await session.execute(
                    text(
                        "SELECT count(*) FROM pg_class c "
                        "JOIN pg_inherits i ON i.inhrelid = c.oid "
                        "JOIN pg_class p ON p.oid = i.inhparent "
                        "WHERE p.relname = 'audit_log'"
                    )
                )
            ).scalar_one()
        )
        next_month = (datetime.now(UTC).replace(day=1) + timedelta(days=32)).strftime("%Y%m")
        gap = not bool(
            (
                await session.execute(
                    text("SELECT 1 FROM pg_class WHERE relname = :name"),
                    {"name": f"audit_log_{next_month}"},
                )
            ).scalar_one_or_none()
        )

    metrics.audit_partitions.set(total)
    metrics.audit_partition_gap.set(1 if gap else 0)

    if gap:
        # Reaching here means the creation ran and next month is still missing,
        # which is not a backlog — it is a broken function or a permission
        # problem, and it will take the audit log down on the 1st.
        log.error("partitioner.gap_remains", next_month=next_month, partitions=total)
    elif created or dropped:
        log.info("partitioner.done", created=created, dropped=dropped, partitions=total)

    return created
