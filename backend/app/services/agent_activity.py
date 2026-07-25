from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_uuid
from app.db.models.chat import AgentActivity, ToolExecution
from app.db.session import session_scope
from app.repositories import agent_activities as activity_repo
from app.repositories.agent_activities import AgentActivityRepositoryError
from app.schemas.agent_activity import (
    ActivityKind,
    AgentActivityPayload,
    humanize_activity_name,
)
from app.schemas.common import ToolStatus


class AgentActivityServiceError(Exception):
    """Safe activity persistence failure."""


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def activity_payload(row: AgentActivity) -> AgentActivityPayload:
    started_at = _as_aware_utc(row.started_at)
    updated_at = _as_aware_utc(row.updated_at)
    assert started_at is not None and updated_at is not None
    return AgentActivityPayload(
        activity_id=row.id,
        run_id=row.run_id,
        sequence=row.sequence,
        kind=cast(ActivityKind, row.kind),
        label=row.label,
        technical_name=row.technical_name,
        state=cast(ToolStatus, row.status),
        started_at=started_at,
        updated_at=updated_at,
        completed_at=_as_aware_utc(row.completed_at),
        duration_ms=row.duration_ms,
        error_code=row.error_code,
    )


def legacy_tool_activity_view(
    tool: ToolExecution, sequence: int
) -> AgentActivityPayload:
    started_at = _as_aware_utc(tool.created_at)
    updated_at = _as_aware_utc(tool.updated_at)
    assert started_at is not None and updated_at is not None
    terminal = tool.status in ("completed", "failed")
    return AgentActivityPayload(
        activity_id=tool.id,
        run_id=tool.run_id,
        sequence=sequence,
        kind="tool",
        label=humanize_activity_name(tool.tool_name),
        technical_name=tool.tool_name,
        state=cast(ToolStatus, tool.status),
        started_at=started_at,
        updated_at=updated_at,
        completed_at=updated_at if terminal else None,
        duration_ms=tool.duration_ms,
        error_code=tool.error_code,
    )


class AgentActivityService:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def start_assistant(
        self, *, run_id: str, label: str, technical_name: str
    ) -> AgentActivityPayload:
        try:
            async with session_scope(self._factory) as session:
                row = await activity_repo.create_activity(
                    session,
                    activity_id=new_uuid(),
                    run_id=run_id,
                    kind="assistant",
                    label=label,
                    technical_name=technical_name,
                    state="running",
                )
            return activity_payload(row)
        except (SQLAlchemyError, AgentActivityRepositoryError) as exc:
            raise AgentActivityServiceError(
                "agent activity persistence failed"
            ) from exc

    async def record_tool(
        self,
        *,
        run_id: str,
        activity_id: str,
        label: str,
        technical_name: str,
        state: ToolStatus,
        duration_ms: int | None,
        error_code: str | None,
    ) -> AgentActivityPayload:
        try:
            async with session_scope(self._factory) as session:
                row = await activity_repo.get_by_id(session, activity_id)
                if row is None:
                    row = await activity_repo.create_activity(
                        session,
                        activity_id=activity_id,
                        run_id=run_id,
                        kind="tool",
                        label=label,
                        technical_name=technical_name,
                        state=state,
                        duration_ms=duration_ms,
                        error_code=error_code,
                    )
                else:
                    if row.run_id != run_id:
                        raise AgentActivityRepositoryError(
                            "agent activity run identity mismatch"
                        )
                    row = await activity_repo.transition_activity(
                        session,
                        row,
                        state=state,
                        duration_ms=duration_ms,
                        error_code=error_code,
                    )
            return activity_payload(row)
        except (SQLAlchemyError, AgentActivityRepositoryError) as exc:
            raise AgentActivityServiceError(
                "agent activity persistence failed"
            ) from exc

    async def finish(
        self,
        *,
        activity_id: str,
        state: Literal["completed", "failed"],
        duration_ms: int,
        error_code: str | None,
    ) -> AgentActivityPayload:
        try:
            async with session_scope(self._factory) as session:
                row = await activity_repo.require_by_id(session, activity_id)
                row = await activity_repo.transition_activity(
                    session,
                    row,
                    state=state,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
            return activity_payload(row)
        except (SQLAlchemyError, AgentActivityRepositoryError) as exc:
            raise AgentActivityServiceError(
                "agent activity persistence failed"
            ) from exc
