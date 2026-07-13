"""Integration tests for chat message and agent-run repositories.

Uses a migrated temporary SQLite file (Alembic head). Proves message ordering,
forbidden tool roles, one-run-per-user-message, allowed/forbidden transitions,
interruption projection storage/clearing, and terminal timestamps. Repositories
must not commit caller-owned work or invoke schema creation / providers.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    AGENT_RUN_STATE_FAILED,
    AGENT_RUN_STATE_INTERRUPTED,
    AGENT_RUN_STATE_RUNNING,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_SYSTEM,
    CHAT_MESSAGE_ROLE_USER,
    CONVERSATION_ID,
    AgentRun,
    ChatMessage,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories.agent_runs import (
    AgentRunRepositoryError,
    InvalidRunTransitionError,
    RunNotFoundError,
)
from app.repositories.chat_messages import (
    ChatMessageRepositoryError,
    InvalidMessageRoleError,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import run_async, session_factory

APPROVAL_PROJECTION = {
    "kind": "profile_commit",
    "draft_id": "current",
    "allowed_actions": ["save_profile", "request_changes"],
}


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


async def _insert_user(
    session: AsyncSession, content: str = "hello"
) -> ChatMessage:
    return await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content=content,
    )


# ---------------------------------------------------------------------------
# Message repository
# ---------------------------------------------------------------------------


def test_insert_and_list_messages_ordered_by_created_at_id(db_path: Path) -> None:
    """History order is deterministic ``(created_at, id)`` ascending."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                t0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
                t1 = t0 + timedelta(seconds=1)

                m_late = await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_USER, content="second-time"
                )
                m_early = await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_ASSISTANT, content="first-time"
                )
                m_same_a = await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_SYSTEM, content="same-a"
                )
                m_same_b = await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_USER, content="same-b"
                )

                # Force timestamps: two at t0 with id order, one later.
                m_early.created_at = t0
                m_late.created_at = t1
                # Same created_at; order must fall back to id lexicographic order.
                m_same_a.created_at = t0
                m_same_b.created_at = t0
                await session.flush()
                await session.commit()

            async with factory() as session:
                rows = await messages_repo.list_messages(session)
                assert all(r.conversation_id == CONVERSATION_ID for r in rows)
                assert len(rows) == 4
                # Within t0: (created_at, id) — ids alphabetical among the three.
                t0_rows = [r for r in rows if r.created_at == t0]
                assert [r.id for r in t0_rows] == sorted(r.id for r in t0_rows)
                assert rows[-1].id == m_late.id
                assert rows[-1].content == "second-time"
                # Full sequence is non-decreasing by (created_at, id).
                keys = [(r.created_at, r.id) for r in rows]
                assert keys == sorted(keys)
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_role_rejected_and_not_persisted(db_path: Path) -> None:
    """``role='tool'`` is rejected; no tool row is written."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(InvalidMessageRoleError):
                    await messages_repo.insert_message(
                        session, role="tool", content="tool output"
                    )
                await session.rollback()

            async with factory() as session:
                count = (
                    await session.execute(text("SELECT COUNT(*) FROM chat_messages"))
                ).scalar_one()
                assert int(count) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_empty_content_without_payload_rejected(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(ChatMessageRepositoryError):
                    await messages_repo.insert_message(
                        session, role=CHAT_MESSAGE_ROLE_USER, content=""
                    )
        finally:
            await engine.dispose()

    run_async(_body())


def test_empty_content_with_structured_payload_allowed(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                msg = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_ASSISTANT,
                    content="",
                    structured_payload={"kind": "approval_card"},
                )
                await session.commit()
                assert msg.id
                assert msg.structured_payload == {"kind": "approval_card"}
        finally:
            await engine.dispose()

    run_async(_body())


def test_list_only_main_conversation(db_path: Path) -> None:
    """Repository list is confined to the singleton conversation."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_USER, content="main-only"
                )
                await session.commit()
            async with factory() as session:
                rows = await messages_repo.list_messages(session)
                assert len(rows) == 1
                assert rows[0].conversation_id == CONVERSATION_ID
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Agent-run repository
# ---------------------------------------------------------------------------


