"""Database wiring.

Classifications are logged for the ``/history`` endpoint. The URL defaults to a
local SQLite file (see config), so history works with no external services;
setting ``DATABASE_URL`` to a Postgres URL switches to Postgres for production.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.models import Base

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db() -> None:
    """Create the engine and tables. Handles SQLite (incl. in-memory for tests)
    and Postgres transparently based on the configured URL."""

    global _engine, _SessionLocal
    url = settings.database_url
    if not url:
        return
    if url.startswith("sqlite"):
        # SQLite needs cross-thread access for the threaded server; in-memory
        # SQLite additionally needs a single shared connection (StaticPool).
        connect_args = {"check_same_thread": False}
        if ":memory:" in url or url == "sqlite://":
            _engine = create_engine(
                url, connect_args=connect_args, poolclass=StaticPool, future=True
            )
        else:
            _engine = create_engine(url, connect_args=connect_args, future=True)
    else:
        _engine = create_engine(url, pool_pre_ping=True, future=True)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(_engine)


def enabled() -> bool:
    """True when a database is configured, so logging and history are available."""
    return _SessionLocal is not None


@contextmanager
def session_scope() -> Iterator[Session | None]:
    """Yield a session, or ``None`` when no database is configured."""

    if _SessionLocal is None:
        yield None
        return
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
