"""Integration tests for thin chat history/turn/resume HTTP + SSE routes.

Fake-backed only (no real ShopAIKey). Covers exact URLs/shapes, direct-answer
SSE order, durable user/assistant/run state, zero tools for greetings,
malformed cursor 422, synthetic interrupt/resume through public endpoints,
safe controlled errors, and CORS origin allow/deny.

Public SSE/client helpers live in ``tests.support.public_api`` (shared with E2E).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
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
from app.repositories import agent_runs as runs_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.chat import HistoryPage
from app.tools.registry import ToolRegistry
from sqlalchemy import func, select

from tests.fakes.fake_chat_model import FakeChatModel, PassiveJdBindingAwareFake
from tests.fakes.synthetic_tool import (
    SYNTHETIC_ALLOWED_ACTIONS,
    SYNTHETIC_APPROVAL_KIND,
    SYNTHETIC_TOOL_NAME,
    build_synthetic_interrupt_tool,
)
from tests.support.db_migration import run_async
from tests.support.health import (
    FAKE_SHOPAIKEY,
    FakeDriver,
    health_client,
    public_api_routes,
)
from tests.support.public_api import (
    FRONTEND_ORIGIN,
    OTHER_ORIGIN,
)
from tests.support.public_api import (
    ai_text as _ai_text,
)
from tests.support.public_api import (
    ai_tool_call as _ai_tool_call,
)
from tests.support.public_api import (
    client_with_fake_chat as _client_with_fake,
)
from tests.support.public_api import (
    direct_model as _direct_model,
)
from tests.support.public_api import (
    override_chat_deps as _override_deps,
)
from tests.support.public_api import (
    parse_sse_wire as _parse_sse,
)

# ---------------------------------------------------------------------------
# Route inventory and thinness
# ---------------------------------------------------------------------------


def test_public_routes_are_exactly_seven_master_endpoints(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    """Public inventory after Plan 8/9: chat + CV manager + observability."""
    del chat_env
    expected = [
        ("DELETE", "/api/cvs/{attachment_id}"),
        ("DELETE", "/api/jobs/{job_id}"),
        ("GET", "/api/chat/history"),
        ("GET", "/api/health"),
        ("GET", "/api/jobs"),
        ("GET", "/api/jobs/{job_id}"),
        ("GET", "/api/observability/cvs"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks/{ordinal}"),
        ("GET", "/api/observability/cvs/{attachment_id}/file"),
            ("GET", "/api/observability/graph"),
            ("GET", "/api/observability/runs"),
            ("GET", "/api/observability/skill-map"),
            ("GET", "/api/profile"),
        ("GET", "/api/profile/cv"),
        ("POST", "/api/attachments/cv"),
        ("POST", "/api/chat/runs/{run_id}/resume"),
        ("POST", "/api/chat/turns"),
        ("POST", "/api/cvs/{attachment_id}/reprocess"),
        ("POST", "/api/jobs/save-and-evaluate"),
        ("POST", "/api/jobs/{job_id}/evaluate"),
        ("POST", "/api/jobs/{job_id}/reextract"),
    ]
    with health_client() as client:
        routes = sorted(public_api_routes(client.app))
    assert routes == sorted(expected)
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
# Plan 12 (01B) / Plan 13 (01C): public save_job confirmation + side effects
# ---------------------------------------------------------------------------


_PUBLIC_JD_MESSAGE = (
    "Job Description\n"
    "Backend Engineer at Acme\n"
    "Location: Berlin\n"
    "Responsibilities\n"
    "- Design REST services\n"
    "- Own deployments\n"
    "Requirements\n"
    "- 3+ years Python experience required for this role\n"
    "- Strong communication skills\n"
    "About the role: build APIs for local demo customers with care."
)

# Five-line 300+ non-whitespace passive JD for binding-aware public path.
_BINDING_AWARE_PUBLIC_JD = (
    "Job Description: Plan13 Labs is hiring a Synthetic Platform Engineer.\n"
    "Responsibilities: Build FastAPI services, design deterministic integration "
    "tests, review SQLite transactions, and keep Neo4j synchronization retry-safe.\n"
    "Requirements: At least two years of Python backend experience, strong SQL, "
    "and practical Docker skills for local portfolio work in Hanoi.\n"
    "Qualifications: Experience with REST APIs, pytest, Git, typed data models, "
    "and clear technical documentation for synthetic acceptance fixtures.\n"
    "Skills: Python, FastAPI, SQL, Docker, pytest, Neo4j, and TypeScript "
    "collaboration; this is entirely synthetic acceptance data for Plan 13."
)


def _install_public_cm_spies(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, str | None]], AsyncMock, AsyncMock]:
    """Record durable source reads; fail if passive confirmation evaluates."""
    import app.tools.jobs as jobs_tools
    from app.services import job_evaluation, saved_jobs
    from app.services.job_save_confirmation import InitiatingMessage

    real_ingest_raw_text = jobs_tools.ingest_raw_text
    ingest_spy = AsyncMock(wraps=real_ingest_raw_text)
    monkeypatch.setattr(jobs_tools, "ingest_raw_text", ingest_spy)

    evaluation_spy = AsyncMock(
        side_effect=AssertionError("passive save must not evaluate")
    )
    monkeypatch.setattr(saved_jobs, "evaluate_job", evaluation_spy)
    monkeypatch.setattr(job_evaluation, "evaluate_job", evaluation_spy)

    real_resolve = jobs_tools.resolve_initiating_user_message
    source_reads: list[tuple[str, str | None]] = []

    async def recording_resolve(session: Any, run_id: str) -> Any:
        resolved = await real_resolve(session, run_id)
        content = (
            resolved.content if isinstance(resolved, InitiatingMessage) else None
        )
        source_reads.append((run_id, content))
        return resolved

    monkeypatch.setattr(
        jobs_tools,
        "resolve_initiating_user_message",
        recording_resolve,
    )
    return source_reads, ingest_spy, evaluation_spy


def test_public_passive_binding_aware_confirmation_card(
    chat_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binding-aware repair reaches public approval_required with strict card."""
    from app.db.models.job_evaluations import JobEvaluation
    from app.db.models.jobs import JobPost
    from app.services.jd_extraction import ExtractedJobPost
    from app.services.skill_normalization import SkillNormalizer
    from app.tools.jobs import SAVE_JOB_NAME, build_save_job_tool
    from app.tools.registry import production_registry
    from sqlalchemy import func, select

    from tests.fakes.embeddings import FakeEmbeddingClient
    from tests.fakes.structured_output import FakeJdInvoker

    db_path, _files, _fake = chat_env
    factory = get_session_factory()
    source_reads, ingest_spy, evaluation_spy = _install_public_cm_spies(monkeypatch)

    skills = (
        Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"
    )
    normalizer = SkillNormalizer.from_path(skills)
    # Grounded to _BINDING_AWARE_PUBLIC_JD (Plan 15 semantic guard).
    extracted = ExtractedJobPost.model_validate(
        {
            "title": "Synthetic Platform Engineer",
            "company": "Plan13 Labs",
            "summary": "Build FastAPI services",
            "responsibilities": ["Build FastAPI services"],
            "required_skills": [
                {
                    "name": "Python",
                    "confidence": 0.9,
                    "evidence": ["two years of Python backend experience"],
                }
            ],
            "preferred_skills": [],
            "seniority": "mid",
            "min_experience_years": 2.0,
            "max_experience_years": 5.0,
            "location": "Hanoi",
            "work_mode": "unknown",
            "extraction_confidence": 0.85,
        }
    )
    invoker = FakeJdInvoker([extracted])
    embedder = FakeEmbeddingClient()
    tool_fn = build_save_job_tool(
        session_factory=factory,
        invoker=invoker,
        normalizer=normalizer,
        embedding_client=embedder,
    )
    # Full production registry so normal bind exposes seven tools; repair
    # substitutes the compatible save_job definition with forced choice.
    registry = production_registry()
    # Replace production save_job with the fake-backed instance for this path.
    tools = [
        tool_fn if getattr(t, "name", None) == SAVE_JOB_NAME else t
        for t in registry.list_tools()
    ]
    model = PassiveJdBindingAwareFake(
        mixed_text=_BINDING_AWARE_PUBLIC_JD,
        preview_value="Synthetic Platform Engineer",
        argument_value="Plan13 Labs",
        provider_payload_value="PROVIDER-PAYLOAD-SENTINEL-DO-NOT-LOG",
        permit_valid_repair=True,
    )
    with _client_with_fake(db_path, model, ToolRegistry(tools)) as client:
        turn = client.post(
            "/api/chat/turns",
            json={"message": _BINDING_AWARE_PUBLIC_JD, "attachment_ids": []},
        )
        assert turn.status_code == 200
        events = _parse_sse(turn.text)
        event_names = [e["event"] for e in events]
        assert event_names[-1] == "approval_required"
        approval = events[-1]["payload"]
        assert approval["kind"] == "job_save_confirmation"
        assert approval["allowed_actions"] == ["save_job", "cancel_save_job"]
        assert approval["card"]["source"] == "current_message"
        assert approval["card"]["tool_name"] == SAVE_JOB_NAME
        assert approval["card"]["text_length"] == len(_BINDING_AWARE_PUBLIC_JD)
        # Strict projection: no raw body key, message id, or JD content.
        assert "text" not in approval["card"]
        assert "content" not in approval["card"]
        assert "message_id" not in str(approval)
        assert "user_message_id" not in str(approval)
        assert _BINDING_AWARE_PUBLIC_JD not in turn.text
        assert _BINDING_AWARE_PUBLIC_JD not in str(approval)
        run_id = events[-1]["run_id"]
        assert source_reads == [(run_id, _BINDING_AWARE_PUBLIC_JD)]
        assert ingest_spy.await_count == 0
        assert evaluation_spy.await_count == 0
        assert len(invoker.calls) == 0
        assert len(embedder.calls) == 0
        # Canonical path: the provider is bound for compatibility but never
        # chooses source arguments for an obvious passive JD.
        assert model.invoke_count == 0
        assert len(model.binding_log) == 2
        _normal_tools, normal_kwargs = model.binding_log[0]
        assert "tool_choice" not in normal_kwargs

    async def _assert_pending() -> None:
        async with factory() as session:
            tools_rows = await tool_repo.list_for_run_ids(session, [run_id])
            assert len(tools_rows) == 1
            assert tools_rows[0].status == "running"
            job_count = await session.execute(
                select(func.count()).select_from(JobPost)
            )
            assert int(job_count.scalar_one()) == 0
            eval_count = await session.execute(
                select(func.count()).select_from(JobEvaluation)
            )
            assert int(eval_count.scalar_one()) == 0

    run_async(_assert_pending())