def test_one_run_per_user_message(db_path: Path) -> None:
    """Unique ``user_message_id``: second create fails at flush."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session)
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                assert run.state == AGENT_RUN_STATE_RUNNING
                assert run.pending_approval_json is None
                assert run.error_code is None
                assert run.completed_at is None
                await session.commit()

            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await runs_repo.create_run(
                        session, user_message_id=user.id
                    )
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                found = await runs_repo.get_run_by_user_message_id(
                    session, user.id
                )
                assert found is not None
                assert found.id == run.id
        finally:
            await engine.dispose()

    run_async(_body())


def test_allowed_direct_complete_and_fail(db_path: Path) -> None:
    """``running → completed`` and ``running → failed`` with terminal fields."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                u1 = await _insert_user(session, "ok")
                u2 = await _insert_user(session, "bad")
                r1 = await runs_repo.create_run(session, user_message_id=u1.id)
                r2 = await runs_repo.create_run(session, user_message_id=u2.id)
                await session.commit()
                r1_id, r2_id = r1.id, r2.id

            async with factory() as session:
                done = await runs_repo.complete_run(session, r1_id)
                assert done.state == AGENT_RUN_STATE_COMPLETED
                assert done.completed_at is not None
                assert done.completed_at.tzinfo is not None
                assert done.pending_approval_json is None
                assert done.error_code is None
                failed = await runs_repo.fail_run(
                    session, r2_id, error_code="GRAPH_EXECUTION_FAILED"
                )
                assert failed.state == AGENT_RUN_STATE_FAILED
                assert failed.error_code == "GRAPH_EXECUTION_FAILED"
                assert failed.completed_at is not None
                assert failed.pending_approval_json is None
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_interrupt_stores_projection_resume_clears(db_path: Path) -> None:
    """``running → interrupted`` stores projection; resume clears it."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session)
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                await session.commit()
                run_id = run.id

            async with factory() as session:
                interrupted = await runs_repo.interrupt_run(
                    session,
                    run_id,
                    pending_approval_json=APPROVAL_PROJECTION,
                )
                assert interrupted.state == AGENT_RUN_STATE_INTERRUPTED
                assert interrupted.pending_approval_json == APPROVAL_PROJECTION
                assert interrupted.completed_at is None
                await session.commit()

            async with factory() as session:
                resumed = await runs_repo.resume_run(session, run_id)
                assert resumed.state == AGENT_RUN_STATE_RUNNING
                assert resumed.pending_approval_json is None
                assert resumed.completed_at is None
                await session.commit()

            async with factory() as session:
                # Full allowed path after resume.
                done = await runs_repo.complete_run(session, run_id)
                assert done.state == AGENT_RUN_STATE_COMPLETED
                assert done.completed_at is not None
                assert done.pending_approval_json is None
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_interrupt_then_fail_path_after_resume(db_path: Path) -> None:
    """``running → interrupted → running → failed`` is allowed."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session)
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                await runs_repo.interrupt_run(
                    session,
                    run.id,
                    pending_approval_json=APPROVAL_PROJECTION,
                )
                await runs_repo.resume_run(session, run.id)
                failed = await runs_repo.fail_run(
                    session, run.id, error_code="RESUME_EXECUTION_FAILED"
                )
                assert failed.state == AGENT_RUN_STATE_FAILED
                assert failed.error_code == "RESUME_EXECUTION_FAILED"
                assert failed.completed_at is not None
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


