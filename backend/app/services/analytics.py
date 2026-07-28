"""The analytical layer: star schema build and Parquet export.

Two layers, two jobs (ADR-008 and ADR-010). The normalised tables are the
source of truth and store no derived value. This module rebuilds a star schema
from them by running numbered SQL files in order, and exports the result for
Power BI.

Why the transformations are SQL files and not Python:

  - hand-written, commented SQL is the artefact worth having here. It is the
    part of this repository closest to what the target roles actually require,
    and a reader can judge it without running anything;
  - each file states the *grain* of the table it produces in its header
    comment. A fact table whose grain cannot be stated in one sentence is a
    fact table that will be double-counted;
  - they are portable. Nothing in them is SQLite-specific, which is checked by
    a test, and the one thing that genuinely cannot be written portably —
    generating a calendar — is done here in Python instead.

`dim_date` is built in Python for exactly that reason. Walking a date range in
SQL means `date(d, '+1 day')` in SQLite and `d + interval '1 day'` in Postgres,
and there is no portable spelling. Building it here also lets the dimension
carry a sequential `day_number`, which is what makes every date difference in
the fact tables plain integer arithmetic rather than a dialect problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Phase

# Only tables with these prefixes belong to this layer. `alembic/env.py`
# excludes the same prefixes from autogeneration, so the two mechanisms that
# create tables in this database never fight over one.
STAR_PREFIXES = ("dim_", "fact_")

CALENDAR_START = date(2024, 1, 1)
CALENDAR_END = date(2036, 12, 31)

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


@dataclass(frozen=True)
class BuildResult:
    tables: dict[str, int]
    build_date: date

    @property
    def total_rows(self) -> int:
        return sum(self.tables.values())


def transformation_files(sql_dir: Path | None = None) -> list[Path]:
    """The numbered SQL files, in the order they must run.

    Sorted by the numeric prefix rather than by filename, so `100_` follows
    `020_` instead of preceding it — which is what a plain string sort would
    do and would break every fact that joins a dimension.
    """
    directory = (sql_dir or get_settings().sql_dir) / "transformations"
    files = [p for p in directory.glob("*.sql")]
    missing_prefix = [p.name for p in files if not re.match(r"^\d{3}_", p.name)]
    if missing_prefix:
        raise ValueError(
            f"transformation files must start with a three-digit order prefix: {missing_prefix}"
        )
    return sorted(files, key=lambda p: (int(p.name[:3]), p.name))


def split_statements(sql: str) -> list[str]:
    """Split a transformation file into executable statements.

    Line comments are stripped *before* splitting on semicolons, not after.
    Splitting first looks simpler and is wrong the moment a comment contains a
    semicolon — which the header comments in these files do, since they
    explain things like "`strftime` in SQLite and `EXTRACT` in Postgres;
    conforming on the date dimension avoids the dialect". The naive version
    then hands the database half a sentence of English and fails with a syntax
    error pointing at a comment.

    Deliberately not a general SQL parser: it does not handle `/* */` blocks or
    semicolons inside string literals, and these files contain neither. If they
    ever do, this needs replacing rather than patching.
    """
    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    return [
        statement.strip()
        for statement in without_comments.split(";")
        if statement.strip()
    ]


def build_dim_date(
    session: Session,
    build_date: date | None = None,
    start: date = CALENDAR_START,
    end: date = CALENDAR_END,
) -> int:
    """Generate the calendar, including the phase each day falls in.

    `is_build_date` marks exactly one row. The fact tables use it to compute
    "how long since" without any date function at all: the snapshot subtracts
    two `day_number` integers.
    """
    build_date = build_date or date.today()
    phase_rows = [
        (p.code, p.name, p.starts_on, p.ends_on)
        for p in session.scalars(select(Phase).order_by(Phase.ordinal))
    ]

    session.execute(text("DROP TABLE IF EXISTS dim_date"))
    session.execute(
        text(
            """
            CREATE TABLE dim_date (
                date_key       INTEGER PRIMARY KEY,
                full_date      DATE    NOT NULL,
                day_number     INTEGER NOT NULL,
                year           INTEGER NOT NULL,
                quarter        INTEGER NOT NULL,
                month          INTEGER NOT NULL,
                day            INTEGER NOT NULL,
                month_name     VARCHAR(16) NOT NULL,
                year_quarter   VARCHAR(8)  NOT NULL,
                year_month     VARCHAR(8)  NOT NULL,
                is_weekday     INTEGER NOT NULL,
                phase_code     VARCHAR(64),
                phase_name     VARCHAR(255),
                is_build_date  INTEGER NOT NULL
            )
            """
        )
    )

    rows = []
    current = start
    while current <= end:
        quarter = (current.month - 1) // 3 + 1
        phase_code = phase_name = None
        for code, name, starts_on, ends_on in phase_rows:
            if starts_on <= current <= ends_on:
                phase_code, phase_name = code, name
                break
        rows.append(
            {
                "date_key": current.year * 10000 + current.month * 100 + current.day,
                "full_date": current,
                "day_number": current.toordinal(),
                "year": current.year,
                "quarter": quarter,
                "month": current.month,
                "day": current.day,
                "month_name": MONTH_NAMES[current.month - 1],
                "year_quarter": f"{current.year}Q{quarter}",
                "year_month": f"{current.year}-{current.month:02d}",
                "is_weekday": 1 if current.weekday() < 5 else 0,
                "phase_code": phase_code,
                "phase_name": phase_name,
                "is_build_date": 1 if current == build_date else 0,
            }
        )
        current += timedelta(days=1)

    session.execute(
        text(
            """
            INSERT INTO dim_date (
                date_key, full_date, day_number, year, quarter, month, day,
                month_name, year_quarter, year_month, is_weekday,
                phase_code, phase_name, is_build_date
            ) VALUES (
                :date_key, :full_date, :day_number, :year, :quarter, :month, :day,
                :month_name, :year_quarter, :year_month, :is_weekday,
                :phase_code, :phase_name, :is_build_date
            )
            """
        ),
        rows,
    )

    if not any(row["is_build_date"] for row in rows):
        raise ValueError(
            f"build date {build_date} falls outside the calendar "
            f"{start}..{end}; widen CALENDAR_START/CALENDAR_END"
        )
    return len(rows)


def build_star(
    session: Session,
    build_date: date | None = None,
    sql_dir: Path | None = None,
) -> BuildResult:
    """Rebuild the whole analytical layer. Idempotent by construction.

    Every transformation drops and recreates its table, so a rebuild is a
    rebuild rather than a migration. Derived data that cannot be regenerated
    from the source is not derived data — it is a second source of truth.
    """
    build_date = build_date or date.today()
    counts: dict[str, int] = {"dim_date": build_dim_date(session, build_date)}

    for path in transformation_files(sql_dir):
        table_name: str | None = None
        for statement in split_statements(path.read_text(encoding="utf-8")):
            session.execute(text(statement))
            match = re.search(r"CREATE TABLE (\w+)", statement, re.IGNORECASE)
            if match:
                table_name = match.group(1)
        if table_name:
            counts[table_name] = (
                session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
            )

    build_views(session, sql_dir)
    session.flush()
    return BuildResult(tables=counts, build_date=build_date)


def view_files(sql_dir: Path | None = None) -> list[Path]:
    """The reporting views, in order. Run after every transformation."""
    directory = (sql_dir or get_settings().sql_dir) / "views"
    if not directory.exists():
        return []
    return sorted(
        (p for p in directory.glob("*.sql") if re.match(r"^\d{3}_", p.name)),
        key=lambda p: (int(p.name[:3]), p.name),
    )


def build_views(session: Session, sql_dir: Path | None = None) -> list[str]:
    """Recreate the reporting views over the star tables.

    Views rather than more tables: they cost nothing to rebuild, they cannot
    drift from the facts underneath them, and they are the contract a Power BI
    report binds to — so the physical tables can be reshaped without breaking
    every visual.
    """
    created: list[str] = []
    for path in view_files(sql_dir):
        for statement in split_statements(path.read_text(encoding="utf-8")):
            session.execute(text(statement))
            match = re.search(r"CREATE VIEW (\w+)", statement, re.IGNORECASE)
            if match:
                created.append(match.group(1))
    session.flush()
    return created


def star_tables(engine: Engine) -> list[str]:
    from sqlalchemy import inspect

    names = inspect(engine).get_table_names()
    return sorted(n for n in names if n.startswith(STAR_PREFIXES))


def export_parquet(
    session: Session,
    engine: Engine,
    exports_dir: Path | None = None,
) -> dict[str, Path]:
    """Write every star table to Parquet for Power BI.

    Parquet rather than CSV because it keeps types. A CSV export turns every
    decimal into a string and every date into a locale argument, and Power BI
    then guesses — which is how a benefit of 1.105,808 becomes 1105808 in one
    report and 1.105808 in another.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "pyarrow is not installed. Run: pip install -e '.[analytics]'"
        ) from exc

    directory = exports_dir or get_settings().exports_dir
    directory.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import inspect

    inspector = inspect(engine)
    written: dict[str, Path] = {}

    for name in star_tables(engine):
        declared = {c["name"]: c["type"] for c in inspector.get_columns(name)}
        result = session.execute(text(f"SELECT * FROM {name}"))
        columns = list(result.keys())
        rows = result.fetchall()

        arrays = []
        for index, column in enumerate(columns):
            values = [
                # Decimal is not a pyarrow type. Float is safe here because
                # this layer is for reporting, not for the ROI model, and the
                # exact values stay in the normalised tables.
                float(row[index]) if isinstance(row[index], Decimal) else row[index]
                for row in rows
            ]
            arrays.append(pa.array(values, type=_arrow_type(declared.get(column), values)))

        path = directory / f"{name}.parquet"
        pq.write_table(pa.table(arrays, names=columns), path)
        written[name] = path
    return written


