"""Alembic environment for async SQLite with batch mode.

Uses the shared application async URL builder and applies PRAGMA listeners via
``build_async_engine``. Schema DDL is migration-owned only. Does not manage
LangGraph checkpoint tables.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

# Import models so Base.metadata is complete for autogenerate / inspection.
import app.db.models  # noqa: F401
from alembic import context
from app.db.base import Base
from app.db.session import build_async_engine, sqlite_url
from sqlalchemy import pool
from sqlalchemy.engine import Connection

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Placeholder URL in alembic.ini — real URL resolved below.
_PLACEHOLDER_URL = "driver://user:pass@localhost/dbname"


def _resolve_database_url() -> str:
    """Prefer sqlalchemy.url override (tests); else settings SQLITE_PATH."""
    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured and configured != _PLACEHOLDER_URL:
        return configured
    from app.core.settings import get_settings

    return sqlite_url(get_settings().SQLITE_PATH)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script emission)."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def _include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Never manage non-application / checkpoint-like tables via autogenerate."""
    if type_ == "table" and name is not None:
        if name.startswith("checkpoint") or name.startswith("langgraph"):
            return False
        if name not in target_metadata.tables:
            return False
    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine with required PRAGMAs and run migrations."""
    url = _resolve_database_url()
    # build_async_engine expects a filesystem path when using sqlite_url helper;
    # when tests pass a full URL via config, construct the engine directly.
    if url.startswith("sqlite+aiosqlite:///"):
        path_part = url.removeprefix("sqlite+aiosqlite:///")
        connectable = build_async_engine(path_part)
    else:
        from sqlalchemy.ext.asyncio import create_async_engine

        connectable = create_async_engine(url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