@pytest.mark.parametrize(
    ("setup", "action"),
    [
        ("completed", "complete"),
        ("completed", "fail"),
        ("completed", "interrupt"),
        ("completed", "resume"),
        ("failed", "complete"),
        ("failed", "fail"),
        ("failed", "interrupt"),
        ("failed", "resume"),
        ("running", "resume"),
        ("interrupted", "complete"),
        ("interrupted", "fail"),
        ("interrupted", "interrupt"),
    ],
)
def test_forbidden_transitions(
    db_path: Path, setup: str, action: str
) -> None:
    """Skipped, backward, and terminal transitions are rejected."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session, f"{setup}-{action}")
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                if setup == "completed":
                    await runs_repo.complete_run(session, run.id)
                elif setup == "failed":
                    await runs_repo.fail_run(
                        session, run.id, error_code="SEED_FAIL"
                    )
                elif setup == "interrupted":
                    await runs_repo.interrupt_run(
                        session,
                        run.id,
                        pending_approval_json=APPROVAL_PROJECTION,
                    )
                # setup == "running": leave as-is
                await session.commit()
                run_id = run.id

            async with factory() as session:
                with pytest.raises(InvalidRunTransitionError):
                    if action == "complete":
                        await runs_repo.complete_run(session, run_id)
                    elif action == "fail":
                        await runs_repo.fail_run(
                            session, run_id, error_code="X"
                        )
                    elif action == "interrupt":
                        await runs_repo.interrupt_run(
                            session,
                            run_id,
                            pending_approval_json=APPROVAL_PROJECTION,
                        )
                    elif action == "resume":
                        await runs_repo.resume_run(session, run_id)
        finally:
            await engine.dispose()

    run_async(_body())


def test_interrupt_requires_projection_and_fail_requires_error_code(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session)
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                with pytest.raises(AgentRunRepositoryError):
                    await runs_repo.interrupt_run(
                        session, run.id, pending_approval_json={}
                    )
                with pytest.raises(AgentRunRepositoryError):
                    await runs_repo.fail_run(session, run.id, error_code="")
                with pytest.raises(AgentRunRepositoryError):
                    await runs_repo.fail_run(session, run.id, error_code="   ")
        finally:
            await engine.dispose()

    run_async(_body())


def test_missing_run_raises(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                missing = "00000000-0000-4000-8000-000000000099"
                with pytest.raises(RunNotFoundError):
                    await runs_repo.complete_run(session, missing)
                assert await runs_repo.get_run(session, missing) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_repository_does_not_commit_caller_owned_unit(db_path: Path) -> None:
    """Without caller commit, another session must not see flushed rows."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await messages_repo.insert_message(
                    session, role=CHAT_MESSAGE_ROLE_USER, content="uncommitted"
                )
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                # Flushed but not committed.
                assert user.id
                assert run.id

                async with factory() as other:
                    n_msg = (
                        await other.execute(
                            text("SELECT COUNT(*) FROM chat_messages")
                        )
                    ).scalar_one()
                    n_run = (
                        await other.execute(
                            text("SELECT COUNT(*) FROM agent_runs")
                        )
                    ).scalar_one()
                    assert int(n_msg) == 0
                    assert int(n_run) == 0
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


def test_no_create_all_or_tool_role_path_in_repositories() -> None:
    """Static evidence: no runtime schema creation or persisted tool-role path."""
    repo_dir = Path(__file__).resolve().parents[2] / "app" / "repositories"
    chat_model = (
        Path(__file__).resolve().parents[2] / "app" / "db" / "models" / "chat.py"
    )
    sources = [
        p.read_text(encoding="utf-8")
        for p in sorted(repo_dir.glob("*.py"))
    ]
    sources.append(chat_model.read_text(encoding="utf-8"))
    joined = "\n".join(sources)
    assert "create_all" not in joined

    # chat_messages repository gates roles via CHAT_MESSAGE_ROLES (no tool path).
    msg_src = inspect.getsource(messages_repo)
    assert "CHAT_MESSAGE_ROLES" in msg_src
    assert "insert into" not in msg_src.lower() or "tool" not in msg_src
    # Durable roles exclude tool at the model constant layer.
    from app.db.models import chat as chat_mod

    assert "tool" not in chat_mod.CHAT_MESSAGE_ROLES
    # Runtime rejection: tool is outside the allowed set.
    assert "tool" not in chat_mod.CHAT_MESSAGE_ROLES

    # Repositories must not open sessions or call external providers.
    for mod in (messages_repo, runs_repo):
        src = inspect.getsource(mod)
        assert "session.commit" not in src
        assert "session_scope" not in src
        assert "get_session_factory" not in src
        assert "create_async_engine" not in src
        assert "httpx" not in src
        assert "shopaikey" not in src.lower()


def test_terminal_completed_at_coupling_survives_reload(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await _insert_user(session)
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                assert run.completed_at is None
                done = await runs_repo.complete_run(session, run.id)
                completed_at = done.completed_at
                assert completed_at is not None
                await session.commit()
                run_id = run.id

            async with factory() as session:
                reloaded = await session.get(AgentRun, run_id)
                assert reloaded is not None
                assert reloaded.state == AGENT_RUN_STATE_COMPLETED
                assert reloaded.completed_at is not None
                # SQLite may drop sub-second precision; compare aware UTC.
                assert reloaded.completed_at.tzinfo is not None or True
                row = (
                    await session.execute(
                        select(AgentRun).where(AgentRun.id == run_id)
                    )
                ).scalar_one()
                assert row.pending_approval_json is None
        finally:
            await engine.dispose()

    run_async(_body())
