"""Alembic environment.

Two settings below are not Alembic defaults and matter a great deal here:

`render_as_batch=True` — SQLite cannot ALTER a column or drop a constraint.
Batch mode makes Alembic rebuild the table instead (create new, copy, drop,
rename). Without it, the second migration of this project that touches an
existing column fails on the local database and only works in Postgres, which
is the worst possible place to discover the problem.

`compare_type=True` — Alembic ignores column type changes by default. Given
that this schema is meant to move from SQLite to Postgres unchanged, silently
skipping type drift is exactly the failure that would make that move painful.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """Keep the analytical star layer out of Alembic's hands.

    Fact and dimension tables are created and dropped by the SQL
    transformation job in /sql/transformations, not by migrations: they are
    derived data, rebuilt from the normalised tables on demand. Letting
    Alembic autogenerate drops for them would be a constant nuisance.
    """
    if type_ == "table" and (name.startswith("fact_") or name.startswith("dim_")):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "sqlite":
            # Migrations that move rows between tables rely on foreign keys
            # being enforced; the engine built here does not go through
            # app.db, so the pragma has to be set again.
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
