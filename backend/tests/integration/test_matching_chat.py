"""Integration: match-results SSE card, history hydration, sanitized tool activity."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from app.config import load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.schemas.matching import (
    KIND_MATCH_RESULTS,
    MATCH_RESULT_CONTRACT_VERSION,
    MatchComponentEntry,
    MatchResult,
    MatchResultCollection,
    MatchSkillPath,
    build_match_results_card,
)
from app.schemas.score_breakdown import COMPONENT_ORDER
from app.schemas.sse import (
    SUPPORTED_SSE_EVENT_TYPES,
    SSEEventOrderValidator,
    parse_sse_event,
)
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from app.services.shopaikey_chat import DecisionResult
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from tests.fakes.agent_tools import ScriptedDecision, decision_text, tool_call
from tests.graph.fakes import FakeDriver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-match-chat"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-match-chat"
SENTINEL_URI = "bolt://match-chat-test.invalid:7687"
RAW_CV_SENTINEL = "RAW_CV_BODY_NEVER_EMIT_IN_SSE_OR_HISTORY"
RAW_JD_SENTINEL = "RAW_JD_BODY_NEVER_EMIT_IN_SSE_OR_HISTORY"
SECRET_SENTINEL = "sk-match-chat-secret-never-emit"
STACK_SENTINEL = 'Traceback (most recent call last):\n  File "x.py"'


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


def _settings(tmp_path: Path) -> Any:
    return load_settings(
        environ={
            "APP_ENV": "local",
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "VITE_API_BASE_URL": "http://localhost:8000",
            "SQLITE_PATH": str(tmp_path / "match_chat.db"),
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


def _full_components() -> list[MatchComponentEntry]:
    defaults: dict[str, tuple[float, float]] = {
        "semantic_similarity": (0.9, 0.3),
        "skill_score": (0.8, 0.4),
        "seniority_score": (1.0, 0.1),
        "experience_score": (1.0, 0.1),
        "location_score": (1.0, 0.05),
        "work_mode_score": (1.0, 0.05),
    }
    return [
        MatchComponentEntry(
            name=name.value,
            available=True,
            value=defaults[name.value][0],
            effective_weight=defaults[name.value][1],
        )
        for name in COMPONENT_ORDER
    ]


def _match_result(
    *,
    job_id: UUID | None = None,
    score: float = 0.85,
    title: str = "Backend Engineer",
    source_url: str | None = "https://example.com/jobs/backend",
) -> MatchResult:
    return MatchResult(
        job_id=job_id or uuid4(),
        title=title,
        company="Acme Corp",
        location="Remote",
        work_mode="remote",
        final_score=score,
        quality="full",
        components=_full_components(),
        matched_required_skills=[
            MatchSkillPath(
                canonical_key="python",
                display_name="Python",
                match_kind="direct",
                strength=1.0,
            )
        ],
        related_skills=[
            MatchSkillPath(
                canonical_key="kubernetes",
                display_name="Kubernetes",
                match_kind="verified_related",
                strength=0.6,
                related_path=["python", "kubernetes"],
            )
        ],
        missing_required_skills=[
            MatchSkillPath(
                canonical_key="java",
                display_name="Java",
                match_kind="no_match",
                strength=0.0,
            )
        ],
        explanation_lines=["Semantic similarity: 0.9 (effective weight 0.3)"],
        source_url=source_url,
        seed_config_version="hybrid_seed_v1",
        contract_version=MATCH_RESULT_CONTRACT_VERSION,
    )


def _success_tool_body(collection: MatchResultCollection, *, limit: int = 10) -> str:
    results = [item.model_dump(mode="json") for item in collection.results]
    payload = {
        "ok": True,
        "status": "matched",
        "count": len(results),
        "limit": limit,
        "contract_version": collection.contract_version,
        "seed_config_version": collection.seed_config_version,
        "results": results,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class _MatchJobsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(default=None, ge=1, le=10)


class _FixedMatchTool:
    def __init__(self, body: str) -> None:
        self.body = body
        self.calls = 0

    def as_tool(self) -> StructuredTool:
        owner = self

        async def _match(limit: int | None = None) -> str:
            owner.calls += 1
            return owner.body

        return StructuredTool.from_function(
            coroutine=_match,
            name="match_jobs",
            description="Match approved profile to jobs (test fixed body).",
            args_schema=_MatchJobsArgs,
        )


def _build_app(
    tmp_path: Path,
    *,
    tool_body: str,
    final_text: str = "Here are your top matches.",
) -> tuple[Any, DatabaseSessionManager, _FixedMatchTool]:
    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    _upgrade_head(db_path)
    db = create_session_manager(db_path)
    fixed = _FixedMatchTool(tool_body)
    tool = fixed.as_tool()
    decision = ScriptedDecision(
        [
            DecisionResult(
                content="",
                tool_calls=(
                    tool_call(
                        "match_jobs",
                        arguments={},
                        tool_call_id="c-match-1",
                    ),
                ),
                response_model="fake-model",
            ),
            decision_text(final_text),
        ]
    )
    chat = ChatService(
        db,
        sqlite_path=db_path,
        decision=decision,
        tools=[tool],
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
    return application, db, fixed


def _assert_no_leaks(blob: str) -> None:
    lowered = blob.lower()
    for token in (
        SENTINEL_API_KEY,
        SENTINEL_NEO4J_PASSWORD,
        RAW_CV_SENTINEL,
        RAW_JD_SENTINEL,
        SECRET_SENTINEL,
        "traceback (most recent",
        "authorization: bearer",
        "api_key=",
        "raw_content",
        "document_text",
        "shopaikey",
    ):
        assert token.lower() not in lowered
    assert '"arguments"' not in blob
    assert RAW_CV_SENTINEL not in blob
    assert RAW_JD_SENTINEL not in blob
    assert STACK_SENTINEL.split("\n", 1)[0] not in blob


def test_match_results_live_and_history_equivalence(tmp_path: Path) -> None:
    job_id = uuid4()
    collection = MatchResultCollection(
        results=[_match_result(job_id=job_id)],
        seed_config_version="hybrid_seed_v1",
    )
    expected_card = build_match_results_card(collection).model_dump(mode="json")
    application, _db, fixed = _build_app(
        tmp_path,
        tool_body=_success_tool_body(collection),
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "Match me to jobs",
                "idempotency_key": "match-chat-live-1",
            },
        )
        hist = client.get("/api/chat/history")

    assert response.status_code == 200
    assert fixed.calls == 1
    payloads = _parse_sse_payloads(response.text)
    typed = [parse_sse_event(p) for p in payloads]
    ordered = SSEEventOrderValidator().validate_sequence(typed)
    kinds = [str(e.event) for e in ordered]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_completed"
    assert kinds.count("run_completed") == 1
    assert "tool_started" in kinds
    assert "tool_completed" in kinds
    assert set(kinds) <= SUPPORTED_SSE_EVENT_TYPES
    assert len(SUPPORTED_SSE_EVENT_TYPES) == 8

    completed = next(p for p in payloads if p["event"] == "run_completed")
    match_payload = completed["payload"].get("match_results")
    assert isinstance(match_payload, dict)
    assert match_payload["kind"] == KIND_MATCH_RESULTS
    assert match_payload["count"] == 1
    assert match_payload["results"][0]["job_id"] == str(job_id)
    assert match_payload["results"][0]["title"] == "Backend Engineer"
    assert match_payload["results"][0]["final_score"] == 0.85
    assert "saved_job" not in completed["payload"] or completed["payload"][
        "saved_job"
    ] is None

    tool_completed = next(p for p in payloads if p["event"] == "tool_completed")
    assert tool_completed["payload"]["label"] == "Match jobs"
    assert tool_completed["payload"]["status"] == "complete"
    assert tool_completed["payload"]["outcome"] == "Matches found"

    assert hist.status_code == 200
    messages = hist.json()["messages"]
    assistant = [m for m in messages if m["role"] == "assistant"]
    assert assistant
    history_payload = assistant[-1]["structured_payload"]
    assert history_payload is not None
    assert history_payload["kind"] == KIND_MATCH_RESULTS
    assert history_payload["results"][0]["job_id"] == str(job_id)
    assert history_payload["count"] == match_payload["count"]
    assert history_payload["results"][0]["title"] == match_payload["results"][0]["title"]
    assert history_payload["results"][0]["final_score"] == match_payload["results"][0][
        "final_score"
    ]
    # Live and durable cards share the same safe contract fields.
    for key in (
        "kind",
        "contract_version",
        "seed_config_version",
        "count",
    ):
        assert history_payload[key] == match_payload[key] == expected_card[key]

    _assert_no_leaks(response.text)
    _assert_no_leaks(json.dumps(hist.json()))


def test_match_jobs_failure_never_emits_card(tmp_path: Path) -> None:
    # Application tool ERROR: convention fails the run (no success card path).
    application, _db, fixed = _build_app(
        tmp_path,
        tool_body='ERROR:{"code":"MATCH_JOBS_RETRIEVAL_FAILED","ok":false}',
        final_text="I could not match jobs right now.",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "Match me",
                "idempotency_key": "match-chat-fail-1",
            },
        )
        hist = client.get("/api/chat/history")

    assert response.status_code == 200
    assert fixed.calls == 1
    payloads = _parse_sse_payloads(response.text)
    events = {p["event"] for p in payloads}
    assert "run_failed" in events
    assert "run_completed" not in events
    for payload in payloads:
        blob = json.dumps(payload)
        assert "match_results" not in blob or '"match_results":null' in blob.replace(
            " ", ""
        )
        assert KIND_MATCH_RESULTS not in blob

    tool_events = [p for p in payloads if p["event"] == "tool_completed"]
    assert tool_events
    assert tool_events[0]["payload"]["status"] == "error"

    assistant = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    for row in assistant:
        assert row.get("structured_payload") in (None, {})
    _assert_no_leaks(response.text)
    _assert_no_leaks(json.dumps(hist.json()))
    assert RAW_JD_SENTINEL not in response.text
    assert SECRET_SENTINEL not in response.text


def test_profile_required_guidance_no_card(tmp_path: Path) -> None:
    body = json.dumps(
        {
            "ok": True,
            "status": "profile_required",
            "code": "PROFILE_REQUIRED",
            "guidance": "Upload a CV and approve a Candidate Profile before matching jobs.",
            "count": 0,
            "limit": 10,
            "results": [],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    application, _db, _ = _build_app(
        tmp_path,
        tool_body=body,
        final_text="Please upload and approve a profile first.",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "match jobs",
                "idempotency_key": "match-chat-profile-1",
            },
        )
        hist = client.get("/api/chat/history")

    payloads = _parse_sse_payloads(response.text)
    completed = next(p for p in payloads if p["event"] == "run_completed")
    assert completed["payload"].get("match_results") in (None, {})
    tool_completed = next(p for p in payloads if p["event"] == "tool_completed")
    assert tool_completed["payload"]["outcome"] == "Profile required"
    assistant = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    assert assistant[-1].get("structured_payload") in (None, {})


def test_malformed_match_payload_fails_closed_keeps_message(tmp_path: Path) -> None:
    # ok matched but results missing required component inventory → no card.
    body = json.dumps(
        {
            "ok": True,
            "status": "matched",
            "count": 1,
            "limit": 10,
            "contract_version": MATCH_RESULT_CONTRACT_VERSION,
            "seed_config_version": "hybrid_seed_v1",
            "results": [
                {
                    "job_id": str(uuid4()),
                    "final_score": 0.5,
                    "quality": "full",
                    "components": [],
                    "seed_config_version": "hybrid_seed_v1",
                    "contract_version": MATCH_RESULT_CONTRACT_VERSION,
                }
            ],
        }
    )
    application, _db, _ = _build_app(
        tmp_path,
        tool_body=body,
        final_text="Matched with incomplete tool body.",
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "match",
                "idempotency_key": "match-chat-malformed-1",
            },
        )
        hist = client.get("/api/chat/history")

    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    completed = next(p for p in payloads if p["event"] == "run_completed")
    assert completed["payload"].get("match_results") in (None, {})
    text_deltas = [p for p in payloads if p["event"] == "text_delta"]
    assert text_deltas
    assistant = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    assert assistant[-1]["content"]
    assert assistant[-1].get("structured_payload") in (None, {})


def test_duplicate_turn_idempotent_match_card(tmp_path: Path) -> None:
    job_id = uuid4()
    collection = MatchResultCollection(
        results=[_match_result(job_id=job_id)],
        seed_config_version="hybrid_seed_v1",
    )
    application, _db, fixed = _build_app(
        tmp_path,
        tool_body=_success_tool_body(collection),
    )
    body = {
        "text": "Match me again",
        "idempotency_key": "match-chat-idem-1",
    }
    with TestClient(application) as client:
        r1 = client.post("/api/chat/turns", json=body)
        r2 = client.post("/api/chat/turns", json=body)
        hist = client.get("/api/chat/history")

    assert r1.status_code == 200
    assert r2.status_code == 200
    # Tool executes once; second request replays durable outcome.
    assert fixed.calls == 1
    c1 = next(p for p in _parse_sse_payloads(r1.text) if p["event"] == "run_completed")
    c2 = next(p for p in _parse_sse_payloads(r2.text) if p["event"] == "run_completed")
    assert c1["payload"].get("match_results", {}).get("results", [{}])[0].get(
        "job_id"
    ) == str(job_id)
    assert c2["payload"].get("match_results", {}).get("results", [{}])[0].get(
        "job_id"
    ) == str(job_id)
    assistants = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 1
    assert assistants[0]["structured_payload"]["results"][0]["job_id"] == str(job_id)


def test_exactly_eight_sse_event_names_with_match_card(tmp_path: Path) -> None:
    collection = MatchResultCollection(
        results=[_match_result()],
        seed_config_version="hybrid_seed_v1",
    )
    application, _db, _ = _build_app(
        tmp_path,
        tool_body=_success_tool_body(collection),
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "match",
                "idempotency_key": "match-chat-eight-1",
            },
        )
        openapi = client.app.openapi()  # type: ignore[attr-defined]
    names = {p["event"] for p in _parse_sse_payloads(response.text)}
    assert names <= SUPPORTED_SSE_EVENT_TYPES
    assert len(SUPPORTED_SSE_EVENT_TYPES) == 8
    paths = set(openapi["paths"])
    assert len(paths) == 7 or "/api/health" in paths
    assert "/api/chat/turns" in paths
    assert not any("match" in p for p in paths)
