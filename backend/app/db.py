"""Database wiring.

Logging classifications is a *best-effort* feature: if ``DATABASE_URL`` is not
set (tests, quick demos) the helpers below become no-ops and the API keeps
working. This keeps the core guardrail decoupled from infrastructure.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def init_db() -> None:
    """Create the engine and tables if a database is configured."""

    global _engine, _SessionLocal
    if not settings.database_url:
        return
    _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
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
