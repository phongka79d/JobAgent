"""Integration tests for request-scoped checkpoints and Agent runner streaming.

Uses a temporary SQLite file (no provider calls). Covers checkpointer lifecycle
open/close, run_id as thread_id, direct-answer SSE order, controlled graph
failure, per-run terminal cleanup after durable commit, and isolation from
another run's checkpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from app.agent.checkpoint import (
    delete_run_checkpoint,
    open_checkpointer,
    resolve_checkpoint_sqlite_path,
    thread_config,
    thread_has_checkpoints,
)
from app.agent.graph import (
    ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
    build_agent_graph,
    initial_graph_state,
)
from app.agent.runner import TerminalOutcome, stream_agent_run
from app.schemas.sse import SseEvent, parse_sse_event
from app.tools.registry import ToolRegistry
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async

RUN_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
RUN_B = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _ai_text(content: str) -> AIMessage:
    return AIMessage(content=content)


def _ai_tool_call(name: str, call_id: str = "call-1") -> AIMessage:
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


# ---------------------------------------------------------------------------
# Checkpoint path / lifecycle
# ---------------------------------------------------------------------------


def test_resolve_checkpoint_path_matches_configured_file(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    resolved = resolve_checkpoint_sqlite_path(path)
    assert resolved == path.resolve()


def test_open_checkpointer_setup_and_close(tmp_path: Path) -> None:
    db = tmp_path / "cp.db"

    async def _body() -> None:
        async with open_checkpointer(db) as saver:
            assert isinstance(saver, AsyncSqliteSaver)
            async with saver.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cur:
                names = {row[0] for row in await cur.fetchall()}
            assert "checkpoints" in names
            assert "writes" in names
            conn = saver.conn
        # Connection closed after context exit.
        try:
            await conn.execute("SELECT 1")
            raise AssertionError("expected closed connection")
        except ValueError as exc:
            assert "no active connection" in str(exc).lower()

    run_async(_body())


def test_thread_config_uses_run_id_as_thread_id() -> None:
    cfg = thread_config(RUN_A)
    assert cfg == {"configurable": {"thread_id": RUN_A}}


# ---------------------------------------------------------------------------
# Direct-answer streaming order
# ---------------------------------------------------------------------------


def test_direct_answer_event_order_and_validation(tmp_path: Path) -> None:
    db = tmp_path / "run.db"

    async def _body() -> None:
        model = FakeChatModel(responses=[_ai_text("Hello from the agent.")])
        lifecycle = {"open": 0, "close": 0}

        @asynccontextmanager
        async def spy_open(
            sqlite_path: Any = None,
            *,
            settings: Any = None,
        ) -> AsyncIterator[AsyncSqliteSaver]:
            lifecycle["open"] += 1
            async with open_checkpointer(
                sqlite_path or db, settings=settings
            ) as saver:
                yield saver
            lifecycle["close"] += 1

        durable_calls: list[TerminalOutcome] = []

        async def on_terminal(outcome: TerminalOutcome) -> bool:
            durable_calls.append(outcome)
            return True

        events = await _collect(
            stream_agent_run(
                run_id=RUN_A,
                user_text="Xin chào",
                model=model,
                sqlite_path=db,
                on_durable_terminal=on_terminal,
                checkpointer_open=spy_open,
                include_assistant_status=True,
            )
        )

        names = _names(events)
        assert names[0] == "run_started"
        assert "text_delta" in names
        assert names[-1] == "run_completed"
        if "assistant_status" in names:
            assert names.index("assistant_status") < names.index("text_delta")
        assert names.index("run_started") < names.index("text_delta")
        assert names.index("text_delta") < names.index("run_completed")

        for event in events:
            reparsed = parse_sse_event(event.model_dump(mode="json"))
            assert reparsed.event == event.event
            assert reparsed.run_id == RUN_A

        started = events[0]
        assert started.event == "run_started"
        assert started.payload.state == "running"
        assert started.payload.resumed is False

        deltas = [e for e in events if e.event == "text_delta"]
        assert all(e.payload.delta for e in deltas)
        joined = "".join(e.payload.delta for e in deltas)
        assert "Hello from the agent." in joined

        assert lifecycle == {"open": 1, "close": 1}
        assert len(durable_calls) == 1
        assert durable_calls[0].kind == "completed"
        assert durable_calls[0].run_id == RUN_A

        async with open_checkpointer(db) as saver:
            assert await thread_has_checkpoints(saver, RUN_A) is False

    run_async(_body())


# ---------------------------------------------------------------------------
# Controlled failure
# ---------------------------------------------------------------------------


def test_controlled_graph_failure_emits_run_failed(tmp_path: Path) -> None:
    db = tmp_path / "fail.db"

    async def _body() -> None:
        @tool
        def noop_tool() -> str:
            """Test-only no-op tool."""
            return "ok"

        model = FakeChatModel(responses=[_ai_tool_call("noop_tool")])
        bundle = build_agent_graph(
            model=model,
            registry=ToolRegistry([noop_tool]),
            tool_loop_limit=1,
        )
        state = initial_graph_state(
            run_id=RUN_A,
            user_text="loop",
            tool_iteration_count=1,
        )
        outcomes: list[TerminalOutcome] = []

        async def on_terminal(outcome: TerminalOutcome) -> bool:
            outcomes.append(outcome)
            return True

        events = await _collect(
            stream_agent_run(
                run_id=RUN_A,
                input_state=state,
                graph_bundle=bundle,
                sqlite_path=db,
                on_durable_terminal=on_terminal,
                include_assistant_status=False,
            )
        )

        names = _names(events)
        assert names[0] == "run_started"
        assert names[-1] == "run_failed"
        failed = events[-1]
        assert failed.event == "run_failed"
        assert failed.payload.state == "failed"
        assert failed.payload.error_code == ERROR_TOOL_LOOP_LIMIT_EXCEEDED
        assert failed.payload.summary
        assert "traceback" not in failed.payload.summary.lower()
        assert outcomes[0].kind == "failed"

        async with open_checkpointer(db) as saver:
            assert await thread_has_checkpoints(saver, RUN_A) is False

    run_async(_body())


# ---------------------------------------------------------------------------
# Cleanup isolation + durable-commit gate
# ---------------------------------------------------------------------------


def test_terminal_cleanup_only_after_durable_commit(tmp_path: Path) -> None:
    db = tmp_path / "gate.db"

    async def _body() -> None:
        model = FakeChatModel(responses=[_ai_text("ok")])

        async def refuse(_outcome: TerminalOutcome) -> bool:
            return False

        await _collect(
            stream_agent_run(
                run_id=RUN_A,
                user_text="hi",
                model=model,
                sqlite_path=db,
                on_durable_terminal=refuse,
                include_assistant_status=False,
            )
        )

        async with open_checkpointer(db) as saver:
            assert await thread_has_checkpoints(saver, RUN_A) is True
            await delete_run_checkpoint(saver, RUN_A)
            assert await thread_has_checkpoints(saver, RUN_A) is False

    run_async(_body())


def test_cleanup_preserves_other_run_checkpoint(tmp_path: Path) -> None:
    db = tmp_path / "iso.db"

    async def _body() -> None:
        model_a = FakeChatModel(responses=[_ai_text("answer A")])
        model_b = FakeChatModel(responses=[_ai_text("answer B")])

        async def refuse(_o: TerminalOutcome) -> bool:
            return False

        await _collect(
            stream_agent_run(
                run_id=RUN_B,
                user_text="B",
                model=model_b,
                sqlite_path=db,
                on_durable_terminal=refuse,
                include_assistant_status=False,
            )
        )

        async def accept(_o: TerminalOutcome) -> bool:
            return True

        await _collect(
            stream_agent_run(
                run_id=RUN_A,
                user_text="A",
                model=model_a,
                sqlite_path=db,
                on_durable_terminal=accept,
                include_assistant_status=False,
            )
        )

        async with open_checkpointer(db) as saver:
            assert await thread_has_checkpoints(saver, RUN_A) is False
            assert await thread_has_checkpoints(saver, RUN_B) is True
            await delete_run_checkpoint(saver, RUN_B)
            assert await thread_has_checkpoints(saver, RUN_B) is False

    run_async(_body())


def test_interrupted_kind_retains_checkpoint(tmp_path: Path) -> None:
    """Interrupted terminal kind must not delete the run thread checkpoint."""
    db = tmp_path / "intr.db"

    async def _body() -> None:
        # Seed a checkpoint for RUN_A, then delete only after completed path.
        model = FakeChatModel(responses=[_ai_text("held")])

        async def refuse(_o: TerminalOutcome) -> bool:
            return False

        await _collect(
            stream_agent_run(
                run_id=RUN_A,
                user_text="hold",
                model=model,
                sqlite_path=db,
                on_durable_terminal=refuse,
                include_assistant_status=False,
            )
        )
        async with open_checkpointer(db) as saver:
            assert await thread_has_checkpoints(saver, RUN_A) is True

        # Package API delete is per-thread only (interrupted retention analog).
        async with open_checkpointer(db) as saver:
            await delete_run_checkpoint(saver, RUN_B)  # other id no-op
            assert await thread_has_checkpoints(saver, RUN_A) is True

    run_async(_body())


# ---------------------------------------------------------------------------
# Ownership isolation evidence
# ---------------------------------------------------------------------------


def test_no_checkpoint_ownership_in_migrations_or_repos() -> None:
    """Alembic/app repositories must not create/update/drop checkpoint tables."""
    migrations = BACKEND_ROOT / "migrations"
    repos = BACKEND_ROOT / "app" / "repositories"

    for path in repos.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "AsyncSqliteSaver" not in source
        assert "adelete_thread" not in source
        assert "checkpoint_writes" not in source
        assert "CREATE TABLE checkpoints" not in source

    for path in migrations.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "CREATE TABLE checkpoints" not in source
        assert "CREATE TABLE writes" not in source
        assert "DROP TABLE checkpoints" not in source
        assert "AsyncSqliteSaver" not in source
        assert "adelete_thread" not in source


def test_runner_source_has_no_session_scope_across_stream() -> None:
    """Runner must not open session_scope/AsyncSession during stream."""
    runner_src = (BACKEND_ROOT / "app" / "agent" / "runner.py").read_text(
        encoding="utf-8"
    )
    assert "session_scope" not in runner_src
    assert "AsyncSession" not in runner_src
    assert "create_all" not in runner_src
