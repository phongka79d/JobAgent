"""Durable tool execution service with identity replay.

Commits short status transitions outside the invoker side effect. Replay by
``(run_id, tool_call_id)`` returns the exact stored validated ``ToolResult``
without invoking the side effect or inserting another row. No second
idempotency-key mechanism is used.

Interrupt-aware tools may re-enter the same ``running`` row under the same
identity (``allow_running_reentry=True``) so LangGraph resume continues one
tool invocation without a second execution row.

Request-scoped ``tool_status`` publication is owned here: each status is
published only after the corresponding durable transaction successfully
commits (and terminal-identity projection on replay). The Agent runner binds
a listener for the duration of one SSE stream; no second executor or polling
store exists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

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


@dataclass(frozen=True, slots=True)
class ToolStatusPublication:
    """Compact durable tool-status projection for the approved SSE payload.

    Never carries raw arguments, full ToolResult ``data``, secrets, provider
    bodies, or stacks — only identity, exact status, and terminal coupling.
    """

    tool_execution_id: str
    tool_call_id: str
    tool_name: str
    status: str
    duration_ms: int | None = None
    summary: str | None = None
    error_code: str | None = None


ToolStatusListener = Callable[[ToolStatusPublication], None]

_tool_status_listener: ContextVar[ToolStatusListener | None] = ContextVar(
    "tool_status_listener",
    default=None,
)


def bind_tool_status_listener(
    listener: ToolStatusListener,
) -> Token[ToolStatusListener | None]:
    """Bind request-scoped listener; token for :func:`reset_tool_status_listener`."""
    return _tool_status_listener.set(listener)


def reset_tool_status_listener(token: Token[ToolStatusListener | None]) -> None:
    """Restore the previous tool-status listener after a runner stream ends."""
    _tool_status_listener.reset(token)


@contextmanager
def tool_status_publication_scope(
    listener: ToolStatusListener,
) -> Iterator[None]:
    """Request-scoped publication seam around durable transitions for one run."""
    token = bind_tool_status_listener(listener)
    try:
        yield
    finally:
        reset_tool_status_listener(token)


def _publish(publication: ToolStatusPublication) -> None:
    listener = _tool_status_listener.get()
    if listener is not None:
        listener(publication)


def _publication(
    *,
    tool_execution_id: str,
    tool_call_id: str,
    tool_name: str,
    status: str,
    duration_ms: int | None = None,
    summary: str | None = None,
    error_code: str | None = None,
) -> ToolStatusPublication:
    return ToolStatusPublication(
        tool_execution_id=tool_execution_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        status=status,
        duration_ms=duration_ms,
        summary=summary,
        error_code=error_code,
    )


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
       row is already terminal, return after projecting stored terminal
       ``tool_status`` (published only after this read transaction commits).
    2. If ``pending``, publish ``pending`` only after the create/select
       transaction commits, then open a second short transaction to transition
       to ``running`` and publish ``running`` only after that commit.
    3. If ``running`` and *allow_running_reentry* is True (interrupt resume of
       the same invocation), keep the same row and re-enter *invoke* without a
       second execution identity or repeated ``pending`` emission.
    4. If ``running`` and re-entry is not allowed, raise
       :class:`ToolExecutionInProgressError`.
    5. Invoke the side effect **outside** any open transaction. An interrupting
       invoker may raise LangGraph's interrupt control exception before
       returning; the row stays ``running`` until a later re-entry terminalizes.
    6. Short transaction: store terminal ``completed`` or ``failed`` with
       validated ``result_json``, ``duration_ms``, and coupled ``error_code``,
       then publish the terminal status only after that commit succeeds.

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

    execution_id: str
    stored_tool_call_id = tool_call_id
    stored_tool_name = tool_name
    claim: Literal["new_pending", "reentry"] | None = None
    replay_result: ToolResult | None = None
    replay_pub: ToolStatusPublication | None = None

    async with _short_transaction(factory) as session:
        row, _created = await tool_repo.get_or_create_pending(
            session,
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments_summary_json=arguments_summary_json,
        )
        stored_tool_call_id = row.tool_call_id
        stored_tool_name = row.tool_name
        execution_id = row.id
        if row.status in _TERMINAL:
            stored = load_stored_result(row)
            replay_result = stored
            replay_pub = _publication(
                tool_execution_id=row.id,
                tool_call_id=row.tool_call_id,
                tool_name=row.tool_name,
                status=row.status,
                duration_ms=row.duration_ms,
                summary=stored.summary,
                error_code=row.error_code,
            )
        elif row.status == TOOL_EXECUTION_STATUS_RUNNING:
            if not allow_running_reentry:
                raise ToolExecutionInProgressError(
                    f"tool execution already running for "
                    f"({run_id!r}, {tool_call_id!r})"
                )
            claim = "reentry"
        elif row.status == TOOL_EXECUTION_STATUS_PENDING:
            claim = "new_pending"
        else:
            raise ToolExecutionServiceError(
                f"unexpected tool status {row.status!r} before claim"
            )

    # Publish only after the short transaction above has committed.
    if replay_result is not None and replay_pub is not None:
        _publish(replay_pub)
        return replay_result

    if claim == "new_pending":
        # Pending row is durable; advertise only after commit above.
        _publish(
            _publication(
                tool_execution_id=execution_id,
                tool_call_id=stored_tool_call_id,
                tool_name=stored_tool_name,
                status=TOOL_EXECUTION_STATUS_PENDING,
            )
        )
        async with _short_transaction(factory) as session:
            row = await tool_repo.mark_running(session, execution_id)
            execution_id = row.id
            stored_tool_call_id = row.tool_call_id
            stored_tool_name = row.tool_name
        # Running transition is durable only after the second commit.
        _publish(
            _publication(
                tool_execution_id=execution_id,
                tool_call_id=stored_tool_call_id,
                tool_name=stored_tool_name,
                status=TOOL_EXECUTION_STATUS_RUNNING,
            )
        )

    started = perf_counter()
    result = await invoke()
    if not isinstance(result, ToolResult):
        raise ToolExecutionServiceError(
            "tool invoker must return a ToolResult instance"
        )
    duration_ms = max(0, int((perf_counter() - started) * 1000))

    terminal_status: str
    terminal_error: str | None
    terminal_summary: str
    terminal_duration: int | None

    async with _short_transaction(factory) as session:
        # Re-check identity for exact terminal replay if another path finished.
        live = await tool_repo.get_by_id(session, execution_id)
        if live is not None and live.status in _TERMINAL:
            stored = load_stored_result(live)
            terminal_status = live.status
            terminal_error = live.error_code
            terminal_summary = stored.summary
            terminal_duration = live.duration_ms
            stored_tool_call_id = live.tool_call_id
            stored_tool_name = live.tool_name
            early_terminal = stored
        else:
            early_terminal = None
            if result.ok:
                await tool_repo.complete_execution(
                    session,
                    execution_id,
                    result=result,
                    duration_ms=duration_ms,
                )
                terminal_status = TOOL_EXECUTION_STATUS_COMPLETED
                terminal_error = None
            else:
                await tool_repo.fail_execution(
                    session,
                    execution_id,
                    result=result,
                    duration_ms=duration_ms,
                )
                terminal_status = TOOL_EXECUTION_STATUS_FAILED
                terminal_error = result.code
            terminal_summary = result.summary
            terminal_duration = duration_ms

    _publish(
        _publication(
            tool_execution_id=execution_id,
            tool_call_id=stored_tool_call_id,
            tool_name=stored_tool_name,
            status=terminal_status,
            duration_ms=terminal_duration,
            summary=terminal_summary,
            error_code=terminal_error,
        )
    )
    if early_terminal is not None:
        return early_terminal
    return result


async def get_replay_result(
    *,
    run_id: str,
    tool_call_id: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> ToolResult | None:
    """Return the stored terminal result for *identity*, or ``None`` if absent.

    Does not invoke any side effect. Raises when a non-terminal row exists but
    has no loadable terminal payload (invariant violation). Does not publish
    SSE (read-only; live emission is owned by :func:`execute_tool` / runner).
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


__all__ = [
    "ToolExecutionInProgressError",
    "ToolExecutionServiceError",
    "ToolInvoker",
    "ToolStatusListener",
    "ToolStatusPublication",
    "bind_tool_status_listener",
    "execute_tool",
    "get_replay_result",
    "reset_tool_status_listener",
    "tool_status_publication_scope",
]
