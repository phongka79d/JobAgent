"""Integration tests for compact save_job / query_jobs tools (Plan 5 / 03B).

Migrated temporary SQLite + injected fakes only. Covers exactly-one input,
authorization-state independence, compact created/returned/retried and
failed/sync-failed results, query filters/default/order/ties, raw-data
exclusion, same-call replay, and exact seven production tool names/order.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args
from unittest.mock import AsyncMock

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
)
from app.db.models.jobs import (
    JOB_COMPACT_QUERY_LIMIT_MAX,
    JOB_COMPACT_QUERY_LIMIT_MIN,
    JOB_JD_QUALITIES,
    JOB_JD_QUALITY_FULL,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_PROCESSING_STATUSES,
    JobPost,
)
from app.db.models.profiles import JOB_PREFERENCE_KEYS
from app.db.session import build_async_engine
from app.graph.sync_shared import NEO4J_SYNC_FAILED
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as profile_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS
from app.schemas.jobs import (
    JOB_INGEST_OUTCOMES,
    QUERY_JOBS_DEFAULT_LIMIT,
    QUERY_JOBS_LIMIT_MAX,
    QUERY_JOBS_LIMIT_MIN,
    JobIngestOutcome,
    JobJdQuality,
    JobProcessingStatus,
)
from app.schemas.sse import ToolStatusEvent, parse_sse_event, sse_event_to_dict
from app.schemas.tools import ToolResult
from app.services.chat_history import get_history_page, history_page_as_dict
from app.services.jd_extraction import ExtractedJobPost
from app.services.jd_ingestion import IngestOutcome
from app.services.skill_normalization import SkillNormalizer
from app.services.url_fetch import UrlFetchResult
from app.tools.jobs import (
    ERROR_INVALID_JOB_INPUT,
    QUERY_JOBS_NAME,
    SAVE_JOB_NAME,
    build_query_jobs_tool,
    build_save_job_tool,
)
from app.tools.registry import production_registry
from sqlalchemy import func, select, text

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.structured_output import FakeJdInvoker
from tests.support.db_migration import run_async, session_factory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"
BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _vector(seed: float = 0.01) -> list[float]:
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


def _full_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python"],
            }
        ],
        "preferred_skills": [],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


class RecordingSync:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.calls += 1
        if self.fail:
            from app.graph.sync_job import JobSyncError

            raise JobSyncError("simulated sync failure")


def _factory(db_path: Path):
    engine = build_async_engine(db_path)
    return engine, session_factory(engine)


async def _seed_run(session: Any, content: str = "job tool turn") -> str:
    user = await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content=content,
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    await session.flush()
    return run.id


async def _ainvoke_tool(
    tool_fn: Any,
    *,
    run_id: str,
    tool_call_id: str,
    args: dict[str, Any],
) -> ToolResult:
    """Invoke with a full ToolCall so InjectedToolCallId/InjectedState work.

    LangChain requires ToolCall shape when InjectedToolCallId is present.
    ``state`` is the same InjectedState channel the ToolNode supplies in graph.
    """
    invoke_args = {**args, "state": {"run_id": run_id}}
    raw = await tool_fn.ainvoke(
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": tool_fn.name,
            "args": invoke_args,
        }
    )
    if isinstance(raw, str):
        payload = json.loads(raw)
    elif hasattr(raw, "content"):
        content = raw.content
        payload = json.loads(content) if isinstance(content, str) else content
    else:
        payload = raw
    return ToolResult.model_validate(payload)


async def _ainvoke_save(
    tool_fn: Any,
    *,
    run_id: str,
    tool_call_id: str,
    url: str | None = None,
    text: str | None = None,
    source: str | None = None,
    preview: dict[str, Any] | None = None,
) -> ToolResult:
    args: dict[str, Any] = {}
    if url is not None:
        args["url"] = url
    if text is not None:
        args["text"] = text
    if source is not None:
        args["source"] = source
    if preview is not None:
        args["preview"] = preview
    return await _ainvoke_tool(
        tool_fn, run_id=run_id, tool_call_id=tool_call_id, args=args
    )


async def _ainvoke_query(
    tool_fn: Any,
    *,
    run_id: str,
    tool_call_id: str,
    job_id: str | None = None,
    processing_status: str | None = None,
    jd_quality: str | None = None,
    limit: int | None = None,
) -> ToolResult:
    args: dict[str, Any] = {}
    if job_id is not None:
        args["job_id"] = job_id
    if processing_status is not None:
        args["processing_status"] = processing_status
    if jd_quality is not None:
        args["jd_quality"] = jd_quality
    if limit is not None:
        args["limit"] = limit
    return await _ainvoke_tool(
        tool_fn, run_id=run_id, tool_call_id=tool_call_id, args=args
    )


def _assert_no_raw_or_embedding(payload: Any) -> None:
    blob = json.dumps(payload, default=str)
    assert "raw_content" not in blob
    assert "raw_content_hash" not in blob
    assert "embedding_json" not in blob
    assert "embedding_model" not in blob
    assert "embedding_dimensions" not in blob
    assert "extraction_json" not in blob
    # Realistic JD body fragments used in fixtures must not leak as free text.
    # Title/company may appear; full responsibility body in extraction must not.
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            assert "raw_content" not in data
            assert "raw_content_hash" not in data
            assert "embedding_json" not in data
            assert "extraction_json" not in data


_MINIMAL_PROFILE: dict[str, Any] = {
    "full_name": "Auth Matrix User",
    "headline": None,
    "summary": None,
    "location": None,
    "email": None,
    "phone": None,
    "links": [],
    "skills": [],
    "experience": [],
    "education": [],
    "languages": [],
    "extraction_confidence": 0.5,
    "source_attachment_id": None,
}


async def _seed_auth_state(
    session: Any,
    *,
    with_active: bool,
    with_draft: bool,
) -> None:
    """Seed Master authorization matrix preconditions (profile/draft presence)."""
    if with_active:
        active_id = new_uuid()
        await att_repo.create_staged(
            session,
            file_hash=f"hash-active-{active_id[:8]}",
            original_name="active.pdf",
            size_bytes=20,
            storage_path=f"active/{active_id}.pdf",
            page_count=1,
            attachment_id=active_id,
        )
        await att_repo.mark_active(session, active_id, page_count=1)
        await profile_repo.upsert_active_profile(
            session,
            active_attachment_id=active_id,
            profile_json=_MINIMAL_PROFILE,
        )
    if with_draft:
        draft_att = new_uuid()
        await att_repo.create_staged(
            session,
            file_hash=f"hash-draft-{draft_att[:8]}",
            original_name="draft.pdf",
            size_bytes=20,
            storage_path=f"draft/{draft_att}.pdf",
            page_count=1,
            attachment_id=draft_att,
        )
        await profile_repo.upsert_current_draft(
            session,
            source_attachment_id=draft_att,
            draft_json={
                "profile": _MINIMAL_PROFILE,
                "preferences": {k: [] for k in JOB_PREFERENCE_KEYS},
                "corrections": [],
                "exclusions": [],
            },
        )


# ---------------------------------------------------------------------------
# Ownership regression: one authoritative contract per vocabulary
# ---------------------------------------------------------------------------


def test_job_tool_contract_ownership_no_parallel_vocabularies() -> None:
    """Status/quality/outcome/limit contracts have one owner each (common.py style)."""
    assert frozenset(get_args(JobProcessingStatus)) == JOB_PROCESSING_STATUSES
    assert frozenset(get_args(JobJdQuality)) == JOB_JD_QUALITIES
    assert frozenset(get_args(JobIngestOutcome)) == JOB_INGEST_OUTCOMES
    assert IngestOutcome is JobIngestOutcome
    assert QUERY_JOBS_LIMIT_MIN == JOB_COMPACT_QUERY_LIMIT_MIN == 1
    assert QUERY_JOBS_LIMIT_MAX == JOB_COMPACT_QUERY_LIMIT_MAX == 50
    assert QUERY_JOBS_LIMIT_MIN <= QUERY_JOBS_DEFAULT_LIMIT <= QUERY_JOBS_LIMIT_MAX

    schemas_src = (
        Path(__file__).resolve().parents[2] / "app" / "schemas" / "jobs.py"
    ).read_text(encoding="utf-8")
    # Schema must assert Literals against ORM owners, not invent private sets.
    assert "JOB_PROCESSING_STATUSES" in schemas_src
    assert "JOB_JD_QUALITIES" in schemas_src
    assert "JOB_COMPACT_QUERY_LIMIT_MIN" in schemas_src
    assert "JOB_COMPACT_QUERY_LIMIT_MAX" in schemas_src
    assert "assert frozenset(get_args(JobProcessingStatus))" in schemas_src
    assert "assert frozenset(get_args(JobJdQuality))" in schemas_src

    repo_src = (
        Path(__file__).resolve().parents[2] / "app" / "repositories" / "jobs.py"
    ).read_text(encoding="utf-8")
    # Private parallel limit constants must be gone; ORM bounds are the owner.
    assert "JOB_COMPACT_QUERY_LIMIT_MIN" in repo_src
    assert "JOB_COMPACT_QUERY_LIMIT_MAX" in repo_src
    assert not re.search(r"(?m)^_LIMIT_MIN\b|^_LIMIT_MAX\b|= 1, 50\b", repo_src)

    ingest_src = (
        Path(__file__).resolve().parents[2] / "app" / "services" / "jd_ingestion.py"
    ).read_text(encoding="utf-8")
    # No independent Literal[\"created\", ...] redefinition of outcome.
    tree = ast.parse(ingest_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "IngestOutcome":
                    # Alias assignment only (IngestOutcome = JobIngestOutcome).
                    assert isinstance(node.value, ast.Name)
                    assert node.value.id == "JobIngestOutcome"


# ---------------------------------------------------------------------------
# Production registry names / order
# ---------------------------------------------------------------------------


def test_production_registry_exactly_seven_tools_order() -> None:
    names = production_registry().tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
    assert "synthetic_interrupt" not in names


def test_no_job_route_and_single_registry_owner() -> None:
    """Agent tools stay transport-free; registry owns the seven tool builders."""
    app_root = BACKEND_ROOT / "app"
    # Tools / agent / tool-execution must not hardcode public job HTTP paths.
    for rel in ("tools", "agent"):
        for path in (app_root / rel).rglob("*.py"):
            text_src = path.read_text(encoding="utf-8")
            assert "/api/jobs" not in text_src, f"unexpected /api/jobs in {path}"
            assert "APIRouter" not in text_src or path.name == "__init__.py"
    reg_src = (app_root / "tools" / "registry.py").read_text(encoding="utf-8")
    assert "build_production_job_tools" in reg_src
    assert "build_production_profile_tools" in reg_src
    assert "build_production_match_tools" in reg_src
    assert "build_production_active_cv_tools" in reg_src
    jobs_src = inspect.getsource(
        __import__("app.tools.jobs", fromlist=["jobs"])
    )
    assert "execute_tool" in jobs_src
    assert "APIRouter" not in jobs_src
    assert "include_router" not in jobs_src
    # Job module stays free of match_jobs registration (matching owns it).
    assert "match_jobs" not in jobs_src
    matching_src = inspect.getsource(
        __import__("app.tools.matching", fromlist=["matching"])
    )
    assert "execute_tool" in matching_src
    assert "APIRouter" not in matching_src
    assert "include_router" not in matching_src


# ---------------------------------------------------------------------------
# save_job: input validation, outcomes, auth independence, replay, sync fail
# ---------------------------------------------------------------------------


def test_save_job_rejects_both_and_neither_input(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            neither = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_neither"
            )
            assert neither.ok is False
            assert neither.code == ERROR_INVALID_JOB_INPUT

            both = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_both",
                url="https://example.com/jd",
                text="pasted body",
            )
            assert both.ok is False
            assert both.code == ERROR_INVALID_JOB_INPUT

            async with factory() as session:
                count = await session.execute(
                    select(func.count()).select_from(JobPost)
                )
                assert int(count.scalar_one()) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_created_compact_and_no_raw(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            jd = (
                "Backend Engineer at Acme. Design REST services. "
                "Required: 3+ years Python."
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_create",
                text=jd,
            )
            assert result.ok is True
            assert result.code is None
            assert result.data is not None
            assert result.data["outcome"] == "created"
            assert result.data["job_id"]
            assert result.data["title"] == "Backend Engineer"
            assert result.data["company"] == "Acme"
            assert result.data["processing_status"] == JOB_PROCESSING_STATUS_PROCESSED
            assert result.data["jd_quality"] == JOB_JD_QUALITY_FULL
            assert result.data["sqlite_committed"] is True
            assert result.data["sync_ok"] is True
            assert result.data["source_url"] is None
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1
            assert sync.calls == 1
            _assert_no_raw_or_embedding(result.model_dump(mode="json"))
            assert jd not in json.dumps(result.model_dump(mode="json"))
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_returned_and_retried_outcomes(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            invoker = FakeJdInvoker([_full_extracted(), _full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            jd = "Unique JD body for return/retry path. Python required."
            first = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_new", text=jd
            )
            assert first.ok is True
            assert first.data is not None
            assert first.data["outcome"] == "created"
            job_id = first.data["job_id"]
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1
            assert sync.calls == 1

            second = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_dup", text=jd
            )
            assert second.ok is True
            assert second.data is not None
            assert second.data["outcome"] == "returned"
            assert second.data["job_id"] == job_id
            # F-04 / Plan 11: exact-duplicate ToolResult must expose returned
            # vocabulary that agent projection can narrate (never "created").
            assert "Returned existing job" in second.summary
            assert "created" not in second.summary.lower()
            assert second.data["outcome"] != "created"
            # Duplicate return: no second extract/embed/graph; still one Job.
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1
            assert sync.calls == 1
            async with factory() as session:
                count = await session.execute(
                    select(func.count()).select_from(JobPost)
                )
                assert int(count.scalar_one()) == 1

            # Force failed row then retry same content (clear scorable embedding).
            async with factory() as session:
                await session.execute(
                    text(
                        "UPDATE job_posts SET processing_status = 'failed', "
                        "failure_code = 'PRIOR_FAIL', extraction_json = NULL, "
                        "jd_quality = NULL, embedding_json = NULL, "
                        "embedding_model = NULL, embedding_dimensions = NULL "
                        "WHERE id = :id"
                    ),
                    {"id": job_id},
                )
                await session.commit()

            retried = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_retry", text=jd
            )
            assert retried.ok is True
            assert retried.data is not None
            assert retried.data["outcome"] == "retried"
            assert retried.data["job_id"] == job_id
            # Retry reprocesses same row: one more extract/embed/graph each.
            assert len(invoker.calls) == 2
            assert len(embedder.calls) == 2
            assert sync.calls == 2
            async with factory() as session:
                count = await session.execute(
                    select(func.count()).select_from(JobPost)
                )
                assert int(count.scalar_one()) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_sync_failed_sqlite_committed_truth(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            sync = RecordingSync(fail=True)
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                job_sync_fn=sync,
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_sync_fail",
                text="JD that processes then fails graph sync. Python.",
            )
            assert result.ok is False
            assert result.code == NEO4J_SYNC_FAILED
            assert result.data is not None
            assert result.data["sqlite_committed"] is True
            assert result.data["sync_ok"] is False
            assert result.data["processing_status"] == JOB_PROCESSING_STATUS_PROCESSED
            assert result.data["jd_quality"] == JOB_JD_QUALITY_FULL
            assert result.data["rebuild_instruction"]
            _assert_no_raw_or_embedding(result.model_dump(mode="json"))

            async with factory() as session:
                row = await jobs_repo.get_by_id(session, result.data["job_id"])
                assert row is not None
                assert row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                assert row.failure_code is None
        finally:
            await engine.dispose()

    run_async(_body())


@pytest.mark.parametrize(
    ("with_active", "with_draft", "label"),
    [
        (False, False, "no_profile_no_draft"),
        (False, True, "draft_only"),
        (True, False, "active_profile_only"),
        (True, True, "active_profile_plus_draft"),
    ],
)
def test_save_job_allowed_in_all_master_authorization_states(
    db_path: Path,
    with_active: bool,
    with_draft: bool,
    label: str,
) -> None:
    """Master §13.7: save_job works in every profile/draft authorization state."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, content=f"auth {label}")
                await _seed_auth_state(
                    session, with_active=with_active, with_draft=with_draft
                )
                if with_active:
                    assert await profile_repo.get_active_profile(session) is not None
                else:
                    assert await profile_repo.get_active_profile(session) is None
                if with_draft:
                    assert await profile_repo.get_current_draft(session) is not None
                else:
                    assert await profile_repo.get_current_draft(session) is None
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id=f"call_auth_{label}",
                text=(
                    f"Auth-state JD for {label}. "
                    "Backend Engineer. Required: 3+ years Python."
                ),
            )
            assert result.ok is True, f"{label}: {result.code} {result.summary}"
            assert result.data is not None
            assert result.data["outcome"] == "created"
            assert result.data["processing_status"] == JOB_PROCESSING_STATUS_PROCESSED
            # query_jobs also available in every state (read-only; no auth gate).
            q = build_query_jobs_tool(session_factory=factory)
            listed = await _ainvoke_query(
                q,
                run_id=run_id,
                tool_call_id=f"q_auth_{label}",
                limit=5,
            )
            assert listed.ok is True
            assert listed.data is not None
            assert listed.data["count"] >= 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_url_path_and_fetch_failure(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            async def ok_fetcher(url: str) -> UrlFetchResult:
                return UrlFetchResult(
                    text=(
                        "Fetched JD title Backend. Design REST services. "
                        "Required: Python."
                    ),
                    failure_code=None,
                )

            tool_ok = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                url_fetcher=ok_fetcher,
            )
            ok = await _ainvoke_save(
                tool_ok,
                run_id=run_id,
                tool_call_id="call_url_ok",
                url="https://example.com/jobs/1",
            )
            assert ok.ok is True
            assert ok.data is not None
            assert ok.data["source_url"] == "https://example.com/jobs/1"
            assert ok.data["outcome"] == "created"

            async def fail_fetcher(url: str) -> UrlFetchResult:
                return UrlFetchResult(
                    text=None,
                    failure_code="URL_FETCH_UNAVAILABLE",
                )

            tool_fail = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                url_fetcher=fail_fetcher,
            )
            failed = await _ainvoke_save(
                tool_fail,
                run_id=run_id,
                tool_call_id="call_url_fail",
                url="https://example.com/jobs/missing",
            )
            assert failed.ok is False
            assert failed.code == "URL_FETCH_UNAVAILABLE"
            assert failed.data is not None
            assert failed.data["sqlite_committed"] is True
            assert failed.data["processing_status"] == JOB_PROCESSING_STATUS_FAILED
            assert "paste" in (failed.summary or "").lower() or failed.data.get(
                "paste_instruction"
            )
            _assert_no_raw_or_embedding(failed.model_dump(mode="json"))
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_same_identity_replay_no_second_side_effect(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            first = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_replay_once",
                text="Replay identity JD. Python engineer role.",
            )
            second = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_replay_once",
                text="Replay identity JD. Python engineer role.",
            )
            assert first.model_dump(mode="json") == second.model_dump(mode="json")
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1
            assert sync.calls == 1

            async with factory() as session:
                rows = await tool_repo.list_for_run_ids(session, [run_id])
                matching = [
                    r for r in rows if r.tool_call_id == "call_replay_once"
                ]
                assert len(matching) == 1
                assert matching[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                assert matching[0].tool_name == SAVE_JOB_NAME
                args = matching[0].arguments_summary_json or {}
                assert args.get("source") == "text"
                assert "text" not in args or args.get("text") is None
                assert "raw" not in json.dumps(args)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# query_jobs: filters, default limit, order, ties, raw exclusion
# ---------------------------------------------------------------------------


def test_query_jobs_default_limit_filters_order_and_ties(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                # Insert 12 processed jobs with controlled timestamps/ids.
                fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
                ids: list[str] = []
                for i in range(12):
                    row = await jobs_repo.create_text_job(
                        session,
                        raw_content=f"job body {i}",
                        raw_content_hash=f"hash-{i:02d}",
                    )
                    await jobs_repo.mark_processing(session, row.id)
                    quality = (
                        JOB_JD_QUALITY_FULL if i % 2 == 0 else "partial"
                    )
                    await jobs_repo.mark_processed(
                        session,
                        row.id,
                        extraction_json={
                            "title": f"Title {i}",
                            "company": f"Co {i}",
                            "summary": "s",
                            "responsibilities": [],
                            "required_skills": [],
                            "preferred_skills": [],
                            "seniority": "mid",
                            "min_experience_years": None,
                            "max_experience_years": None,
                            "location": None,
                            "work_mode": "remote",
                            "extraction_confidence": 0.5,
                        },
                        jd_quality=quality,
                        embedding_json=_vector(float(i) * 0.01),
                        embedding_model="text-embedding-3-small",
                        embedding_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
                    )
                    ids.append(row.id)
                # Force identical created_at on last two for id DESC tie-break.
                await session.execute(
                    text(
                        "UPDATE job_posts SET created_at = :ts, updated_at = :ts"
                    ),
                    {"ts": fixed.isoformat()},
                )
                await session.commit()

            tool_fn = build_query_jobs_tool(session_factory=factory)

            defaulted = await _ainvoke_query(
                tool_fn, run_id=run_id, tool_call_id="q_default"
            )
            assert defaulted.ok is True
            assert defaulted.data is not None
            assert defaulted.data["limit"] == QUERY_JOBS_DEFAULT_LIMIT
            assert defaulted.data["count"] == QUERY_JOBS_DEFAULT_LIMIT
            assert len(defaulted.data["jobs"]) == 10

            # Explicit order: created_at DESC, id DESC (repository owner).
            ordered = await _ainvoke_query(
                tool_fn,
                run_id=run_id,
                tool_call_id="q_order",
                limit=50,
            )
            assert ordered.data is not None
            jobs = ordered.data["jobs"]
            assert len(jobs) == 12
            # After forcing same created_at for all, order is pure id DESC.
            job_ids = [j["job_id"] for j in jobs]
            assert job_ids == sorted(job_ids, reverse=True)

            filtered = await _ainvoke_query(
                tool_fn,
                run_id=run_id,
                tool_call_id="q_filter",
                jd_quality=JOB_JD_QUALITY_FULL,
                limit=50,
            )
            assert filtered.data is not None
            assert all(
                j["jd_quality"] == JOB_JD_QUALITY_FULL
                for j in filtered.data["jobs"]
            )

            # processing_status filter (required 03B coverage).
            status_filtered = await _ainvoke_query(
                tool_fn,
                run_id=run_id,
                tool_call_id="q_status_filter",
                processing_status=JOB_PROCESSING_STATUS_PROCESSED,
                limit=50,
            )
            assert status_filtered.ok is True
            assert status_filtered.data is not None
            assert status_filtered.data["count"] == 12
            assert all(
                j["processing_status"] == JOB_PROCESSING_STATUS_PROCESSED
                for j in status_filtered.data["jobs"]
            )
            none_status = await _ainvoke_query(
                tool_fn,
                run_id=run_id,
                tool_call_id="q_status_failed",
                processing_status=JOB_PROCESSING_STATUS_FAILED,
                limit=50,
            )
            assert none_status.ok is True
            assert none_status.data is not None
            assert none_status.data["count"] == 0

            by_id = await _ainvoke_query(
                tool_fn,
                run_id=run_id,
                tool_call_id="q_id",
                job_id=ids[0],
            )
            assert by_id.data is not None
            assert by_id.data["count"] == 1
            assert by_id.data["jobs"][0]["job_id"] == ids[0]

            # Raw / embedding exclusion on every result surface.
            _assert_no_raw_or_embedding(ordered.model_dump(mode="json"))
            for j in jobs:
                assert "raw_content" not in j
                assert "embedding_json" not in j
                assert set(j.keys()) >= {
                    "job_id",
                    "title",
                    "company",
                    "source_url",
                    "processing_status",
                    "jd_quality",
                }
        finally:
            await engine.dispose()

    run_async(_body())


def test_query_jobs_rejects_bad_limit(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            tool_fn = build_query_jobs_tool(session_factory=factory)
            for bad in (0, 51, -1):
                result = await _ainvoke_query(
                    tool_fn,
                    run_id=run_id,
                    tool_call_id=f"q_bad_{bad}",
                    limit=bad,
                )
                assert result.ok is False
                assert result.code == "INVALID_QUERY"
        finally:
            await engine.dispose()

    run_async(_body())


def test_query_jobs_replay_stable(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                row = await jobs_repo.create_text_job(
                    session,
                    raw_content="query replay body",
                    raw_content_hash="query-replay-hash",
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_processed(
                    session,
                    row.id,
                    extraction_json={
                        "title": "T",
                        "company": "C",
                        "summary": "s",
                        "responsibilities": [],
                        "required_skills": [],
                        "preferred_skills": [],
                        "seniority": "mid",
                        "min_experience_years": None,
                        "max_experience_years": None,
                        "location": None,
                        "work_mode": "remote",
                        "extraction_confidence": 0.5,
                    },
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_vector(),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
                )
                await session.commit()

            tool_fn = build_query_jobs_tool(session_factory=factory)
            first = await _ainvoke_query(
                tool_fn, run_id=run_id, tool_call_id="q_replay"
            )
            second = await _ainvoke_query(
                tool_fn, run_id=run_id, tool_call_id="q_replay"
            )
            assert first.model_dump(mode="json") == second.model_dump(mode="json")
            async with factory() as session:
                rows = await tool_repo.list_for_run_ids(session, [run_id])
                matching = [r for r in rows if r.tool_call_id == "q_replay"]
                assert len(matching) == 1
                assert matching[0].tool_name == QUERY_JOBS_NAME
                assert matching[0].status == TOOL_EXECUTION_STATUS_COMPLETED
        finally:
            await engine.dispose()

    run_async(_body())


def test_sync_failed_tool_execution_status_failed(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                job_sync_fn=RecordingSync(fail=True),
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_sync_status",
                text="Sync fail status coupling JD. Python.",
            )
            assert result.ok is False
            assert result.code == NEO4J_SYNC_FAILED
            async with factory() as session:
                row = await tool_repo.get_by_identity(
                    session,
                    run_id=run_id,
                    tool_call_id="call_sync_status",
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_FAILED
                assert row.error_code == NEO4J_SYNC_FAILED
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_history_and_current_sse_exclude_raw_and_embeddings(
    db_path: Path,
) -> None:
    """Durable history hydration and current SSE projection exclude raw Job data.

    Does not implement 03C tool_status emission; only projects the existing
    ``tool_status`` schema from durable execution fields (status/summary only).
    """

    unique_raw = (
        "UNIQUE_RAW_JD_BODY_PRIVACY_MARKER_03B xyzzy-private-content. "
        "Design REST services with embedded secrets. Required: Python."
    )

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, content="save a job please")
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_privacy_hist",
                text=unique_raw,
            )
            assert result.ok is True
            assert result.data is not None
            job_id = result.data["job_id"]

            # ORM still holds raw/hash/extraction/embedding (not tool surfaces).
            async with factory() as session:
                row = await jobs_repo.get_by_id(session, job_id)
                assert row is not None
                assert row.raw_content == unique_raw
                assert row.raw_content_hash is not None
                assert row.extraction_json is not None
                assert row.embedding_json is not None
                tool_row = await tool_repo.get_by_identity(
                    session,
                    run_id=run_id,
                    tool_call_id="call_privacy_hist",
                )
                assert tool_row is not None
                assert tool_row.status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tool_row.result_json is not None
                await runs_repo.complete_run(session, run_id)
                await session.commit()
                tool_execution_id = tool_row.id
                tool_summary = result.summary or "Saved job description"
                args_summary = tool_row.arguments_summary_json

            # 1) Durable history hydration surface.
            async with factory() as session:
                page = await get_history_page(session, limit=50, before=None)
                hist = history_page_as_dict(page)
            hist_blob = json.dumps(hist, default=str)
            assert "raw_content" not in hist_blob
            assert "raw_content_hash" not in hist_blob
            assert "extraction_json" not in hist_blob
            assert "embedding_json" not in hist_blob
            assert "embedding_model" not in hist_blob
            assert "embedding_dimensions" not in hist_blob
            assert unique_raw not in hist_blob
            assert "xyzzy-private-content" not in hist_blob
            # Compact ToolResult data may be present without raw body.
            user_items = [
                i for i in page.items if i.role == CHAT_MESSAGE_ROLE_USER
            ]
            assert user_items
            run_view = user_items[0].run
            assert run_view is not None
            assert len(run_view.tool_executions) == 1
            te = run_view.tool_executions[0]
            assert te.tool_name == SAVE_JOB_NAME
            assert te.result is not None
            assert te.result.data is not None
            assert te.result.data.get("job_id") == job_id
            assert "raw_content" not in te.result.data
            assert "embedding_json" not in te.result.data
            assert te.arguments_summary is not None
            assert te.arguments_summary.get("source") == "text"
            assert "text" not in te.arguments_summary
            assert unique_raw not in json.dumps(te.arguments_summary)

            # 2) Current SSE tool_status projection (schema only; no 03C emission).
            # Existing contract carries status/summary — never raw JD or ToolResult.
            sse_event = parse_sse_event(
                {
                    "event": "tool_status",
                    "event_id": new_uuid(),
                    "run_id": run_id,
                    "timestamp": utc_now(),
                    "payload": {
                        "tool_execution_id": tool_execution_id,
                        "tool_call_id": "call_privacy_hist",
                        "tool_name": SAVE_JOB_NAME,
                        "status": "completed",
                        "duration_ms": 12,
                        "summary": tool_summary,
                    },
                }
            )
            assert isinstance(sse_event, ToolStatusEvent)
            sse_blob = json.dumps(sse_event_to_dict(sse_event), default=str)
            assert "raw_content" not in sse_blob
            assert "raw_content_hash" not in sse_blob
            assert "extraction_json" not in sse_blob
            assert "embedding_json" not in sse_blob
            assert unique_raw not in sse_blob
            assert "xyzzy-private-content" not in sse_blob
            assert "result" not in sse_event.payload.model_dump(mode="json")
            assert "data" not in sse_event.payload.model_dump(mode="json")
            # Arguments summary stored durably stays compact (no body).
            assert args_summary is not None
            assert unique_raw not in json.dumps(args_summary)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Plan 12 (01B): current-message interrupt, save, cancel, replay, opt-out
# ---------------------------------------------------------------------------


_OBVIOUS_JD_MESSAGE = (
    "Job Description\n"
    "Backend Engineer at Acme\n"
    "Responsibilities\n"
    "- Design REST services\n"
    "- Own deployments\n"
    "Requirements\n"
    "- 3+ years Python experience required for this role\n"
    "- Strong communication skills\n"
    "About the role: build APIs for local demo customers with care."
)

_FORBIDDEN_PENDING_KEYS = frozenset(
    {
        "raw",
        "raw_jd",
        "raw_content",
        "message_id",
        "user_message_id",
        "url",
        "source_url",
        "hash",
        "content_hash",
        "raw_content_hash",
        "arguments",
        "prompt",
        "provider",
        "credential",
        "api_key",
        "password",
        "storage",
        "storage_path",
        "stack",
        "traceback",
        "content",
        "text",
    }
)


def _assert_pending_redacted(projection: dict[str, Any], *, body: str) -> None:
    blob = json.dumps(projection, default=str)
    assert body not in blob
    lower_keys = {k.casefold() for k in _walk_keys(projection)}
    for forbidden in _FORBIDDEN_PENDING_KEYS:
        assert forbidden not in lower_keys, f"forbidden key {forbidden!r} in pending"
    assert "xyzzy" not in blob


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


async def _count_jobs(session: Any) -> int:
    result = await session.execute(select(func.count()).select_from(JobPost))
    return int(result.scalar_one())


async def _count_evaluations(session: Any) -> int:
    from app.db.models.job_evaluations import JobEvaluation

    result = await session.execute(select(func.count()).select_from(JobEvaluation))
    return int(result.scalar_one())


def _install_cm_side_effect_spies(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[tuple[str, str | None]], AsyncMock, AsyncMock]:
    """Record durable source reads and wrap ingest/evaluation seams."""
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


def test_save_job_current_message_interrupts_before_dependencies(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One running execution, one pre-interrupt lookup, zero pre-action side effects."""
    from app.agent.graph import build_agent_graph
    from app.db.models.chat import (
        AGENT_RUN_STATE_INTERRUPTED,
        TOOL_EXECUTION_STATUS_RUNNING,
    )
    from app.services.chat_turns import stream_chat_turn
    from app.services.job_save_confirmation import (
        JOB_SAVE_CONFIRMATION_ACTIONS,
        JOB_SAVE_CONFIRMATION_KIND,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel

    source_reads, ingest_spy, evaluation_spy = _install_cm_side_effect_spies(
        monkeypatch
    )

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {
                                    "source": "current_message",
                                    "preview": {
                                        "title": "Backend Engineer",
                                        "company": "Acme",
                                        "skills": ["Python"],
                                    },
                                },
                                "id": "call-cm-interrupt",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting for your decision."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool_fn]),
            )
            events = [
                e
                async for e in stream_chat_turn(
                    message=_OBVIOUS_JD_MESSAGE,
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            names = [e.event for e in events]
            assert names[0] == "run_started"
            assert names[-1] == "approval_required"
            assert "run_completed" not in names

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
            assert all(s.payload.tool_name == SAVE_JOB_NAME for s in interrupt_statuses)

            approval = events[-1]
            payload = approval.payload
            assert payload.kind == JOB_SAVE_CONFIRMATION_KIND
            assert list(payload.allowed_actions) == list(
                JOB_SAVE_CONFIRMATION_ACTIONS
            )
            assert payload.card["tool_name"] == SAVE_JOB_NAME
            assert payload.card["tool_call_id"] == "call-cm-interrupt"
            assert payload.card["source"] == "current_message"
            assert payload.card["text_length"] == len(_OBVIOUS_JD_MESSAGE)
            run_id = approval.run_id
            approval_blob = json.dumps(payload.model_dump(mode="json"), default=str)
            assert _OBVIOUS_JD_MESSAGE not in approval_blob
            for forbidden in (
                "message_id",
                "user_message_id",
                "raw_content",
                "prompt",
                "provider",
            ):
                assert forbidden not in approval_blob

            # Exactly one pre-interrupt durable lookup; zero domain side effects.
            assert source_reads == [(run_id, _OBVIOUS_JD_MESSAGE)]
            assert ingest_spy.await_count == 0
            assert evaluation_spy.await_count == 0

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                proj = run.pending_approval_json
                assert proj is not None
                assert proj["kind"] == JOB_SAVE_CONFIRMATION_KIND
                assert proj["allowed_actions"] == list(JOB_SAVE_CONFIRMATION_ACTIONS)
                card = proj["card"]
                assert card["tool_name"] == SAVE_JOB_NAME
                assert card["tool_call_id"] == "call-cm-interrupt"
                assert card["source"] == "current_message"
                assert card["text_length"] == len(_OBVIOUS_JD_MESSAGE)
                assert card["preview"]["title"] == "Backend Engineer"
                assert card["preview"]["company"] == "Acme"
                assert card["preview"]["skills"] == ["Python"]
                _assert_pending_redacted(proj, body=_OBVIOUS_JD_MESSAGE)

                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_RUNNING
                assert tools[0].result_json is None
                assert tools[0].id == durable_exec_id
                args = tools[0].arguments_summary_json or {}
                assert args == {"source": "current_message"}
                assert await _count_jobs(session) == 0
                assert await _count_evaluations(session) == 0

            # Zero pre-action provider/ingestion/graph calls.
            assert len(invoker.calls) == 0
            assert len(embedder.calls) == 0
            assert sync.calls == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_current_message_save_reloads_exact_source_once(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Save: two reads total, one ingest of fresh content, zero evaluation."""
    from app.agent.graph import build_agent_graph
    from app.db.models.chat import (
        AGENT_RUN_STATE_COMPLETED,
        TOOL_EXECUTION_STATUS_COMPLETED,
    )
    from app.services.chat_turns import stream_chat_turn, stream_resume
    from app.services.tool_execution import get_replay_result
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel

    source_reads, ingest_spy, evaluation_spy = _install_cm_side_effect_spies(
        monkeypatch
    )

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            invoker = FakeJdInvoker([_full_extracted(), _full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {"source": "current_message"},
                                "id": "call-cm-save",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool_fn]),
            )
            events = [
                e
                async for e in stream_chat_turn(
                    message=_OBVIOUS_JD_MESSAGE,
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert events[-1].event == "approval_required"
            run_id = events[-1].run_id
            assert len(invoker.calls) == 0
            assert source_reads == [(run_id, _OBVIOUS_JD_MESSAGE)]
            assert ingest_spy.await_count == 0
            assert evaluation_spy.await_count == 0

            tool2 = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            model2 = FakeChatModel(
                responses=[AIMessage(content="Saved the JD.")]
            )
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )
            resume_events = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="save_job",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert "run_completed" in [e.event for e in resume_events]
            # One pre-interrupt + one re-entry read; never a third reload.
            assert source_reads == [
                (run_id, _OBVIOUS_JD_MESSAGE),
                (run_id, _OBVIOUS_JD_MESSAGE),
            ]
            assert ingest_spy.await_count == 1
            assert ingest_spy.await_args.args[0] == _OBVIOUS_JD_MESSAGE
            assert evaluation_spy.await_count == 0
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1
            assert sync.calls == 1

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                assert run.pending_approval_json is None
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tools[0].tool_call_id == "call-cm-save"
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data["outcome"] == "created"
                assert stored.data["sqlite_committed"] is True
                job_id = stored.data["job_id"]
                row = await jobs_repo.get_by_id(session, job_id)
                assert row is not None
                assert row.raw_content == _OBVIOUS_JD_MESSAGE
                assert await _count_jobs(session) == 1
                assert await _count_evaluations(session) == 0

            # Terminal replay: exact stored result, no extra lookup or side effect.
            replay = await get_replay_result(
                run_id=run_id,
                tool_call_id="call-cm-save",
                session_factory=factory,
            )
            assert replay is not None
            assert replay.model_dump(mode="json") == stored.model_dump(mode="json")
            assert len(source_reads) == 2
            assert ingest_spy.await_count == 1
            assert evaluation_spy.await_count == 0
            assert len(invoker.calls) == 1
            assert sync.calls == 1

            # Terminal no-op resume.
            boom = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {"source": "current_message"},
                                "id": "should-not-run",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            )
            noop = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="save_job",
                    graph_bundle=build_agent_graph(
                        model=boom,
                        registry=ToolRegistry([tool2]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert [e.event for e in noop] == ["run_started", "run_completed"]
            assert boom.invoke_count == 0
            assert len(source_reads) == 2
            assert ingest_spy.await_count == 1
            assert len(invoker.calls) == 1
            assert sync.calls == 1

            # Exact-hash return on a second current-message paste of same body.
            dup_reads_start = len(source_reads)
            invoker2 = FakeJdInvoker([_full_extracted()])
            embedder2 = FakeEmbeddingClient()
            sync2 = RecordingSync()
            tool_dup = build_save_job_tool(
                session_factory=factory,
                invoker=invoker2,
                normalizer=_normalizer(),
                embedding_client=embedder2,
                job_sync_fn=sync2,
            )
            model_dup = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {"source": "current_message"},
                                "id": "call-cm-dup",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting again."),
                ]
            )
            events_dup = [
                e
                async for e in stream_chat_turn(
                    message=_OBVIOUS_JD_MESSAGE,
                    graph_bundle=build_agent_graph(
                        model=model_dup,
                        registry=ToolRegistry([tool_dup]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert events_dup[-1].event == "approval_required"
            run_dup = events_dup[-1].run_id
            assert source_reads[dup_reads_start:] == [
                (run_dup, _OBVIOUS_JD_MESSAGE)
            ]
            tool_dup2 = build_save_job_tool(
                session_factory=factory,
                invoker=invoker2,
                normalizer=_normalizer(),
                embedding_client=embedder2,
                job_sync_fn=sync2,
            )
            resume_dup = [
                e
                async for e in stream_resume(
                    run_id=run_dup,
                    action="save_job",
                    graph_bundle=build_agent_graph(
                        model=FakeChatModel(
                            responses=[AIMessage(content="Returned existing.")]
                        ),
                        registry=ToolRegistry([tool_dup2]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert "run_completed" in [e.event for e in resume_dup]
            # Dedupe run: own one pre-interrupt + one re-entry read; no extract.
            assert source_reads[dup_reads_start:] == [
                (run_dup, _OBVIOUS_JD_MESSAGE),
                (run_dup, _OBVIOUS_JD_MESSAGE),
            ]
            assert ingest_spy.await_count == 2  # create + returned hash path
            assert len(invoker2.calls) == 0
            assert len(embedder2.calls) == 0
            assert sync2.calls == 0
            assert evaluation_spy.await_count == 0
            async with factory() as session:
                tools_dup = await tool_repo.list_for_run_ids(session, [run_dup])
                assert len(tools_dup) == 1
                stored_dup = tool_repo.load_stored_result(tools_dup[0])
                assert stored_dup.data is not None
                assert stored_dup.data["outcome"] == "returned"
                assert stored_dup.data["job_id"] == job_id
                assert await _count_jobs(session) == 1
                assert await _count_evaluations(session) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_current_message_cancel_zero_dependencies(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel: two reads total, zero domain side effects, durable cancelled result."""
    from app.agent.graph import build_agent_graph
    from app.db.models.chat import (
        AGENT_RUN_STATE_COMPLETED,
        TOOL_EXECUTION_STATUS_COMPLETED,
    )
    from app.services.chat_turns import stream_chat_turn, stream_resume
    from app.services.job_save_confirmation import CANCEL_SUMMARY
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel

    source_reads, ingest_spy, evaluation_spy = _install_cm_side_effect_spies(
        monkeypatch
    )

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {"source": "current_message"},
                                "id": "call-cm-cancel",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting."),
                ]
            )
            events = [
                e
                async for e in stream_chat_turn(
                    message=_OBVIOUS_JD_MESSAGE,
                    graph_bundle=build_agent_graph(
                        model=model,
                        registry=ToolRegistry([tool_fn]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert events[-1].event == "approval_required"
            run_id = events[-1].run_id
            assert source_reads == [(run_id, _OBVIOUS_JD_MESSAGE)]

            tool2 = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            resume_events = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="cancel_save_job",
                    graph_bundle=build_agent_graph(
                        model=FakeChatModel(
                            responses=[AIMessage(content="Understood, not saved.")]
                        ),
                        registry=ToolRegistry([tool2]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert "run_completed" in [e.event for e in resume_events]
            # Cancel re-entry records one fresh lookup (two reads total).
            assert source_reads == [
                (run_id, _OBVIOUS_JD_MESSAGE),
                (run_id, _OBVIOUS_JD_MESSAGE),
            ]
            assert ingest_spy.await_count == 0
            assert evaluation_spy.await_count == 0
            assert len(invoker.calls) == 0
            assert len(embedder.calls) == 0
            assert sync.calls == 0

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.code is None
                assert stored.summary == CANCEL_SUMMARY
                assert stored.data == {
                    "committed": False,
                    "outcome": "cancelled",
                }
                assert await _count_jobs(session) == 0
                assert await _count_evaluations(session) == 0
        finally:
            await engine.dispose()

    run_async(_body())


@pytest.mark.parametrize(
    ("mode", "tool_args", "message"),
    [
        (
            "current_message",
            {"source": "current_message"},
            f"{_OBVIOUS_JD_MESSAGE}\nPlease không lưu this.",
        ),
        (
            "text",
            {
                "text": (
                    "Backend Engineer at Acme. Design REST services. "
                    "Required: 3+ years Python."
                )
            },
            "Please save this JD but do not save after all.",
        ),
        (
            "url",
            {"url": "https://example.com/jobs/opt-out"},
            "Here is a link but don't save it.",
        ),
    ],
)
def test_save_job_opt_out_precondition_all_source_modes(
    db_path: Path,
    mode: str,
    tool_args: dict[str, Any],
    message: str,
) -> None:
    """Clear opt-out cancels without interrupt, card, dependency, or mutation."""
    from app.services.job_save_confirmation import CANCEL_SUMMARY

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, content=message)
                await session.commit()

            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()

            async def ok_fetcher(url: str) -> UrlFetchResult:
                return UrlFetchResult(
                    text="Fetched body. Required: Python.",
                    failure_code=None,
                )

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
                url_fetcher=ok_fetcher,
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id=f"call-opt-out-{mode}",
                **tool_args,
            )
            assert result.ok is True
            assert result.code is None
            assert result.summary == CANCEL_SUMMARY
            assert result.data == {"committed": False, "outcome": "cancelled"}
            assert len(invoker.calls) == 0
            assert len(embedder.calls) == 0
            assert sync.calls == 0
            async with factory() as session:
                assert await _count_jobs(session) == 0
                assert await _count_evaluations(session) == 0
                row = await tool_repo.get_by_identity(
                    session,
                    run_id=run_id,
                    tool_call_id=f"call-opt-out-{mode}",
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_current_message_only_allows_running_reentry(
    db_path: Path,
) -> None:
    """Direct URL/text reject concurrent running re-entry; CM enables it."""
    from app.services.tool_execution import ToolExecutionInProgressError

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, content="direct text turn")
                # Force a durable running identity for direct text path.
                pending, _created = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call-text-running",
                    tool_name=SAVE_JOB_NAME,
                    arguments_summary_json={
                        "source": "text",
                        "text_length": 10,
                    },
                )
                await tool_repo.mark_running(session, pending.id)
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            with pytest.raises(ToolExecutionInProgressError):
                await _ainvoke_save(
                    tool_fn,
                    run_id=run_id,
                    tool_call_id="call-text-running",
                    text="Backend Engineer. Required: Python.",
                )

            # Source inspection: only current-message enables re-entry flag.
            jobs_src = (
                Path(__file__).resolve().parents[2] / "app" / "tools" / "jobs.py"
            ).read_text(encoding="utf-8")
            assert "allow_running_reentry=allow_reentry" in jobs_src
            assert "_is_current_message_only" in jobs_src
            assert "interrupt(" in jobs_src
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_current_message_source_lookup_failure_no_side_effects(
    db_path: Path,
) -> None:
    """Invalid initiating message fails safely without Job/ingestion work."""
    from app.services.job_save_confirmation import ERROR_INVALID_CURRENT_MESSAGE

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                # Empty content allowed only with structured_payload on insert.
                user = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="",
                    structured_payload={"kind": "empty_fixture"},
                )
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                await session.commit()
                run_id = run.id

            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()
            sync = RecordingSync()
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                job_sync_fn=sync,
            )
            result = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call-cm-invalid",
                source="current_message",
            )
            assert result.ok is False
            assert result.code == ERROR_INVALID_CURRENT_MESSAGE
            assert len(invoker.calls) == 0
            assert len(embedder.calls) == 0
            assert sync.calls == 0
            async with factory() as session:
                assert await _count_jobs(session) == 0
                assert await _count_evaluations(session) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_save_job_arguments_summary_current_message_redacted(
    db_path: Path,
) -> None:
    """Current-message args summary is exactly {source: current_message}."""
    from app.agent.graph import build_agent_graph
    from app.services.chat_turns import stream_chat_turn
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": SAVE_JOB_NAME,
                                "args": {
                                    "source": "current_message",
                                    "preview": {
                                        "title": "Secret Title Guess",
                                        "company": "Secret Co",
                                        "skills": ["Go"],
                                    },
                                },
                                "id": "call-cm-args",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting."),
                ]
            )
            events = [
                e
                async for e in stream_chat_turn(
                    message=_OBVIOUS_JD_MESSAGE,
                    graph_bundle=build_agent_graph(
                        model=model,
                        registry=ToolRegistry([tool_fn]),
                    ),
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            run_id = events[-1].run_id
            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                args = tools[0].arguments_summary_json or {}
                assert args == {"source": "current_message"}
                assert "preview" not in args
                assert "title" not in args
                assert "Secret Title Guess" not in json.dumps(args)
        finally:
            await engine.dispose()

    run_async(_body())


def test_provider_save_job_dict_bound_toolnode_keeps_basetool() -> None:
    """Model sees ordinary provider dict; ToolNode keeps identical BaseTool."""
    from app.agent.graph import build_agent_graph
    from app.tools.jobs import save_job_openai_tool_schema
    from app.tools.registry import ToolRegistry
    from tests.fakes.fake_chat_model import FakeChatModel

    tool_fn = build_save_job_tool(
        invoker=FakeJdInvoker([_full_extracted()]),
        normalizer=_normalizer(),
        embedding_client=FakeEmbeddingClient(),
    )
    model = FakeChatModel(responses=[])
    registry = ToolRegistry([tool_fn])
    bundle = build_agent_graph(model=model, registry=registry)

    assert bundle.tool_node.tools_by_name[SAVE_JOB_NAME] is tool_fn
    assert model.bound_tools
    save_bound = next(
        item
        for item in model.bound_tools
        if isinstance(item, dict)
        and item.get("function", {}).get("name") == SAVE_JOB_NAME
    )
    assert save_bound == save_job_openai_tool_schema()
    params = save_bound["function"]["parameters"]
    assert params["type"] == "object"
    assert set(params["properties"]) == {"url", "text", "source", "preview"}
    assert "oneOf" not in params
    assert "tool_call_id" not in str(params)
    assert "state" not in str(params)


def test_save_job_runtime_mixed_source_invalid_via_tool(
    db_path: Path,
) -> None:
    """Runtime SaveJobInput still rejects mixed non-empty sources at the tool."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                await session.commit()

            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
            )
            mixed = await _ainvoke_save(
                tool_fn,
                run_id=run_id,
                tool_call_id="call_mixed_source",
                text="pasted body",
                source="current_message",
            )
            assert mixed.ok is False
            assert mixed.code == ERROR_INVALID_JOB_INPUT
        finally:
            await engine.dispose()

    run_async(_body())
