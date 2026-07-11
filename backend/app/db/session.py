"""Async SQLAlchemy 2 engine and session ownership for SQLite.

Owns connection URL construction for the configured ``SQLITE_PATH``, enables
SQLite foreign-key enforcement on every connection, and provides explicit
transaction boundaries suitable for tests and application services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def sqlite_url_for_path(path: str | Path) -> str:
    """Build an aiosqlite URL for an absolute or relative filesystem path.

    Does not accept arbitrary URLs; callers pass the configured SQLite file path
    from typed settings (or a temporary path in tests).
    """
    resolved = Path(path).expanduser()
    # SQLAlchemy expects forward slashes; absolute Windows paths need three slashes
    # after the scheme (sqlite+aiosqlite:///C:/...) which Path.as_posix provides
    # when combined with the triple-slash form for absolute paths.
    posix = resolved.as_posix()
    if resolved.is_absolute():
        return f"sqlite+aiosqlite:///{posix}"
    return f"sqlite+aiosqlite:///{posix}"


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable FK enforcement for every new SQLite connection (off by default)."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _in_memory_sqlite_url() -> str:
    """Build a manager-unique shared-cache in-memory SQLite URI.

    Distinct connections share schema/data within one name (one manager) while
    remaining transaction-isolated. A new random name isolates separate managers.

    SQLAlchemy's SQLite dialect only treats the database as a native SQLite URI
    when ``uri=true`` is present on the SQLAlchemy URL query (see
    ``SQLiteDialect_pysqlite.create_connect_args``). Passing ``uri=True`` only
    via ``connect_args`` leaves the filename path-absolutized (e.g. ``file:name``
    becomes a filesystem path and can create a zero-byte ``file`` artifact).
    """
    name = f"jobagent-{uuid4().hex}"
    return (
        f"sqlite+aiosqlite:///file:{name}"
        f"?mode=memory&cache=shared&uri=true"
    )


def create_async_engine_for_path(
    path: str | Path,
    *,
    echo: bool = False,
    in_memory: bool = False,
) -> AsyncEngine:
    """Create an async engine bound to a SQLite file (or isolated in-memory DB).

    Parameters
    ----------
    path:
        Filesystem path for the SQLite file. Parent directories are created when
        the path is not in-memory.
    echo:
        When true, log SQL statements (tests default off).
    in_memory:
        When true, use a named shared-cache in-memory database with ``NullPool``
        so simultaneous sessions get distinct connections (transaction isolation)
        while still sharing schema/data for this engine. ``path`` is ignored for
        the URL but kept for API symmetry. Callers must retain at least one open
        connection for the lifetime of the memory database (see
        ``DatabaseSessionManager``).
    """
    if in_memory:
        # NullPool: every checkout is a new physical connection (not StaticPool).
        # Shared-cache SQLite URI (uri=true on the SQLAlchemy URL, not only in
        # connect_args): those connections share one named in-memory database
        # without creating filesystem artifacts.
        engine = create_async_engine(
            _in_memory_sqlite_url(),
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
    else:
        file_path = Path(path).expanduser()
        if not file_path.is_absolute():
            file_path = file_path.resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            sqlite_url_for_path(file_path),
            echo=echo,
        )

    # Listen on the sync engine underlying the async wrapper.
    event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


class DatabaseSessionManager:
    """Owns one async engine and session factory for a SQLite database file.

    Explicit transaction ownership: callers commit or rollback; ``session_scope``
    commits on success and rolls back on error so partial state does not leak.

    For in-memory engines, a keepalive connection is held so the shared-cache
    memory database is not destroyed when transient NullPool connections close.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        retain_connection: bool = False,
    ) -> None:
        self._engine = engine
        self._retain_connection = retain_connection
        self._keepalive: AsyncConnection | None = None
        self._session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    async def _ensure_keepalive(self) -> None:
        """Hold one connection open for shared-cache in-memory databases."""
        if self._retain_connection and self._keepalive is None:
            self._keepalive = await self._engine.connect()

    async def create_all(self) -> None:
        """Create all application tables from model metadata (tests / bootstrap).

        Production schema ownership for empty and initialized volumes belongs to
        Alembic migrations (task 02B). This method is for metadata tests and
        isolated temporary databases only.
        """
        # Import models so they register on Base.metadata before create_all.
        from app.db import models as _models  # noqa: F401
        from app.db.base import Base

        await self._ensure_keepalive()
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        """Drop all application tables (test teardown only)."""
        from app.db.base import Base

        await self._ensure_keepalive()
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        """Release keepalive and pool connections."""
        if self._keepalive is not None:
            await self._keepalive.close()
            self._keepalive = None
        await self._engine.dispose()

    async def foreign_keys_enabled(self) -> bool:
        """Return whether PRAGMA foreign_keys is enabled on a live connection."""
        await self._ensure_keepalive()
        async with self._engine.connect() as conn:
            result = await conn.execute(text("PRAGMA foreign_keys"))
            value = result.scalar_one()
            return int(value) == 1

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        """Yield a session with commit-on-success and rollback-on-error.

        If the session is already inactive (for example after a failed flush
        that the caller handled), rollback instead of attempting commit so
        partial state never leaks.
        """
        await self._ensure_keepalive()
        session = self._session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # Failed flushes leave the transaction inactive; never commit then.
            if not session.is_active:
                await session.rollback()
            else:
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
        finally:
            await session.close()


def create_session_manager(
    path: str | Path,
    *,
    echo: bool = False,
    in_memory: bool = False,
) -> DatabaseSessionManager:
    """Convenience: engine + session manager for a configured SQLite path."""
    engine = create_async_engine_for_path(path, echo=echo, in_memory=in_memory)
    return DatabaseSessionManager(engine, retain_connection=in_memory)
