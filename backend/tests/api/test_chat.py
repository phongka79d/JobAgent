"""API tests for Plan 3 public chat routes (fakes only; no ShopAIKey network)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import Settings, load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.schemas.sse import (
    SSEEventOrderValidator,
    parse_sse_event,
    serialize_sse_event,
)
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.fakes.agent_tools import (
    ScriptedDecision,
    decision_text,
    decision_with_tool,
    make_approval_request_tool,
    make_echo_label_tool,
)
from tests.graph.fakes import FakeDriver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-chat-api"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-chat-api"
SENTINEL_URI = "bolt://chat-api-test.invalid:7687"
LEAK_TOKENS = (
    SENTINEL_API_KEY,
    SENTINEL_NEO4J_PASSWORD,
    SENTINEL_URI,
    "Traceback",
    "Authorization",
    "SHOPAIKEY_API_KEY",
    "stack_trace",
)

APPROVED_PATHS = {
    "/api/health",
    "/api/attachments/cv",
    "/api/chat/history",
    "/api/chat/turns",
    "/api/chat/runs/{run_id}/resume",
}


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


def _upgrade_head(db_path: Path) -> None:
    previous = os.environ.get("SQLITE_PATH")
    os.environ["SQLITE_PATH"] = str(db_path)
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if previous is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = previous


def _settings(tmp_path: Path, **overrides: str) -> Settings:
    values: dict[str, str] = {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://localhost:5173",
        "VITE_API_BASE_URL": "http://localhost:8000",
        "SQLITE_PATH": str(tmp_path / "chat.db"),
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
    values.update(overrides)
    return load_settings(environ=values)


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
        raw = "\n".join(data_lines)
        events.append(json.loads(raw))
    return events


def _assert_no_leaks(payload: str, extra: tuple[str, ...] = ()) -> None:
    for token in LEAK_TOKENS + extra:
        assert token not in payload
        assert token.lower() not in payload.lower() or token in {
            "Traceback",
            "Authorization",
            "stack_trace",
        }
    lowered = payload.lower()
    for banned in (
        "traceback (most recent",
        "authorization: bearer",
        "api_key=",
        "password=",
        "shopaikey_api_key",
    ):
        assert banned not in lowered


def _build_app(
    tmp_path: Path,
    *,
    decision: Any,
    tools: list[Any] | None = None,
    frontend_origin: str = "http://localhost:5173",
) -> tuple[FastAPI, DatabaseSessionManager, Path]:
    settings = _settings(tmp_path, FRONTEND_ORIGIN=frontend_origin)
    db_path = Path(settings.sqlite_path)
    _upgrade_head(db_path)
    db = create_session_manager(db_path)
    chat = ChatService(
        db,
        sqlite_path=db_path,
        decision=decision,
        tools=tools if tools is not None else [],
    )
    application = create_app(
        settings=settings,
        session_manager=db,
        storage=FilesystemAttachmentStorage(settings.files_dir),
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=FakeDriver,
            health_timeout_seconds=0.2,
        ),
        chat_service=chat,
        run_schema_setup=False,
    )
    return application, db, db_path


@pytest.fixture
def chat_client(tmp_path: Path) -> Iterator[tuple[TestClient, DatabaseSessionManager]]:
    decision = ScriptedDecision([decision_text("Hello from assistant")])
    application, db, _db_path = _build_app(tmp_path, decision=decision, tools=[])
    with TestClient(application) as client:
        yield client, db


def test_openapi_route_inventory_exactly_health_and_three_chat_paths(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, _db = chat_client
    paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
    assert paths == APPROVED_PATHS
    assert "get" in client.app.openapi()["paths"]["/api/health"]  # type: ignore[attr-defined]
    assert "get" in client.app.openapi()["paths"]["/api/chat/history"]  # type: ignore[attr-defined]
    assert "post" in client.app.openapi()["paths"]["/api/chat/turns"]  # type: ignore[attr-defined]
    assert "post" in client.app.openapi()["paths"][
        "/api/chat/runs/{run_id}/resume"
    ]  # type: ignore[attr-defined]
    # No later-phase or synthetic public application routes.
    # `/api/attachments/cv` is the accepted Plan 4 upload boundary; profile GETs
    # and job/match routes remain later-phase.
    forbidden = ("profile", "job", "synthetic", "upload", "match")
    assert not any(any(m in p for m in forbidden) for p in paths)


def _assert_no_public_db_ids(
    history_body: dict[str, Any] | None = None,
    sse_payloads: list[dict[str, Any]] | None = None,
    *,
    forbidden_id_strings: set[str] | frozenset[str] = frozenset(),
) -> None:
    """Public history/SSE must omit conversation/message/tool-execution PKs.

    Allowed durable public identity: ``run_id`` on SSE events only.
    Tool activity may use short opaque per-stream ``tool_call_id`` values that
    are not database primary keys.
    """
    if history_body is not None:
        assert "conversation_id" not in history_body
        assert set(history_body.keys()) <= {"messages"}
        for message in history_body.get("messages", []):
            assert "id" not in message
            assert "conversation_id" not in message
            assert set(message.keys()) <= {
                "role",
                "content",
                "created_at",
                "structured_payload",
            }
            blob = json.dumps(message)
            for banned in forbidden_id_strings:
                assert banned not in blob

    if sse_payloads is not None:
        for payload in sse_payloads:
            assert "run_id" in payload
            # Never surface application table primary-key field names.
            assert "conversation_id" not in payload
            assert "message_id" not in payload
            assert "agent_run_id" not in payload
            event_blob = json.dumps(payload)
            for banned in forbidden_id_strings:
                assert banned not in event_blob
            event_payload = payload.get("payload")
            if not isinstance(event_payload, dict):
                continue
            tool_call_id = event_payload.get("tool_call_id")
            if tool_call_id is not None:
                assert isinstance(tool_call_id, str)
                assert tool_call_id not in forbidden_id_strings
                # Opaque stream-local form (t1, t2, ...), not a UUID PK.
                assert re.fullmatch(r"t[1-9]\d*", tool_call_id)


def test_history_hydration_empty_then_after_turn(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, db = chat_client
    empty = client.get("/api/chat/history")
    assert empty.status_code == 200
    body = empty.json()
    assert "conversation_id" not in body
    assert body["messages"] == []
    _assert_no_leaks(empty.text)
    _assert_no_public_db_ids(history_body=body)

    turn = client.post(
        "/api/chat/turns",
        json={
            "text": "Help me refine my CV summary",
            "idempotency_key": "turn-hist-1",
            "attachment_ids": [],
        },
    )
    assert turn.status_code == 200
    assert "text/event-stream" in turn.headers.get("content-type", "")

    hist = client.get("/api/chat/history")
    assert hist.status_code == 200
    hist_body = hist.json()
    messages = hist_body["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello from assistant"

    async def _message_pk_strings() -> set[str]:
        async with db.session_scope() as session:
            result = await session.execute(text("SELECT id FROM chat_messages"))
            return {str(row[0]) for row in result.all()}

    import anyio

    forbidden = anyio.run(_message_pk_strings)
    _assert_no_public_db_ids(
        history_body=hist_body,
        sse_payloads=_parse_sse_payloads(turn.text),
        forbidden_id_strings=forbidden,
    )


def test_history_limit_bounds(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, _db = chat_client
    for i in range(3):
        r = client.post(
            "/api/chat/turns",
            json={
                "text": f"CV tip request number {i}",
                "idempotency_key": f"turn-bound-{i}",
            },
        )
        assert r.status_code == 200

    limited = client.get("/api/chat/history", params={"limit": 2})
    assert limited.status_code == 200
    assert len(limited.json()["messages"]) == 2

    bad = client.get("/api/chat/history", params={"limit": 0})
    assert bad.status_code == 422
    over = client.get("/api/chat/history", params={"limit": 501})
    assert over.status_code == 422


def test_validation_before_write_empty_text_and_bad_key(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, db = chat_client

    async def _count_messages() -> int:
        async with db.session_scope() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM chat_messages")
            )
            return int(result.scalar_one())

    import anyio

    assert anyio.run(_count_messages) == 0

    empty = client.post(
        "/api/chat/turns",
        json={"text": "   ", "idempotency_key": "turn-empty"},
    )
    assert empty.status_code == 422
    assert anyio.run(_count_messages) == 0

    bad_key = client.post(
        "/api/chat/turns",
        json={"text": "Valid CV question", "idempotency_key": " bad key "},
    )
    assert bad_key.status_code == 422
    assert anyio.run(_count_messages) == 0

    too_many = client.post(
        "/api/chat/turns",
        json={
            "text": "Valid CV question",
            "idempotency_key": "turn-attach",
            "attachment_ids": [f"att-{i}" for i in range(33)],
        },
    )
    assert too_many.status_code == 422
    assert anyio.run(_count_messages) == 0


def test_ordered_sse_completed_and_parseable(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, _db = chat_client
    response = client.post(
        "/api/chat/turns",
        json={
            "text": "How should I structure my profile skills?",
            "idempotency_key": "turn-sse-1",
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    payloads = _parse_sse_payloads(response.text)
    assert payloads
    typed = [parse_sse_event(p) for p in payloads]
    ordered = SSEEventOrderValidator().validate_sequence(typed)
    assert str(ordered[0].event) == "run_started"
    assert str(ordered[-1].event) == "run_completed"
    terminal_count = sum(
        1 for e in ordered if str(e.event) in {"run_completed", "run_failed"}
    )
    assert terminal_count == 1
    text_bits = [
        e.payload.delta  # type: ignore[attr-defined]
        for e in ordered
        if str(e.event) == "text_delta"
    ]
    assert "".join(text_bits) == "Hello from assistant"
    _assert_no_leaks(response.text)
    # Re-serialize for leakage key scan.
    for event in ordered:
        dumped = json.dumps(serialize_sse_event(event))
        assert "arguments" not in dumped or "tool_call_id" in dumped
        assert "stack_trace" not in dumped
        assert SENTINEL_API_KEY not in dumped


def test_duplicate_turn_idempotency_no_second_write(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, db = chat_client
    body = {
        "text": "Improve my CV objective",
        "idempotency_key": "turn-dup-1",
    }
    first = client.post("/api/chat/turns", json=body)
    second = client.post("/api/chat/turns", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    p1 = _parse_sse_payloads(first.text)
    p2 = _parse_sse_payloads(second.text)
    assert p1[0]["run_id"] == p2[0]["run_id"]
    assert p2[-1]["event"] == "run_completed"

    async def _counts() -> tuple[int, int]:
        async with db.session_scope() as session:
            msgs = await session.execute(text("SELECT COUNT(*) FROM chat_messages"))
            runs = await session.execute(text("SELECT COUNT(*) FROM agent_runs"))
            return int(msgs.scalar_one()), int(runs.scalar_one())

    import anyio

    msg_n, run_n = anyio.run(_counts)
    assert msg_n == 2  # user + assistant once
    assert run_n == 1


def test_terminal_failure_sse(tmp_path: Path) -> None:
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

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

    def _failing_factory(checkpointer: Any) -> Any:
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

    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    _upgrade_head(db_path)
    db = create_session_manager(db_path)
    chat = ChatService(db, sqlite_path=db_path, graph_factory=_failing_factory)
    application = create_app(
        settings=settings,
        session_manager=db,
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
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "This will fail controllably",
                "idempotency_key": "turn-fail-api-1",
            },
        )
    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    typed = [parse_sse_event(p) for p in payloads]
    ordered = SSEEventOrderValidator().validate_sequence(typed)
    assert str(ordered[-1].event) == "run_failed"
    assert ordered[-1].payload.error_code  # type: ignore[attr-defined]
    _assert_no_leaks(response.text)


def test_cors_post_methods_exact_origin(tmp_path: Path) -> None:
    decision = ScriptedDecision([decision_text("ok")])
    application, _db, _ = _build_app(tmp_path, decision=decision)
    with TestClient(application) as client:
        preflight = client.options(
            "/api/chat/turns",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code in {200, 204}
        assert preflight.headers.get("access-control-allow-origin") == (
            "http://localhost:5173"
        )
        methods = preflight.headers.get("access-control-allow-methods", "")
        assert "POST" in methods
        assert "GET" in methods

        evil = client.options(
            "/api/chat/turns",
            headers={
                "Origin": "http://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert evil.headers.get("access-control-allow-origin") is None

        ok = client.post(
            "/api/chat/turns",
            json={"text": "CV help please", "idempotency_key": "cors-1"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert ok.status_code == 200
        assert ok.headers.get("access-control-allow-origin") == (
            "http://localhost:5173"
        )


def test_interrupt_and_resume_same_run_with_duplicate_resume_key(tmp_path: Path) -> None:
    decision = ScriptedDecision(
        [
            decision_with_tool(
                "propose_action",
                label="draft1",
                tool_call_id="c_approve_0",
            ),
            decision_text("profile draft saved after approval"),
        ]
    )
    application, db, db_path = _build_app(
        tmp_path,
        decision=decision,
        tools=[make_approval_request_tool()],
    )
    with TestClient(application) as client:
        first = client.post(
            "/api/chat/turns",
            json={
                "text": "Please update my candidate profile draft",
                "idempotency_key": "turn-resume-api-1",
            },
        )
        assert first.status_code == 200
        payloads = _parse_sse_payloads(first.text)
        typed = [parse_sse_event(p) for p in payloads]
        ordered = SSEEventOrderValidator().validate_sequence(typed)
        assert str(ordered[-1].event) == "approval_required"
        run_id = payloads[0]["run_id"]

        # Swap decision for resume finalization (same app.state chat_service).
        resume_decision = ScriptedDecision(
            [decision_text("profile draft saved after approval")]
        )
        client.app.state.chat_service = ChatService(  # type: ignore[attr-defined]
            db,
            sqlite_path=db_path,
            decision=resume_decision,
            tools=[make_approval_request_tool()],
        )

        resume_body = {
            "action": "approve",
            "idempotency_key": "resume-api-1",
        }
        resumed = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json=resume_body,
        )
        assert resumed.status_code == 200
        assert "text/event-stream" in resumed.headers.get("content-type", "")
        r_payloads = _parse_sse_payloads(resumed.text)
        r_typed = [parse_sse_event(p) for p in r_payloads]
        r_ordered = SSEEventOrderValidator().validate_sequence(r_typed)
        assert str(r_ordered[-1].event) == "run_completed"
        assert r_payloads[0]["run_id"] == run_id

        # Duplicate resume key: same run, no second assistant write.
        again = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json=resume_body,
        )
        assert again.status_code == 200
        a_payloads = _parse_sse_payloads(again.text)
        assert a_payloads[0]["run_id"] == run_id
        assert a_payloads[-1]["event"] == "run_completed"

    async def _assistant_count() -> int:
        async with db.session_scope() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant'"
                )
            )
            return int(result.scalar_one())

    import anyio

    assert anyio.run(_assistant_count) == 1


def test_tool_activity_events_sanitized(tmp_path: Path) -> None:
    decision = ScriptedDecision(
        [
            decision_with_tool("echo_label", label="x", tool_call_id="c0"),
            decision_text("done with tool"),
        ]
    )
    application, db, _ = _build_app(
        tmp_path,
        decision=decision,
        tools=[make_echo_label_tool()],
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "Match my profile to jobs",
                "idempotency_key": "turn-tool-api-1",
            },
        )
        hist = client.get("/api/chat/history")
    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    typed = [parse_sse_event(p) for p in payloads]
    SSEEventOrderValidator().validate_sequence(typed)
    kinds = [p["event"] for p in payloads]
    assert "tool_started" in kinds
    assert "tool_completed" in kinds
    assert "run_completed" in kinds
    blob = response.text.lower()
    assert "arguments" not in blob or "tool_call_id" in blob
    assert "traceback" not in blob
    assert SENTINEL_API_KEY.lower() not in blob

    async def _internal_pk_strings() -> set[str]:
        async with db.session_scope() as session:
            tools = await session.execute(text("SELECT id FROM tool_executions"))
            msgs = await session.execute(text("SELECT id FROM chat_messages"))
            return {str(row[0]) for row in tools.all()} | {
                str(row[0]) for row in msgs.all()
            }

    import anyio

    forbidden = anyio.run(_internal_pk_strings)
    assert forbidden  # tool + message rows exist; must not leak as public IDs
    _assert_no_public_db_ids(
        history_body=hist.json(),
        sse_payloads=payloads,
        forbidden_id_strings=forbidden,
    )
    tool_call_ids = [
        p["payload"]["tool_call_id"]
        for p in payloads
        if p["event"] in {"tool_started", "tool_completed"}
    ]
    assert tool_call_ids
    assert all(re.fullmatch(r"t[1-9]\d*", tid) for tid in tool_call_ids)
    assert all(tid not in forbidden for tid in tool_call_ids)


def test_resume_validation_requires_correction_text(
    chat_client: tuple[TestClient, DatabaseSessionManager],
) -> None:
    client, _db = chat_client
    response = client.post(
        f"/api/chat/runs/{uuid4()}/resume",
        json={"action": "correct", "idempotency_key": "resume-bad-1"},
    )
    assert response.status_code == 422
