"""Tool-execution get-or-create, transition, result storage, and replay reads.

Owns durable rows for ``tool_executions`` with identity ``(run_id, tool_call_id)``
only — no second idempotency key. Allowed transitions are
``pending → running → completed|failed``. Terminal rows store a validated
``ToolResult`` in ``result_json`` plus ``duration_ms`` (and matching
``error_code`` on failure). Callers own the async session and commit; this
module never opens a session or finalizes the unit of work.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.chat import (
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
    TOOL_EXECUTION_STATUS_PENDING,
    TOOL_EXECUTION_STATUS_RUNNING,
    ToolExecution,
)
from app.schemas.tools import (
    ToolResult,
    parse_tool_result,
    validate_tool_result_terminal_coupling,
)

# Approved transitions only (Master §6.2 tool_executions):
# pending → running → completed | failed
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    TOOL_EXECUTION_STATUS_PENDING: frozenset({TOOL_EXECUTION_STATUS_RUNNING}),
    TOOL_EXECUTION_STATUS_RUNNING: frozenset(
        {
            TOOL_EXECUTION_STATUS_COMPLETED,
            TOOL_EXECUTION_STATUS_FAILED,
        }
    ),
    TOOL_EXECUTION_STATUS_COMPLETED: frozenset(),
    TOOL_EXECUTION_STATUS_FAILED: frozenset(),
}

_TERMINAL = frozenset(
    {TOOL_EXECUTION_STATUS_COMPLETED, TOOL_EXECUTION_STATUS_FAILED}
)


class ToolExecutionRepositoryError(Exception):
    """Base error for tool-execution repository invariant violations."""


class ToolExecutionNotFoundError(ToolExecutionRepositoryError):
    """Raised when the requested tool execution does not exist."""


class InvalidToolTransitionError(ToolExecutionRepositoryError):
    """Raised when a status transition is skipped, backward, or terminal."""


class ToolResultCouplingError(ToolExecutionRepositoryError):
    """Raised when terminal result/status/error_code coupling is invalid."""


async def get_by_identity(
    session: AsyncSession,
    *,
    run_id: str,
    tool_call_id: str,
) -> ToolExecution | None:
    """Return the row for ``(run_id, tool_call_id)``, or ``None`` if missing."""
    stmt = select(ToolExecution).where(
        ToolExecution.run_id == run_id,
        ToolExecution.tool_call_id == tool_call_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_id(
    session: AsyncSession,
    execution_id: str,
) -> ToolExecution | None:
    """Return the tool execution with primary key *execution_id*, or ``None``."""
    return await session.get(ToolExecution, execution_id)


async def list_for_run_ids(
    session: AsyncSession,
    run_ids: Sequence[str],
) -> list[ToolExecution]:
    """Return tool executions for *run_ids*, ordered by ``(created_at, id)``.

    Empty input yields an empty list without querying. Does not finalize the
    caller's unit of work.
    """
    if not run_ids:
        return []
    stmt = (
        select(ToolExecution)
        .where(ToolExecution.run_id.in_(list(run_ids)))
        .order_by(ToolExecution.created_at.asc(), ToolExecution.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_source_attachment_id(
    session: AsyncSession,
    attachment_id: str,
) -> list[ToolExecution]:
    """Return tool executions with explicit CV ``source_attachment_id``.

    Does not finalize the caller's unit of work.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ToolExecutionRepositoryError(
            "attachment_id must be a non-empty string"
        )
    stmt = (
        select(ToolExecution)
        .where(ToolExecution.source_attachment_id == attachment_id.strip())
        .order_by(ToolExecution.created_at.asc(), ToolExecution.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_with_argument_or_result_json(
    session: AsyncSession,
) -> list[ToolExecution]:
    """Return tools that still carry argument summaries or terminal results.

    Supports historical ownership resolution when ``source_attachment_id`` was
    not stamped. Does not finalize the unit of work.
    """
    stmt = (
        select(ToolExecution)
        .where(
            (ToolExecution.arguments_summary_json.is_not(None))
            | (ToolExecution.result_json.is_not(None))
        )
        .order_by(ToolExecution.created_at.asc(), ToolExecution.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_execution(session: AsyncSession, execution_id: str) -> bool:
    """Delete one tool execution by primary key.

    Returns ``True`` when deleted, ``False`` when already absent. Does not
    finalize the caller's unit of work.
    """
    if not isinstance(execution_id, str) or execution_id.strip() == "":
        raise ToolExecutionRepositoryError(
            "execution_id must be a non-empty string"
        )
    row = await session.get(ToolExecution, execution_id.strip())
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_or_create_pending(
    session: AsyncSession,
    *,
    run_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments_summary_json: dict[str, Any] | None = None,
    source_attachment_id: str | None = None,
) -> tuple[ToolExecution, bool]:
    """Get existing row by identity or insert a new ``pending`` execution.

    Race-safe under the unique constraint ``uq_tool_executions__run_tool_call``:
    concurrent inserts recover via savepoint + re-select. Optional
    *source_attachment_id* records CV tool ownership on insert only (existing
    rows are returned unchanged). Returns ``(row, created)`` where *created*
    is ``True`` only when this call inserted the row. Does not finalize the
    caller's unit of work.
    """
    if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
        raise ToolExecutionRepositoryError("tool_call_id must be a non-empty string")
    if not isinstance(tool_name, str) or tool_name.strip() == "":
        raise ToolExecutionRepositoryError("tool_name must be a non-empty string")
    if source_attachment_id is not None and (
        not isinstance(source_attachment_id, str)
        or source_attachment_id.strip() == ""
    ):
        raise ToolExecutionRepositoryError(
            "source_attachment_id must be a non-empty string when set"
        )

    existing = await get_by_identity(
        session, run_id=run_id, tool_call_id=tool_call_id
    )
    if existing is not None:
        return existing, False

    kwargs: dict[str, Any] = {
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "status": TOOL_EXECUTION_STATUS_PENDING,
    }
    if arguments_summary_json is not None:
        kwargs["arguments_summary_json"] = arguments_summary_json
    if source_attachment_id is not None:
        kwargs["source_attachment_id"] = source_attachment_id

    row = ToolExecution(**kwargs)
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row, True
    except IntegrityError:
        existing = await get_by_identity(
            session, run_id=run_id, tool_call_id=tool_call_id
        )
        if existing is None:
            raise ToolExecutionRepositoryError(
                "unique (run_id, tool_call_id) conflict but row not found on re-select"
            ) from None
        return existing, False


async def mark_running(session: AsyncSession, execution_id: str) -> ToolExecution:
    """Transition ``pending → running``. Leaves terminal fields null."""
    return await _transition(
        session,
        execution_id,
        to_status=TOOL_EXECUTION_STATUS_RUNNING,
        result=None,
        duration_ms=None,
        error_code=None,
    )


async def complete_execution(
    session: AsyncSession,
    execution_id: str,
    *,
    result: ToolResult,
    duration_ms: int,
) -> ToolExecution:
    """Transition ``running → completed`` with validated success result."""
    if duration_ms < 0:
        raise ToolExecutionRepositoryError("duration_ms must be >= 0")
    try:
        validate_tool_result_terminal_coupling(
            result,
            status=TOOL_EXECUTION_STATUS_COMPLETED,
            error_code=None,
        )
    except ValueError as exc:
        raise ToolResultCouplingError(str(exc)) from exc
    return await _transition(
        session,
        execution_id,
        to_status=TOOL_EXECUTION_STATUS_COMPLETED,
        result=result,
        duration_ms=duration_ms,
        error_code=None,
    )


async def fail_execution(
    session: AsyncSession,
    execution_id: str,
    *,
    result: ToolResult,
    duration_ms: int,
) -> ToolExecution:
    """Transition ``running → failed`` with validated failure result and code."""
    if duration_ms < 0:
        raise ToolExecutionRepositoryError("duration_ms must be >= 0")
    error_code = result.code
    try:
        validate_tool_result_terminal_coupling(
            result,
            status=TOOL_EXECUTION_STATUS_FAILED,
            error_code=error_code,
        )
    except ValueError as exc:
        raise ToolResultCouplingError(str(exc)) from exc
    assert error_code is not None  # narrowed by coupling validator
    return await _transition(
        session,
        execution_id,
        to_status=TOOL_EXECUTION_STATUS_FAILED,
        result=result,
        duration_ms=duration_ms,
        error_code=error_code,
    )


def load_stored_result(row: ToolExecution) -> ToolResult:
    """Parse and re-validate the terminal ``result_json`` for idempotent replay.

    Raises :class:`ToolExecutionRepositoryError` when the row is not terminal
    or stored JSON fails ``ToolResult`` / status coupling validation.
    """
    if row.status not in _TERMINAL:
        raise ToolExecutionRepositoryError(
            f"cannot load stored result for non-terminal status {row.status!r}"
        )
    if row.result_json is None:
        raise ToolExecutionRepositoryError(
            "terminal tool execution missing result_json"
        )
    try:
        parsed = parse_tool_result(row.result_json)
        validate_tool_result_terminal_coupling(
            parsed,
            status=row.status,
            error_code=row.error_code,
        )
    except ValueError as exc:
        raise ToolResultCouplingError(str(exc)) from exc
    return parsed


def serialize_result(result: ToolResult) -> dict[str, Any]:
    """Serialize a validated ``ToolResult`` for ``result_json`` storage."""
    return result.model_dump(mode="json")


async def _transition(
    session: AsyncSession,
    execution_id: str,
    *,
    to_status: str,
    result: ToolResult | None,
    duration_ms: int | None,
    error_code: str | None,
) -> ToolExecution:
    """Apply one allowed status transition with exact field coupling."""
    row = await session.get(ToolExecution, execution_id)
    if row is None:
        raise ToolExecutionNotFoundError(
            f"tool execution {execution_id!r} not found"
        )

    from_status = row.status
    allowed = _ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise InvalidToolTransitionError(
            f"transition {from_status!r} → {to_status!r} is not allowed"
        )

    now = utc_now()
    row.status = to_status
    row.updated_at = now

    if to_status == TOOL_EXECUTION_STATUS_RUNNING:
        # Leave duration_ms / result_json / error_code untouched so they remain
        # SQL NULL (JSON columns map Python None to JSON null by default).
        pass
    elif to_status in _TERMINAL:
        assert result is not None
        assert duration_ms is not None
        row.duration_ms = duration_ms
        row.result_json = serialize_result(result)
        row.error_code = error_code
    else:
        raise InvalidToolTransitionError(f"unsupported target status {to_status!r}")

    await session.flush()
    return row
