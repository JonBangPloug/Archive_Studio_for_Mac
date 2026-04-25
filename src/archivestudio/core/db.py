"""Engine and session helpers for per-project SQLite databases."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from archivestudio.core.models import Base


def _enable_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Enable foreign keys and set sensible SQLite pragmas."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


def make_engine(db_path: Path, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine pointed at ``db_path``.

    Foreign keys and WAL are enabled on every new connection.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=echo, future=True)
    event.listen(engine, "connect", _enable_sqlite_pragmas)
    return engine


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    """Return a configured sessionmaker bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create all tables declared on :class:`Base` metadata."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional session context manager: commit on success, rollback on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
