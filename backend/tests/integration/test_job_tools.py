"""Integration tests for compact save_job / query_jobs tools (Plan 5 / 03B).

Migrated temporary SQLite + injected fakes only. Covers exactly-one input,
authorization-state independence, compact created/returned/retried and
failed/sync-failed results, query filters/default/order/ties, raw-data
exclusion, same-call replay, and exact six production tool names/order.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

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


class FakeJdInvoker:
    def __init__(self, script: list[Any] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedJobPost | dict[str, Any]:
        self.calls.append(
            {"is_repair": is_repair, "message_count": len(list(messages))}
        )
        if not self.script:
            raise RuntimeError("fake invoker script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


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
) -> ToolResult:
    args: dict[str, Any] = {}
    if url is not None:
        args["url"] = url
    if text is not None:
        args["text"] = text
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


def test_production_registry_exactly_six_tools_order() -> None:
    names = production_registry().tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
    ]
    assert "synthetic_interrupt" not in names


def test_no_job_route_and_single_registry_owner() -> None:
    app_root = BACKEND_ROOT / "app"
    for path in app_root.rglob("*.py"):
        text_src = path.read_text(encoding="utf-8")
        assert "/api/jobs" not in text_src
    reg_src = (app_root / "tools" / "registry.py").read_text(encoding="utf-8")
    assert "build_production_job_tools" in reg_src
    assert "build_production_profile_tools" in reg_src
    assert "build_production_match_tools" in reg_src
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
            tool_fn = build_save_job_tool(
                session_factory=factory,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
            )
            jd = "Unique JD body for return/retry path. Python required."
            first = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_new", text=jd
            )
            assert first.ok is True
            assert first.data is not None
            assert first.data["outcome"] == "created"
            job_id = first.data["job_id"]

            second = await _ainvoke_save(
                tool_fn, run_id=run_id, tool_call_id="call_dup", text=jd
            )
            assert second.ok is True
            assert second.data is not None
            assert second.data["outcome"] == "returned"
            assert second.data["job_id"] == job_id
            # Duplicate return: no second extract/embed.
            assert len(invoker.calls) == 1
            assert len(embedder.calls) == 1

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
            assert len(invoker.calls) == 2
            assert len(embedder.calls) == 2
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
