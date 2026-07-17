"""Agent-run create and transition repository.

Creates one run per unique user message (``state='running'``) and enforces the
approved status transitions with exact ``pending_approval_json``,
``error_code``, and ``completed_at`` coupling. Callers own the async session
and commit; this module never opens a session or finalizes the unit of work.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.time import utc_now
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    AGENT_RUN_STATE_FAILED,
    AGENT_RUN_STATE_INTERRUPTED,
    AGENT_RUN_STATE_RUNNING,
    AgentRun,
)

# Approved transitions only (Master §12.2):
# running → interrupted | completed | failed
# interrupted → running
# completed / failed are terminal.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    AGENT_RUN_STATE_RUNNING: frozenset(
        {
            AGENT_RUN_STATE_INTERRUPTED,
            AGENT_RUN_STATE_COMPLETED,
            AGENT_RUN_STATE_FAILED,
        }
    ),
    AGENT_RUN_STATE_INTERRUPTED: frozenset({AGENT_RUN_STATE_RUNNING}),
    AGENT_RUN_STATE_COMPLETED: frozenset(),
    AGENT_RUN_STATE_FAILED: frozenset(),
}


class AgentRunRepositoryError(Exception):
    """Base error for agent-run repository invariant violations."""


class RunNotFoundError(AgentRunRepositoryError):
    """Raised when the requested run primary key does not exist."""


class InvalidRunTransitionError(AgentRunRepositoryError):
    """Raised when a status transition is skipped, backward, or terminal."""


def _sql_null_json() -> Any:
    """Return a SQL NULL bind for JSON columns.

    SQLAlchemy's JSON type defaults to ``none_as_null=False``, so Python
    ``None`` becomes JSON ``null`` rather than SQL NULL. CHECK constraints on
    ``pending_approval_json`` require true SQL NULL when not interrupted.
    """
    return null()


async def create_run(
    session: AsyncSession,
    *,
    user_message_id: str,
    source_attachment_id: str | None = None,
) -> AgentRun:
    """Create one ``running`` run bound uniquely to *user_message_id*.

    Initial fields: ``state='running'`` with SQL-null approval/error/completion
    columns. Optional *source_attachment_id* records CV-scoped ownership without
    lifecycle logic. Uniqueness is enforced by the ``user_message_id`` unique
    constraint; a second create for the same message fails at flush. Does not
    finalize the caller's unit of work.
    """
    if source_attachment_id is not None and (
        not isinstance(source_attachment_id, str)
        or source_attachment_id.strip() == ""
    ):
        raise AgentRunRepositoryError(
            "source_attachment_id must be a non-empty string when set"
        )
    kwargs: dict[str, Any] = {
        "user_message_id": user_message_id,
        "state": AGENT_RUN_STATE_RUNNING,
    }
    if source_attachment_id is not None:
        kwargs["source_attachment_id"] = source_attachment_id
    run = AgentRun(**kwargs)
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: str) -> AgentRun | None:
    """Return the run with primary key *run_id*, or ``None`` if missing."""
    return await session.get(AgentRun, run_id)


async def get_run_by_user_message_id(
    session: AsyncSession,
    user_message_id: str,
) -> AgentRun | None:
    """Return the single run for *user_message_id*, or ``None`` if missing."""
    stmt = select(AgentRun).where(AgentRun.user_message_id == user_message_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_runs_for_user_message_ids(
    session: AsyncSession,
    user_message_ids: Sequence[str],
) -> list[AgentRun]:
    """Return runs whose ``user_message_id`` is in *user_message_ids*.

    Empty input yields an empty list without querying. At most one run exists
    per user message (unique constraint). Does not finalize the caller's unit
    of work.
    """
    if not user_message_ids:
        return []
    stmt = select(AgentRun).where(AgentRun.user_message_id.in_(list(user_message_ids)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_by_source_attachment_id(
    session: AsyncSession,
    attachment_id: str,
) -> list[AgentRun]:
    """Return runs with explicit CV ``source_attachment_id`` ownership.

    Does not finalize the caller's unit of work.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise AgentRunRepositoryError(
            "attachment_id must be a non-empty string"
        )
    stmt = select(AgentRun).where(
        AgentRun.source_attachment_id == attachment_id.strip()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_run(session: AsyncSession, run_id: str) -> bool:
    """Delete one agent run by primary key (cascades tool executions).

    Returns ``True`` when a row was deleted, ``False`` when already absent.
    Does not finalize the caller's unit of work or touch checkpoints.
    """
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise AgentRunRepositoryError("run_id must be a non-empty string")
    row = await session.get(AgentRun, run_id.strip())
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def interrupt_run(
    session: AsyncSession,
    run_id: str,
    *,
    pending_approval_json: dict[str, Any],
) -> AgentRun:
    """Transition ``running → interrupted`` and store the approval projection.

    *pending_approval_json* must be a non-empty mapping. Leaves
    ``completed_at`` null.
    """
    if not isinstance(pending_approval_json, dict) or not pending_approval_json:
        raise AgentRunRepositoryError(
            "pending_approval_json must be a non-empty mapping for interrupt"
        )
    return await _transition(
        session,
        run_id,
        to_state=AGENT_RUN_STATE_INTERRUPTED,
        pending_approval_json=pending_approval_json,
        error_code=None,
        set_completed_at=False,
    )


async def resume_run(session: AsyncSession, run_id: str) -> AgentRun:
    """Transition ``interrupted → running`` and clear ``pending_approval_json``."""
    return await _transition(
        session,
        run_id,
        to_state=AGENT_RUN_STATE_RUNNING,
        pending_approval_json=None,
        error_code=None,
        set_completed_at=False,
    )


async def complete_run(session: AsyncSession, run_id: str) -> AgentRun:
    """Transition ``running → completed`` and set ``completed_at`` (UTC)."""
    return await _transition(
        session,
        run_id,
        to_state=AGENT_RUN_STATE_COMPLETED,
        pending_approval_json=None,
        error_code=None,
        set_completed_at=True,
    )


async def fail_run(
    session: AsyncSession,
    run_id: str,
    *,
    error_code: str,
) -> AgentRun:
    """Transition ``running → failed`` with *error_code* and ``completed_at``."""
    if not isinstance(error_code, str) or error_code.strip() == "":
        raise AgentRunRepositoryError(
            "error_code must be a non-empty string for failed runs"
        )
    return await _transition(
        session,
        run_id,
        to_state=AGENT_RUN_STATE_FAILED,
        pending_approval_json=None,
        error_code=error_code,
        set_completed_at=True,
    )


async def _transition(
    session: AsyncSession,
    run_id: str,
    *,
    to_state: str,
    pending_approval_json: dict[str, Any] | None,
    error_code: str | None,
    set_completed_at: bool,
) -> AgentRun:
    """Apply one allowed transition with exact field coupling.

    Does not finalize the caller's unit of work.
    """
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise RunNotFoundError(f"agent run {run_id!r} not found")

    from_state = run.state
    allowed = _ALLOWED_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise InvalidRunTransitionError(
            f"transition {from_state!r} → {to_state!r} is not allowed"
        )

    now = utc_now()
    run.state = to_state
    run.updated_at = now

    if to_state == AGENT_RUN_STATE_INTERRUPTED:
        run.pending_approval_json = pending_approval_json
        run.completed_at = None
    elif to_state == AGENT_RUN_STATE_RUNNING:
        # Resume: clear projection with SQL NULL (not JSON null).
        run.pending_approval_json = _sql_null_json()
        run.completed_at = None
        run.error_code = None
    elif to_state == AGENT_RUN_STATE_COMPLETED:
        run.pending_approval_json = _sql_null_json()
        run.error_code = None
        run.completed_at = now
    elif to_state == AGENT_RUN_STATE_FAILED:
        run.pending_approval_json = _sql_null_json()
        run.error_code = error_code
        run.completed_at = now
    else:
        raise InvalidRunTransitionError(f"unsupported target state {to_state!r}")

    if set_completed_at and run.completed_at is None:
        run.completed_at = now
    if not set_completed_at and to_state not in (
        AGENT_RUN_STATE_COMPLETED,
        AGENT_RUN_STATE_FAILED,
    ):
        run.completed_at = None

    await session.flush()
    # SQL NULL JSON binds leave a ClauseElement in the identity map; normalize
    # in-memory values so callers observe Python None without a refresh that
    # would drop timezone awareness on SQLite datetimes.
    if to_state != AGENT_RUN_STATE_INTERRUPTED:
        set_committed_value(run, "pending_approval_json", None)
    return run
