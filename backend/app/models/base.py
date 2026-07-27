"""Declarative base, shared column types and cross-cutting conventions.

Naming convention
-----------------
Alembic generates migrations by diffing the model metadata against the live
database. Without an explicit naming convention, constraint names are decided
by the backend, they differ between SQLite and Postgres, and autogenerate
starts proposing drop/create churn for constraints that never changed. Fixing
the convention up front is the single cheapest portability decision in this
project.

Enumerations
------------
Closed sets that only change when the code changes (status, severity,
scenario) are VARCHAR columns guarded by a CHECK constraint. Native ENUM types
are a Postgres feature SQLite does not have, and altering one in Postgres is a
migration in its own right. Sets the user can extend at runtime (skill
domains, deliverable types, review criteria) are lookup tables instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, MetaData, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """Row-level audit trail. Present on every table that holds user input."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# --- Shared column types ---------------------------------------------------

# Money is NUMERIC, never FLOAT. A ROI model that a CFO is meant to trust
# cannot round 0.1 + 0.2 to 0.30000000000000004. SQLite has no native decimal
# type, so SQLAlchemy converts on the way in and out; Postgres stores it
# natively. Same Python semantics on both.
Money = Numeric(18, 2)

# Rates, ratios and confidence weights: more precision, smaller magnitude.
Rate = Numeric(9, 6)

Code = String(64)
Label = String(255)


def enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """Build a portable CHECK constraint restricting a column to a value set."""
    rendered = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({rendered})", name=name)


# --- Closed value sets -----------------------------------------------------

SKILL_LEVELS = (0, 1, 2, 3, 4, 5)

DELIVERABLE_STATUSES = ("planned", "in_progress", "published", "abandoned")

IMPORTANCE = ("must_have", "nice_to_have")

CONFIDENCE = ("low", "medium", "high")

ROI_KINDS = ("cost", "benefit")

ROI_CATEGORIES = (
    # costs
    "build",
    "run",
    "license",
    "change_management",
    "hardware",
    # benefits
    "labour_saving",
    "loss_avoidance",
    "revenue_uplift",
    "working_capital",
)

SCENARIOS = ("pessimistic", "base", "optimistic")

REVIEW_PERSONAS = ("cfo", "coo", "cio")

SEVERITIES = ("blocking", "major", "minor")

AGENT_RUN_STATUSES = ("pending", "succeeded", "failed")

PERIODIC_REVIEW_KINDS = ("weekly", "quarterly")

CASE_STATUSES = ("draft", "quantified", "reviewed", "archived")


def zero() -> Decimal:
    return Decimal("0")
