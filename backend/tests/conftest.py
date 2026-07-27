"""Shared test fixtures.

Tests run against an in-memory SQLite database with `StaticPool`, so every
session in a test shares one connection and the schema survives between them.
Foreign keys are enabled explicitly — without the pragma the constraint tests
would pass by doing nothing, which is the worst kind of green.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import REPO_ROOT
from app.models import Base
from app.services.seeding import seed_demo, seed_reference

SEEDS_DIR = REPO_ROOT / "backend" / "seeds"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as session:
        yield session


@pytest.fixture
def seeded_session(session: Session) -> Session:
    """A session with the reference taxonomy loaded."""
    seed_reference(session, SEEDS_DIR)
    session.commit()
    return session


@pytest.fixture
def demo_session(seeded_session: Session) -> Session:
    """A session with the reference taxonomy and the demo profile loaded."""
    seed_demo(seeded_session, SEEDS_DIR)
    seeded_session.commit()
    return seeded_session
