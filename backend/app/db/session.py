"""One async SQLite engine/session factory with required connection PRAGMAs.

Owns the application ``sqlite+aiosqlite`` engine for ``SQLITE_PATH``, applies
``foreign_keys=ON``, ``journal_mode=WAL``, and ``busy_timeout=5000`` on every
connection, and exposes short-lived transaction helpers. Callers must not hold a
session open across provider calls, URL reads, file writes, Neo4j work, or SSE
streaming. Schema DDL is owned by Alembic migrations, not this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings

# Required connection invariants (Master Plan §6.1 / Plan 2 §7.2).
REQUIRED_FOREIGN_KEYS = 1
REQUIRED_JOURNAL_MODE = "wal"
REQUIRED_BUSY_TIMEOUT_MS = 5000

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def sqlite_url(sqlite_path: str | Path) -> str:
    """Build the async SQLAlchemy URL for a filesystem SQLite path."""
    resolved = Path(sqlite_path).expanduser().resolve()
    return f"sqlite+aiosqlite:///{resolved.as_posix()}"


def _apply_and_verify_pragmas(dbapi_connection: Any) -> None:
    """Set and verify the three required SQLite PRAGMAs on one DBAPI connection.

    Single owner for connection-event PRAGMA logic; registered once per engine.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={REQUIRED_BUSY_TIMEOUT_MS}")

        cursor.execute("PRAGMA foreign_keys")
        foreign_keys = cursor.fetchone()[0]
        cursor.execute("PRAGMA journal_mode")
        journal_mode = str(cursor.fetchone()[0]).lower()
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]

        if int(foreign_keys) != REQUIRED_FOREIGN_KEYS:
            raise RuntimeError(
                f"SQLite foreign_keys must be {REQUIRED_FOREIGN_KEYS}, "
                f"got {foreign_keys!r}"
            )
        if journal_mode != REQUIRED_JOURNAL_MODE:
            raise RuntimeError(
                f"SQLite journal_mode must be {REQUIRED_JOURNAL_MODE!r}, "
                f"got {journal_mode!r}"
            )
        if int(busy_timeout) != REQUIRED_BUSY_TIMEOUT_MS:
            raise RuntimeError(
                f"SQLite busy_timeout must be {REQUIRED_BUSY_TIMEOUT_MS}, "
                f"got {busy_timeout!r}"
            )
    finally:
        cursor.close()


def _register_pragma_listeners(engine: AsyncEngine) -> None:
    """Attach the shared PRAGMA handler to every new connection on *engine*."""

    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        _apply_and_verify_pragmas(dbapi_connection)

    event.listen(engine.sync_engine, "connect", _on_connect)


def build_async_engine(sqlite_path: str | Path) -> AsyncEngine:
    """Create an async engine for *sqlite_path* with required PRAGMAs.

    Prefer :func:`get_engine` for the process-wide application engine. Tests and
    isolated runners may call this with a temporary path.
    """
    engine = create_async_engine(
        sqlite_url(sqlite_path),
        pool_pre_ping=False,
    )
    _register_pragma_listeners(engine)
    return engine


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine for configured ``SQLITE_PATH``."""
    global _engine, _session_factory
    if _engine is None:
        path = get_settings().SQLITE_PATH
        _engine = build_async_engine(path)
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the single async session factory bound to :func:`get_engine`."""
    global _session_factory
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a short-lived session; commit on success, roll back on error.

    Do not perform external I/O while this context is open.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose and clear the process-wide engine and session factory (tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def read_connection_pragmas(session: AsyncSession) -> dict[str, Any]:
    """Return foreign_keys, journal_mode, and busy_timeout for *session*."""
    fk = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
    journal = (await session.execute(text("PRAGMA journal_mode"))).scalar_one()
    timeout = (await session.execute(text("PRAGMA busy_timeout"))).scalar_one()
    return {
        "foreign_keys": int(fk),
        "journal_mode": str(journal).lower(),
        "busy_timeout": int(timeout),
    }
