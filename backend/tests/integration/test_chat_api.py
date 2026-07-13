"""Integration tests for thin chat history/turn/resume HTTP + SSE routes.

Fake-backed only (no real ShopAIKey). Covers exact URLs/shapes, direct-answer
SSE order, durable user/assistant/run state, zero tools for greetings,
malformed cursor 422, synthetic interrupt/resume through public endpoints,
safe controlled errors, and CORS origin allow/deny.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.core.ids import new_uuid
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    AgentRun,
    ChatMessage,
    ToolExecution,
)
from app.db.session import get_session_factory
from app.main import create_app
from app.repositories import agent_runs as runs_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.chat import HistoryPage
from app.schemas.sse import parse_sse_event
from app.tools.registry import ToolRegistry, production_registry
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from tests.fakes.fake_chat_model import FakeChatModel
from tests.fakes.synthetic_tool import (
    SYNTHETIC_ALLOWED_ACTIONS,
    SYNTHETIC_APPROVAL_KIND,
    SYNTHETIC_TOOL_NAME,
    build_synthetic_interrupt_tool,
)
from tests.support.db_migration import cleanup_isolated_sqlite, run_async
from tests.support.health import (
    FAKE_SHOPAIKEY,
    FakeDriver,
    health_client,
    install_fake_driver,
    prepare_health_env,
    public_api_routes,
)

FRONTEND_ORIGIN = "http://127.0.0.1:5173"
OTHER_ORIGIN = "http://evil.example:9999"


def _ai_text(content: str) -> AIMessage:
    return AIMessage(content=content)


def _ai_tool_call(name: str, call_id: str = "call-api-1") -> AIMessage:
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


def _parse_sse(body: str) -> list[dict[str, Any]]:
    """Parse SSE wire text into validated event dicts (full data envelope)."""
    events: list[dict[str, Any]] = []
    # Split on blank line terminators.
    for chunk in re.split(r"\n\n+", body.strip()):
        if not chunk.strip() or chunk.strip().startswith(":"):
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        event_id: str | None = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
            elif line.startswith("id:"):
                event_id = line[len("id:") :].strip()
        if not data_lines:
            continue
        data = json.loads("\n".join(data_lines))
        typed = parse_sse_event(data)
        assert typed.event == event_name or event_name is None
        if event_id is not None:
            assert typed.event_id == event_id
        events.append(data)
    return events


@pytest.fixture
def chat_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    """Migrated temp SQLite + FILES_DIR + fake Neo4j for API tests."""
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()


def _direct_model(
    text: str = "Hello! How can I help with your job search?",
) -> FakeChatModel:
    return FakeChatModel(responses=[_ai_text(text)])

def _override_deps(
    client: TestClient,
    *,
    model: FakeChatModel,
    registry: ToolRegistry | None = None,
    db_path: Path,
) -> None:
    deps = ChatAgentDeps(
        model=model,
        registry=registry if registry is not None else production_registry(),
        sqlite_path=db_path,
        include_assistant_status=False,
    )
    client.app.dependency_overrides[get_chat_agent_deps] = lambda: deps


def _client_with_fake(
    db_path: Path,
    model: FakeChatModel,
    registry: ToolRegistry | None = None,
) -> TestClient:
    app = create_app()
    client = TestClient(app)
    _override_deps(client, model=model, registry=registry, db_path=db_path)
    return client


# ---------------------------------------------------------------------------
# Route inventory and thinness
# ---------------------------------------------------------------------------


def test_public_routes_are_exactly_seven_master_endpoints(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    """Master §14: health, CV upload, profile/CV reads, three chat routes."""
    with health_client() as client:
        routes = sorted(public_api_routes(client.app))
    assert routes == sorted(
        [
            ("GET", "/api/health"),
            ("POST", "/api/attachments/cv"),
            ("GET", "/api/profile"),
            ("GET", "/api/profile/cv"),
            ("GET", "/api/chat/history"),
            ("POST", "/api/chat/turns"),
            ("POST", "/api/chat/runs/{run_id}/resume"),
        ]
    )
    # No profile write CRUD.
    for method, path in routes:
        if path.startswith("/api/profile"):
            assert method == "GET"


def test_route_handlers_are_transport_thin() -> None:
    """Static evidence: chat routes have no graph/SQLAlchemy/provider work."""
    chat_src = (
        Path(__file__).resolve().parents[2] / "app" / "api" / "chat.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "StateGraph",
        "ChatOpenAI",
        "build_agent_graph",
        "create_all",
        "AsyncSqliteSaver",
        "insert_message",
        "create_run",
        "session.execute",
    )
    for needle in forbidden:
        assert needle not in chat_src, f"chat route leaked {needle!r}"
    assert "stream_chat_turn" in chat_src
    assert "stream_resume" in chat_src
    assert "get_history_page" in chat_src
    assert "EventSourceResponse" in chat_src


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_empty_page_shape(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    with _client_with_fake(db_path, _direct_model()) as client:
        response = client.get("/api/chat/history")
    assert response.status_code == 200
    body = response.json()
    page = HistoryPage.model_validate(body)
    assert set(body.keys()) == {"items", "next_cursor"}
    assert page.items == []
    assert page.next_cursor is None


def test_history_malformed_cursor_returns_422(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    with _client_with_fake(db_path, _direct_model()) as client:
        bad = client.get(
            "/api/chat/history",
            params={"before": "!!!not-base64!!!"},
        )
        assert bad.status_code == 422
        assert FAKE_SHOPAIKEY not in bad.text
        assert "Traceback" not in bad.text

        bad_limit = client.get("/api/chat/history", params={"limit": 0})
        assert bad_limit.status_code == 422
        bad_limit2 = client.get("/api/chat/history", params={"limit": 101})
        assert bad_limit2.status_code == 422


# ---------------------------------------------------------------------------
# Approved candidate_context injection on new turns
# ---------------------------------------------------------------------------


def test_turn_injects_approved_candidate_context_not_draft(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    """New turns load approved compact profile; pending draft is ignored."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.repositories import attachments as att_repo
    from app.repositories import profiles as profile_repo
    from app.storage.attachments import AttachmentStorage

    db_path, files_dir, _fake = chat_env
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    profile_json = {
        "summary": "APPROVED_CTX_SUMMARY",
        "current_title": "Approved Engineer",
        "total_experience_years": 4.0,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": ["python3"],
                    "category": "language",
                },
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 4.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["Python backend"],
            }
        ],
        "experiences": [
            {
                "title": "Engineer",
                "company": "Co",
                "start_date_text": "2020",
                "end_date_text": "present",
                "summary": "APIs",
            }
        ],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.8,
    }
    prefs_json = {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }
    draft_json = {
        "candidate_profile": {
            **profile_json,
            "summary": "DRAFT_CTX_SUMMARY_SHOULD_NOT_APPEAR",
            "current_title": "Draft Only Title",
        },
        "job_preferences": {
            **prefs_json,
            "target_roles": ["Draft Role Only"],
        },
    }

    async def _seed() -> None:
        factory = get_session_factory()
        async with factory() as session:
            att_id = new_uuid()
            storage.write_bytes(att_id, b"%PDF-1.4 chat-ctx\n%%EOF\n")
            await att_repo.create_staged(
                session,
                file_hash="ctx-active-hash",
                original_name="approved.pdf",
                size_bytes=20,
                storage_path=att_id,
                page_count=1,
                attachment_id=att_id,
            )
            await att_repo.mark_active(session, att_id, page_count=1)
            await profile_repo.upsert_active_profile(
                session,
                active_attachment_id=att_id,
                profile_json=profile_json,
            )
            await profile_repo.upsert_job_preferences(
                session, preferences_json=prefs_json
            )
            staged_id = new_uuid()
            storage.write_bytes(staged_id, b"%PDF-1.4 draft-ctx\n%%EOF\n")
            staged = await att_repo.create_staged(
                session,
                file_hash="ctx-staged-hash",
                original_name="draft.pdf",
                size_bytes=20,
                storage_path=staged_id,
                page_count=1,
                attachment_id=staged_id,
            )
            await profile_repo.upsert_current_draft(
                session,
                source_attachment_id=staged.id,
                draft_json=draft_json,
            )
            await session.commit()
            assert ATTACHMENT_STATE_ACTIVE == "active"

    run_async(_seed())

    model = _direct_model("I see your approved profile.")
    with _client_with_fake(db_path, model) as client:
        response = client.post(
            "/api/chat/turns",
            json={"message": "what is my title?", "attachment_ids": []},
        )
        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["event"] == "run_completed"

    assert model.invoke_count >= 1
    joined = "\n".join(
        str(m.content) for call in model.call_log for m in call
    )
    assert "APPROVED_CTX_SUMMARY" in joined
    assert "Approved Engineer" in joined
    assert "Backend Engineer" in joined
    assert "DRAFT_CTX_SUMMARY_SHOULD_NOT_APPEAR" not in joined
    assert "Draft Only Title" not in joined
    assert "Draft Role Only" not in joined
    assert "storage_path" not in joined
    assert "raw_cv" not in joined
    assert "%PDF" not in joined


