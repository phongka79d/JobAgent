"""Integration tests for per-run checkpoint lifecycle and chat execution.

Uses a temporary Alembic-migrated SQLite file plus injected graph/provider
fakes. No ShopAIKey network calls.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.agent.lifecycle import (
    CHECKPOINT_TABLE_NAMES,
    count_thread_checkpoints_on_disk,
    open_async_sqlite_saver,
    thread_run_config,
)
from app.db.enums import AgentRunState, MessageRole
from app.db.models.conversation import AgentRun, ChatMessage
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.tool_executions import ToolExecutionRepository
from app.services.chat_service import ChatService
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from tests.fakes.agent_tools import (
    ScriptedDecision,
    decision_text,
    decision_with_tool,
    make_approval_request_tool,
    make_echo_label_tool,
)
from typing_extensions import TypedDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@contextmanager
def _sqlite_path_env(db_path: Path) -> Iterator[None]:
    previous = os.environ.get("SQLITE_PATH")
    os.environ["SQLITE_PATH"] = str(db_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = previous


def upgrade_head(db_path: Path) -> None:
    with _sqlite_path_env(db_path):
        command.upgrade(_alembic_config(), "head")


def list_user_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {str(r[0]) for r in rows}


@asynccontextmanager
async def migrated_db(tmp_path: Path) -> AsyncIterator[tuple[Path, DatabaseSessionManager]]:
    db_path = tmp_path / "lifecycle.db"
    upgrade_head(db_path)
    manager = create_session_manager(db_path)
    try:
        yield db_path, manager
    finally:
        await manager.dispose()


class _ProbeState(TypedDict):
    conversation_id: str
    run_id: str
    messages_for_this_turn: list[Any]
    recent_context: list[Any]
    candidate_context: dict[str, Any] | None
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: dict[str, Any] | None
    final_assistant_text: str | None
    run_outcome: str | None
    response_persisted: bool
    checkpoint_cleaned: bool


def _production_approval_turn(
    *,
    final_text: str = "profile draft saved after approval",
) -> tuple[ScriptedDecision, list[Any]]:
    """Drive the production graph interrupt seam (await_approval) via a synthetic tool.

    Does not inject an alternate StateGraph — ChatService uses build_agent_graph.
    """
    decision = ScriptedDecision(
        [
            decision_with_tool(
                "propose_action",
                label="draft1",
                tool_call_id="c_approve_0",
            ),
            decision_text(final_text),
        ]
    )
    return decision, [make_approval_request_tool()]


def _failing_graph_factory(checkpointer: Any) -> Any:
    def fail_node(state: _ProbeState) -> dict[str, Any]:
        return {
            "error": {"code": "AGENT_DECISION_FAILED"},
            "run_outcome": "failed",
            "final_assistant_text": None,
            "response_persisted": True,
            "checkpoint_cleaned": True,
        }

    graph = StateGraph(_ProbeState)
    graph.add_node("fail", fail_node)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=checkpointer)


def _slow_graph_factory(
    checkpointer: Any,
    *,
    started: asyncio.Event,
    release: asyncio.Event,
) -> Any:
    async def slow_node(state: _ProbeState) -> dict[str, Any]:
        started.set()
        await release.wait()
        return {
            "final_assistant_text": "should-not-finish-after-disconnect",
            "run_outcome": "completed",
            "response_persisted": True,
            "checkpoint_cleaned": True,
        }

    graph = StateGraph(_ProbeState)
    graph.add_node("slow", slow_node)
    graph.add_edge(START, "slow")
    graph.add_edge("slow", END)
    return graph.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_completed_run_persists_assistant_before_checkpoint_cleanup(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        decision = ScriptedDecision([decision_text("final validated answer")])
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=[],
        )
        result = await service.start_turn(
            user_text="Help me improve my CV summary",
            turn_idempotency_key="turn-complete-1",
        )
        assert result.outcome == "completed"
        assert result.state == AgentRunState.COMPLETED.value
        assert result.replayed is False
        assert result.final_text == "final validated answer"
        assert result.assistant_message_id is not None
        assert result.checkpoints_deleted is True
        assert result.thread_id == str(result.run_id)

        # Application durable rows remain.
        async with manager.session_scope() as session:
            msgs = (
                await session.execute(
                    select(ChatMessage).order_by(
                        ChatMessage.created_at.asc(), ChatMessage.id.asc()
                    )
                )
            ).scalars().all()
            assert len(msgs) == 2
            assert msgs[0].role == MessageRole.USER.value
            assert msgs[1].role == MessageRole.ASSISTANT.value
            assert msgs[1].content == "final validated answer"
            run = await session.get(AgentRun, result.run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value
            assert run.error is None

        # Completed thread has no remaining checkpoint rows.
        remaining = await count_thread_checkpoints_on_disk(db_path, result.thread_id)
        assert remaining == 0


@pytest.mark.asyncio
async def test_interrupt_resume_same_thread_across_requests(tmp_path: Path) -> None:
    """Production graph await_approval interrupt across separate request lifecycles."""
    async with migrated_db(tmp_path) as (db_path, manager):
        decision, tools = _production_approval_turn(
            final_text="profile draft saved after approval"
        )
        # Default ChatService path: build_agent_graph (no alternate graph_factory).
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=tools,
        )
        first = await service.start_turn(
            user_text="Please update my candidate profile draft",
            turn_idempotency_key="turn-interrupt-1",
        )
        assert first.outcome == "interrupted"
        assert first.state == AgentRunState.INTERRUPTED.value
        assert first.pending_approval is not None
        assert first.pending_approval.get("kind") == "approval_required"
        assert first.assistant_message_id is None
        assert first.checkpoints_deleted is False
        thread_id = first.thread_id
        run_id = first.run_id
        assert thread_id == str(run_id)

        # Checkpoints retained after request 1 ends (new saver closed).
        ck_mid = await count_thread_checkpoints_on_disk(db_path, thread_id)
        assert ck_mid > 0

        # Separate request: new ChatService / saver on the same production graph
        # and durable thread identity. Resume re-enters await_approval then
        # agent_decision for the final validated assistant text.
        service2 = ChatService(
            manager,
            sqlite_path=db_path,
            decision=ScriptedDecision(
                [decision_text("profile draft saved after approval")]
            ),
            tools=[make_approval_request_tool()],
        )
        second = await service2.resume_run(
            run_id=run_id,
            resume_idempotency_key="resume-key-1",
            resume_value="yes",
        )
        assert second.run_id == run_id
        assert second.thread_id == thread_id
        assert second.outcome == "completed"
        assert second.state == AgentRunState.COMPLETED.value
        assert second.final_text == "profile draft saved after approval"
        assert second.assistant_message_id is not None
        assert second.checkpoints_deleted is True

        remaining = await count_thread_checkpoints_on_disk(db_path, thread_id)
        assert remaining == 0

        async with manager.session_scope() as session:
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value
            assistants = (
                await session.execute(
                    select(ChatMessage).where(
                        ChatMessage.role == MessageRole.ASSISTANT.value
                    )
                )
            ).scalars().all()
            assert len(assistants) == 1


@pytest.mark.asyncio
async def test_idempotent_resume_and_turn_keys_do_not_replay_writes(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        decision, tools = _production_approval_turn(
            final_text="saved after idempotent resume"
        )
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=tools,
        )
        first = await service.start_turn(
            user_text="Need profile approval path",
            turn_idempotency_key="turn-idem-1",
        )
        assert first.outcome == "interrupted"

        # Duplicate turn key: no second user message / run.
        dup_turn = await service.start_turn(
            user_text="Need profile approval path again",
            turn_idempotency_key="turn-idem-1",
        )
        assert dup_turn.replayed is True
        assert dup_turn.run_id == first.run_id

        async with manager.session_scope() as session:
            user_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.USER.value)
                )
            ).scalar_one()
            run_count = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert int(user_count) == 1
            assert int(run_count) == 1

        service_resume = ChatService(
            manager,
            sqlite_path=db_path,
            decision=ScriptedDecision(
                [decision_text("saved after idempotent resume")]
            ),
            tools=[make_approval_request_tool()],
        )
        resumed = await service_resume.resume_run(
            run_id=first.run_id,
            resume_idempotency_key="resume-idem-1",
            resume_value="ok",
        )
        assert resumed.outcome == "completed"
        assistant_id = resumed.assistant_message_id

        # Duplicate resume key: no second assistant message / graph write.
        again = await service_resume.resume_run(
            run_id=first.run_id,
            resume_idempotency_key="resume-idem-1",
            resume_value="ok",
        )
        assert again.replayed is True
        assert again.run_id == first.run_id
        assert again.assistant_message_id == assistant_id

        async with manager.session_scope() as session:
            assistants = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.ASSISTANT.value)
                )
            ).scalar_one()
            assert int(assistants) == 1


@pytest.mark.asyncio
async def test_failed_run_retains_outcome_and_checkpoints_or_safe_state(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        service = ChatService(
            manager,
            sqlite_path=db_path,
            graph_factory=_failing_graph_factory,
        )
        result = await service.start_turn(
            user_text="This will fail controllably",
            turn_idempotency_key="turn-fail-1",
        )
        assert result.outcome == "failed"
        assert result.state == AgentRunState.FAILED.value
        assert result.assistant_message_id is None
        assert result.checkpoints_deleted is False

        async with manager.session_scope() as session:
            run = await session.get(AgentRun, result.run_id)
            assert run is not None
            assert run.error is not None
            msgs = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            # User message only — no assistant success write.
            assert int(msgs) == 1


@pytest.mark.asyncio
async def test_tool_records_retained_after_completed_cleanup(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        decision = ScriptedDecision(
            [
                decision_with_tool("echo_label", label="x", tool_call_id="c0"),
                decision_text("done with tool"),
            ]
        )
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=[make_echo_label_tool()],
        )
        result = await service.start_turn(
            user_text="Match my profile to jobs",
            turn_idempotency_key="turn-tools-1",
        )
        assert result.outcome == "completed"
        assert result.checkpoints_deleted is True
        remaining = await count_thread_checkpoints_on_disk(db_path, result.thread_id)
        assert remaining == 0

        async with manager.session_scope() as session:
            tools = ToolExecutionRepository(session)
            rows = await tools.list_for_run(result.run_id)
            assert len(rows) >= 1
            assert all(r.tool_name for r in rows)
            run = await session.get(AgentRun, result.run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value
            assistants = (
                await session.execute(
                    select(ChatMessage).where(
                        ChatMessage.role == MessageRole.ASSISTANT.value
                    )
                )
            ).scalars().all()
            assert len(assistants) == 1


@pytest.mark.asyncio
async def test_disconnect_advances_to_safe_state_no_replay_on_reconnect(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        started = asyncio.Event()
        release = asyncio.Event()

        def factory(checkpointer: Any) -> Any:
            return _slow_graph_factory(
                checkpointer, started=started, release=release
            )

        service = ChatService(
            manager,
            sqlite_path=db_path,
            graph_factory=factory,
        )
        cancel = asyncio.Event()

        async def _run() -> Any:
            return await service.start_turn(
                user_text="long running turn",
                turn_idempotency_key="turn-disconnect-1",
                cancel_event=cancel,
            )

        task = asyncio.create_task(_run())
        await asyncio.wait_for(started.wait(), timeout=5.0)
        cancel.set()
        result = await asyncio.wait_for(task, timeout=5.0)
        # Allow slow node to finish after cancel path recorded disconnect.
        release.set()

        assert result.outcome in {"disconnected", "failed"}
        assert result.state == AgentRunState.FAILED.value
        assert result.assistant_message_id is None

        # Reconnect with same turn key must not replay writes / re-execute.
        service2 = ChatService(
            manager,
            sqlite_path=db_path,
            graph_factory=factory,
        )
        again = await service2.start_turn(
            user_text="long running turn",
            turn_idempotency_key="turn-disconnect-1",
        )
        assert again.replayed is True
        assert again.run_id == result.run_id

        async with manager.session_scope() as session:
            user_count = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.USER.value)
                )
            ).scalar_one()
            assert int(user_count) == 1
            assistants = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.ASSISTANT.value)
                )
            ).scalar_one()
            assert int(assistants) == 0


@pytest.mark.asyncio
async def test_no_application_orm_owns_checkpoint_tables(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        # Application migration tables only (no checkpoint names).
        tables = list_user_tables(db_path)
        for name in CHECKPOINT_TABLE_NAMES:
            assert name not in tables

        # After a saver setup, library tables appear without ORM models.
        async with open_async_sqlite_saver(db_path) as saver:
            await saver.setup()
            config = thread_run_config("probe-thread")
            del config
            _ = saver
        tables_after = list_user_tables(db_path)
        assert "checkpoints" in tables_after

        from app.db.base import Base

        orm_tables = set(Base.metadata.tables.keys())
        for name in CHECKPOINT_TABLE_NAMES:
            assert name not in orm_tables


@pytest.mark.asyncio
async def test_thread_config_identity_matches_run_id(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        decision = ScriptedDecision([decision_text("hi")])
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=[],
        )
        result = await service.start_turn(
            user_text="Hello about my CV",
            turn_idempotency_key="turn-id-match",
        )
        assert result.thread_id == str(result.run_id)
        assert UUID(result.thread_id) == result.run_id
        cfg = thread_run_config(result.thread_id)
        assert cfg["configurable"]["thread_id"] == result.thread_id


@pytest.mark.asyncio
async def test_interrupted_run_retains_user_message_and_run_row(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager):
        decision, tools = _production_approval_turn()
        service = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=tools,
        )
        result = await service.start_turn(
            user_text="Please propose a profile update for approval",
            turn_idempotency_key="turn-keep-1",
        )
        assert result.outcome == "interrupted"
        ck = await count_thread_checkpoints_on_disk(db_path, result.thread_id)
        assert ck > 0

        async with manager.session_scope() as session:
            runs = AgentRunRepository(session)
            run = await runs.get_by_id(result.run_id)
            assert run is not None
            assert run.state == AgentRunState.INTERRUPTED.value
            assert run.pending_approval is True
            conv = ConversationRepository(session)
            history = await conv.list_history()
            assert len(history) == 1
            assert history[0].role == MessageRole.USER.value
