"""Durable tool execution service with identity replay.

Commits short status transitions outside the invoker side effect. Replay by
``(run_id, tool_call_id)`` returns the exact stored validated ``ToolResult``
without invoking the side effect or inserting another row. No second
idempotency-key mechanism is used.

Interrupt-aware tools may re-enter the same ``running`` row under the same
identity (``allow_running_reentry=True``) so LangGraph resume continues one
tool invocation without a second execution row.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.chat import (
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
    TOOL_EXECUTION_STATUS_PENDING,
    TOOL_EXECUTION_STATUS_RUNNING,
)
from app.db.session import get_session_factory
from app.repositories import tool_executions as tool_repo
from app.repositories.tool_executions import (
    ToolExecutionRepositoryError,
    load_stored_result,
)
from app.schemas.tools import ToolResult

ToolInvoker = Callable[[], Awaitable[ToolResult]]

_TERMINAL = frozenset(
    {TOOL_EXECUTION_STATUS_COMPLETED, TOOL_EXECUTION_STATUS_FAILED}
)


class ToolExecutionServiceError(Exception):
    """Base error for durable tool-execution service failures."""


class ToolExecutionInProgressError(ToolExecutionServiceError):
    """Raised when the identity is already ``running`` and not terminal."""


@asynccontextmanager
async def _short_transaction(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session; commit on success, roll back on error.

    Must not wrap provider/graph/side-effect work — only durable transitions.
    """
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def execute_tool(
    *,
    run_id: str,
    tool_call_id: str,
    tool_name: str,
    invoke: ToolInvoker,
    arguments_summary_json: dict[str, Any] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    allow_running_reentry: bool = False,
) -> ToolResult:
    """Run one tool call with durable get-or-create and exact identity replay.

    Flow:
    1. Short transaction: get-or-create by ``(run_id, tool_call_id)``. If the
       row is already terminal, return the stored validated result without
       calling *invoke*.
    2. If ``pending``, transition to ``running`` and commit.
    3. If ``running`` and *allow_running_reentry* is True (interrupt resume of
       the same invocation), keep the same row and re-enter *invoke*.
    4. If ``running`` and re-entry is not allowed, raise
       :class:`ToolExecutionInProgressError`.
    5. Invoke the side effect **outside** any open transaction. An interrupting
       invoker may raise LangGraph's interrupt control exception before
       returning; the row stays ``running`` until a later re-entry terminalizes.
    6. Short transaction: store terminal ``completed`` or ``failed`` with
       validated ``result_json``, ``duration_ms``, and coupled ``error_code``.

    Parameters
    ----------
    session_factory:
        Optional async session factory. Defaults to the process-wide factory
        from :func:`app.db.session.get_session_factory`.
    allow_running_reentry:
        When True, a non-terminal ``running`` row is re-entered under the same
        identity (required for interrupt-guarded tools). Default False preserves
        the original concurrent-running rejection for non-interrupt tools.
    """
    factory = session_factory if session_factory is not None else get_session_factory()

    async with _short_transaction(factory) as session:
        row, _created = await tool_repo.get_or_create_pending(
            session,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments_summary_json=arguments_summary_json,
        )
        if row.status in _TERMINAL:
            return load_stored_result(row)
        if row.status == TOOL_EXECUTION_STATUS_RUNNING:
            if not allow_running_reentry:
                raise ToolExecutionInProgressError(
                    f"tool execution already running for "
                    f"({run_id!r}, {tool_call_id!r})"
                )
            execution_id = row.id
        elif row.status == TOOL_EXECUTION_STATUS_PENDING:
            row = await tool_repo.mark_running(session, row.id)
            execution_id = row.id
        else:
            raise ToolExecutionServiceError(
                f"unexpected tool status {row.status!r} before claim"
            )

    started = perf_counter()
    result = await invoke()
    if not isinstance(result, ToolResult):
        raise ToolExecutionServiceError(
            "tool invoker must return a ToolResult instance"
        )
    duration_ms = max(0, int((perf_counter() - started) * 1000))

    async with _short_transaction(factory) as session:
        # Re-check identity for exact terminal replay if another path finished.
        live = await tool_repo.get_by_id(session, execution_id)
        if live is not None and live.status in _TERMINAL:
            return load_stored_result(live)
        if result.ok:
            await tool_repo.complete_execution(
                session,
                execution_id,
                result=result,
                duration_ms=duration_ms,
            )
        else:
            await tool_repo.fail_execution(
                session,
                execution_id,
                result=result,
                duration_ms=duration_ms,
            )

    return result


async def get_replay_result(
    *,
    run_id: str,
    tool_call_id: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> ToolResult | None:
    """Return the stored terminal result for *identity*, or ``None`` if absent.

    Does not invoke any side effect. Raises when a non-terminal row exists but
    has no loadable terminal payload (invariant violation).
    """
    factory = session_factory if session_factory is not None else get_session_factory()
    async with factory() as session:
        row = await tool_repo.get_by_identity(
            session, run_id=run_id, tool_call_id=tool_call_id
        )
        if row is None:
            return None
        if row.status not in _TERMINAL:
            raise ToolExecutionRepositoryError(
                f"tool execution ({run_id!r}, {tool_call_id!r}) is not terminal "
                f"(status={row.status!r})"
            )
        return load_stored_result(row)