# ---------------------------------------------------------------------------
# Direct greeting turn via public SSE
# ---------------------------------------------------------------------------


def test_turn_greeting_sse_order_and_persistence(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    reply = "Hello! Happy to help with your search."
    model = _direct_model(reply)
    with _client_with_fake(db_path, model) as client:
        response = client.post(
            "/api/chat/turns",
            json={"message": "hi there", "attachment_ids": []},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert FAKE_SHOPAIKEY not in response.text
        assert "Traceback" not in response.text
        events = _parse_sse(response.text)
        names = [e["event"] for e in events]
        assert names[0] == "run_started"
        assert events[0]["payload"]["state"] == "running"
        assert events[0]["payload"]["resumed"] is False
        assert "tool_status" not in names
        assert "approval_required" not in names
        assert "text_delta" in names
        assert names[-1] == "run_completed"
        assert events[-1]["payload"]["state"] == "completed"
        # Ordered non-empty deltas
        deltas = [
            e["payload"]["delta"] for e in events if e["event"] == "text_delta"
        ]
        assert deltas and all(d for d in deltas)
        assert "".join(deltas) == reply

        # Durable history reflects user + assistant + one completed run, zero tools
        hist = client.get("/api/chat/history", params={"limit": 50})
        assert hist.status_code == 200
        page = HistoryPage.model_validate(hist.json())
        assert len(page.items) == 2
        user, assistant = page.items[0], page.items[1]
        assert user.role == CHAT_MESSAGE_ROLE_USER
        assert user.content == "hi there"
        assert user.run is not None
        assert user.run.state == AGENT_RUN_STATE_COMPLETED
        assert user.run.tool_executions == []
        assert assistant.role == CHAT_MESSAGE_ROLE_ASSISTANT
        assert assistant.content == reply
        assert assistant.run is None

    async def _counts() -> tuple[int, int, int]:
        factory = get_session_factory()
        async with factory() as session:
            msgs = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ChatMessage)
                    )
                ).scalar_one()
            )
            runs = int(
                (
                    await session.execute(
                        select(func.count()).select_from(AgentRun)
                    )
                ).scalar_one()
            )
            tools = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ToolExecution)
                    )
                ).scalar_one()
            )
            return msgs, runs, tools

    assert run_async(_counts()) == (2, 1, 0)
    assert model.invoke_count >= 1


