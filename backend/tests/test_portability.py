"""Portability and migration integrity.

The stated constraint is: SQLite locally, but a schema Postgres would accept
unchanged. That promise is worth nothing unless something checks it, because
the failure mode is silent — everything works on the laptop, and the first
attempt to move to Postgres, years later, turns into a rewrite.

The second test here is the one that catches the most common real bug in an
Alembic project: a model changed, the migration was never regenerated, and the
two drift apart until a fresh install produces a different database from an
upgraded one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.schema import CreateTable

from app.config import REPO_ROOT
from app.models import Base

# Types and constructs that exist in SQLite and have no direct Postgres
# equivalent, or that behave differently enough to break a migration.
FORBIDDEN_TYPE_FRAGMENTS = (
    "AUTOINCREMENT",  # SQLite-specific; Postgres uses sequences/identity
    "UNSIGNED",
    "BLOB SUB_TYPE",
)


class TestSchemaPortability:
    def test_no_sqlite_specific_constructs_in_ddl(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        for table in Base.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(engine)).upper()
            for fragment in FORBIDDEN_TYPE_FRAGMENTS:
                assert fragment not in ddl, f"{table.name} uses {fragment}"

    def test_schema_compiles_against_postgresql_dialect(self) -> None:
        """Compile every table for Postgres without a server.

        `create_engine` with a postgresql URL does not connect until used, so
        this exercises the dialect's DDL compiler on the real metadata. A type
        Postgres cannot render raises here.
        """
        pytest.importorskip(
            "psycopg", reason="install the 'postgres' extra to run the portability check"
        )
        engine = create_engine("postgresql+psycopg://user:pw@localhost/none")
        for table in Base.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(engine))
            assert ddl.strip().upper().startswith("CREATE TABLE")

    def test_every_table_has_a_primary_key(self) -> None:
        for table in Base.metadata.sorted_tables:
            assert table.primary_key.columns, f"{table.name} has no primary key"

    def test_every_constraint_is_named(self) -> None:
        """Unnamed constraints cannot be dropped in a later migration.

        On SQLite the backend invents a name; on Postgres it invents a
        different one. A migration that needs to drop one then works on one
        backend and fails on the other.
        """
        unnamed: list[str] = []
        for table in Base.metadata.sorted_tables:
            for constraint in table.constraints:
                # Primary keys are named by the convention automatically.
                if constraint.name is None:
                    unnamed.append(f"{table.name}.{type(constraint).__name__}")
        assert not unnamed, f"unnamed constraints: {unnamed}"


class TestMigrationsMatchModels:
    def test_upgrade_head_reproduces_the_model_metadata(self, tmp_path: Path) -> None:
        """Run the real migrations, then diff against the models.

        An empty diff means `alembic upgrade head` on a fresh database and
        `Base.metadata.create_all` produce the same schema — which is exactly
        the guarantee that stops a fresh install and an upgraded install from
        diverging.
        """
        db_path = tmp_path / "migrated.db"
        url = f"sqlite+pysqlite:///{db_path}"

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env={"TOS_DATABASE_URL": url, "PATH": "/usr/bin:/bin:/usr/local/bin"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

        engine = create_engine(url)
        try:
            diff = _metadata_differences(engine)
        finally:
            engine.dispose()
        assert not diff, "models and migrations have drifted:\n  " + "\n  ".join(diff)


def _metadata_differences(engine: Engine) -> list[str]:
    """Compare table and column names between the database and the models.

    Deliberately structural rather than using Alembic's own comparison: the
    aim is to catch a forgotten migration, and comparing names catches that
    without the false positives type comparison produces on SQLite.
    """
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    expected_tables = set(Base.metadata.tables)

    differences: list[str] = []
    for missing in sorted(expected_tables - actual_tables):
        differences.append(f"table missing from migrations: {missing}")
    for extra in sorted(actual_tables - expected_tables):
        differences.append(f"table in database but not in models: {extra}")

    for name in sorted(expected_tables & actual_tables):
        actual_columns = {c["name"] for c in inspector.get_columns(name)}
        expected_columns = set(Base.metadata.tables[name].columns.keys())
        for missing in sorted(expected_columns - actual_columns):
            differences.append(f"{name}.{missing} missing from migrations")
        for extra in sorted(actual_columns - expected_columns):
            differences.append(f"{name}.{extra} in database but not in models")
    return differences
