"""Integration tests for request-scoped checkpoints and Agent runner streaming.

Uses a temporary SQLite file (no provider calls). Covers checkpointer lifecycle
open/close, run_id as thread_id, direct-answer SSE order, controlled graph
failure, per-run terminal cleanup after durable commit, and isolation from
another run's checkpoint.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

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
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    AgentRun,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.sse import SseEvent, parse_sse_event
from app.schemas.tools import ToolResult
from app.services.tool_execution import execute_tool
from app.tools.registry import ToolRegistry
from langchain_core.messages import AIMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.prebuilt import InjectedState
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async, session_factory

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


# ---------------------------------------------------------------------------
# Durable tool_status SSE (03C) — publication seam + runner merge
# ---------------------------------------------------------------------------


async def _seed_run_for_tools(
    factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    content: str = "tool status turn",
) -> None:
    """Insert user message + agent_run with fixed *run_id* for tool FK."""
    async with factory() as session:
        user = await messages_repo.insert_message(
            session,
            role=CHAT_MESSAGE_ROLE_USER,
            content=content,
        )
        run = AgentRun(
            id=run_id,
            user_message_id=user.id,
            state="running",
        )
        session.add(run)
        await session.flush()
        # Ensure repository path remains available for other tests.
        assert await runs_repo.get_run(session, run_id) is not None
        await session.commit()


def _build_durable_echo_tool(
    *,
    factory: async_sessionmaker[AsyncSession],
    side_effect: dict[str, int],
    fail: bool = False,
    secret_arg_marker: str = "RAW_SECRET_NEVER_IN_SSE",
) -> Any:
    """Test tool that uses shared execute_tool (production publication path)."""

    @tool("durable_echo")
    async def durable_echo(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        note: str = "ok",
    ) -> dict[str, Any]:
        """Echo a note through durable tool execution."""
        run_id = state.get("run_id") if isinstance(state, dict) else None
        if not isinstance(run_id, str) or run_id.strip() == "":
            return ToolResult(
                ok=False,
                code="MISSING_RUN_ID",
                summary="run_id required",
                data=None,
            ).model_dump(mode="json")

        async def _invoke() -> ToolResult:
            side_effect["n"] = int(side_effect.get("n", 0)) + 1
            if fail:
                return ToolResult(
                    ok=False,
                    code="ECHO_FAILED",
                    summary="echo failed on purpose",
                    data={"note": note, "secret": secret_arg_marker},
                )
            return ToolResult(
                ok=True,
                code=None,
                summary=f"echoed {note}",
                data={"note": note, "secret": secret_arg_marker},
            )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name="durable_echo",
            invoke=_invoke,
            arguments_summary_json={"note": note},
            session_factory=factory,
        )
        return result.model_dump(mode="json")

    return durable_echo


def test_tool_status_pending_running_completed_ordered(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """Normal fake tool: pending → running → completed, one durable id."""
    cp = tmp_path / "ts_ok.db"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            await _seed_run_for_tools(factory, run_id=RUN_A)
            side: dict[str, int] = {"n": 0}
            tool = _build_durable_echo_tool(factory=factory, side_effect=side)
            model = FakeChatModel(
                responses=[
                    _ai_tool_call("durable_echo", call_id="call-echo-1"),
                    _ai_text("Tool finished cleanly."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = await _collect(
                stream_agent_run(
                    run_id=RUN_A,
                    user_text="run durable echo",
                    graph_bundle=bundle,
                    sqlite_path=cp,
                    include_assistant_status=False,
                )
            )
            statuses = [e for e in events if e.event == "tool_status"]
            assert [s.payload.status for s in statuses] == [
                "pending",
                "running",
                "completed",
            ]
            exec_ids = {s.payload.tool_execution_id for s in statuses}
            assert len(exec_ids) == 1
            call_ids = {s.payload.tool_call_id for s in statuses}
            assert call_ids == {"call-echo-1"}
            names = {s.payload.tool_name for s in statuses}
            assert names == {"durable_echo"}

            completed = statuses[-1]
            assert completed.payload.duration_ms is not None
            assert completed.payload.duration_ms >= 0
            assert completed.payload.summary == "echoed ok"
            assert completed.payload.error_code is None
            assert side["n"] == 1

            # Ordered relative to stream: after run_started, before run_completed.
            names_all = _names(events)
            assert names_all[0] == "run_started"
            assert names_all[-1] == "run_completed"
            first_ts = names_all.index("tool_status")
            assert first_ts > 0
            assert "text_delta" in names_all
            text_i = names_all.index("text_delta")
            done_i = names_all.index("run_completed")
            assert first_ts < text_i or first_ts < done_i

            # Unique event_ids (dedup identity is execution id, not event_id).
            event_ids = [e.event_id for e in events]
            assert len(event_ids) == len(set(event_ids))

            async with factory() as session:
                rows = await tool_repo.list_for_run_ids(session, [RUN_A])
                assert len(rows) == 1
                assert rows[0].id == completed.payload.tool_execution_id
                assert rows[0].status == TOOL_EXECUTION_STATUS_COMPLETED
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_status_failed_error_coupling(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """Failed tool emits terminal failed with coupled error_code + duration."""
    cp = tmp_path / "ts_fail.db"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            await _seed_run_for_tools(factory, run_id=RUN_A)
            side: dict[str, int] = {"n": 0}
            tool = _build_durable_echo_tool(
                factory=factory, side_effect=side, fail=True
            )
            model = FakeChatModel(
                responses=[
                    _ai_tool_call("durable_echo", call_id="call-fail-1"),
                    _ai_text("The tool failed; explaining truthfully."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = await _collect(
                stream_agent_run(
                    run_id=RUN_A,
                    user_text="fail please",
                    graph_bundle=bundle,
                    sqlite_path=cp,
                    include_assistant_status=False,
                )
            )
            statuses = [e for e in events if e.event == "tool_status"]
            assert [s.payload.status for s in statuses] == [
                "pending",
                "running",
                "failed",
            ]
            failed = statuses[-1]
            assert failed.payload.error_code == "ECHO_FAILED"
            assert failed.payload.duration_ms is not None
            assert failed.payload.summary == "echo failed on purpose"
            # Failed tool may still complete the run when assistant explains.
            assert _names(events)[-1] == "run_completed"
            assert side["n"] == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_status_raw_data_excluded_from_sse(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """tool_status payloads never carry ToolResult data or raw secrets."""
    cp = tmp_path / "ts_priv.db"
    marker = "RAW_SECRET_NEVER_IN_SSE"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            await _seed_run_for_tools(factory, run_id=RUN_A)
            side: dict[str, int] = {"n": 0}
            tool = _build_durable_echo_tool(
                factory=factory,
                side_effect=side,
                secret_arg_marker=marker,
            )
            model = FakeChatModel(
                responses=[
                    _ai_tool_call("durable_echo", call_id="call-priv-1"),
                    _ai_text("done"),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = await _collect(
                stream_agent_run(
                    run_id=RUN_A,
                    user_text="private",
                    graph_bundle=bundle,
                    sqlite_path=cp,
                    include_assistant_status=False,
                )
            )
            dumped = [e.model_dump(mode="json") for e in events]
            blob = json.dumps(dumped)
            assert marker not in blob
            assert "result_json" not in blob
            assert "raw_content" not in blob
            for e in events:
                if e.event != "tool_status":
                    continue
                payload = e.payload.model_dump(mode="json")
                assert set(payload.keys()) <= {
                    "tool_execution_id",
                    "tool_call_id",
                    "tool_name",
                    "status",
                    "duration_ms",
                    "summary",
                    "error_code",
                }
                assert "data" not in payload
                assert "arguments" not in payload
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_status_concurrent_identities_distinct(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """Two tool calls in one ToolNode update keep distinct durable identities.

    Same AIMessage carries both tool_calls so ToolNode handles overlapping
    identities in one tools-node update (not two sequential model turns).
    """
    cp = tmp_path / "ts_two.db"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            await _seed_run_for_tools(factory, run_id=RUN_A)
            side: dict[str, int] = {"n": 0}
            tool = _build_durable_echo_tool(factory=factory, side_effect=side)
            multi = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "durable_echo",
                        "args": {"note": "a"},
                        "id": "call-a",
                        "type": "tool_call",
                    },
                    {
                        "name": "durable_echo",
                        "args": {"note": "b"},
                        "id": "call-b",
                        "type": "tool_call",
                    },
                ],
            )
            model = FakeChatModel(
                responses=[
                    multi,
                    _ai_text("both done"),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = await _collect(
                stream_agent_run(
                    run_id=RUN_A,
                    user_text="two tools same node",
                    graph_bundle=bundle,
                    sqlite_path=cp,
                    include_assistant_status=False,
                )
            )
            statuses = [e for e in events if e.event == "tool_status"]
            # Two full transitions: 3 + 3
            assert len(statuses) == 6
            by_call: dict[str, list[str]] = {}
            exec_by_call: dict[str, set[str]] = {}
            for s in statuses:
                by_call.setdefault(s.payload.tool_call_id, []).append(
                    s.payload.status
                )
                exec_by_call.setdefault(s.payload.tool_call_id, set()).add(
                    s.payload.tool_execution_id
                )
            assert by_call["call-a"] == ["pending", "running", "completed"]
            assert by_call["call-b"] == ["pending", "running", "completed"]
            assert len(exec_by_call["call-a"]) == 1
            assert len(exec_by_call["call-b"]) == 1
            assert exec_by_call["call-a"].isdisjoint(exec_by_call["call-b"])
            assert side["n"] == 2
            assert len({e.event_id for e in statuses}) == 6
            assert len({e.event_id for e in events}) == len(events)

            # Listener/run isolation: only RUN_A rows; two durable IDs.
            async with factory() as session:
                rows = await tool_repo.list_for_run_ids(session, [RUN_A])
                assert len(rows) == 2
                assert {r.tool_call_id for r in rows} == {"call-a", "call-b"}
                assert {r.id for r in rows} == (
                    exec_by_call["call-a"] | exec_by_call["call-b"]
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_status_live_pending_running_while_side_effect_blocks(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """pending/running SSE yield before a blocking tool side effect is released.

    Reproduces the A2 blocking probe: first event is run_started; before the
    tool gate is released the stream must already have delivered tool_status
    pending and running (not only after the side effect completes).
    """
    import asyncio

    cp = tmp_path / "ts_live_block.db"
    release = asyncio.Event()
    entered = asyncio.Event()

    def _build_blocking_tool(
        *,
        factory: async_sessionmaker[AsyncSession],
        side_effect: dict[str, int],
    ) -> Any:
        @tool("blocking_echo")
        async def blocking_echo(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[dict[str, Any], InjectedState],
        ) -> dict[str, Any]:
            """Block inside the side effect until the test releases the gate."""
            run_id = state.get("run_id") if isinstance(state, dict) else None
            if not isinstance(run_id, str) or run_id.strip() == "":
                return ToolResult(
                    ok=False,
                    code="MISSING_RUN_ID",
                    summary="run_id required",
                    data=None,
                ).model_dump(mode="json")

            async def _invoke() -> ToolResult:
                side_effect["n"] = int(side_effect.get("n", 0)) + 1
                entered.set()
                await release.wait()
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="released",
                    data={"blocked": True},
                )

            result = await execute_tool(
                run_id=run_id,
                tool_call_id=tool_call_id,
                tool_name="blocking_echo",
                invoke=_invoke,
                arguments_summary_json={"blocked": True},
                session_factory=factory,
            )
            return result.model_dump(mode="json")

        return blocking_echo

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            await _seed_run_for_tools(factory, run_id=RUN_A)
            side: dict[str, int] = {"n": 0}
            tool = _build_blocking_tool(factory=factory, side_effect=side)
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "blocking_echo",
                                "args": {},
                                "id": "call-block-1",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    _ai_text("after block"),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            gen = stream_agent_run(
                run_id=RUN_A,
                user_text="block please",
                graph_bundle=bundle,
                sqlite_path=cp,
                include_assistant_status=False,
            )
            first = await gen.__anext__()
            assert first.event == "run_started"

            # Consume until we have pending+running *before* releasing the tool.
            before_release: list[SseEvent] = [first]
            saw_pending = False
            saw_running = False
            deadline = asyncio.get_running_loop().time() + 5.0

            async def _pump_until_running() -> None:
                nonlocal saw_pending, saw_running
                while not (saw_pending and saw_running):
                    if asyncio.get_running_loop().time() > deadline:
                        break
                    try:
                        ev = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
                    except TimeoutError:
                        # Allow the blocked tool to publish while we wait.
                        if entered.is_set() and not (saw_pending and saw_running):
                            # Still no status: fail fast after entry without SSE.
                            continue
                        continue
                    before_release.append(ev)
                    if ev.event == "tool_status":
                        if ev.payload.status == "pending":
                            saw_pending = True
                        elif ev.payload.status == "running":
                            saw_running = True
                        # completed must not appear before release.
                        assert ev.payload.status != "completed"
                        assert ev.payload.status != "failed"

            await _pump_until_running()
            assert entered.is_set(), "tool side effect never entered the block"
            assert saw_pending, (
                "BEFORE_RELEASE NO_SSE_EVENT pending — live merge failed; "
                f"events={[e.event for e in before_release]}"
            )
            pre_statuses = [
                e.payload.status
                for e in before_release
                if e.event == "tool_status"
            ]
            assert saw_running, (
                f"BEFORE_RELEASE missing running — live merge failed; "
                f"statuses={pre_statuses}"
            )
            # No terminal status before release.
            assert not any(
                e.event == "tool_status" and e.payload.status == "completed"
                for e in before_release
            )

            release.set()
            rest = [ev async for ev in gen]
            all_events = before_release + rest
            statuses = [e for e in all_events if e.event == "tool_status"]
            assert [s.payload.status for s in statuses] == [
                "pending",
                "running",
                "completed",
            ]
            assert statuses[-1].payload.summary == "released"
            assert side["n"] == 1
            assert _names(all_events)[-1] == "run_completed"
        finally:
            release.set()
            await engine.dispose()

    run_async(_body())
