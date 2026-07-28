from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.chat import AgentActivity

_TERMINAL = frozenset({"completed", "failed"})
_ALLOWED = {
    "pending": frozenset({"running", "completed", "failed"}),
    "running": frozenset({"completed", "failed"}),
}


class AgentActivityRepositoryError(Exception):
    """Durable activity invariant violation."""


async def get_by_id(session: AsyncSession, activity_id: str) -> AgentActivity | None:
    return await session.get(AgentActivity, activity_id)


async def require_by_id(session: AsyncSession, activity_id: str) -> AgentActivity:
    row = await get_by_id(session, activity_id)
    if row is None:
        raise AgentActivityRepositoryError(f"agent activity {activity_id!r} not found")
    return row


async def list_for_run_ids(
    session: AsyncSession, run_ids: Sequence[str]
) -> list[AgentActivity]:
    if not run_ids:
        return []
    result = await session.scalars(
        select(AgentActivity)
        .where(AgentActivity.run_id.in_(list(dict.fromkeys(run_ids))))
        .order_by(AgentActivity.run_id, AgentActivity.sequence)
    )
    return list(result)


async def next_sequence(session: AsyncSession, run_id: str) -> int:
    value = await session.scalar(
        select(func.coalesce(func.max(AgentActivity.sequence), -1) + 1).where(
            AgentActivity.run_id == run_id
        )
    )
    return int(value or 0)


async def create_activity(
    session: AsyncSession,
    *,
    activity_id: str,
    run_id: str,
    kind: str,
    label: str,
    technical_name: str | None,
    state: str,
    duration_ms: int | None = None,
    error_code: str | None = None,
) -> AgentActivity:
    now = utc_now()
    row = AgentActivity(
        id=activity_id,
        run_id=run_id,
        sequence=await next_sequence(session, run_id),
        kind=kind,
        label=label.strip(),
        technical_name=technical_name.strip() if technical_name is not None else None,
        status=state,
        duration_ms=duration_ms,
        error_code=error_code,
        started_at=now,
        updated_at=now,
        completed_at=now if state in _TERMINAL else None,
    )
    session.add(row)
    await session.flush()
    return row


async def create_terminal_assistant_activity(
    session: AsyncSession,
    *,
    activity_id: str,
    run_id: str,
    label: str,
    technical_name: str,
    error_code: str,
) -> AgentActivity:
    return await create_activity(
        session,
        activity_id=activity_id,
        run_id=run_id,
        kind="assistant",
        label=label,
        technical_name=technical_name,
        state="failed",
        duration_ms=0,
        error_code=error_code,
    )


async def transition_activity(
    session: AsyncSession,
    row: AgentActivity,
    *,
    state: str,
    duration_ms: int | None,
    error_code: str | None,
) -> AgentActivity:
    if row.status == state:
        return row
    if row.status in _TERMINAL or state not in _ALLOWED.get(row.status, frozenset()):
        raise AgentActivityRepositoryError(
            f"invalid agent activity transition {row.status!r} -> {state!r}"
        )
    now = utc_now()
    row.status = state
    row.duration_ms = duration_ms
    row.error_code = error_code
    row.updated_at = now
    row.completed_at = now if state in _TERMINAL else None
    await session.flush()
    return row
