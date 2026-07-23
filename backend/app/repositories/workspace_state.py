"""Flush-only workspace selection repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.profiles import WORKSPACE_STATE_ID, WorkspaceState


async def get_state(session: AsyncSession) -> WorkspaceState | None:
    return await session.get(WorkspaceState, WORKSPACE_STATE_ID)


async def get_active_profile_id(session: AsyncSession) -> str | None:
    state = await get_state(session)
    return state.active_profile_id if state is not None else None


async def set_active_profile_id(
    session: AsyncSession, profile_id: str | None
) -> WorkspaceState:
    state = await get_state(session)
    if state is None:
        state = WorkspaceState(
            id=WORKSPACE_STATE_ID,
            active_profile_id=profile_id,
            updated_at=utc_now(),
        )
        session.add(state)
    else:
        state.active_profile_id = profile_id
        state.updated_at = utc_now()
    await session.flush()
    return state
