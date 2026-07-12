"""Full-path Plan 3 transport proof (task 04A).

Drives the real FastAPI chat routes, ChatService, production graph/ToolNode,
validated SSE wire format, durable repositories, and checkpoint cleanup with
injected fakes only (ScriptedDecision + test-only synthetic tools).

Never calls ShopAIKey. Synthetic tools are injected per-test and must not appear
on production app modules or the empty production registry.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.agent.lifecycle import count_thread_checkpoints_on_disk
from app.agent.prompt import DOMAIN_REDIRECT_MESSAGE
from app.config import Settings, load_settings
from app.db.enums import AgentRunState, MessageRole
from app.db.models.conversation import AgentRun, ChatMessage, ToolExecution
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.repositories.tool_executions import ToolExecutionRepository
from app.schemas.sse import SSEEventOrderValidator, parse_sse_event
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from app.tools.registry import ToolRegistry
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from tests.fakes.agent_tools import (
    ScriptedDecision,
    decision_text,
    decision_with_tool,
    make_echo_label_tool,
)
from tests.graph.fakes import FakeDriver
from typing_extensions import TypedDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
APP_SRC = BACKEND_ROOT / "app"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-full-transport"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-full-transport"
SENTINEL_URI = "bolt://full-transport-test.invalid:7687"
# Unique raw tool-argument value that must never reach public/durable surfaces.
RAW_ARG_SENTINEL = "RAW_ARG_SENTINEL_7f3a9c2e_UNIQUE_PING_xQ9m"

# Production modules must not import synthetic helpers or implement match_jobs.
# Plan 5 production tools include four Candidate tools plus save_job/query_jobs.
_PRODUCTION_FORBIDDEN_RE = re.compile(
    r"echo_label|make_echo_label_tool|tests\.fakes\.agent_tools|"
    r"name\s*=\s*[\"']match_jobs[\"']|def\s+create_match_jobs"
)


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


def _settings(tmp_path: Path) -> Settings:
    return load_settings(
        environ={
            "APP_ENV": "local",
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "VITE_API_BASE_URL": "http://localhost:8000",
            "SQLITE_PATH": str(tmp_path / "full_transport.db"),
            "FILES_DIR": str(tmp_path / "files"),
            "NEO4J_URI": SENTINEL_URI,
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
            "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
            "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TEMPERATURE": "0",
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "EMBEDDING_DIMENSIONS": "1536",
            "MAX_PDF_SIZE_MB": "10",
            "MAX_PDF_PAGES": "10",
            "URL_FETCH_TIMEOUT_SECONDS": "10",
            "URL_MAX_RESPONSE_MB": "5",
            "TOOL_LOOP_LIMIT": "6",
        }
    )


@asynccontextmanager
async def migrated_db(
    tmp_path: Path,
) -> AsyncIterator[tuple[Path, DatabaseSessionManager, Settings]]:
    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    upgrade_head(db_path)
    manager = create_session_manager(db_path)
    try:
        yield db_path, manager, settings
    finally:
        await manager.dispose()


def _parse_sse_payloads(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in re.split(r"\n\n+", body.strip()):
        if not block.strip():
            continue
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        events.append(json.loads("\n".join(data_lines)))
    return events


def _event_kinds(payloads: Sequence[dict[str, Any]]) -> list[str]:
    return [str(p["event"]) for p in payloads]


def _assert_no_leakage(*blobs: str) -> None:
    for blob in blobs:
        assert SENTINEL_API_KEY not in blob
        assert SENTINEL_NEO4J_PASSWORD not in blob
        assert "Traceback" not in blob
        assert "Authorization" not in blob
        assert "SHOPAIKEY" not in blob.upper() or "sentinel" not in blob.lower()


def _assert_sentinel_absent(sentinel: str, *values: Any) -> None:
    """Recursively assert a unique raw-argument sentinel is absent."""

    def walk(obj: Any) -> None:
        if obj is None:
            return
        if isinstance(obj, str):
            assert sentinel not in obj, f"sentinel leaked in string: {obj[:200]!r}"
            return
        if isinstance(obj, (bytes, bytearray)):
            assert sentinel.encode("utf-8") not in bytes(obj)
            return
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                walk(key)
                walk(value)
            return
        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for item in obj:
                walk(item)
            return
        if isinstance(obj, (int, float, bool)):
            return
        text = str(obj)
        assert sentinel not in text, f"sentinel leaked in {type(obj)!r}"

    for value in values:
        walk(value)


def _build_app(
    *,
    manager: DatabaseSessionManager,
    settings: Settings,
    db_path: Path,
    decision: ScriptedDecision | None = None,
    tools: Sequence[Any] | None = None,
    graph_factory: Any | None = None,
) -> Any:
    chat = ChatService(
        manager,
        sqlite_path=db_path,
        decision=decision,
        tools=list(tools) if tools is not None else None,
        graph_factory=graph_factory,
    )
    return create_app(
        settings=settings,
        session_manager=manager,
        storage=FilesystemAttachmentStorage(settings.files_dir),
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=FakeDriver,
            health_timeout_seconds=0.2,
        ),
        chat_service=chat,
        run_schema_setup=False,
    )


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


# ---------------------------------------------------------------------------
# Ordinary completion + history (real FastAPI / SSE / repositories)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_ordinary_completion_and_history(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            decision=ScriptedDecision([decision_text("full path ordinary answer")]),
            tools=[],
        )
        with TestClient(application) as client:
            turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Help improve my CV summary",
                    "idempotency_key": "full-ordinary-1",
                },
            )
            assert turn.status_code == 200
            assert "text/event-stream" in turn.headers.get("content-type", "")
            payloads = _parse_sse_payloads(turn.text)
            typed = [parse_sse_event(p) for p in payloads]
            SSEEventOrderValidator().validate_sequence(typed)
            kinds = _event_kinds(payloads)
            assert kinds[0] == "run_started"
            assert kinds[-1] == "run_completed"
            assert "text_delta" in kinds
            assert "tool_started" not in kinds
            text = "".join(
                p["payload"]["delta"] for p in payloads if p["event"] == "text_delta"
            )
            assert text == "full path ordinary answer"

            hist = client.get("/api/chat/history")
            assert hist.status_code == 200
            body = hist.json()
            assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
            assert body["messages"][1]["content"] == "full path ordinary answer"
            assert "conversation_id" not in body
            for message in body["messages"]:
                assert "id" not in message

            _assert_no_leakage(turn.text, hist.text, json.dumps(payloads))
            run_id = UUID(payloads[0]["run_id"])
            remaining = await count_thread_checkpoints_on_disk(db_path, str(run_id))
            assert remaining == 0


# ---------------------------------------------------------------------------
# Synthetic tool through FastAPI -> graph -> ToolNode -> SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_synthetic_tool_activity_sse_and_cleanup(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    async with migrated_db(tmp_path) as (db_path, manager, settings):
        decision = ScriptedDecision(
            [
                decision_with_tool(
                    "echo_label",
                    label=RAW_ARG_SENTINEL,
                    tool_call_id="c0",
                ),
                decision_text("done after echo"),
            ]
        )
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            decision=decision,
            tools=[make_echo_label_tool()],
        )
        with caplog.at_level(logging.DEBUG):
            with TestClient(application) as client:
                turn = client.post(
                    "/api/chat/turns",
                    json={
                        "text": "Match keywords on my profile",
                        "idempotency_key": "full-tool-1",
                    },
                )
                assert turn.status_code == 200
                payloads = _parse_sse_payloads(turn.text)
                typed = [parse_sse_event(p) for p in payloads]
                SSEEventOrderValidator().validate_sequence(typed)
                kinds = _event_kinds(payloads)
                assert "tool_started" in kinds
                assert "tool_completed" in kinds
                assert kinds[-1] == "run_completed"
                # Public tool_call_id is opaque stream index, not DB PK / raw call id.
                tool_ids = [
                    p["payload"]["tool_call_id"]
                    for p in payloads
                    if p["event"] in {"tool_started", "tool_completed"}
                ]
                assert tool_ids
                assert all(re.fullmatch(r"t[1-9]\d*", tid) for tid in tool_ids)
                labels = [
                    p["payload"]["label"]
                    for p in payloads
                    if p["event"] in {"tool_started", "tool_completed"}
                ]
                assert any(
                    "Echo" in label or "echo" in label.lower() for label in labels
                )
                # Public outcomes must be generic allowlisted status only.
                for payload in payloads:
                    if payload["event"] == "tool_completed":
                        outcome = payload["payload"].get("outcome")
                        assert outcome in {None, "completed", "tool_completed", "ok"}
                        assert outcome != f"echo:{RAW_ARG_SENTINEL}"

                wire = turn.text
                hist = client.get("/api/chat/history")
                assert hist.status_code == 200
                hist_body = hist.json()
                roles = [m["role"] for m in hist_body["messages"]]
                assert roles == ["user", "assistant"]

                run_id = UUID(payloads[0]["run_id"])

            remaining = await count_thread_checkpoints_on_disk(db_path, str(run_id))
            assert remaining == 0

            async with manager.session_scope() as session:
                tools = await ToolExecutionRepository(session).list_for_run(run_id)
                assert len(tools) >= 1
                assert any(row.tool_name == "echo_label" for row in tools)
                durable_summaries = [row.arguments_summary for row in tools]
                durable_errors = [row.error_code for row in tools]
                for row in tools:
                    # Never persist raw tool result / argument bodies.
                    assert row.arguments_summary in {None, "completed", "tool_completed"}
                    if row.arguments_summary is not None:
                        assert RAW_ARG_SENTINEL not in row.arguments_summary
                        assert not row.arguments_summary.startswith("echo:")
                run = await session.get(AgentRun, run_id)
                assert run is not None
                assert run.state == AgentRunState.COMPLETED.value
                assistants = (
                    await session.execute(
                        select(func.count())
                        .select_from(ChatMessage)
                        .where(ChatMessage.role == MessageRole.ASSISTANT.value)
                    )
                ).scalar_one()
                assert int(assistants) == 1

            log_text = "\n".join(
                f"{rec.name}:{rec.levelname}:{rec.getMessage()}"
                for rec in caplog.records
            )

            # Unique sentinel must be absent from every public/durable surface.
            _assert_sentinel_absent(
                RAW_ARG_SENTINEL,
                payloads,
                wire,
                hist_body,
                hist.text,
                durable_summaries,
                durable_errors,
                log_text,
            )
            # Compact JSON and result-shaped forms must not appear either.
            assert f"echo:{RAW_ARG_SENTINEL}" not in wire
            assert RAW_ARG_SENTINEL not in wire
            assert "call_echo_label" not in wire
            _assert_no_leakage(wire, hist.text, json.dumps(payloads), log_text)


# ---------------------------------------------------------------------------
# Interrupt / resume across separate HTTP requests + duplicate keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_interrupt_resume_duplicate_keys_and_cleanup(
    tmp_path: Path,
) -> None:
    from langchain_core.tools import StructuredTool

    async with migrated_db(tmp_path) as (db_path, manager, settings):
        # Instrument the approval tool action to prove exactly-once execution.
        approval_action_calls: list[str] = []

        def _propose(label: str) -> str:
            approval_action_calls.append(label)
            return (
                "APPROVAL_REQUIRED:"
                f'{{"kind":"approval_required","tool":"propose_action",'
                f'"label":"{label}"}}'
            )

        approval_tool = StructuredTool.from_function(
            func=_propose,
            name="propose_action",
            description="Instrumented synthetic approval tool for full transport.",
        )

        decision = ScriptedDecision(
            [
                decision_with_tool(
                    "propose_action",
                    label="draft1",
                    tool_call_id="c_approve_0",
                ),
                decision_text("saved after full transport resume"),
            ]
        )
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            decision=decision,
            tools=[approval_tool],
        )
        with TestClient(application) as client:
            first = client.post(
                "/api/chat/turns",
                json={
                    "text": "Please update my candidate profile draft",
                    "idempotency_key": "full-interrupt-1",
                },
            )
            assert first.status_code == 200
            first_payloads = _parse_sse_payloads(first.text)
            first_ordered = SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in first_payloads]
            )
            assert str(first_ordered[-1].event) == "approval_required"
            run_id = UUID(first_payloads[0]["run_id"])
            assert len(approval_action_calls) == 1

            async with manager.session_scope() as session:
                tools_after_interrupt = await ToolExecutionRepository(
                    session
                ).list_for_run(run_id)
            tools_after_interrupt_count = len(tools_after_interrupt)
            # Interrupt may persist tool observability immediately or at finalize.
            assert tools_after_interrupt_count in {0, 1}

            mid_ck = await count_thread_checkpoints_on_disk(db_path, str(run_id))
            assert mid_ck > 0

            # Separate request lifecycle: replace service (new graph/saver path).
            client.app.state.chat_service = ChatService(  # type: ignore[attr-defined]
                manager,
                sqlite_path=db_path,
                decision=ScriptedDecision(
                    [decision_text("saved after full transport resume")]
                ),
                tools=[approval_tool],
            )
            second = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={
                    "action": "approve",
                    "idempotency_key": "full-resume-1",
                },
            )
            assert second.status_code == 200
            second_payloads = _parse_sse_payloads(second.text)
            second_ordered = SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in second_payloads]
            )
            assert str(second_ordered[-1].event) == "run_completed"
            assert second_payloads[0]["run_id"] == str(run_id)
            text = "".join(
                p["payload"]["delta"]
                for p in second_payloads
                if p["event"] == "text_delta"
            )
            assert text == "saved after full transport resume"
            # Resume must not re-execute the approval tool action.
            assert len(approval_action_calls) == 1

            # Duplicate turn key: same run, no second write / tool action.
            dup_turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Please update my candidate profile draft",
                    "idempotency_key": "full-interrupt-1",
                },
            )
            assert dup_turn.status_code == 200
            assert _parse_sse_payloads(dup_turn.text)[0]["run_id"] == str(run_id)
            assert len(approval_action_calls) == 1

            # Duplicate resume key: terminal replay, still same run, no re-exec.
            dup_resume = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={
                    "action": "approve",
                    "idempotency_key": "full-resume-1",
                },
            )
            assert dup_resume.status_code == 200
            dup_payloads = _parse_sse_payloads(dup_resume.text)
            assert dup_payloads[0]["run_id"] == str(run_id)
            assert dup_payloads[-1]["event"] == "run_completed"
            assert len(approval_action_calls) == 1

            hist = client.get("/api/chat/history")
            assert hist.status_code == 200
            roles = [m["role"] for m in hist.json()["messages"]]
            assert roles == ["user", "assistant"]

        remaining = await count_thread_checkpoints_on_disk(db_path, str(run_id))
        assert remaining == 0

        async with manager.session_scope() as session:
            users = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.USER.value)
                )
            ).scalar_one()
            assistants = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == MessageRole.ASSISTANT.value)
                )
            ).scalar_one()
            runs = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            tool_rows = await ToolExecutionRepository(session).list_for_run(run_id)
            tool_row_count = (
                await session.execute(
                    select(func.count()).select_from(ToolExecution)
                )
            ).scalar_one()
            assert int(users) == 1
            assert int(assistants) == 1
            assert int(runs) == 1
            # Exactly one tool action and one durable tool observability row.
            assert len(approval_action_calls) == 1
            assert len(tool_rows) == 1
            assert int(tool_row_count) == 1
            assert tool_rows[0].tool_name == "propose_action"
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value


# ---------------------------------------------------------------------------
# Unrelated redirect: exact message, zero tools, durable history retained
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_unrelated_redirect_zero_tools(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        decision = ScriptedDecision([decision_text("should never be invoked")])
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            decision=decision,
            tools=[make_echo_label_tool()],
        )
        with TestClient(application) as client:
            turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "What is the weather in Paris today?",
                    "idempotency_key": "full-redirect-1",
                },
            )
            assert turn.status_code == 200
            payloads = _parse_sse_payloads(turn.text)
            SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in payloads]
            )
            kinds = _event_kinds(payloads)
            assert kinds[-1] == "run_completed"
            assert "tool_started" not in kinds
            assert "tool_completed" not in kinds
            text = "".join(
                p["payload"]["delta"] for p in payloads if p["event"] == "text_delta"
            )
            assert text == DOMAIN_REDIRECT_MESSAGE
            assert decision.calls == []

            hist = client.get("/api/chat/history")
            assert hist.json()["messages"][-1]["content"] == DOMAIN_REDIRECT_MESSAGE

        run_id = UUID(payloads[0]["run_id"])
        remaining = await count_thread_checkpoints_on_disk(db_path, str(run_id))
        assert remaining == 0

        async with manager.session_scope() as session:
            tool_count = (
                await session.execute(select(func.count()).select_from(ToolExecution))
            ).scalar_one()
            assert int(tool_count) == 0


# ---------------------------------------------------------------------------
# Controlled failure via HTTP SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_controlled_failure_sse(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            graph_factory=_failing_graph_factory,
        )
        with TestClient(application) as client:
            turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Help with my CV analysis that will fail",
                    "idempotency_key": "full-fail-1",
                },
            )
            assert turn.status_code == 200
            payloads = _parse_sse_payloads(turn.text)
            SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in payloads]
            )
            assert payloads[-1]["event"] == "run_failed"
            code = payloads[-1]["payload"]["error_code"]
            assert isinstance(code, str) and code
            assert "Traceback" not in turn.text
            assert SENTINEL_API_KEY not in turn.text

            hist = client.get("/api/chat/history")
            # User message retained; no successful assistant write.
            roles = [m["role"] for m in hist.json()["messages"]]
            assert roles == ["user"]

        run_id = UUID(payloads[0]["run_id"])
        async with manager.session_scope() as session:
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert run.state == AgentRunState.FAILED.value
            assert run.error is not None


# ---------------------------------------------------------------------------
# Disconnect / reconnect via service cancel (same durable key, no replay)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_path_disconnect_reconnect_no_replay(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, _settings):
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

        async def cancel_after_start() -> None:
            await started.wait()
            cancel.set()

        watcher = asyncio.create_task(cancel_after_start())
        try:
            result = await service.start_turn(
                user_text="Long running CV analysis",
                turn_idempotency_key="full-disconnect-1",
                cancel_event=cancel,
            )
        finally:
            release.set()
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass

        assert result.outcome in {"disconnected", "failed"}
        assert result.state == AgentRunState.FAILED.value

        replay = await service.start_turn(
            user_text="Long running CV analysis",
            turn_idempotency_key="full-disconnect-1",
        )
        assert replay.replayed is True
        assert replay.run_id == result.run_id

        async with manager.session_scope() as session:
            msgs = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            runs = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert int(msgs) == 1
            assert int(runs) == 1


# ---------------------------------------------------------------------------
# Production exposure + route inventory (static + runtime)
# ---------------------------------------------------------------------------


def test_production_registry_seam_and_no_forbidden_tool_exposure() -> None:
    # Empty default registry remains a valid injection base; Plan 5 production
    # startup registers exactly six tools via create_production_registry.
    from app.tools.registry import (
        CURRENT_PROFILE_TOOL_NAMES,
        PRODUCTION_TOOL_NAMES,
        create_production_registry,
    )
    from langchain_core.tools import StructuredTool

    registry = ToolRegistry()
    assert len(registry) == 0
    assert "echo_label" not in registry
    assert "propose_action" not in registry
    assert "match_jobs" not in registry

    production = create_production_registry(
        [
            StructuredTool.from_function(
                func=lambda: "ok", name=name, description=name
            )
            for name in sorted(PRODUCTION_TOOL_NAMES)
        ]
    )
    assert production.names() == PRODUCTION_TOOL_NAMES
    assert CURRENT_PROFILE_TOOL_NAMES < PRODUCTION_TOOL_NAMES
    assert production.names() == {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
    }
    assert "match_jobs" not in production

    # Synthetic helpers and later Job/matching tools must not appear in app code.
    hits: list[str] = []
    for path in APP_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _PRODUCTION_FORBIDDEN_RE.search(text):
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], f"forbidden production exposure: {hits}"

    # Frontend production source (exclude tests) must not reference synthetic tools.
    if FRONTEND_SRC.exists():
        fe_hits: list[str] = []
        for path in FRONTEND_SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            rel = path.relative_to(FRONTEND_SRC).as_posix()
            if rel.startswith("test/") or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            if "echo_label" in text or "make_echo_label" in text:
                fe_hits.append(str(path.relative_to(REPO_ROOT)))
        assert fe_hits == [], f"frontend synthetic exposure: {fe_hits}"


@pytest.mark.asyncio
async def test_full_path_route_inventory_only_approved_public_paths(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        application = _build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            decision=ScriptedDecision([decision_text("route ok")]),
            tools=[],
        )
        with TestClient(application) as client:
            paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
            # Plan 4 application surface: health + CV upload + profile reads + chat.
            app_paths = {p for p in paths if p.startswith("/api/")}
            assert app_paths == {
                "/api/health",
                "/api/attachments/cv",
                "/api/profile",
                "/api/profile/cv",
                "/api/chat/history",
                "/api/chat/turns",
                "/api/chat/runs/{run_id}/resume",
            }
            forbidden_fragments = (
                "synthetic",
                "job",
                "match",
            )
            for path in app_paths:
                lowered = path.lower()
                for frag in forbidden_fragments:
                    assert frag not in lowered, path
