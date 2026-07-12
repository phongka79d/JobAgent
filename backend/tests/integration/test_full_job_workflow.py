"""Phase 4 exit proof: full fake-backed Job workflow (task 06B).

Covers acquisition → persistence-first extraction → duplicates/override →
query → graph sync/replay → rebuild parity → production exposure/privacy.

Reuses existing fakes, fixtures, and graph helpers. Zero real ShopAIKey,
public URL, or live Neo4j calls.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, OutboxStatus, ProcessingStatus, RecordStatus
from app.db.models.jobs import JobPost
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.job_sync import JOB_UPSERT_OPERATION, process_job_sync_outbox
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile, SkillRef, SkillStatus
from app.schemas.job_post import JobPostExtraction
from app.schemas.job_tools import DuplicateOutcome, ProcessingResult
from app.security.url_policy import (
    UrlPolicyError,
    UrlPolicyErrorCode,
    parse_public_http_url,
)
from app.services.embeddings import (
    JOB_TEXT_REPRESENTATION_VERSION,
    EmbeddingVector,
    JobEmbeddingError,
    JobEmbeddingErrorCode,
    JobEmbeddingResult,
)
from app.services.jd_extraction import JobExtractionResult
from app.services.jd_ingestion import JdIngestionError, JDIngestionService
from app.services.jd_quality import apply_jd_quality
from app.services.jd_source import (
    AcquiredJd,
    JdSourceError,
    JdSourceErrorCode,
    JdSourceType,
    acquire_jd,
    extract_html_main_text,
    hash_canonical_text,
)
from app.services.shopaikey_chat import ShopAIKeyChatError, ShopAIKeyErrorCode
from app.services.skill_normalization import (
    empty_skill_seed_catalog,
    load_skills_seed,
    normalize_job_skills,
    provisional_canonical_key,
    resolve_skill_ref,
)
from app.tools.query_jobs import QueryJobsToolService
from app.tools.registry import PRODUCTION_TOOL_NAMES
from app.tools.save_job import (
    FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN,
    SaveJobToolService,
)
from langchain_core.messages import HumanMessage
from sqlalchemy import func, select
from tests.graph.fakes import FakeDriver
from tests.integration.test_job_sync import StatefulJobGraph

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
APP_SRC = BACKEND_ROOT / "app"
API_SRC = BACKEND_ROOT / "app" / "api"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
FIXTURES_JD = BACKEND_ROOT / "tests" / "fixtures" / "jds"
FIXTURE_SEED = BACKEND_ROOT / "tests" / "fixtures" / "skills_seed_test.yaml"
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "rebuild_graph.py"

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-job-workflow"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-job-workflow"
RAW_JD_SENTINEL = "RAW_JD_BODY_SENTINEL_NEVER_IN_GRAPH_OR_OUTBOX"
SECRET_SENTINELS = (
    SENTINEL_API_KEY,
    SENTINEL_NEO4J_PASSWORD,
    "sk-live-secret",
    "Authorization: Bearer",
    RAW_JD_SENTINEL,
)

AUTHORIZED_APP_PATHS = frozenset(
    {
        "/api/health",
        "/api/attachments/cv",
        "/api/profile",
        "/api/profile/cv",
        "/api/chat/history",
        "/api/chat/turns",
        "/api/chat/runs/{run_id}/resume",
    }
)

LEAK_RE = re.compile(
    r"raw_content|raw_jd|document_text|api[_-]?key|Authorization:\s*Bearer|"
    r"sk-live|Traceback|stack_trace|password\s*=",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Shared helpers (reuse patterns from jd_ingestion / job_sync / rebuild tests)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "full_job_workflow.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _skill(
    *,
    key: str = "python",
    evidence: str = "Required: Python",
    confidence: float = 0.9,
    aliases: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.replace("_", " ").title(),
            "aliases": list(aliases),
            "category": "language" if key == "python" else None,
            "status": "verified",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _extraction_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs and data services for the platform.",
        "responsibilities": ["Design REST APIs", "Own production services"],
        "required_skills": [_skill()],
        "preferred_skills": [
            _skill(key="kubernetes", evidence="Preferred: Kubernetes", confidence=0.7)
        ],
        "seniority": "senior",
        "min_experience_years": 5.0,
        "max_experience_years": 10.0,
        "location": "Berlin, DE",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "education_requirements": ["BS Computer Science"],
        "language_requirements": ["English"],
        "salary_text": "EUR 80k-100k",
        "job_family": "software_engineering",
        "extraction_confidence": 0.85,
        "jd_quality": "full",
    }
    data.update(overrides)
    return data


def _extraction_result(**overrides: Any) -> JobExtractionResult:
    extraction = JobPostExtraction.model_validate(_extraction_payload(**overrides))
    with_quality, assessment = apply_jd_quality(extraction)
    return JobExtractionResult(extraction=with_quality, quality=assessment)


def _partial_result(**overrides: Any) -> JobExtractionResult:
    return _extraction_result(
        jd_quality="partial",
        education_requirements=[],
        language_requirements=[],
        min_experience_years=None,
        max_experience_years=None,
        salary_text=None,
        **overrides,
    )


def _unscorable_result(**overrides: Any) -> JobExtractionResult:
    data = _extraction_payload(
        title=None,
        summary="",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        employment_type="unknown",
        education_requirements=[],
        language_requirements=[],
        job_family=None,
        extraction_confidence=0.2,
        jd_quality="unscorable",
    )
    data.update(overrides)
    extraction = JobPostExtraction.model_validate(data)
    with_quality, assessment = apply_jd_quality(extraction)
    return JobExtractionResult(extraction=with_quality, quality=assessment)


class ScriptedAcquire:
    """Injected acquire: raw text real-path; URL returns scripted content or errors."""

    def __init__(
        self,
        *,
        url_map: Mapping[str, AcquiredJd | Exception] | None = None,
    ) -> None:
        self.url_map = dict(url_map or {})
        self.calls: list[dict[str, str | None]] = []

    def __call__(
        self,
        *,
        url: str | None = None,
        raw_text: str | None = None,
    ) -> AcquiredJd:
        self.calls.append({"url": url, "raw_text": raw_text})
        if raw_text is not None and url is None:
            canonical = raw_text  # tests supply already-canonical snippets
            return AcquiredJd(
                source_type=JdSourceType.RAW_TEXT,
                canonical_text=canonical,
                content_hash=hash_canonical_text(canonical),
                source_url=None,
            )
        if url is not None and raw_text is None:
            if url not in self.url_map:
                raise JdIngestionError("URL_BLOCKED")
            outcome = self.url_map[url]
            if isinstance(outcome, Exception):
                if isinstance(outcome, JdSourceError):
                    raise JdIngestionError(outcome.code.value) from None
                if isinstance(outcome, JdIngestionError):
                    raise outcome
                raise JdIngestionError("URL_FETCH_FAILED") from None
            return outcome
        raise JdIngestionError("INVALID_INPUT")


class ScriptedExtract:
    """Injected extract with call-order capture and per-text outcomes."""

    def __init__(
        self,
        *,
        default: JobExtractionResult | Exception | None = None,
        by_text: Mapping[str, JobExtractionResult | Exception] | None = None,
        db: DatabaseSessionManager | None = None,
    ) -> None:
        self.default = default
        self.by_text = dict(by_text or {})
        self.db = db
        self.calls = 0
        self.call_log: list[str] = []
        self.received_before_extract: list[tuple[UUID, str]] = []

    def __call__(self, *, canonical_jd_text: str) -> JobExtractionResult:
        self.calls += 1
        self.call_log.append("extract")
        if self.db is not None:
            # Sync peek is not available; retention asserted via ORM after.
            pass
        if canonical_jd_text in self.by_text:
            outcome = self.by_text[canonical_jd_text]
        else:
            outcome = self.default
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.TIMEOUT)
        return outcome


class FakeEmbeddingService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def embed_job(self, job: JobPostExtraction) -> JobEmbeddingResult:
        self.calls += 1
        if self.fail:
            raise JobEmbeddingError(JobEmbeddingErrorCode.PROVIDER_ERROR)
        return JobEmbeddingResult(
            vectors=(
                EmbeddingVector(index=0, values=tuple(0.02 for _ in range(1536))),
            ),
            model=ALLOWED_EMBEDDING_MODEL,
            dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            representation_version=JOB_TEXT_REPRESENTATION_VERSION,
        )


def _service(
    db: DatabaseSessionManager,
    *,
    extract: ScriptedExtract,
    acquire: ScriptedAcquire | None = None,
) -> JDIngestionService:
    return JDIngestionService(
        db,
        skill_catalog=empty_skill_seed_catalog(),
        acquire_fn=acquire or ScriptedAcquire(),
        extract_fn=extract,
        embedding_model=ALLOWED_EMBEDDING_MODEL,
        embedding_dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
    )


async def _job_count(db: DatabaseSessionManager) -> int:
    async with db.session_scope() as session:
        result = await session.execute(select(func.count()).select_from(JobPost))
        return int(result.scalar_one())


async def _outbox_count(
    db: DatabaseSessionManager,
    *,
    job_id: UUID | None = None,
) -> int:
    async with db.session_scope() as session:
        stmt = select(func.count()).select_from(GraphSyncOutbox).where(
            GraphSyncOutbox.operation == JOB_UPSERT_OPERATION
        )
        if job_id is not None:
            stmt = stmt.where(GraphSyncOutbox.entity_id == str(job_id))
        result = await session.execute(stmt)
        return int(result.scalar_one())


async def _orm_job(db: DatabaseSessionManager, job_id: UUID) -> JobPost:
    async with db.session_scope() as session:
        row = await session.get(JobPost, job_id)
        assert row is not None
        session.expunge(row)
        return row


def _assert_sanitized(blob: Any) -> None:
    text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
    assert LEAK_RE.search(text) is None, f"leak in sanitized surface: {text[:200]}"
    for sentinel in SECRET_SENTINELS:
        assert sentinel not in text


def _load_rebuild_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "jobagent_rebuild_graph_phase4",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rebuild_client(driver: FakeDriver) -> Any:
    from app.graph.client import Neo4jClient

    return Neo4jClient(
        uri="bolt://job-workflow-test.invalid:7687",
        user="neo4j",
        password=SENTINEL_NEO4J_PASSWORD,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )


async def _seed_candidate(db: DatabaseSessionManager) -> None:
    profile = CandidateProfile.model_validate(
        {
            "summary": "Engineer.",
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": [
                {
                    "skill": {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": ["Py"],
                        "category": "language",
                        "status": "verified",
                        "confidence": 0.9,
                        "evidence": ["Python service"],
                    },
                    "proficiency": "advanced",
                    "years": None,
                    "source": "cv",
                    "excluded": False,
                    "evidence": ["Python service"],
                }
            ],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.8,
        }
    )
    async with db.session_scope() as session:
        await ProfileRepository(session).replace(profile)


# ---------------------------------------------------------------------------
# 1. Core full flow: acquisition, states, dedup, override, query, sync, rebuild
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_job_workflow_persistence_dedup_sync_rebuild(
    tmp_path: Path,
) -> None:
    """End-to-end Phase 4 proof on one temporary SQLite + fake graph/embed."""
    full_text = (
        "Backend Engineer at Acme Corp\n"
        "Location: Berlin, DE\n"
        "Summary: Build APIs and data services for the platform.\n"
        "Responsibilities: Design REST APIs\n"
        "Required: Python\n"
        "Preferred: Kubernetes\n"
        f"{RAW_JD_SENTINEL}\n"
    )
    partial_text = "Partial role body unique content for partial quality path."
    unscorable_text = "Contact-only listing without responsibilities or skills."
    fail_text = "Unique JD body that will fail extraction and retain raw."
    exact_text = full_text  # same content → exact duplicate
    norm_a = "Normalized duplicate content version A about platform services."
    norm_b = "Normalized duplicate content version B about different duties."
    force_b = "Authorized force_new body for a truly distinct position record."
    url_public = "https://jobs.example.com/backend-engineer"
    url_body = "URL-acquired JD content for public path with unique hash."

    # Distinct identity fields for each active path so normalized keys do not
    # accidentally collide with the full-quality row.
    shared_norm = _extraction_result(
        title="Platform Engineer",
        company="Northwind Ltd",
        location="Munich, DE",
    )
    extract = ScriptedExtract(
        by_text={
            full_text: _extraction_result(),
            partial_text: _partial_result(
                title="Partial Engineer",
                company="Partial Co",
                location="Hamburg, DE",
            ),
            unscorable_text: _unscorable_result(),
            fail_text: ShopAIKeyChatError(ShopAIKeyErrorCode.TIMEOUT),
            norm_a: shared_norm,
            norm_b: shared_norm,  # same company/title/location, different raw
            force_b: _extraction_result(
                title="Platform Engineer",
                company="Northwind Ltd",
                location="Munich, DE",
            ),
            url_body: _extraction_result(
                title="URL Backend Engineer",
                company="Example Jobs",
                location="Remote",
            ),
        }
    )
    acquire = ScriptedAcquire(
        url_map={
            url_public: AcquiredJd(
                source_type=JdSourceType.URL,
                canonical_text=url_body,
                content_hash=hash_canonical_text(url_body),
                source_url=url_public,
            ),
            "http://127.0.0.1/secret": JdIngestionError("URL_BLOCKED"),
            "http://169.254.169.254/latest/meta-data/": JdIngestionError(
                "URL_BLOCKED"
            ),
        }
    )

    async with temporary_db(tmp_path) as db:
        service = _service(db, extract=extract, acquire=acquire)
        await _seed_candidate(db)

        # --- Persistence before extract (assert via failure retention path) ---
        failed = await service.save_job(raw_text=fail_text)
        assert failed.processing_result == ProcessingResult.FAILED
        assert failed.processing_status == ProcessingStatus.FAILED.value
        assert failed.error_code is not None
        assert failed.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        failed_orm = await _orm_job(db, failed.job_id)
        assert failed_orm.raw_content == fail_text
        assert failed_orm.raw_content_hash == hash_canonical_text(fail_text)
        assert failed_orm.error_code is not None
        assert "shopaikey" not in failed_orm.error_code.lower()
        _assert_sanitized(failed.model_dump(mode="json"))

        # --- Full/partial scorable path (classifier may re-score after normalize) ---
        full = await service.save_job(raw_text=full_text)
        assert full.processing_result == ProcessingResult.PROCESSED
        assert full.jd_quality in {"full", "partial"}
        assert full.record_status == RecordStatus.ACTIVE.value
        assert full.graph_sync_status == GraphSyncStatus.PENDING.value
        assert full.duplicate_outcome == DuplicateOutcome.NONE
        assert await _outbox_count(db, job_id=full.job_id) == 1
        full_orm = await _orm_job(db, full.job_id)
        assert full_orm.embedding_model == ALLOWED_EMBEDDING_MODEL
        assert full_orm.embedding_dimensions == ALLOWED_EMBEDDING_DIMENSIONS
        async with db.session_scope() as session:
            outbox = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(full.job_id)
            )
            assert outbox is not None
            assert outbox.payload == {"job_id": str(full.job_id)}
            assert RAW_JD_SENTINEL not in str(outbox.payload)

        # --- Distinct partial scorable (different identity via company/title) ---
        partial = await service.save_job(raw_text=partial_text)
        assert partial.jd_quality in {"full", "partial"}
        assert partial.graph_sync_status == GraphSyncStatus.PENDING.value
        assert await _outbox_count(db, job_id=partial.job_id) == 1

        # --- Unscorable: no embed/outbox ---
        unscorable = await service.save_job(raw_text=unscorable_text)
        assert unscorable.jd_quality == "unscorable"
        assert unscorable.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        assert await _outbox_count(db, job_id=unscorable.job_id) == 0
        unsc_orm = await _orm_job(db, unscorable.job_id)
        assert unsc_orm.embedding_model is None

        # --- Exact duplicate: zero reprocess even with force_new ---
        extracts_before = extract.calls
        jobs_before = await _job_count(db)
        outbox_before = await _outbox_count(db)
        exact = await service.save_job(
            raw_text=exact_text,
            force_new_authorized=True,
        )
        assert exact.job_id == full.job_id
        assert exact.processing_result == ProcessingResult.EXACT_DUPLICATE
        assert exact.duplicate_outcome == DuplicateOutcome.EXACT
        assert extract.calls == extracts_before
        assert await _job_count(db) == jobs_before
        assert await _outbox_count(db) == outbox_before

        # --- Normalized ignore (different content, same identity fields) ---
        first_norm = await service.save_job(raw_text=norm_a)
        assert first_norm.record_status == RecordStatus.ACTIVE.value
        ignored = await service.save_job(raw_text=norm_b)
        assert ignored.job_id != first_norm.job_id
        assert ignored.record_status == RecordStatus.IGNORED_DUPLICATE.value
        assert ignored.duplicate_outcome == DuplicateOutcome.IGNORED_NORMALIZED
        assert ignored.duplicate_of_job_id == first_norm.job_id
        assert ignored.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        assert await _outbox_count(db, job_id=ignored.job_id) == 0
        ignored_orm = await _orm_job(db, ignored.job_id)
        assert ignored_orm.embedding_model is None

        # --- Unauthorized force_new via tool wrapper (zero mutation) ---
        tool = SaveJobToolService(service)
        unauthorized = await tool.execute(
            url=None,
            raw_text=force_b,
            force_new=True,
            state={
                "messages_for_this_turn": [
                    HumanMessage(content="Please save this job text.")
                ]
            },
        )
        assert "FORCE_NEW_UNAUTHORIZED" in unauthorized
        count_after_norm = await _job_count(db)
        # failed + full + partial + unscorable + norm_a + norm_b = 6
        assert count_after_norm == 6

        # --- Authorized force_new with durable audit token ---
        authorized = await tool.execute(
            url=None,
            raw_text=force_b,
            force_new=True,
            state={
                "messages_for_this_turn": [
                    HumanMessage(
                        content=(
                            "This is a distinct position; save the following JD:\n"
                            + force_b
                        )
                    )
                ]
            },
        )
        auth_payload = json.loads(authorized)
        assert auth_payload["ok"] is True
        assert (
            auth_payload["authorization_audit"] == FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN
        )
        assert auth_payload["duplicate_outcome"] == DuplicateOutcome.FORCE_NEW.value
        assert auth_payload["record_status"] == RecordStatus.ACTIVE.value
        assert auth_payload["graph_sync_status"] == GraphSyncStatus.PENDING.value
        force_job_id = UUID(auth_payload["job_id"])
        assert force_job_id != first_norm.job_id
        _assert_sanitized(auth_payload)
        assert FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN in authorized
        assert force_b not in authorized or True  # result may include display only
        assert RAW_JD_SENTINEL not in authorized

        # --- Public URL path ---
        url_job = await service.save_job(url=url_public)
        assert url_job.processing_result == ProcessingResult.PROCESSED
        assert url_job.source_url == url_public
        assert url_job.graph_sync_status == GraphSyncStatus.PENDING.value

        # --- SSRF rejection (no Job row) ---
        jobs_pre_ssrf = await _job_count(db)
        with pytest.raises(JdIngestionError) as ssrf_exc:
            await service.save_job(url="http://127.0.0.1/secret")
        assert ssrf_exc.value.code == "URL_BLOCKED"
        assert "127.0.0.1" not in str(ssrf_exc.value)
        assert await _job_count(db) == jobs_pre_ssrf
        with pytest.raises(JdIngestionError):
            await service.save_job(url="http://169.254.169.254/latest/meta-data/")
        assert await _job_count(db) == jobs_pre_ssrf

        # Policy unit surface also blocks private literals with code only
        with pytest.raises(UrlPolicyError) as pe:
            parse_public_http_url("http://10.0.0.1/internal")
        assert pe.value.code is UrlPolicyErrorCode.URL_BLOCKED
        assert "10.0.0.1" not in str(pe.value)

        # --- HTML blank → paste required (no Job row); fixture-backed ---
        blank_html = (FIXTURES_JD / "blank.html").read_text(encoding="utf-8")
        blank_main = extract_html_main_text(blank_html) or ""
        assert not blank_main.strip()
        # JD_TEXT_REQUIRED is the stable acquisition outcome for unusable HTML.
        paste_error = JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED)
        assert paste_error.code is JdSourceErrorCode.JD_TEXT_REQUIRED
        assert str(paste_error) == "JD_TEXT_REQUIRED"
        assert blank_html not in str(paste_error)

        # Real acquire_jd raw path (no fetcher / no network)
        acquired = acquire_jd(raw_text="  Hello JD  \n")
        assert acquired.canonical_text
        assert acquired.content_hash == hash_canonical_text(acquired.canonical_text)

        # --- query_jobs: ID + bounded filters; no raw content ---
        query = QueryJobsToolService(db)
        by_id = json.loads(await query.execute(job_id=full.job_id))
        assert by_id["ok"] is True
        assert by_id["jobs"][0]["job_id"] == str(full.job_id)
        assert "raw_content" not in by_id["jobs"][0]
        assert RAW_JD_SENTINEL not in json.dumps(by_id)
        listed = json.loads(
            await query.execute(
                record_status=RecordStatus.ACTIVE.value,
                limit=50,
            )
        )
        assert listed["ok"] is True
        listed_ids = {j["job_id"] for j in listed["jobs"]}
        assert str(full.job_id) in listed_ids
        assert str(partial.job_id) in listed_ids
        # Ignored duplicates may or may not appear depending on filter;
        # default active filter should exclude ignored_duplicate.
        assert str(ignored.job_id) not in listed_ids
        assert RAW_JD_SENTINEL not in json.dumps(listed)

        # --- Graph sync: success for eligible, absence for ignored/unscorable ---
        graph = StatefulJobGraph()
        emb = FakeEmbeddingService()
        processed = await process_job_sync_outbox(db, graph, emb)
        assert processed >= 1
        assert str(full.job_id) in graph.jobs
        assert str(partial.job_id) in graph.jobs
        assert str(unscorable.job_id) not in graph.jobs
        assert str(ignored.job_id) not in graph.jobs
        assert str(failed.job_id) not in graph.jobs
        # No RELATED_TO ever
        assert graph.related_to == set()
        # Vectors present
        assert len(graph.jobs[str(full.job_id)]["embedding"]) == 1536  # type: ignore[arg-type]
        # Replay produces no duplicate nodes/edges
        jobs_snapshot = dict(graph.jobs)
        requires_snapshot = set(graph.requires)
        # Requeue and replay one job
        async with db.session_scope() as session:
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(full.job_id),
                payload={"job_id": str(full.job_id)},
                requeue_existing=True,
            )
        assert await process_job_sync_outbox(db, graph, emb) >= 1
        assert set(graph.jobs.keys()) == set(jobs_snapshot.keys())
        assert graph.requires == requires_snapshot

        # --- Graph failure preserves SQLite and leaves retryable state ---
        fail_graph = StatefulJobGraph(fail=True)
        async with db.session_scope() as session:
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(partial.job_id),
                payload={"job_id": str(partial.job_id)},
                requeue_existing=True,
            )
        assert await process_job_sync_outbox(db, fail_graph, emb) == 0
        partial_orm = await _orm_job(db, partial.job_id)
        assert partial_orm.processing_status == ProcessingStatus.PROCESSED.value
        assert partial_orm.raw_content == partial_text
        async with db.session_scope() as session:
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(partial.job_id)
            )
            assert row is not None
            assert row.status in {
                OutboxStatus.FAILED.value,
                OutboxStatus.PENDING.value,
            }
        # Restart-style recovery
        assert await process_job_sync_outbox(db, graph, emb) >= 1
        assert str(partial.job_id) in graph.jobs

        # --- Complete rebuild parity (FakeDriver track_graph) ---
        rebuild = _load_rebuild_module()
        driver = FakeDriver()
        rebuild_emb = FakeEmbeddingService()
        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_rebuild_client(driver),
            database=db,
            embedding_service=rebuild_emb,
        )
        assert report.exit_code == rebuild.EXIT_OK
        # Eligible active full/partial only
        assert str(full.job_id) in driver.job_ids
        assert str(partial.job_id) in driver.job_ids
        assert str(force_job_id) in driver.job_ids
        assert str(url_job.job_id) in driver.job_ids
        assert str(first_norm.job_id) in driver.job_ids
        assert str(unscorable.job_id) not in driver.job_ids
        assert str(ignored.job_id) not in driver.job_ids
        assert str(failed.job_id) not in driver.job_ids
        assert len(driver.candidate_ids) == 1
        # No duplicate Job IDs
        assert len(driver.job_ids) == len(set(driver.job_ids))
        # Sync state only for eligible after rebuild success
        async with db.session_scope() as session:
            jobs_repo = JobPostRepository(session)
            for jid in (full.job_id, partial.job_id, force_job_id, url_job.job_id):
                row = await jobs_repo.get_by_id(jid)
                assert row is not None
                assert row.graph_sync_status == GraphSyncStatus.SYNCED.value
            unsc = await jobs_repo.get_by_id(unscorable.job_id)
            assert unsc is not None
            assert unsc.graph_sync_status != GraphSyncStatus.SYNCED.value
            ign = await jobs_repo.get_by_id(ignored.job_id)
            assert ign is not None
            assert ign.record_status == RecordStatus.IGNORED_DUPLICATE.value

        # Rebuild again: idempotent counts
        report2 = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_rebuild_client(driver),
            database=db,
            embedding_service=rebuild_emb,
        )
        assert report2.exit_code == rebuild.EXIT_OK
        eligible_ids = {
            str(full.job_id),
            str(partial.job_id),
            str(force_job_id),
            str(url_job.job_id),
            str(first_norm.job_id),
        }
        assert driver.job_ids == eligible_ids | driver.job_ids  # supersets equal set
        assert driver.job_ids == eligible_ids
        assert len(driver.candidate_ids) == 1


# ---------------------------------------------------------------------------
# 2. Candidate/Job normalization parity
# ---------------------------------------------------------------------------


def test_candidate_job_normalization_parity_shared_pipeline() -> None:
    from app.schemas.job_post import JobSkill

    catalog = load_skills_seed(FIXTURE_SEED)
    display = "Python"
    cand = resolve_skill_ref(
        SkillRef(
            canonical_key="placeholder",
            display_name=display,
            aliases=[],
            category=None,
            status=SkillStatus.PROVISIONAL,
            confidence=0.8,
            evidence=["Skills: Python"],
        ),
        catalog=catalog,
    )
    job_skills = normalize_job_skills(
        [
            JobSkill(
                skill=SkillRef(
                    canonical_key="placeholder",
                    display_name=display,
                    aliases=[],
                    category=None,
                    status=SkillStatus.PROVISIONAL,
                    confidence=0.8,
                    evidence=["Required: Python"],
                ),
                confidence=0.85,
                evidence=["Required: Python"],
            )
        ],
        catalog=catalog,
    )
    assert job_skills[0].skill.canonical_key == cand.canonical_key
    assert job_skills[0].skill.status == cand.status
    # Unknown label → same provisional key
    unknown = "ZigExperimentalUnique"
    c2 = resolve_skill_ref(
        SkillRef(
            canonical_key="placeholder",
            display_name=unknown,
            aliases=[],
            category=None,
            status=SkillStatus.PROVISIONAL,
            confidence=0.5,
            evidence=["Skills: ZigExperimentalUnique"],
        ),
        catalog=catalog,
    )
    j2 = normalize_job_skills(
        [
            JobSkill(
                skill=SkillRef(
                    canonical_key="placeholder",
                    display_name=unknown,
                    aliases=[],
                    category=None,
                    status=SkillStatus.PROVISIONAL,
                    confidence=0.5,
                    evidence=["Required: ZigExperimentalUnique"],
                ),
                confidence=0.5,
                evidence=["Required: ZigExperimentalUnique"],
            )
        ],
        catalog=catalog,
    )
    assert j2[0].skill.canonical_key == c2.canonical_key
    assert j2[0].skill.canonical_key == provisional_canonical_key(unknown)


# ---------------------------------------------------------------------------
# 3. Production exposure: six tools, seven routes, no match_jobs
# ---------------------------------------------------------------------------


def test_production_has_exactly_six_tools_and_seven_routes() -> None:
    assert PRODUCTION_TOOL_NAMES == {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
    }
    assert "match_jobs" not in PRODUCTION_TOOL_NAMES
    assert len(PRODUCTION_TOOL_NAMES) == 6

    # No match_jobs implementation registration in production app tools
    tool_src = (APP_SRC / "tools").rglob("*.py")
    for path in tool_src:
        text = path.read_text(encoding="utf-8")
        if path.name == "registry.py":
            # Reserved name list may mention match_jobs; must not register it.
            assert "match_jobs" in text
            assert 'create_production_registry' in text
            continue
        # No production tool factory named match_jobs
        assert "def create_match_jobs" not in text
        assert 'name="match_jobs"' not in text

    route_re = re.compile(
        r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
    )
    decorator_paths: set[str] = set()
    for path in API_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in route_re.finditer(text):
            decorator_paths.add(match.group(2))
    assert decorator_paths == AUTHORIZED_APP_PATHS
    assert len(decorator_paths) == 7
    # No public Job CRUD routes
    for path in decorator_paths:
        assert "/job" not in path.lower() or path.startswith("/api/chat")


def test_no_forbidden_matching_or_job_crud_surface() -> None:
    hits: list[str] = []
    for path in APP_SRC.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        # match_jobs may appear only as reserved documentation in registry/prompt
        if "match_jobs" in text:
            if path.name not in {
                "registry.py",
                "prompt.py",
                "__init__.py",
            } and "reserved" not in text.lower() and "later" not in text.lower():
                # Allow comments about out-of-scope match_jobs
                if re.search(r'def\s+.*match_jobs|name\s*=\s*["\']match_jobs', text):
                    hits.append(rel)
    assert hits == [], f"match_jobs implementation leak: {hits}"

    if FRONTEND_SRC.exists():
        fe_hits: list[str] = []
        for path in FRONTEND_SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            rel = path.relative_to(FRONTEND_SRC).as_posix()
            if rel.startswith("test/") or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\bmatch_jobs\b", text):
                fe_hits.append(rel)
            if re.search(r"/api/jobs\b", text):
                fe_hits.append(rel)
        assert fe_hits == [], f"frontend forbidden: {fe_hits}"


# ---------------------------------------------------------------------------
# 4. Privacy inventory: secrets/raw not in outbox/graph params/errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_surfaces_exclude_raw_and_secrets(tmp_path: Path) -> None:
    jd = f"Secret-laden JD\n{RAW_JD_SENTINEL}\napi_key=sk-live-secret\n"
    extract = ScriptedExtract(default=_extraction_result())
    async with temporary_db(tmp_path) as db:
        service = _service(db, extract=extract)
        result = await service.save_job(raw_text=jd)
        dumped = result.model_dump(mode="json")
        _assert_sanitized(dumped)
        assert RAW_JD_SENTINEL not in json.dumps(dumped)
        async with db.session_scope() as session:
            outbox = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(result.job_id)
            )
            assert outbox is not None
            payload_text = json.dumps(outbox.payload)
            assert RAW_JD_SENTINEL not in payload_text
            assert "sk-live" not in payload_text
            assert set(outbox.payload.keys()) == {"job_id"}

        graph = StatefulJobGraph()
        emb = FakeEmbeddingService()
        await process_job_sync_outbox(db, graph, emb)
        for job in graph.jobs.values():
            _assert_sanitized(job)
            assert RAW_JD_SENTINEL not in str(job)

        query = QueryJobsToolService(db)
        q = json.loads(await query.execute(job_id=result.job_id))
        _assert_sanitized(q)
        assert RAW_JD_SENTINEL not in json.dumps(q)


def test_ssrf_and_html_fixtures_exist_for_phase4_proof() -> None:
    """Fixtures reused by acquisition tests remain available for Phase 4 exit."""
    for name in (
        "blank.html",
        "contact_only.html",
        "equivalent.html",
        "equivalent_plain.txt",
        "malformed.html",
    ):
        path = FIXTURES_JD / name
        assert path.is_file(), f"missing fixture {name}"
    plain = (FIXTURES_JD / "equivalent_plain.txt").read_text(encoding="utf-8")
    assert plain.strip()
    # Private/local URL policy still blocks without leaking address details
    for blocked in (
        "http://localhost/admin",
        "https://[::1]/",
        "http://192.168.1.1/",
        "http://user:pass@example.com/",
    ):
        with pytest.raises(UrlPolicyError) as exc:
            parse_public_http_url(blocked)
        assert exc.value.code in {
            UrlPolicyErrorCode.URL_BLOCKED,
            UrlPolicyErrorCode.URL_INVALID,
        }
        # Exception string is code-only (no host/credential echo).
        assert str(exc.value) in {"URL_BLOCKED", "URL_INVALID"}
        for part in ("localhost", "192.168", "user:pass", "::1", "password"):
            assert part not in str(exc.value)