def test_public_save_job_current_message_interrupt_cancel_and_save(
    chat_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public SSE: exact card, two-read cancel/save, zero evaluation."""
    from app.db.models.job_evaluations import JobEvaluation
    from app.db.models.jobs import JobPost
    from app.services.jd_extraction import ExtractedJobPost
    from app.services.skill_normalization import SkillNormalizer
    from app.tools.jobs import SAVE_JOB_NAME, build_save_job_tool
    from sqlalchemy import func, select

    from tests.fakes.embeddings import FakeEmbeddingClient
    from tests.fakes.structured_output import FakeJdInvoker

    db_path, _files, _fake = chat_env
    factory = get_session_factory()
    source_reads, ingest_spy, evaluation_spy = _install_public_cm_spies(monkeypatch)
    skills = (
        Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"
    )
    normalizer = SkillNormalizer.from_path(skills)

    # Grounded to _PUBLIC_JD_MESSAGE (Plan 15 semantic guard).
    extracted = ExtractedJobPost.model_validate(
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "summary": "build APIs for local demo customers with care",
            "responsibilities": ["Design REST services", "Own deployments"],
            "required_skills": [
                {
                    "name": "Python",
                    "confidence": 0.9,
                    "evidence": [
                        "3+ years Python experience required for this role"
                    ],
                }
            ],
            "preferred_skills": [],
            "seniority": "mid",
            "min_experience_years": 3.0,
            "max_experience_years": 5.0,
            "location": "Berlin",
            "work_mode": "unknown",
            "extraction_confidence": 0.85,
        }
    )

    # --- Cancel path ---
    invoker_cancel = FakeJdInvoker([extracted])
    embedder_cancel = FakeEmbeddingClient()
    tool_cancel = build_save_job_tool(
        session_factory=factory,
        invoker=invoker_cancel,
        normalizer=normalizer,
        embedding_client=embedder_cancel,
    )
    model_cancel = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                call_id="call-public-cm-cancel",
                args={
                    "source": "current_message",
                    "preview": {
                        "title": "Backend Engineer",
                        "company": "Acme",
                        "skills": ["Python"],
                    },
                },
            ),
            _ai_text("Waiting for confirmation."),
        ]
    )
    with _client_with_fake(
        db_path, model_cancel, ToolRegistry([tool_cancel])
    ) as client:
        turn = client.post(
            "/api/chat/turns",
            json={"message": _PUBLIC_JD_MESSAGE, "attachment_ids": []},
        )
        assert turn.status_code == 200
        events = _parse_sse(turn.text)
        names = [e["event"] for e in events]
        assert names[0] == "run_started"
        assert names[-1] == "approval_required"
        assert "run_completed" not in names
        approval = events[-1]
        payload = approval["payload"]
        assert payload["kind"] == "job_save_confirmation"
        assert payload["allowed_actions"] == ["save_job", "cancel_save_job"]
        card = payload["card"]
        assert card["tool_name"] == SAVE_JOB_NAME
        assert card["tool_call_id"] == "call-public-cm-cancel"
        assert card["source"] == "current_message"
        assert card["text_length"] == len(_PUBLIC_JD_MESSAGE)
        assert card["preview"]["title"] == "Backend Engineer"
        assert _PUBLIC_JD_MESSAGE not in turn.text
        assert "user_message_id" not in turn.text
        assert "raw_content" not in turn.text
        assert len(invoker_cancel.calls) == 0
        run_cancel = approval["run_id"]
        assert source_reads == [(run_cancel, _PUBLIC_JD_MESSAGE)]
        assert ingest_spy.await_count == 0
        assert evaluation_spy.await_count == 0

        # Invalid action leaves interrupt in place
        bad = client.post(
            f"/api/chat/runs/{run_cancel}/resume",
            json={"action": "approve"},
        )
        assert bad.status_code == 400
        assert bad.json()["detail"]["code"] == "INVALID_APPROVAL_ACTION"

        model_resume = FakeChatModel(
            responses=[_ai_text("Understood; JD was not saved.")]
        )
        tool_cancel2 = build_save_job_tool(
            session_factory=factory,
            invoker=invoker_cancel,
            normalizer=normalizer,
            embedding_client=embedder_cancel,
        )
        _override_deps(
            client,
            model=model_resume,
            registry=ToolRegistry([tool_cancel2]),
            db_path=db_path,
        )
        resume = client.post(
            f"/api/chat/runs/{run_cancel}/resume",
            json={"action": "cancel_save_job"},
        )
        assert resume.status_code == 200
        rev = _parse_sse(resume.text)
        assert "run_completed" in [e["event"] for e in rev]
        assert len(invoker_cancel.calls) == 0
        # Cancel re-entry: one fresh read (two total); zero domain side effects.
        assert source_reads == [
            (run_cancel, _PUBLIC_JD_MESSAGE),
            (run_cancel, _PUBLIC_JD_MESSAGE),
        ]
        assert ingest_spy.await_count == 0
        assert evaluation_spy.await_count == 0

    async def _assert_cancel() -> None:
        async with factory() as session:
            run = await runs_repo.get_run(session, run_cancel)
            assert run is not None
            assert run.state == AGENT_RUN_STATE_COMPLETED
            tools = await tool_repo.list_for_run_ids(session, [run_cancel])
            assert len(tools) == 1
            assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
            data = tools[0].result_json
            assert data is not None
            assert data.get("data") == {
                "committed": False,
                "outcome": "cancelled",
            }
            job_count = await session.execute(
                select(func.count()).select_from(JobPost)
            )
            assert int(job_count.scalar_one()) == 0
            eval_count = await session.execute(
                select(func.count()).select_from(JobEvaluation)
            )
            assert int(eval_count.scalar_one()) == 0

    run_async(_assert_cancel())

    # --- Save path (separate turn) ---
    save_reads_start = len(source_reads)
    invoker_save = FakeJdInvoker([extracted])
    embedder_save = FakeEmbeddingClient()
    tool_save = build_save_job_tool(
        session_factory=factory,
        invoker=invoker_save,
        normalizer=normalizer,
        embedding_client=embedder_save,
    )
    model_save = FakeChatModel(
        responses=[
            _ai_tool_call(
                SAVE_JOB_NAME,
                call_id="call-public-cm-save",
                args={"source": "current_message"},
            ),
            _ai_text("Waiting for confirmation."),
        ]
    )
    with _client_with_fake(
        db_path, model_save, ToolRegistry([tool_save])
    ) as client:
        turn = client.post(
            "/api/chat/turns",
            json={"message": _PUBLIC_JD_MESSAGE, "attachment_ids": []},
        )
        assert turn.status_code == 200
        events = _parse_sse(turn.text)
        assert events[-1]["event"] == "approval_required"
        run_save = events[-1]["run_id"]
        assert len(invoker_save.calls) == 0
        assert source_reads[save_reads_start:] == [
            (run_save, _PUBLIC_JD_MESSAGE)
        ]
        assert ingest_spy.await_count == 0

        tool_save2 = build_save_job_tool(
            session_factory=factory,
            invoker=invoker_save,
            normalizer=normalizer,
            embedding_client=embedder_save,
        )
        _override_deps(
            client,
            model=FakeChatModel(responses=[_ai_text("Saved the JD.")]),
            registry=ToolRegistry([tool_save2]),
            db_path=db_path,
        )
        resume = client.post(
            f"/api/chat/runs/{run_save}/resume",
            json={"action": "save_job"},
        )
        assert resume.status_code == 200
        rev = _parse_sse(resume.text)
        assert "run_completed" in [e["event"] for e in rev]
        assert len(invoker_save.calls) == 1
        assert source_reads[save_reads_start:] == [
            (run_save, _PUBLIC_JD_MESSAGE),
            (run_save, _PUBLIC_JD_MESSAGE),
        ]
        assert ingest_spy.await_count == 1
        assert ingest_spy.await_args.args[0] == _PUBLIC_JD_MESSAGE
        assert evaluation_spy.await_count == 0

        # Terminal no-op resume
        _override_deps(
            client,
            model=FakeChatModel(responses=[_ai_text("should not run")]),
            registry=ToolRegistry([]),
            db_path=db_path,
        )
        noop = client.post(
            f"/api/chat/runs/{run_save}/resume",
            json={"action": "save_job"},
        )
        assert noop.status_code == 200
        nevents = _parse_sse(noop.text)
        assert [e["event"] for e in nevents] == ["run_started", "run_completed"]
        assert len(invoker_save.calls) == 1
        assert len(source_reads[save_reads_start:]) == 2
        assert ingest_spy.await_count == 1
        assert evaluation_spy.await_count == 0

    async def _assert_save() -> None:
        async with factory() as session:
            tools = await tool_repo.list_for_run_ids(session, [run_save])
            assert len(tools) == 1
            assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
            result = tools[0].result_json
            assert result is not None
            assert result.get("ok") is True
            data = result.get("data") or {}
            assert data.get("outcome") == "created"
            assert data.get("sqlite_committed") is True
            job_id = data.get("job_id")
            assert job_id
            from app.repositories import jobs as jobs_repo

            row = await jobs_repo.get_by_id(session, job_id)
            assert row is not None
            assert row.raw_content == _PUBLIC_JD_MESSAGE
            job_count = await session.execute(
                select(func.count()).select_from(JobPost)
            )
            assert int(job_count.scalar_one()) == 1
            eval_count = await session.execute(
                select(func.count()).select_from(JobEvaluation)
            )
            assert int(eval_count.scalar_one()) == 0

    run_async(_assert_save())


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


def test_cors_allows_configured_origin_delete_preflight(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    """Representative Job and CV DELETE preflights succeed and advertise DELETE."""
    db_path, _files, _fake = chat_env
    job_id = new_uuid()
    attachment_id = new_uuid()
    with _client_with_fake(db_path, _direct_model()) as client:
        for path in (
            f"/api/jobs/{job_id}",
            f"/api/cvs/{attachment_id}",
        ):
            preflight = client.options(
                path,
                headers={
                    "Origin": FRONTEND_ORIGIN,
                    "Access-Control-Request-Method": "DELETE",
                },
            )
            assert preflight.status_code in (200, 204)
            assert (
                preflight.headers.get("access-control-allow-origin")
                == FRONTEND_ORIGIN
            )
            allow_methods = preflight.headers.get(
                "access-control-allow-methods", ""
            )
            methods_upper = allow_methods.upper()
            assert "DELETE" in methods_upper
            # Retained GET/POST advertisement on the same allowlist.
            assert "GET" in methods_upper
            assert "POST" in methods_upper


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