def _arrow_type(sql_type: object, values: list[object]):  # noqa: ANN202
    """Pick an explicit type for a column pyarrow cannot infer.

    A column whose every value is null infers as pyarrow's `null` type, which
    Power BI will not accept as a measure — a genuinely empty `business_value`
    would arrive as an untyped column and break the report rather than showing
    as blank. Falling back to the database's own declared type keeps an empty
    numeric column numeric.
    """
    import pyarrow as pa

    if any(value is not None for value in values):
        return None  # let pyarrow infer from the data

    rendered = str(sql_type or "").upper()
    if any(token in rendered for token in ("INT", "NUMERIC", "DECIMAL", "FLOAT", "REAL")):
        return pa.float64()
    if "DATE" in rendered or "TIME" in rendered:
        return pa.date32()
    return pa.string()


def drop_star(session: Session, engine: Engine) -> list[str]:
    """Remove the analytical layer. The normalised tables are untouched."""
    from sqlalchemy import inspect

    for view in inspect(engine).get_view_names():
        if view.startswith("v_"):
            session.execute(text(f"DROP VIEW IF EXISTS {view}"))
    dropped = star_tables(engine)
    for name in dropped:
        session.execute(text(f"DROP TABLE IF EXISTS {name}"))
    session.flush()
    return dropped