def test_turn_empty_message_422(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    with _client_with_fake(db_path, _direct_model()) as client:
        response = client.post(
            "/api/chat/turns",
            json={"message": "   ", "attachment_ids": []},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Synthetic interrupt/resume through public endpoints
# ---------------------------------------------------------------------------


def test_public_turn_resume_synthetic_interrupt(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    counter: dict[str, int] = {"n": 0}
    factory = get_session_factory()
    tool = build_synthetic_interrupt_tool(
        session_factory=factory,
        side_effect_counter=counter,
    )
    model = FakeChatModel(
        responses=[
            _ai_tool_call(SYNTHETIC_TOOL_NAME),
            _ai_text("Done after approval."),
        ]
    )
    registry = ToolRegistry([tool])

    with _client_with_fake(db_path, model, registry) as client:
        turn = client.post(
            "/api/chat/turns",
            json={"message": "please interrupt", "attachment_ids": []},
        )
        assert turn.status_code == 200
        events = _parse_sse(turn.text)
        names = [e["event"] for e in events]
        assert names[0] == "run_started"
        assert names[-1] == "approval_required"
        assert "run_completed" not in names
        assert counter["n"] == 0
        approval = events[-1]
        assert approval["payload"]["kind"] == SYNTHETIC_APPROVAL_KIND
        assert approval["payload"]["allowed_actions"] == list(
            SYNTHETIC_ALLOWED_ACTIONS
        )
        run_id = approval["run_id"]

        # New turn blocked while interrupted
        blocked = client.post(
            "/api/chat/turns",
            json={"message": "another turn", "attachment_ids": []},
        )
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["code"] == "APPROVAL_ACTION_REQUIRED"
        assert FAKE_SHOPAIKEY not in blocked.text
        assert "Traceback" not in blocked.text

        # Invalid action leaves interruption unchanged
        bad_resume = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json={"action": "not_an_action"},
        )
        assert bad_resume.status_code == 400
        assert bad_resume.json()["detail"]["code"] == "INVALID_APPROVAL_ACTION"

        # Resume across request boundary with same run_id
        model2 = FakeChatModel(responses=[_ai_text("Approved path finished.")])
        tool2 = build_synthetic_interrupt_tool(
            session_factory=factory,
            side_effect_counter=counter,
        )
        _override_deps(
            client,
            model=model2,
            registry=ToolRegistry([tool2]),
            db_path=db_path,
        )
        resume = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json={"action": "approve"},
        )
        assert resume.status_code == 200
        rev = _parse_sse(resume.text)
        rnames = [e["event"] for e in rev]
        assert rnames[0] == "run_started"
        assert rev[0]["payload"]["resumed"] is True
        assert rnames[-1] == "run_completed"
        assert counter["n"] == 1

        # Terminal no-op resume
        model3 = FakeChatModel(responses=[_ai_text("should not run")])
        _override_deps(
            client,
            model=model3,
            registry=ToolRegistry([]),
            db_path=db_path,
        )
        noop = client.post(
            f"/api/chat/runs/{run_id}/resume",
            json={"action": "approve"},
        )
        assert noop.status_code == 200
        nevents = _parse_sse(noop.text)
        assert [e["event"] for e in nevents] == ["run_started", "run_completed"]
        assert model3.invoke_count == 0
        assert counter["n"] == 1

    async def _assert_db() -> None:
        factory2 = get_session_factory()
        async with factory2() as session:
            run = await runs_repo.get_run(session, run_id)
            assert run is not None
            assert run.state == AGENT_RUN_STATE_COMPLETED
            tools = await tool_repo.list_for_run_ids(session, [run_id])
            assert len(tools) == 1
            assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
            assert tools[0].result_json is not None

    run_async(_assert_db())

    async def _checkpoint_gone() -> bool:
        async with open_checkpointer(db_path) as saver:
            return await thread_has_checkpoints(saver, run_id)

    assert run_async(_checkpoint_gone()) is False


def test_resume_unknown_run_404(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    missing = new_uuid()
    with _client_with_fake(db_path, _direct_model()) as client:
        response = client.post(
            f"/api/chat/runs/{missing}/resume",
            json={"action": "approve"},
        )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_allows_configured_origin_get_and_post(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    with _client_with_fake(db_path, _direct_model()) as client:
        # Preflight for POST turns
        preflight = client.options(
            "/api/chat/turns",
            headers={
                "Origin": FRONTEND_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code in (200, 204)
        allow_origin = preflight.headers.get("access-control-allow-origin")
        assert allow_origin == FRONTEND_ORIGIN
        allow_methods = preflight.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods.upper() or "POST" in allow_methods
        assert "GET" in allow_methods.upper() or "GET" in allow_methods

        get_resp = client.get(
            "/api/chat/history",
            headers={"Origin": FRONTEND_ORIGIN},
        )
        assert get_resp.status_code == 200
        assert get_resp.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN

        post_resp = client.post(
            "/api/chat/turns",
            json={"message": "hello", "attachment_ids": []},
            headers={"Origin": FRONTEND_ORIGIN},
        )
        assert post_resp.status_code == 200
        assert post_resp.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_cors_rejects_disallowed_origin(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env
    with _client_with_fake(db_path, _direct_model()) as client:
        preflight = client.options(
            "/api/chat/turns",
            headers={
                "Origin": OTHER_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        # Starlette CORS omits allow-origin for disallowed origins
        assert preflight.headers.get("access-control-allow-origin") != OTHER_ORIGIN

        get_resp = client.get(
            "/api/chat/history",
            headers={"Origin": OTHER_ORIGIN},
        )
        assert get_resp.headers.get("access-control-allow-origin") != OTHER_ORIGIN


def test_history_after_turn_has_cursor_when_paged(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    """History API returns exact shape after durable turns (pagination smoke)."""
    db_path, _files, _fake = chat_env
    model = FakeChatModel(
        responses=[
            _ai_text("A1"),
            _ai_text("A2"),
            _ai_text("A3"),
        ]
    )
    with _client_with_fake(db_path, model) as client:
        for i in range(3):
            r = client.post(
                "/api/chat/turns",
                json={"message": f"msg {i}", "attachment_ids": []},
            )
            assert r.status_code == 200
            assert _parse_sse(r.text)[-1]["event"] == "run_completed"

        page1 = client.get("/api/chat/history", params={"limit": 2})
        assert page1.status_code == 200
        body = page1.json()
        assert set(body.keys()) == {"items", "next_cursor"}
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None
        page2 = client.get(
            "/api/chat/history",
            params={"limit": 2, "before": body["next_cursor"]},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert set(body2.keys()) == {"items", "next_cursor"}
        # No duplicate ids across pages
        ids1 = {item["id"] for item in body["items"]}
        ids2 = {item["id"] for item in body2["items"]}
        assert ids1.isdisjoint(ids2)
