"""Tool execution repository: start/finish/fail, sanitization, rollback."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.enums import ToolExecutionStatus
from app.db.models.conversation import ToolExecution
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.tool_executions import (
    ToolExecutionNotFoundError,
    ToolExecutionRepository,
    ToolExecutionStateError,
    ToolExecutionValidationError,
    sanitize_arguments_summary,
    sanitize_error_code,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "tool_executions.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


async def _run_with_message(session: AsyncSession) -> object:
    msg = await ConversationRepository(session).append_message(
        role="user", content="use a tool"
    )
    return await AgentRunRepository(session).create_for_turn(
        message_id=msg.id,
        turn_idempotency_key=f"turn-{msg.id}",
    )


@pytest.mark.asyncio
async def test_start_finish_fail_lifecycle_and_fields(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            run = await _run_with_message(session)
            repo = ToolExecutionRepository(session)

            started = await repo.start(
                agent_run_id=run.id,
                tool_name="lookup_memory",
                arguments_summary="key=preferred_city",
            )
            assert started.status == ToolExecutionStatus.STARTED.value
            assert started.tool_name == "lookup_memory"
            assert started.arguments_summary == "key=preferred_city"
            assert started.duration_ms is None
            assert started.error_code is None

            finished = await repo.finish(
                started.id, duration_ms=42, arguments_summary="key=preferred_city ok"
            )
            assert finished.status == ToolExecutionStatus.SUCCEEDED.value
            assert finished.duration_ms == 42
            assert finished.error_code is None
            assert finished.arguments_summary == "key=preferred_city ok"

            # Replay finish is stable.
            again = await repo.finish(started.id, duration_ms=99)
            assert again.status == ToolExecutionStatus.SUCCEEDED.value
            assert again.duration_ms == 42  # original duration retained on replay

            other = await repo.start(
                agent_run_id=run.id,
                tool_name="noop_tool",
                arguments_summary=None,
            )
            failed = await repo.fail(
                other.id, error_code="tool_timeout", duration_ms=7
            )
            assert failed.status == ToolExecutionStatus.FAILED.value
            assert failed.error_code == "TOOL_TIMEOUT"
            assert failed.duration_ms == 7

            rows = await repo.list_for_run(run.id)
            assert len(rows) == 2
            assert [r.id for r in rows] == [started.id, other.id]


@pytest.mark.asyncio
async def test_secret_and_raw_argument_exclusion(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            run = await _run_with_message(session)
            repo = ToolExecutionRepository(session)

            with pytest.raises(ToolExecutionValidationError):
                await repo.start(
                    agent_run_id=run.id,
                    tool_name="save_job",
                    arguments_summary="password=hunter2",
                )
            with pytest.raises(ToolExecutionValidationError):
                await repo.start(
                    agent_run_id=run.id,
                    tool_name="save_job",
                    arguments_summary="Bearer sk-abc123",
                )
            with pytest.raises(ToolExecutionValidationError):
                await repo.start(
                    agent_run_id=run.id,
                    tool_name="save_job",
                    arguments_summary="C:\\Users\\me\\cv.pdf",
                )
            with pytest.raises(ToolExecutionValidationError):
                await repo.start(
                    agent_run_id=run.id,
                    tool_name="save_job",
                    arguments_summary="raw_document dump here",
                )
            with pytest.raises(ToolExecutionValidationError):
                sanitize_arguments_summary({"url": "https://example.com"})  # type: ignore[arg-type]
            with pytest.raises(ToolExecutionValidationError):
                sanitize_error_code("not a code!!!")

            assert sanitize_arguments_summary("  skill=python  ") == "skill=python"
            assert sanitize_error_code("tool-failed") == "TOOL_FAILED"

            count = (
                await session.execute(select(func.count()).select_from(ToolExecution))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_invalid_transitions_and_missing_ids(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            run = await _run_with_message(session)
            repo = ToolExecutionRepository(session)
            row = await repo.start(
                agent_run_id=run.id,
                tool_name="lookup_memory",
            )
            await repo.finish(row.id, duration_ms=1)

            with pytest.raises(ToolExecutionStateError):
                await repo.fail(row.id, error_code="TOO_LATE")

            with pytest.raises(ToolExecutionNotFoundError):
                await repo.finish(uuid4(), duration_ms=1)

            with pytest.raises(ToolExecutionValidationError, match="agent_run_id"):
                await repo.start(
                    agent_run_id=uuid4(),
                    tool_name="lookup_memory",
                )
            with pytest.raises(ToolExecutionValidationError, match="tool_name"):
                await repo.start(
                    agent_run_id=run.id,
                    tool_name="bad-name!",
                )
            with pytest.raises(ToolExecutionValidationError, match="duration_ms"):
                started = await repo.start(
                    agent_run_id=run.id,
                    tool_name="lookup_memory",
                )
                await repo.finish(started.id, duration_ms=-1)


@pytest.mark.asyncio
async def test_start_does_not_commit_and_rollback_discards(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        session = db.session_factory()
        try:
            run = await _run_with_message(session)
            repo = ToolExecutionRepository(session)
            row = await repo.start(
                agent_run_id=run.id,
                tool_name="lookup_memory",
                arguments_summary="key=city",
            )
            exec_id = row.id
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = ToolExecutionRepository(session)
            assert await repo.get_by_id(exec_id) is None
            count = (
                await session.execute(select(func.count()).select_from(ToolExecution))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_fail_replay_is_stable(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            run = await _run_with_message(session)
            repo = ToolExecutionRepository(session)
            row = await repo.start(
                agent_run_id=run.id,
                tool_name="lookup_memory",
            )
            failed = await repo.fail(row.id, error_code="TOOL_FAILED", duration_ms=3)
            again = await repo.fail(row.id, error_code="OTHER", duration_ms=9)
            assert again.id == failed.id
            assert again.error_code == "TOOL_FAILED"
            assert again.duration_ms == 3
