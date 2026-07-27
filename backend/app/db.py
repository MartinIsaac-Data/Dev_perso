"""Engine and session management.

Two things happen here that are easy to get wrong and expensive to fix later:

1. SQLite does not enforce foreign keys unless you ask it to, per connection.
   Without the PRAGMA below, every FK in this schema is decorative and the
   local database silently diverges from what Postgres would accept.
2. Sessions are handed out through an explicit context manager rather than a
   module-level global, so tests can run against an in-memory database
   without monkey-patching anything.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def build_engine(settings: Settings | None = None, url: str | None = None) -> Engine:
    settings = settings or get_settings()
    engine = create_engine(
        url or settings.database_url,
        echo=settings.sql_echo,
        future=True,
    )
    if engine.dialect.name == "sqlite":
        _enable_sqlite_foreign_keys(engine)
    return engine


_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        _engine = build_engine()
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any exception."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Read-mostly; endpoints commit explicitly."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
