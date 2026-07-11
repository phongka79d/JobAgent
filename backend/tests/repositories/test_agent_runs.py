"""Agent run repository: one-run-per-message, turn/resume idempotency, transitions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.db.enums import AgentRunState
from app.db.models.conversation import AgentRun
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.agent_runs import (
    AgentRunNotFoundError,
    AgentRunRepository,
    AgentRunStateError,
    AgentRunValidationError,
    langgraph_thread_id,
    sanitize_run_error,
)
from app.repositories.conversations import ConversationRepository
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "agent_runs.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


async def _user_message(
    session: AsyncSession, content: str = "hello"
) -> object:
    repo = ConversationRepository(session)
    return await repo.append_message(role="user", content=content)


@pytest.mark.asyncio
async def test_create_for_turn_one_run_per_message_and_thread_id(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "turn-1")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-key-1",
            )
            assert run.state == AgentRunState.PENDING.value
            assert run.message_id == message.id
            assert run.turn_idempotency_key == "turn-key-1"
            assert run.pending_approval is False
            assert run.error is None
            assert run.thread_id == str(run.id)
            assert langgraph_thread_id(run) == str(run.id)
            assert await repo.count_for_message(message.id) == 1

            # Same message cannot receive a second durable run via create.
            again = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="other-key-should-not-create",
            )
            assert again.id == run.id
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_duplicate_turn_idempotency_key_returns_existing_without_second_run(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            msg_a = await _user_message(session, "a")
            repo = AgentRunRepository(session)
            first = await repo.create_for_turn(
                message_id=msg_a.id,
                turn_idempotency_key="client-turn-99",
            )
            second = await repo.create_for_turn(
                message_id=msg_a.id,
                turn_idempotency_key="client-turn-99",
            )
            assert second.id == first.id
            assert second.turn_idempotency_key == "client-turn-99"
            assert (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one() == 1

            looked_up = await repo.get_by_turn_idempotency_key("client-turn-99")
            assert looked_up is not None
            assert looked_up.id == first.id


@pytest.mark.asyncio
async def test_same_run_resume_and_duplicate_resume_key_is_noop(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "need-approval")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-resume-1",
            )
            await repo.mark_running(run.id)
            interrupted = await repo.mark_interrupted(run.id)
            assert interrupted.state == AgentRunState.INTERRUPTED.value
            assert interrupted.pending_approval is True
            thread = interrupted.thread_id

            resumed = await repo.apply_resume(
                run.id, resume_idempotency_key="resume-key-1"
            )
            assert resumed.id == run.id
            assert resumed.thread_id == thread
            assert resumed.state == AgentRunState.RUNNING.value
            assert resumed.pending_approval is False
            assert resumed.resume_idempotency_key == "resume-key-1"

            # Replay same resume key: no second write / state flip.
            replay = await repo.apply_resume(
                run.id, resume_idempotency_key="resume-key-1"
            )
            assert replay.id == run.id
            assert replay.state == AgentRunState.RUNNING.value
            assert replay.resume_idempotency_key == "resume-key-1"

            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_invalid_and_stale_transitions_reject_and_keep_interrupted(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "state-machine")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-states-1",
            )
            await repo.mark_running(run.id)
            await repo.mark_interrupted(run.id)

            # Convenience helpers that require RUNNING see interrupted as stale.
            with pytest.raises(AgentRunStateError, match="stale state transition"):
                await repo.mark_completed(run.id)

            with pytest.raises(AgentRunStateError, match="stale state transition"):
                await repo.mark_running(run.id)

            # Generic FSM rejects terminal reverse and non-edges as invalid.
            with pytest.raises(AgentRunStateError, match="invalid state transition"):
                await repo.transition(run.id, to_state=AgentRunState.PENDING)

            with pytest.raises(AgentRunStateError, match="invalid state transition"):
                await repo.transition(run.id, to_state=AgentRunState.COMPLETED)

            # Interrupted outcome retained and still resumable.
            current = await repo.get_by_id(run.id)
            assert current is not None
            assert current.state == AgentRunState.INTERRUPTED.value
            assert current.pending_approval is True

            resumed = await repo.apply_resume(
                run.id, resume_idempotency_key="resume-after-reject"
            )
            assert resumed.state == AgentRunState.RUNNING.value

            await repo.mark_completed(run.id)
            with pytest.raises(AgentRunStateError):
                await repo.mark_failed(run.id, error="too late")
            terminal = await repo.get_by_id(run.id)
            assert terminal is not None
            assert terminal.state == AgentRunState.COMPLETED.value


@pytest.mark.asyncio
async def test_mark_failed_sanitizes_error_and_rejects_unknown_run(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "fail-me")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-fail-1",
            )
            await repo.mark_running(run.id)
            failed = await repo.mark_failed(
                run.id, error="  provider timeout after 30s  "
            )
            assert failed.state == AgentRunState.FAILED.value
            assert failed.error == "provider timeout after 30s"
            assert failed.pending_approval is False

            secret_failed = sanitize_run_error("Bearer sk-secret-value")
            assert secret_failed == "run_failed"
            path_failed = sanitize_run_error("C:\\Users\\secret\\file.txt")
            assert path_failed == "run_failed"

            with pytest.raises(AgentRunNotFoundError):
                await repo.mark_failed(uuid4(), error="missing")


@pytest.mark.asyncio
async def test_create_does_not_commit_and_rollback_discards_run(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        session = db.session_factory()
        try:
            message = await _user_message(session, "rollback")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-rollback-1",
            )
            run_id = run.id
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = AgentRunRepository(session)
            assert await repo.get_by_id(run_id) is None
            assert await repo.get_by_turn_idempotency_key("turn-rollback-1") is None
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_invalid_idempotency_keys_and_missing_message_fail_closed(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = AgentRunRepository(session)
            with pytest.raises(AgentRunValidationError, match="turn_idempotency_key"):
                await repo.create_for_turn(
                    message_id=uuid4(),
                    turn_idempotency_key="",
                )
            with pytest.raises(AgentRunValidationError, match="turn_idempotency_key"):
                await repo.create_for_turn(
                    message_id=uuid4(),
                    turn_idempotency_key="has space",
                )
            with pytest.raises(AgentRunValidationError, match="message_id not found"):
                await repo.create_for_turn(
                    message_id=uuid4(),
                    turn_idempotency_key="valid-key-1",
                )
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_resume_rejected_when_not_interrupted(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "no-interrupt")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-no-int-1",
            )
            with pytest.raises(AgentRunStateError):
                await repo.apply_resume(run.id, resume_idempotency_key="r1")
            await repo.mark_running(run.id)
            with pytest.raises(AgentRunStateError):
                await repo.apply_resume(run.id, resume_idempotency_key="r1")


@pytest.mark.asyncio
async def test_conflict_path_duplicate_turn_key_returns_existing_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When pre-checks miss an existing unique turn key, create resolves safely.

    Simulates a concurrent miss: lookups return None while the row already
    exists; ON CONFLICT DO NOTHING + select returns the existing run without
    raising a duplicate/retry error or requiring caller rollback.
    """
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "race")
            existing = await AgentRunRepository(session).create_for_turn(
                message_id=message.id,
                turn_idempotency_key="race-key",
            )
            existing_id = existing.id
            existing_thread = existing.thread_id
            message_id = message.id

        async with db.session_scope() as session:
            repo = AgentRunRepository(session)
            key_calls = {"n": 0}
            real_by_key = repo.get_by_turn_idempotency_key
            real_by_message = repo.get_by_message_id

            async def miss_then_real_key(turn_idempotency_key: str) -> AgentRun | None:
                key_calls["n"] += 1
                if key_calls["n"] == 1:
                    return None
                return await real_by_key(turn_idempotency_key)

            async def miss_precheck_message(mid: UUID) -> AgentRun | None:
                # Force create path past both pre-checks; post-insert selects use
                # the real methods after the first key lookup miss.
                if key_calls["n"] <= 1:
                    return None
                return await real_by_message(mid)

            monkeypatch.setattr(repo, "get_by_turn_idempotency_key", miss_then_real_key)
            monkeypatch.setattr(repo, "get_by_message_id", miss_precheck_message)

            resolved = await repo.create_for_turn(
                message_id=message_id,
                turn_idempotency_key="race-key",
            )
            assert resolved.id == existing_id
            assert resolved.thread_id == existing_thread
            assert resolved.turn_idempotency_key == "race-key"
            assert key_calls["n"] >= 2

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_concurrent_duplicate_turn_keys_independent_sessions_one_run(
    tmp_path: Path,
) -> None:
    """Independent sessions racing the same turn key produce one durable run."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "concurrent-turn")
            message_id = message.id

        async def create_in_own_transaction() -> tuple[UUID, str]:
            async with db.session_scope() as session:
                run = await AgentRunRepository(session).create_for_turn(
                    message_id=message_id,
                    turn_idempotency_key="client-turn-concurrent",
                )
                return run.id, run.thread_id

        results = await asyncio.gather(
            create_in_own_transaction(),
            create_in_own_transaction(),
            create_in_own_transaction(),
        )
        ids = {r[0] for r in results}
        threads = {r[1] for r in results}
        assert len(ids) == 1
        assert len(threads) == 1
        assert str(next(iter(ids))) == next(iter(threads))

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 1
            again = await AgentRunRepository(session).create_for_turn(
                message_id=message_id,
                turn_idempotency_key="client-turn-concurrent",
            )
            assert again.id == next(iter(ids))
            assert again.thread_id == next(iter(threads))


@pytest.mark.asyncio
async def test_concurrent_duplicate_resume_keys_independent_sessions_one_action(
    tmp_path: Path,
) -> None:
    """Independent sessions racing the same resume key apply one state change."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            message = await _user_message(session, "concurrent-resume")
            repo = AgentRunRepository(session)
            run = await repo.create_for_turn(
                message_id=message.id,
                turn_idempotency_key="turn-concurrent-resume",
            )
            await repo.mark_running(run.id)
            await repo.mark_interrupted(run.id)
            run_id = run.id
            thread = run.thread_id

        async def resume_in_own_transaction() -> tuple[UUID, str, str, bool]:
            async with db.session_scope() as session:
                resumed = await AgentRunRepository(session).apply_resume(
                    run_id, resume_idempotency_key="resume-concurrent-1"
                )
                return (
                    resumed.id,
                    resumed.thread_id,
                    resumed.state,
                    resumed.pending_approval,
                )

        results = await asyncio.gather(
            resume_in_own_transaction(),
            resume_in_own_transaction(),
            resume_in_own_transaction(),
        )
        assert {r[0] for r in results} == {run_id}
        assert {r[1] for r in results} == {thread}
        assert {r[2] for r in results} == {AgentRunState.RUNNING.value}
        assert {r[3] for r in results} == {False}

        async with db.session_scope() as session:
            repo = AgentRunRepository(session)
            current = await repo.get_by_id(run_id)
            assert current is not None
            assert current.state == AgentRunState.RUNNING.value
            assert current.resume_idempotency_key == "resume-concurrent-1"
            assert current.pending_approval is False
            assert current.thread_id == thread
            # Replay same key remains a no-op outcome (no extra run row).
            replay = await repo.apply_resume(
                run_id, resume_idempotency_key="resume-concurrent-1"
            )
            assert replay.id == run_id
            assert replay.state == AgentRunState.RUNNING.value
            count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert count == 1
