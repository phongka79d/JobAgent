"""Per-run LangGraph checkpoint lifecycle (AsyncSqliteSaver).

Owns short-lived library checkpoint tables for one application run/thread.
Application models and Alembic migrations never define these tables.

Rules (Plan 3 §7.1 / §7.3):
- One ``AsyncSqliteSaver`` open/setup lifecycle per request that needs the graph
  (new run, resume, cleanup, or inspection). Checkpoints for a thread remain on
  disk across request boundaries until completed-run cleanup.
- Resume always uses the same LangGraph ``thread_id`` (= durable agent run id).
- Completed runs: delete that thread's checkpoint rows only after the final
  validated assistant message is already durable.
- Interrupted / failed / disconnected runs keep checkpoints when still useful
  for resume or inspection; never global-delete other threads.

Production interrupt seam (graph ``await_approval`` /
``request_human_approval``):
- First request opens a saver, runs the production graph, and when the graph
  hits ``interrupt()`` the invoke result carries ``__interrupt__``. Callers
  (``ChatService``) mark the durable run interrupted and **retain** checkpoints.
- Second request opens a new saver on the same SQLite file, resumes with
  ``Command(resume=...)`` and the **same** ``thread_id``, then finalizes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Library-owned table names (must never appear in application ORM/migrations).
CHECKPOINT_TABLE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "checkpoints",
        "writes",
        "checkpoint_migrations",
    }
)


class CheckpointLifecycleError(Exception):
    """Checkpoint open, setup, or cleanup failed without secret leakage."""


def checkpoint_conn_string(sqlite_path: str | Path) -> str:
    """Build an aiosqlite connection string for the configured SQLite file.

    Shares the application database file so library checkpoint tables live next
    to application rows without a second configured path. Does not create ORM
    models for those tables.
    """
    path = Path(sqlite_path).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def thread_run_config(thread_id: str) -> dict[str, Any]:
    """Runnable config binding graph execution to one durable run/thread id."""
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise CheckpointLifecycleError("invalid thread_id")
    return {"configurable": {"thread_id": thread_id.strip()}}


@asynccontextmanager
async def open_async_sqlite_saver(
    sqlite_path: str | Path,
) -> AsyncIterator[AsyncSqliteSaver]:
    """Open one ``AsyncSqliteSaver`` lifecycle and ensure library tables exist.

    Yields a connected saver. Caller must not use the saver after the context
    exits. Safe to open again later for the same file (resume / cleanup).
    """
    conn_string = checkpoint_conn_string(sqlite_path)
    try:
        async with AsyncSqliteSaver.from_conn_string(conn_string) as saver:
            await saver.setup()
            yield saver
    except CheckpointLifecycleError:
        raise
    except Exception as exc:
        raise CheckpointLifecycleError("checkpoint saver open failed") from exc


async def count_thread_checkpoints(
    saver: AsyncSqliteSaver,
    thread_id: str,
) -> int:
    """Return checkpoint row count for one thread (writes table excluded)."""
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise CheckpointLifecycleError("invalid thread_id")
    tid = thread_id.strip()
    try:
        async with saver.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
            (tid,),
        ) as cur:
            row = await cur.fetchone()
    except Exception as exc:
        raise CheckpointLifecycleError("checkpoint count failed") from exc
    if row is None:
        return 0
    return int(row[0])


async def count_thread_checkpoints_on_disk(
    sqlite_path: str | Path,
    thread_id: str,
) -> int:
    """Open a short-lived saver and count checkpoints for ``thread_id``."""
    async with open_async_sqlite_saver(sqlite_path) as saver:
        return await count_thread_checkpoints(saver, thread_id)


async def delete_thread_checkpoints(
    saver: AsyncSqliteSaver,
    thread_id: str,
) -> None:
    """Delete checkpoint rows for one completed thread only.

    Uses ``AsyncSqliteSaver.adelete_thread`` so other runs are unaffected.
    """
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise CheckpointLifecycleError("invalid thread_id")
    try:
        await saver.adelete_thread(thread_id.strip())
    except Exception as exc:
        raise CheckpointLifecycleError("checkpoint thread delete failed") from exc


async def delete_completed_thread_checkpoints(
    sqlite_path: str | Path,
    thread_id: str,
) -> None:
    """Completed-run cleanup: remove one thread's library checkpoint rows."""
    async with open_async_sqlite_saver(sqlite_path) as saver:
        await delete_thread_checkpoints(saver, thread_id)


def extract_interrupt_payload(result: Mapping[str, Any] | Any) -> dict[str, Any] | None:
    """Return a sanitized pending-approval mapping when the graph interrupted.

    LangGraph places ``__interrupt__`` on the invoke result when ``interrupt()``
    was hit. Values are coerced to small JSON-safe structures only.
    """
    if not isinstance(result, Mapping):
        return None
    raw = result.get("__interrupt__")
    if not raw:
        return None

    first: Any
    if isinstance(raw, (list, tuple)) and raw:
        first = raw[0]
    else:
        first = raw

    value = getattr(first, "value", first)
    if value is None:
        return {"kind": "approval_required"}
    if isinstance(value, Mapping):
        # Prefer the shared profile-aware sanitizer so skill previews survive
        # the interrupt → ChatService → SSE path without type-name collapse.
        from app.agent.approval import sanitize_profile_approval_fields

        return sanitize_profile_approval_fields(value)
    if isinstance(value, str):
        return {"kind": "approval_required", "detail": value[:512]}
    return {"kind": "approval_required"}


def result_is_graph_interrupt(result: Mapping[str, Any] | Any) -> bool:
    """True when invoke stopped on a LangGraph interrupt (not terminal success)."""
    return extract_interrupt_payload(result) is not None


__all__ = [
    "CHECKPOINT_TABLE_NAMES",
    "CheckpointLifecycleError",
    "checkpoint_conn_string",
    "count_thread_checkpoints",
    "count_thread_checkpoints_on_disk",
    "delete_completed_thread_checkpoints",
    "delete_thread_checkpoints",
    "extract_interrupt_payload",
    "open_async_sqlite_saver",
    "result_is_graph_interrupt",
    "thread_run_config",
]
