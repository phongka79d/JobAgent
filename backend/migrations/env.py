"""Alembic environment for JobAgent application SQLite schema.

Consumes the typed SQLite filesystem path and application model metadata.
Does not import network clients (ShopAIKey, Neo4j, LangGraph).

Path resolution order for the database file:
1. Process environment ``SQLITE_PATH`` (used by tests and explicit overrides).
2. Typed root settings via ``load_settings()`` (local CLI with root ``.env``).

Tests must set ``SQLITE_PATH`` so the user's real root ``.env`` is never read.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

# Register all application models on Base.metadata before autogenerate/upgrade.
import app.db.models  # noqa: F401, E402
from alembic import context
from app.db.base import Base
from sqlalchemy import create_engine, event, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Names that must never appear as application migration targets.
_FORBIDDEN_TABLE_MARKERS = ("checkpoint",)


def _sync_sqlite_url(path: str | Path) -> str:
    """Build a sync sqlite URL for Alembic (not aiosqlite)."""
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = resolved.resolve()
    # Ensure parent exists for file-backed databases before engine connect.
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved.as_posix()}"


def get_sqlite_path() -> str:
    """Resolve SQLITE_PATH without requiring network clients.

    Prefer process environment so tests inject a temporary path and never load
    the user-owned root ``.env``. Full typed settings are used only when the
    path is not already present in the environment (local CLI).
    """
    env_path = os.environ.get("SQLITE_PATH")
    if env_path is not None and env_path.strip():
        return env_path.strip()

    # Local CLI: load the root configuration contract (may read root .env).
    from app.config import load_settings

    return load_settings().sqlite_path


def get_url() -> str:
    """Return the sync SQLite URL for the configured application database file."""
    return _sync_sqlite_url(get_sqlite_path())


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """Match runtime session behavior: SQLite FK enforcement on every connect."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Exclude LangGraph checkpoint objects from autogenerate noise."""
    if type_ == "table" and name is not None:
        lowered = name.lower()
        if any(marker in lowered for marker in _FORBIDDEN_TABLE_MARKERS):
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script emission only)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the configured SQLite file."""
    url = get_url()
    # Override any placeholder URL in alembic.ini; path comes from typed contract.
    config.set_main_option("sqlalchemy.url", url)

    connectable = create_engine(
        url,
        poolclass=pool.NullPool,
    )
    event.listen(connectable, "connect", _enable_sqlite_foreign_keys)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
