"""Integration tests for chat transport: SSE, resume, disconnect, leakage."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from app.config import Settings, load_settings
from app.db.enums import AgentRunState
from app.db.models.conversation import AgentRun, ChatMessage, ToolExecution
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.schemas.sse import SSEEventOrderValidator, parse_sse_event
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from tests.fakes.agent_tools import (
    ScriptedDecision,
    decision_text,
    decision_with_tool,
    make_approval_request_tool,
)
from tests.graph.fakes import FakeDriver
from typing_extensions import TypedDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-chat-transport"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-chat-transport"
SENTINEL_URI = "bolt://chat-transport-test.invalid:7687"


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
            "SQLITE_PATH": str(tmp_path / "transport.db"),
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
async def test_transport_full_turn_history_and_ordered_sse(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        decision = ScriptedDecision([decision_text("transport final answer")])
        chat = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=[],
        )
        application = create_app(
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
        with TestClient(application) as client:
            assert client.get("/api/health").status_code == 200
            turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Help with my CV keywords",
                    "idempotency_key": "transport-turn-1",
                },
            )
            assert turn.status_code == 200
            assert "text/event-stream" in turn.headers.get("content-type", "")
            payloads = _parse_sse_payloads(turn.text)
            typed = [parse_sse_event(p) for p in payloads]
            ordered = SSEEventOrderValidator().validate_sequence(typed)
            assert str(ordered[0].event) == "run_started"
            assert str(ordered[-1].event) == "run_completed"
            hist = client.get("/api/chat/history")
            assert hist.status_code == 200
            hist_body = hist.json()
            roles = [m["role"] for m in hist_body["messages"]]
            assert roles == ["user", "assistant"]
            # Public contract must not expose conversation/message primary keys.
            assert "conversation_id" not in hist_body
            for message in hist_body["messages"]:
                assert "id" not in message
                assert "conversation_id" not in message
            async with manager.session_scope() as session:
                msg_ids = {
                    str(row[0])
                    for row in (await session.execute(select(ChatMessage.id))).all()
                }
                tool_ids = {
                    str(row[0])
                    for row in (
                        await session.execute(select(ToolExecution.id))
                    ).all()
                }
            forbidden = msg_ids | tool_ids
            assert msg_ids
            hist_wire = json.dumps(hist_body)
            for banned in forbidden:
                # Message/tool PKs must not appear in history (SSE run_id is public).
                assert banned not in hist_wire
            for payload in payloads:
                assert "conversation_id" not in payload
                assert "message_id" not in payload
                event_payload = payload.get("payload")
                if isinstance(event_payload, dict) and "tool_call_id" in event_payload:
                    tid = event_payload["tool_call_id"]
                    assert tid not in forbidden
                    assert re.fullmatch(r"t[1-9]\d*", str(tid))
            # Leakage scan on wire and history.
            for blob in (turn.text, hist.text, json.dumps(payloads)):
                assert SENTINEL_API_KEY not in blob
                assert SENTINEL_NEO4J_PASSWORD not in blob
                assert "Traceback" not in blob
                assert "Authorization" not in blob


@pytest.mark.asyncio
async def test_transport_same_run_resume_across_requests(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        decision = ScriptedDecision(
            [
                decision_with_tool(
                    "propose_action",
                    label="draft1",
                    tool_call_id="c_approve_0",
                ),
                decision_text("saved after transport resume"),
            ]
        )
        chat = ChatService(
            manager,
            sqlite_path=db_path,
            decision=decision,
            tools=[make_approval_request_tool()],
        )
        application = create_app(
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
        with TestClient(application) as client:
            first = client.post(
                "/api/chat/turns",
                json={
                    "text": "Please update my candidate profile draft",
                    "idempotency_key": "transport-interrupt-1",
                },
            )
            assert first.status_code == 200
            payloads = _parse_sse_payloads(first.text)
            ordered = SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in payloads]
            )
            assert str(ordered[-1].event) == "approval_required"
            run_id = UUID(payloads[0]["run_id"])

            client.app.state.chat_service = ChatService(  # type: ignore[attr-defined]
                manager,
                sqlite_path=db_path,
                decision=ScriptedDecision(
                    [decision_text("saved after transport resume")]
                ),
                tools=[make_approval_request_tool()],
            )
            second = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={"action": "approve", "idempotency_key": "transport-resume-1"},
            )
            assert second.status_code == 200
            r_payloads = _parse_sse_payloads(second.text)
            r_ordered = SSEEventOrderValidator().validate_sequence(
                [parse_sse_event(p) for p in r_payloads]
            )
            assert str(r_ordered[-1].event) == "run_completed"
            assert r_payloads[0]["run_id"] == str(run_id)

            # Duplicate keys: no second message/run/assistant.
            dup_turn = client.post(
                "/api/chat/turns",
                json={
                    "text": "Please update my candidate profile draft",
                    "idempotency_key": "transport-interrupt-1",
                },
            )
            assert dup_turn.status_code == 200
            assert _parse_sse_payloads(dup_turn.text)[0]["run_id"] == str(run_id)

            dup_resume = client.post(
                f"/api/chat/runs/{run_id}/resume",
                json={"action": "approve", "idempotency_key": "transport-resume-1"},
            )
            assert dup_resume.status_code == 200

        async with manager.session_scope() as session:
            users = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == "user")
                )
            ).scalar_one()
            assistants = (
                await session.execute(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.role == "assistant")
                )
            ).scalar_one()
            runs = (
                await session.execute(select(func.count()).select_from(AgentRun))
            ).scalar_one()
            assert int(users) == 1
            assert int(assistants) == 1
            assert int(runs) == 1
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert run.state == AgentRunState.COMPLETED.value


@pytest.mark.asyncio
async def test_disconnect_safe_state_via_service_cancel(tmp_path: Path) -> None:
    """Disconnect path: cancel_event advances to durable failed/safe state."""
    async with migrated_db(tmp_path) as (db_path, manager, _settings_obj):
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
                turn_idempotency_key="transport-disconnect-1",
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
        assert result.error in {"client_disconnected", "CLIENT_DISCONNECTED"} or (
            result.error is not None and "disconnect" in result.error.lower()
        )

        # Reconnect/replay: no second write for same key; durable outcome retained.
        replay = await service.start_turn(
            user_text="Long running CV analysis",
            turn_idempotency_key="transport-disconnect-1",
        )
        assert replay.replayed is True
        assert replay.run_id == result.run_id

        async with manager.session_scope() as session:
            msgs = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert int(msgs) == 1  # user only


@pytest.mark.asyncio
async def test_route_inventory_and_cors_on_live_app(tmp_path: Path) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings):
        chat = ChatService(
            manager,
            sqlite_path=db_path,
            decision=ScriptedDecision([decision_text("cors ok")]),
            tools=[],
        )
        application = create_app(
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
        with TestClient(application) as client:
            paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
            assert paths == {
                "/api/health",
                "/api/chat/history",
                "/api/chat/turns",
                "/api/chat/runs/{run_id}/resume",
            }
            preflight = client.options(
                "/api/chat/turns",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert "POST" in preflight.headers.get(
                "access-control-allow-methods", ""
            )
            assert preflight.headers.get("access-control-allow-origin") == (
                "http://localhost:5173"
            )
