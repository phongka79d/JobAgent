"""Request-scoped LangGraph AsyncSqliteSaver lifecycle (Plan 3 §7.6).

One saver is opened per turn/resume request against the application SQLite file
(same path as settings ``SQLITE_PATH``). LangGraph owns checkpoint table DDL;
Alembic and application repositories never create, alter, or drop them.

``run_id`` is the only LangGraph ``thread_id``. Terminal cleanup deletes only
that thread's rows via the package API after durable terminal commit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.settings import Settings, get_settings


def resolve_checkpoint_sqlite_path(
    sqlite_path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> Path:
    """Resolve the filesystem path used for the checkpointer connection.

    Defaults to configured application ``SQLITE_PATH`` — no second path parser.
    """
    if sqlite_path is not None:
        return Path(sqlite_path).expanduser().resolve()
    cfg = settings if settings is not None else get_settings()
    return Path(cfg.SQLITE_PATH).expanduser().resolve()


def thread_config(run_id: str) -> RunnableConfig:
    """Build LangGraph config with ``run_id`` as ``thread_id``."""
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")
    return RunnableConfig(configurable={"thread_id": run_id})


@asynccontextmanager
async def open_checkpointer(
    sqlite_path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> AsyncIterator[AsyncSqliteSaver]:
    """Open one ``AsyncSqliteSaver`` for a single turn/resume request.

    Yields a setup saver bound to the application SQLite file, then closes the
    connection when the request lifecycle ends.
    """
    path = resolve_checkpoint_sqlite_path(sqlite_path, settings=settings)
    # aiosqlite accepts a filesystem path string (same file as app engine).
    async with AsyncSqliteSaver.from_conn_string(path.as_posix()) as saver:
        await saver.setup()
        yield saver


async def delete_run_checkpoint(
    saver: AsyncSqliteSaver,
    run_id: str,
) -> None:
    """Delete only the checkpoint rows for ``run_id`` (thread_id).

    Uses the package-supported per-thread deletion API. Never deletes another
    run's continuation and never touches application tables.
    """
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")
    await saver.adelete_thread(run_id)


async def thread_has_checkpoints(
    saver: AsyncSqliteSaver,
    run_id: str,
) -> bool:
    """Return True if any checkpoint exists for the run thread."""
    config = thread_config(run_id)
    async for _ in saver.alist(config, limit=1):
        return True
    return False
