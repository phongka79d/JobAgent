"""Integration: saved-job SSE card, history hydration, sanitized JD tool activity."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.schemas.job_tools import (
    KIND_SAVED_JOB,
    DuplicateOutcome,
    JobDisplaySummary,
    ProcessingResult,
    SaveJobResult,
)
from app.schemas.sse import SSEEventOrderValidator, parse_sse_event
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from app.services.shopaikey_chat import DecisionResult
from app.tools.save_job import SaveJobToolService, create_save_job_tool
from fastapi.testclient import TestClient
from tests.fakes.agent_tools import ScriptedDecision, decision_text, tool_call
from tests.graph.fakes import FakeDriver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-job-chat"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-job-chat"
SENTINEL_URI = "bolt://job-chat-test.invalid:7687"
RAW_JD_SENTINEL = "RAW_JD_BODY_NEVER_EMIT_IN_SSE_OR_HISTORY"
SECRET_SENTINEL = "sk-job-chat-secret-never-emit"
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
            "SQLITE_PATH": str(tmp_path / "job_chat.db"),
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


class _FixedIngestion:
    def __init__(self, result: SaveJobResult) -> None:
        self.result = result
        self.calls = 0

    async def save_job(
        self,
        *,
        url: str | None = None,
        raw_text: str | None = None,
        force_new_authorized: bool = False,
    ) -> SaveJobResult:
        self.calls += 1
        return self.result


def _save_result(
    *,
    processing_result: ProcessingResult = ProcessingResult.PROCESSED,
    duplicate_outcome: DuplicateOutcome = DuplicateOutcome.NONE,
    jd_quality: str | None = "full",
    graph_sync_status: str = "pending",
    title: str = "Backend Engineer",
    company: str = "Acme Corp",
    source_url: str | None = "https://example.com/jobs/backend",
    quality_reasons: list[str] | None = None,
    job_id: UUID | None = None,
) -> SaveJobResult:
    return SaveJobResult(
        job_id=job_id or uuid4(),
        source_type="url" if source_url else "text",
        source_url=source_url,
        processing_result=processing_result,
        processing_status=(
            "processed"
            if processing_result != ProcessingResult.FAILED
            else "failed"
        ),
        jd_quality=jd_quality,
        quality_reasons=quality_reasons,
        record_status=(
            "active"
            if duplicate_outcome != DuplicateOutcome.IGNORED_NORMALIZED
            else "ignored_duplicate"
        ),
        duplicate_outcome=duplicate_outcome,
        duplicate_of_job_id=None,
        graph_sync_status=graph_sync_status,
        error_code=None,
        display=JobDisplaySummary(
            title=title,
            company=company,
            location="Remote",
            work_mode="remote",
            employment_type="full_time",
            source_url=source_url,
        ),
    )


def _build_app(
    tmp_path: Path,
    *,
    result: SaveJobResult,
    tool_args: dict[str, Any] | None = None,
) -> tuple[Any, DatabaseSessionManager, _FixedIngestion]:
    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    _upgrade_head(db_path)
    db = create_session_manager(db_path)
    ingestion = _FixedIngestion(result)
    tool = create_save_job_tool(SaveJobToolService(ingestion))
    args = tool_args or {"url": "https://example.com/jobs/backend"}
    decision = ScriptedDecision(
        [
            DecisionResult(
                content="",
                tool_calls=(
                    tool_call(
                        "save_job",
                        arguments=args,
                        tool_call_id="c-save-1",
                    ),
                ),
                response_model="fake-model",
            ),
            decision_text("Saved the job for you."),
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
    return application, db, ingestion


def _assert_no_leaks(blob: str) -> None:
    lowered = blob.lower()
    for token in (
        SENTINEL_API_KEY,
        SENTINEL_NEO4J_PASSWORD,
        RAW_JD_SENTINEL,
        SECRET_SENTINEL,
        "traceback (most recent",
        "authorization: bearer",
        "api_key=",
        "raw_content",
        "document_text",
    ):
        assert token.lower() not in lowered
    assert '"arguments"' not in blob
    assert RAW_JD_SENTINEL not in blob
    assert SECRET_SENTINEL not in blob
    assert STACK_SENTINEL.split("\n", 1)[0] not in blob


def test_processed_save_job_card_live_and_history(tmp_path: Path) -> None:
    job_id = uuid4()
    result = _save_result(job_id=job_id, graph_sync_status="pending")
    application, db, ingestion = _build_app(tmp_path, result=result)

    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "Please save https://example.com/jobs/backend",
                "idempotency_key": "job-chat-processed-1",
            },
        )
        hist = client.get("/api/chat/history")

    assert response.status_code == 200
    assert ingestion.calls == 1
    payloads = _parse_sse_payloads(response.text)
    typed = [parse_sse_event(p) for p in payloads]
    ordered = SSEEventOrderValidator().validate_sequence(typed)
    kinds = [str(e.event) for e in ordered]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_completed"
    assert kinds.count("run_completed") == 1
    assert "tool_started" in kinds
    assert "tool_completed" in kinds
    assert set(kinds) <= {
        "run_started",
        "assistant_status",
        "tool_started",
        "tool_completed",
        "approval_required",
        "text_delta",
        "run_completed",
        "run_failed",
    }
    assert len({k for k in kinds}) <= 8

    completed = next(p for p in payloads if p["event"] == "run_completed")
    saved = completed["payload"].get("saved_job")
    assert isinstance(saved, dict)
    assert saved["kind"] == KIND_SAVED_JOB
    assert saved["job_id"] == str(job_id)
    assert saved["title"] == "Backend Engineer"
    assert saved["company"] == "Acme Corp"
    assert saved["location"] == "Remote"
    assert saved["work_mode"] == "remote"
    assert saved["employment_type"] == "full_time"
    assert saved["jd_quality"] == "full"
    assert saved["processing_result"] == "processed"
    assert saved["duplicate_outcome"] == "none"
    assert saved["graph_sync_status"] == "pending"
    assert saved["source_url"] == "https://example.com/jobs/backend"
    assert "raw_content" not in saved
    assert "quality_reasons" not in saved or "quality_reasons_preview" in saved

    tool_completed = next(p for p in payloads if p["event"] == "tool_completed")
    assert tool_completed["payload"]["label"] == "Save job"
    assert tool_completed["payload"]["status"] == "complete"
    assert tool_completed["payload"]["outcome"] in {
        "Job saved",
        "Job saved graph pending",
    }

    assert hist.status_code == 200
    messages = hist.json()["messages"]
    assistant = [m for m in messages if m["role"] == "assistant"]
    assert assistant
    payload = assistant[-1]["structured_payload"]
    assert payload is not None
    assert payload["kind"] == KIND_SAVED_JOB
    assert payload["job_id"] == str(job_id)
    assert payload["title"] == saved["title"]
    assert payload["company"] == saved["company"]

    _assert_no_leaks(response.text)
    _assert_no_leaks(json.dumps(hist.json()))


@pytest.mark.parametrize(
    ("processing_result", "duplicate", "quality", "graph", "expected_outcome_part"),
    [
        (
            ProcessingResult.EXACT_DUPLICATE,
            DuplicateOutcome.EXACT,
            "full",
            "not_required",
            "Exact duplicate",
        ),
        (
            ProcessingResult.PROCESSED,
            DuplicateOutcome.IGNORED_NORMALIZED,
            "partial",
            "not_required",
            "Duplicate ignored",
        ),
        (
            ProcessingResult.PROCESSED,
            DuplicateOutcome.NONE,
            "unscorable",
            "not_required",
            "Unscorable",
        ),
        (
            ProcessingResult.FAILED,
            DuplicateOutcome.NONE,
            None,
            "not_required",
            "Save failed",
        ),
        (
            ProcessingResult.PROCESSED,
            DuplicateOutcome.NONE,
            "full",
            "failed",
            "graph",
        ),
    ],
)
def test_save_job_outcome_states_sanitized(
    tmp_path: Path,
    processing_result: ProcessingResult,
    duplicate: DuplicateOutcome,
    quality: str | None,
    graph: str,
    expected_outcome_part: str,
) -> None:
    result = _save_result(
        processing_result=processing_result,
        duplicate_outcome=duplicate,
        jd_quality=quality,
        graph_sync_status=graph,
        quality_reasons=["missing responsibilities"] if quality == "unscorable" else None,
    )
    application, _db, _ = _build_app(tmp_path, result=result)
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "save this job https://example.com/jobs/backend",
                "idempotency_key": f"job-chat-state-{processing_result}-{duplicate}-{quality}-{graph}",
            },
        )
    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    tool_completed = next(p for p in payloads if p["event"] == "tool_completed")
    outcome = tool_completed["payload"].get("outcome") or ""
    assert expected_outcome_part.lower() in outcome.lower()
    completed = next(p for p in payloads if p["event"] == "run_completed")
    saved = completed["payload"].get("saved_job")
    assert isinstance(saved, dict)
    assert saved["kind"] == KIND_SAVED_JOB
    _assert_no_leaks(response.text)


def test_duplicate_turn_idempotency_no_second_card_mutation(tmp_path: Path) -> None:
    job_id = uuid4()
    result = _save_result(job_id=job_id)
    application, _db, ingestion = _build_app(tmp_path, result=result)
    body = {
        "text": "save https://example.com/jobs/backend",
        "idempotency_key": "job-chat-idem-1",
    }
    with TestClient(application) as client:
        first = client.post("/api/chat/turns", json=body)
        second = client.post("/api/chat/turns", json=body)
        hist = client.get("/api/chat/history")
    assert first.status_code == 200
    assert second.status_code == 200
    # Replay must not re-invoke ingestion.
    assert ingestion.calls == 1
    p1 = _parse_sse_payloads(first.text)
    p2 = _parse_sse_payloads(second.text)
    c1 = next(p for p in p1 if p["event"] == "run_completed")
    c2 = next(p for p in p2 if p["event"] == "run_completed")
    assert c1["payload"].get("saved_job", {}).get("job_id") == str(job_id)
    assert c2["payload"].get("saved_job", {}).get("job_id") == str(job_id)
    assistant = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    assert len(assistant) == 1


def test_malformed_save_job_body_fails_closed_to_text(
    tmp_path: Path,
) -> None:
    """Non-SaveJobResult tool JSON must not produce a card or leak body."""
    from langchain_core.tools import StructuredTool

    def _bad(**_kwargs: Any) -> str:
        return json.dumps(
            {
                "ok": True,
                "raw_content": RAW_JD_SENTINEL,
                "secret": SECRET_SENTINEL,
                "stack_trace": STACK_SENTINEL,
            }
        )

    bad_tool = StructuredTool.from_function(
        func=_bad,
        name="save_job",
        description="synthetic bad save_job",
    )
    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    _upgrade_head(db_path)
    db = create_session_manager(db_path)
    decision = ScriptedDecision(
        [
            DecisionResult(
                content="",
                tool_calls=(
                    tool_call(
                        "save_job",
                        arguments={"url": "https://example.com/x"},
                        tool_call_id="c-bad",
                    ),
                ),
                response_model="fake-model",
            ),
            decision_text("Could not structure the job."),
        ]
    )
    chat = ChatService(
        db,
        sqlite_path=db_path,
        decision=decision,
        tools=[bad_tool],
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
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "save a job",
                "idempotency_key": "job-chat-malformed-1",
            },
        )
        hist = client.get("/api/chat/history")
    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    completed = next(p for p in payloads if p["event"] == "run_completed")
    assert completed["payload"].get("saved_job") in (None, {})
    assert "saved_job" not in completed["payload"] or completed["payload"]["saved_job"] is None
    assistant = [m for m in hist.json()["messages"] if m["role"] == "assistant"]
    assert assistant
    assert assistant[-1].get("structured_payload") in (None, {})
    _assert_no_leaks(response.text)
    _assert_no_leaks(json.dumps(hist.json()))


def test_unsafe_source_url_dropped_from_card(tmp_path: Path) -> None:
    result = _save_result(source_url="http://localhost:8080/secret-jd")
    # display source_url also private
    result = result.model_copy(
        update={
            "display": JobDisplaySummary(
                title="Local Job",
                company="Internal",
                source_url="http://127.0.0.1/admin",
            )
        }
    )
    application, _db, _ = _build_app(
        tmp_path,
        result=result,
        tool_args={"raw_text": "Pastable JD text without url"},
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "Save this pasted JD",
                "idempotency_key": "job-chat-unsafe-url-1",
            },
        )
    payloads = _parse_sse_payloads(response.text)
    completed = next(p for p in payloads if p["event"] == "run_completed")
    saved = completed["payload"].get("saved_job")
    assert isinstance(saved, dict)
    assert saved.get("source_url") is None
    assert "127.0.0.1" not in response.text
    assert "localhost:8080" not in response.text


def test_exactly_eight_sse_event_names_still(tmp_path: Path) -> None:
    from app.schemas.sse import SUPPORTED_SSE_EVENT_TYPES

    assert len(SUPPORTED_SSE_EVENT_TYPES) == 8
    result = _save_result()
    application, _db, _ = _build_app(tmp_path, result=result)
    with TestClient(application) as client:
        response = client.post(
            "/api/chat/turns",
            json={
                "text": "save https://example.com/jobs/backend",
                "idempotency_key": "job-chat-eight-1",
            },
        )
        openapi = client.app.openapi()  # type: ignore[attr-defined]
    payloads = _parse_sse_payloads(response.text)
    names = {p["event"] for p in payloads}
    assert names <= SUPPORTED_SSE_EVENT_TYPES
    paths = set(openapi["paths"])
    assert not any("job" in p for p in paths)
    assert "/api/chat/turns" in paths
