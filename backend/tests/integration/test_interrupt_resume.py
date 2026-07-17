"""Integration tests for durable interrupt/resume and interruption guard.

Uses a migrated temporary SQLite file and the test-only synthetic interrupting
tool (no provider/domain calls). Proves both approval branches across a new
request boundary, single side effect + terminal tool result, retained interrupt
checkpoint, terminal cleanup, no-op terminal resume, invalid-action stability,
and blocked new turns with zero inserts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.agent.graph import build_agent_graph
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    AGENT_RUN_STATE_INTERRUPTED,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_RUNNING,
    AgentRun,
    ChatMessage,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.sse import SseEvent, parse_sse_event
from app.services import chat_turns
from app.services.chat_turns import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    ERROR_INVALID_APPROVAL_ACTION,
    ERROR_RUN_NOT_RESUMABLE,
    ChatTurnError,
    count_chat_messages,
    create_user_turn,
    stream_chat_turn,
    stream_resume,
)
from app.tools.registry import ToolRegistry, production_registry
from langchain_core.messages import AIMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes.fake_chat_model import FakeChatModel
from tests.fakes.synthetic_tool import (
    SYNTHETIC_ALLOWED_ACTIONS,
    SYNTHETIC_APPROVAL_KIND,
    SYNTHETIC_TOOL_NAME,
    build_synthetic_interrupt_tool,
)
from tests.support.db_migration import run_async, session_factory

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def _ai_text(content: str) -> AIMessage:
    return AIMessage(content=content)


def _ai_tool_call(name: str, call_id: str = "call-synth-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": {},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


async def _collect(gen: AsyncIterator[SseEvent]) -> list[SseEvent]:
    return [event async for event in gen]


def _names(events: list[SseEvent]) -> list[str]:
    return [e.event for e in events]


def _factory(db_path: Path) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    engine = build_async_engine(db_path)
    return engine, session_factory(engine)


def _bundle(
    factory: async_sessionmaker[AsyncSession],
    counter: dict[str, int],
) -> tuple[Any, FakeChatModel, dict[str, int]]:
    tool = build_synthetic_interrupt_tool(
        session_factory=factory,
        side_effect_counter=counter,
    )
    model = FakeChatModel(
        responses=[
            _ai_tool_call(SYNTHETIC_TOOL_NAME),
            _ai_text("Finished after approval decision."),
        ]
    )
    bundle = build_agent_graph(
        model=model,
        registry=ToolRegistry([tool]),
        tool_loop_limit=6,
    )
    return bundle, model, counter


# ---------------------------------------------------------------------------
# Both approval branches
# ---------------------------------------------------------------------------


def test_interrupt_resume_approve_branch(db_path: Path) -> None:
    """Approve resumes same run/thread, one side effect, one terminal result."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _model, counter = _bundle(factory, counter)

            events = await _collect(
                stream_chat_turn(
                    message="please run synthetic approval",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            names = _names(events)
            assert names[0] == "run_started"
            assert names[-1] == "approval_required"
            assert "run_completed" not in names
            assert counter["n"] == 0

            # 03C: interrupt keeps one durable row running; emit pending+running.
            interrupt_statuses = [e for e in events if e.event == "tool_status"]
            assert [s.payload.status for s in interrupt_statuses] == [
                "pending",
                "running",
            ]
            durable_exec_id = interrupt_statuses[0].payload.tool_execution_id
            assert all(
                s.payload.tool_execution_id == durable_exec_id
                for s in interrupt_statuses
            )
            assert all(
                s.payload.tool_name == SYNTHETIC_TOOL_NAME for s in interrupt_statuses
            )

            approval = events[-1]
            assert approval.event == "approval_required"
            assert approval.payload.state == "interrupted"
            assert approval.payload.kind == SYNTHETIC_APPROVAL_KIND
            assert list(approval.payload.allowed_actions) == list(
                SYNTHETIC_ALLOWED_ACTIONS
            )
            run_id = approval.run_id

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                assert run.pending_approval_json is not None
                assert run.pending_approval_json["kind"] == SYNTHETIC_APPROVAL_KIND
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_RUNNING
                assert tools[0].result_json is None
                assert tools[0].id == durable_exec_id

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is True

            # New request boundary: re-open checkpointer via stream_resume.
            # Fresh model responses for post-tool agent turn after resume.
            tool2 = build_synthetic_interrupt_tool(
                session_factory=factory,
                side_effect_counter=counter,
            )
            model2 = FakeChatModel(
                responses=[_ai_text("Approved and done.")]
            )
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )

            resume_events = await _collect(
                stream_resume(
                    run_id=run_id,
                    action="approve",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            rnames = _names(resume_events)
            assert rnames[0] == "run_started"
            assert resume_events[0].payload.resumed is True
            assert "run_completed" in rnames
            assert rnames[-1] == "run_completed"
            assert "approval_required" not in rnames
            assert counter["n"] == 1

            # 03C: resume terminalizes the same execution id (no second pending).
            resume_statuses = [
                e for e in resume_events if e.event == "tool_status"
            ]
            assert [s.payload.status for s in resume_statuses] == ["completed"]
            assert resume_statuses[0].payload.tool_execution_id == durable_exec_id
            assert resume_statuses[0].payload.duration_ms is not None
            assert resume_statuses[0].payload.summary == "synthetic approval accepted"
            assert resume_statuses[0].payload.error_code is None

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                assert run.pending_approval_json is None
                assert run.completed_at is not None
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tools[0].error_code is None
                assert tools[0].id == durable_exec_id
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("action") == "approve"
                assert stored.data.get("committed") is True
                assistants = (
                    await session.execute(
                        select(func.count())
                        .select_from(ChatMessage)
                        .where(ChatMessage.role == CHAT_MESSAGE_ROLE_ASSISTANT)
                    )
                ).scalar_one()
                assert int(assistants) >= 1

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is False
        finally:
            await engine.dispose()

    run_async(_body())


def test_interrupt_resume_reject_branch(db_path: Path) -> None:
    """Reject resumes same run/thread with committed=false, one side effect."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _, counter = _bundle(factory, counter)
            events = await _collect(
                stream_chat_turn(
                    message="synthetic reject path",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            run_id = events[-1].run_id
            assert events[-1].event == "approval_required"
            assert counter["n"] == 0

            tool2 = build_synthetic_interrupt_tool(
                session_factory=factory,
                side_effect_counter=counter,
            )
            model2 = FakeChatModel(responses=[_ai_text("Rejected path done.")])
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )
            resume_events = await _collect(
                stream_resume(
                    run_id=run_id,
                    action="reject",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert _names(resume_events)[-1] == "run_completed"
            assert counter["n"] == 1

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("action") == "reject"
                assert stored.data.get("committed") is False

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is False
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Guard, invalid action, terminal no-op
# ---------------------------------------------------------------------------


def test_new_turn_blocked_during_interrupt_zero_inserts(db_path: Path) -> None:
    """APPROVAL_ACTION_REQUIRED before insert; message/run counts unchanged."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _, _ = _bundle(factory, counter)
            events = await _collect(
                stream_chat_turn(
                    message="start interrupt",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert events[-1].event == "approval_required"

            async with factory() as session:
                before_msgs = await count_chat_messages(session)
                before_runs = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(AgentRun)
                        )
                    ).scalar_one()
                )

            with pytest.raises(ChatTurnError) as exc_info:
                await create_user_turn(
                    message="should be blocked",
                    session_factory=factory,
                )
            assert exc_info.value.code == ERROR_APPROVAL_ACTION_REQUIRED

            async with factory() as session:
                after_msgs = await count_chat_messages(session)
                after_runs = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(AgentRun)
                        )
                    ).scalar_one()
                )
                assert after_msgs == before_msgs
                assert after_runs == before_runs
                users = (
                    await session.execute(
                        select(func.count())
                        .select_from(ChatMessage)
                        .where(ChatMessage.role == CHAT_MESSAGE_ROLE_USER)
                    )
                ).scalar_one()
                assert int(users) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_invalid_action_leaves_interruption_unchanged(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _, _ = _bundle(factory, counter)
            events = await _collect(
                stream_chat_turn(
                    message="interrupt for invalid action",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            run_id = events[-1].run_id
            projection_before: dict[str, Any]
            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                projection_before = dict(run.pending_approval_json or {})

            with pytest.raises(ChatTurnError) as exc_info:
                await _collect(
                    stream_resume(
                        run_id=run_id,
                        action="not_an_allowed_action",
                        session_factory=factory,
                        sqlite_path=db_path,
                    )
                )
            assert exc_info.value.code == ERROR_INVALID_APPROVAL_ACTION
            assert counter["n"] == 0

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                assert run.pending_approval_json == projection_before

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is True
        finally:
            await engine.dispose()

    run_async(_body())


def test_terminal_resume_is_noop_no_graph_or_side_effect(db_path: Path) -> None:
    """Resuming completed/failed emits persisted terminal state only."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _, counter = _bundle(factory, counter)
            events = await _collect(
                stream_chat_turn(
                    message="full lifecycle then noop",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            run_id = events[-1].run_id
            tool2 = build_synthetic_interrupt_tool(
                session_factory=factory,
                side_effect_counter=counter,
            )
            model2 = FakeChatModel(responses=[_ai_text("ok")])
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )
            await _collect(
                stream_resume(
                    run_id=run_id,
                    action="approve",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert counter["n"] == 1
            side_effects_after_complete = counter["n"]

            # Model that would fail loudly if the graph were re-invoked.
            boom_model = FakeChatModel(
                responses=[_ai_tool_call(SYNTHETIC_TOOL_NAME)]
            )
            boom_bundle = build_agent_graph(
                model=boom_model,
                registry=ToolRegistry(
                    [
                        build_synthetic_interrupt_tool(
                            session_factory=factory,
                            side_effect_counter=counter,
                        )
                    ]
                ),
            )
            noop = await _collect(
                stream_resume(
                    run_id=run_id,
                    action="approve",
                    graph_bundle=boom_bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert _names(noop) == ["run_started", "run_completed"]
            assert noop[0].payload.resumed is True
            assert noop[-1].payload.state == "completed"
            assert boom_model.invoke_count == 0
            assert counter["n"] == side_effects_after_complete

            # No extra tool rows.
            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_rapid_repeated_approval_accepts_once_exact_counts(db_path: Path) -> None:
    """Rapid double approval: one side effect, one ToolResult row, second is no-op.

    Covers sequential re-entry (double-click after accept) and concurrent claims
    while the first resume still owns the run (second is not resumable).
    """
    import asyncio

    async def _body() -> None:
        engine, factory = _factory(db_path)
        counter: dict[str, int] = {"n": 0}
        try:
            bundle, _, counter = _bundle(factory, counter)
            events = await _collect(
                stream_chat_turn(
                    message="rapid double approval",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert events[-1].event == "approval_required"
            run_id = events[-1].run_id
            assert counter["n"] == 0

            # --- Concurrent rapid claims: exactly one accepts the interrupt. ---
            model_a = FakeChatModel(responses=[_ai_text("first winner")])
            model_b = FakeChatModel(responses=[_ai_text("should not run graph")])
            bundle_a = build_agent_graph(
                model=model_a,
                registry=ToolRegistry(
                    [
                        build_synthetic_interrupt_tool(
                            session_factory=factory,
                            side_effect_counter=counter,
                        )
                    ]
                ),
            )
            bundle_b = build_agent_graph(
                model=model_b,
                registry=ToolRegistry(
                    [
                        build_synthetic_interrupt_tool(
                            session_factory=factory,
                            side_effect_counter=counter,
                        )
                    ]
                ),
            )

            outcomes = await asyncio.gather(
                _collect(
                    stream_resume(
                        run_id=run_id,
                        action="approve",
                        graph_bundle=bundle_a,
                        session_factory=factory,
                        sqlite_path=db_path,
                    )
                ),
                _collect(
                    stream_resume(
                        run_id=run_id,
                        action="approve",
                        graph_bundle=bundle_b,
                        session_factory=factory,
                        sqlite_path=db_path,
                    )
                ),
                return_exceptions=True,
            )

            successes = [o for o in outcomes if not isinstance(o, BaseException)]
            failures = [o for o in outcomes if isinstance(o, BaseException)]
            # Winner finishes the run; loser is either still-running rejection
            # or terminal no-op if the winner already committed.
            assert len(successes) >= 1
            assert counter["n"] == 1

            completed_streams = 0
            for o in successes:
                names = _names(o)  # type: ignore[arg-type]
                if names[-1] == "run_completed":
                    completed_streams += 1
                # Terminal no-op stream is exactly run_started → run_completed.
                if names == ["run_started", "run_completed"]:
                    assert len(names) == 2
            assert completed_streams >= 1

            for err in failures:
                assert isinstance(err, ChatTurnError)
                assert err.code == ERROR_RUN_NOT_RESUMABLE

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("action") == "approve"
                assert stored.data.get("committed") is True

            # --- Sequential rapid re-entry after accept: terminal no-op. ---
            boom_model = FakeChatModel(
                responses=[_ai_tool_call(SYNTHETIC_TOOL_NAME)]
            )
            boom_bundle = build_agent_graph(
                model=boom_model,
                registry=ToolRegistry(
                    [
                        build_synthetic_interrupt_tool(
                            session_factory=factory,
                            side_effect_counter=counter,
                        )
                    ]
                ),
            )
            side_effects_before_third = counter["n"]
            third = await _collect(
                stream_resume(
                    run_id=run_id,
                    action="approve",
                    graph_bundle=boom_bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            )
            assert _names(third) == ["run_started", "run_completed"]
            assert boom_model.invoke_count == 0
            assert counter["n"] == side_effects_before_third == 1

            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_unrecoverable_failure_retains_user_turn(db_path: Path) -> None:
    """Controlled graph failure marks run failed and keeps the user message."""

    async def _body() -> None:
        from app.agent.graph import ERROR_TOOL_LOOP_LIMIT_EXCEEDED, initial_graph_state
        from app.agent.runner import stream_agent_run
        from langchain_core.tools import tool as lc_tool

        engine, factory = _factory(db_path)
        try:

            @lc_tool
            def noop() -> str:
                """noop"""
                return "x"

            turn = await create_user_turn(
                message="will fail controlled",
                session_factory=factory,
            )
            model = FakeChatModel(responses=[_ai_tool_call("noop")])
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([noop]),
                tool_loop_limit=1,
            )
            # tool_iteration_count already at limit → controlled failure.
            state = initial_graph_state(
                run_id=turn.run_id,
                user_text=turn.content,
                tool_iteration_count=1,
            )

            async def on_term(o: Any) -> bool:
                if o.kind == "failed":
                    await chat_turns.persist_terminal_failure(
                        run_id=o.run_id,
                        error_code=o.error_code or "AGENT_EXECUTION_FAILED",
                        session_factory=factory,
                    )
                    return True
                if o.kind == "completed":
                    await chat_turns.persist_terminal_success(
                        run_id=o.run_id,
                        assistant_text=o.assistant_text,
                        session_factory=factory,
                    )
                    return True
                return False

            events = await _collect(
                stream_agent_run(
                    run_id=turn.run_id,
                    input_state=state,
                    graph_bundle=bundle,
                    sqlite_path=db_path,
                    on_durable_terminal=on_term,
                    include_assistant_status=False,
                )
            )
            assert _names(events)[-1] == "run_failed"
            assert events[-1].payload.error_code == ERROR_TOOL_LOOP_LIMIT_EXCEEDED

            async with factory() as session:
                run = await runs_repo.get_run(session, turn.run_id)
                assert run is not None
                assert run.state == "failed"
                assert run.error_code == ERROR_TOOL_LOOP_LIMIT_EXCEEDED
                user = await session.get(ChatMessage, turn.user_message_id)
                assert user is not None
                assert user.role == CHAT_MESSAGE_ROLE_USER
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Production registry / ownership
# ---------------------------------------------------------------------------


def test_production_registry_seven_tools_and_synthetic_is_test_only() -> None:
    reg = production_registry()
    names = reg.tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
    assert SYNTHETIC_TOOL_NAME not in names

    prod_registry = (BACKEND_ROOT / "app" / "tools" / "registry.py").read_text(
        encoding="utf-8"
    )
    # Exclude docstring mentions of banned helpers by checking code tokens only.
    assert "build_synthetic" not in prod_registry
    assert "interrupt(" not in prod_registry
    assert "build_production_job_tools" in prod_registry
    assert "build_production_match_tools" in prod_registry
    assert "build_production_active_cv_tools" in prod_registry

    synth_path = BACKEND_ROOT / "tests" / "fakes" / "synthetic_tool.py"
    assert synth_path.is_file()
    app_tools = BACKEND_ROOT / "app" / "tools"
    for path in app_tools.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "synthetic_interrupt" not in text
        assert "build_synthetic_interrupt_tool" not in text

    chat_turns_src = (
        BACKEND_ROOT / "app" / "services" / "chat_turns.py"
    ).read_text(encoding="utf-8")
    assert "APPROVAL_ACTION_REQUIRED" in chat_turns_src
    assert "pending_approval" in chat_turns_src
    # Generic interruption — no domain profile/CV action names hard-coded.
    assert "commit_profile" not in chat_turns_src
    assert "save_profile" not in chat_turns_src
    assert "request_changes" not in chat_turns_src
    assert "propose_profile" not in chat_turns_src
    # Optional draft_id passthrough remains domain-agnostic.
    assert "draft_id" in chat_turns_src


def test_sse_events_validate() -> None:
    """Smoke: approval_required envelope matches (01A) contract."""
    from app.core.ids import new_uuid
    from app.core.time import utc_now

    event = parse_sse_event(
        {
            "event": "approval_required",
            "event_id": new_uuid(),
            "run_id": new_uuid(),
            "timestamp": utc_now(),
            "payload": {
                "state": "interrupted",
                "kind": SYNTHETIC_APPROVAL_KIND,
                "allowed_actions": list(SYNTHETIC_ALLOWED_ACTIONS),
                "card": {"tool_name": SYNTHETIC_TOOL_NAME},
            },
        }
    )
    assert event.event == "approval_required"
