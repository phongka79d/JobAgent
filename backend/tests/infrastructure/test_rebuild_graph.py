"""Safety and complete rebuild parity tests for rebuild_graph.py."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, OutboxStatus, ProcessingStatus, RecordStatus
from app.db.session import create_session_manager
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphErrorCode
from app.graph.job_sync import JOB_UPSERT_OPERATION
from app.graph.schema import SCHEMA_STATEMENTS, ensure_graph_schema
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.job_post import JdQuality, JobPostExtraction
from app.services.embeddings import (
    JOB_TEXT_REPRESENTATION_VERSION,
    EmbeddingVector,
    JobEmbeddingError,
    JobEmbeddingErrorCode,
    JobEmbeddingResult,
)
from app.services.jd_source import hash_canonical_text
from tests.graph.fakes import FakeDriver

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "rebuild_graph.py"
SENTINEL_PASSWORD = "sentinel-rebuild-secret-never-emit"
SENTINEL_API_KEY = "sentinel-shopaikey-rebuild-never-emit"
SENTINEL_URI = "bolt://neo4j:7687"
VECTOR_DIM = 1536


def _load_rebuild_module() -> ModuleType:
    """Import the infrastructure script as a module without installing it."""
    spec = importlib.util.spec_from_file_location(
        "jobagent_rebuild_graph",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rebuild() -> ModuleType:
    assert SCRIPT_PATH.is_file(), f"missing rebuild script: {SCRIPT_PATH}"
    return _load_rebuild_module()


def _client(driver: FakeDriver) -> Neo4jClient:
    return Neo4jClient(
        uri=SENTINEL_URI,
        user="neo4j",
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )


class FakeEmbeddingService:
    def __init__(
        self,
        *,
        fail: bool = False,
        code: JobEmbeddingErrorCode = JobEmbeddingErrorCode.PROVIDER_ERROR,
        vector: Sequence[float] | None = None,
    ) -> None:
        self.fail = fail
        self.code = code
        self.calls: list[JobPostExtraction] = []
        self._vector = list(vector) if vector is not None else [0.01] * VECTOR_DIM

    def embed_job(self, job: JobPostExtraction) -> JobEmbeddingResult:
        self.calls.append(job)
        if self.fail:
            raise JobEmbeddingError(self.code)
        return JobEmbeddingResult(
            vectors=(EmbeddingVector(index=0, values=tuple(self._vector)),),
            model=ALLOWED_EMBEDDING_MODEL,
            dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            representation_version=JOB_TEXT_REPRESENTATION_VERSION,
        )


def _skill(
    key: str = "python",
    *,
    aliases: list[str] | None = None,
    evidence: str = "Required: Python",
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.replace("_", " ").title(),
            "aliases": aliases if aliases is not None else [],
            "category": "language" if key == "python" else None,
            "status": "verified",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _extraction(**overrides: Any) -> JobPostExtraction:
    data: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs and services.",
        "responsibilities": ["Own production services"],
        "required_skills": [_skill("python", aliases=["Py"])],
        "preferred_skills": [
            _skill("kubernetes", evidence="Preferred: Kubernetes", confidence=0.7)
        ],
        "seniority": "senior",
        "min_experience_years": 5.0,
        "max_experience_years": 10.0,
        "location": "Berlin, DE",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "education_requirements": [],
        "language_requirements": [],
        "salary_text": None,
        "job_family": "Software Engineering",
        "extraction_confidence": 0.85,
        "jd_quality": "full",
    }
    data.update(overrides)
    return JobPostExtraction.model_validate(data)


async def _seed_job(
    db: Any,
    *,
    extraction: JobPostExtraction | None = None,
    raw_suffix: str = "a",
    quality: str | None = None,
    record_status: str = RecordStatus.ACTIVE.value,
    graph_status: str = GraphSyncStatus.PENDING.value,
) -> UUID:
    extraction = extraction or _extraction()
    if quality is not None:
        extraction = extraction.model_copy(update={"jd_quality": JdQuality(quality)})
    raw = f"Canonical JD body for rebuild test {raw_suffix}."
    async with db.session_scope() as session:
        jobs = JobPostRepository(session)
        created = await jobs.create_received(
            source_type="text",
            raw_content=raw,
            raw_content_hash=hash_canonical_text(raw),
        )
        job_id = created.record.id
        await jobs.mark_processing(job_id)
        quality_value = (
            extraction.jd_quality.value
            if hasattr(extraction.jd_quality, "value")
            else str(extraction.jd_quality)
        )
        reasons = None if quality_value == "full" else ["partial_fields"]
        await jobs.mark_processed(
            job_id,
            extraction=extraction,
            quality_reasons=reasons,
            force_new=True,
        )
        if record_status == RecordStatus.IGNORED_DUPLICATE.value:
            peer_raw = f"Peer canonical JD for ignored link {raw_suffix}."
            peer = await jobs.create_received(
                source_type="text",
                raw_content=peer_raw,
                raw_content_hash=hash_canonical_text(peer_raw),
            )
            peer_id = peer.record.id
            await jobs.mark_processing(peer_id)
            await jobs.mark_processed(
                peer_id,
                extraction=extraction.model_copy(
                    update={"title": "Other Title Distinct"}
                ),
                quality_reasons=reasons,
                force_new=True,
            )
            await jobs.mark_ignored_duplicate(job_id, duplicate_of_job_id=peer_id)
        else:
            await jobs.set_embedding_identity(
                job_id,
                embedding_model=ALLOWED_EMBEDDING_MODEL,
                embedding_dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            )
            await jobs.set_graph_sync_status(job_id, status=graph_status)
        return job_id


async def _seed_candidate(db: Any) -> None:
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


def test_help_displays_safety_controls_without_connection(
    rebuild: ModuleType,
) -> None:
    parser = rebuild.build_parser()
    help_text = parser.format_help()
    assert "--confirm-destructive" in help_text
    assert "--dry-run" in help_text
    assert "Candidate" in help_text or "JobAgent" in help_text
    assert "non-destructive" in help_text.lower() or "dry-run" in help_text.lower()
    assert SENTINEL_PASSWORD not in help_text
    assert "password" not in help_text.lower() or "Passwords" in help_text


def test_help_subprocess_no_config_leak() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0
    combined = completed.stdout + completed.stderr
    assert "--confirm-destructive" in combined
    assert SENTINEL_PASSWORD not in combined
    assert SENTINEL_API_KEY not in combined
    for key in ("NEO4J_PASSWORD", "SHOPAIKEY_API_KEY"):
        value = __import__("os").environ.get(key)
        if value:
            assert value not in combined


def test_default_main_is_dry_run_non_destructive(rebuild: ModuleType) -> None:
    out = io.StringIO()
    err = io.StringIO()
    code = rebuild.main([], stdout=out, stderr=err)
    assert code == rebuild.EXIT_OK
    text = out.getvalue()
    assert "rebuild_mode=dry_run" in text
    assert "dry_run=true" in text
    assert "no connection opened" in text
    assert err.getvalue() == ""
    for label in rebuild.JOBAGENT_DERIVED_LABELS:
        assert f"MATCH (n:{label}) DETACH DELETE n" in text
    assert SENTINEL_PASSWORD not in text


def test_explicit_dry_run_flag(rebuild: ModuleType) -> None:
    out = io.StringIO()
    code = rebuild.main(["--dry-run"], stdout=out, stderr=io.StringIO())
    assert code == rebuild.EXIT_OK
    assert "rebuild_mode=dry_run" in out.getvalue()


def test_dry_run_wins_over_confirm(rebuild: ModuleType) -> None:
    out = io.StringIO()
    code = rebuild.main(
        ["--dry-run", "--confirm-destructive"],
        stdout=out,
        stderr=io.StringIO(),
        client=_client(FakeDriver()),
    )
    assert code == rebuild.EXIT_OK
    assert "rebuild_mode=dry_run" in out.getvalue()


def test_clear_statements_are_label_scoped(rebuild: ModuleType) -> None:
    statements = rebuild.assert_clear_statements_are_scoped()
    assert len(statements) == 4
    assert statements == (
        "MATCH (n:Candidate) DETACH DELETE n",
        "MATCH (n:Job) DETACH DELETE n",
        "MATCH (n:Skill) DETACH DELETE n",
        "MATCH (n:JobFamily) DETACH DELETE n",
    )
    joined = "\n".join(statements)
    assert "MATCH (n) DETACH DELETE" not in joined
    assert "DROP DATABASE" not in joined.upper()


def test_clear_statement_guard_rejects_unlabeled(rebuild: ModuleType) -> None:
    with pytest.raises(ValueError, match="approved labels|indiscriminate|exact label|unlabeled"):
        rebuild.assert_clear_statements_are_scoped(
            ("MATCH (n) DETACH DELETE n",),
        )


@pytest.mark.asyncio
async def test_destructive_requires_confirm_flag_path(rebuild: ModuleType) -> None:
    driver = FakeDriver()
    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=False,
        client=_client(driver),
    )
    assert report.dry_run is True
    assert report.exit_code == rebuild.EXIT_OK
    assert driver.queries == []


@pytest.mark.asyncio
async def test_destructive_missing_database_fails(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver()
    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=_client(driver),
        embedding_service=FakeEmbeddingService(),
    )
    assert report.exit_code == rebuild.EXIT_FAILURE
    statuses = {s.name: s for s in report.stages}
    assert statuses[rebuild.StageName.CLEAR_DERIVED].status == rebuild.StageStatus.COMPLETED
    assert statuses[rebuild.StageName.RECREATE_SCHEMA].status == rebuild.StageStatus.COMPLETED
    assert statuses[rebuild.StageName.REBUILD_CANDIDATE].status == rebuild.StageStatus.FAILED
    assert statuses[rebuild.StageName.REBUILD_CANDIDATE].detail == "database_required"


@pytest.mark.asyncio
async def test_complete_rebuild_parity_candidate_and_jobs(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "rebuild-complete.db")
    await database.create_all()
    try:
        await _seed_candidate(database)
        job_full = await _seed_job(database, raw_suffix="full")
        job_partial = await _seed_job(
            database,
            extraction=_extraction(jd_quality="partial", title="Partial Role"),
            raw_suffix="partial",
            quality="partial",
        )
        unscorable = await _seed_job(
            database,
            extraction=_extraction(
                jd_quality="unscorable",
                required_skills=[],
                preferred_skills=[],
                job_family=None,
            ),
            raw_suffix="unscorable",
            quality="unscorable",
        )
        ignored = await _seed_job(
            database,
            raw_suffix="ignored",
            record_status=RecordStatus.IGNORED_DUPLICATE.value,
        )

        driver = FakeDriver()
        embeddings = FakeEmbeddingService()
        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(driver),
            database=database,
            embedding_service=embeddings,
        )

        assert report.exit_code == rebuild.EXIT_OK
        assert report.dry_run is False
        statuses = {s.name: s.status for s in report.stages}
        for name in rebuild.ALL_STAGES:
            assert statuses[name] == rebuild.StageStatus.COMPLETED
        assert "rebuild_complete=true" in "\n".join(report.messages)
        assert "rebuild_incomplete" not in "\n".join(report.messages)

        # Eligible: full + partial + active peer of ignored duplicate.
        # Unscorable and ignored_duplicate rows never embed or enter Neo4j.
        assert len(embeddings.calls) == 3
        assert str(job_full) in driver.job_ids
        assert str(job_partial) in driver.job_ids
        assert str(unscorable) not in driver.job_ids
        assert str(ignored) not in driver.job_ids
        assert len(driver.candidate_ids) == 1
        assert len(driver.job_ids) == 3

        async with database.session_scope() as session:
            jobs = JobPostRepository(session)
            for job_id in (job_full, job_partial):
                row = await jobs.get_by_id(job_id)
                assert row is not None
                assert row.graph_sync_status == GraphSyncStatus.SYNCED.value
                outbox = await GraphOutboxRepository(session).get_by_identity(
                    JOB_UPSERT_OPERATION, str(job_id)
                )
                assert outbox is not None
                assert outbox.status == OutboxStatus.SYNCED.value
                assert outbox.payload == {"job_id": str(job_id)}
            unscored = await jobs.get_by_id(unscorable)
            assert unscored is not None
            # Never falsely marked synced by rebuild.
            assert unscored.graph_sync_status != GraphSyncStatus.SYNCED.value
            ignored_row = await jobs.get_by_id(ignored)
            assert ignored_row is not None
            assert ignored_row.record_status == RecordStatus.IGNORED_DUPLICATE.value
            assert ignored_row.graph_sync_status != GraphSyncStatus.SYNCED.value

        # Four scoped clears + schema + candidate + job projections + parity reads.
        clear_queries = [item.query for item in driver.queries[:4]]
        assert clear_queries == list(rebuild.CLEAR_STATEMENTS)
        assert SENTINEL_PASSWORD not in "\n".join(report.messages)
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_rebuild_replay_is_idempotent(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "rebuild-replay.db")
    await database.create_all()
    try:
        await _seed_candidate(database)
        job_id = await _seed_job(database, raw_suffix="replay")
        driver = FakeDriver()
        emb = FakeEmbeddingService()
        first = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(driver),
            database=database,
            embedding_service=emb,
        )
        second = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(driver),
            database=database,
            embedding_service=emb,
        )
        assert first.exit_code == rebuild.EXIT_OK
        assert second.exit_code == rebuild.EXIT_OK
        assert driver.job_ids == {str(job_id)}
        assert len(driver.candidate_ids) == 1
        assert emb.calls  # recomputed each rebuild
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_embedding_failure_does_not_mark_sync(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "rebuild-embed-fail.db")
    await database.create_all()
    try:
        job_id = await _seed_job(database, raw_suffix="embed-fail")
        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(FakeDriver()),
            database=database,
            embedding_service=FakeEmbeddingService(
                fail=True, code=JobEmbeddingErrorCode.TIMEOUT
            ),
        )
        assert report.exit_code == rebuild.EXIT_FAILURE
        statuses = {s.name: s for s in report.stages}
        assert statuses[rebuild.StageName.REBUILD_ENTITIES].status == (
            rebuild.StageStatus.FAILED
        )
        assert statuses[rebuild.StageName.UPDATE_SYNC_STATES].status == (
            rebuild.StageStatus.SKIPPED
        )
        async with database.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(job_id)
            assert job is not None
            assert job.processing_status == ProcessingStatus.PROCESSED.value
            assert job.graph_sync_status != GraphSyncStatus.SYNCED.value
        blob = "\n".join([*(s.detail for s in report.stages), *report.messages])
        assert SENTINEL_PASSWORD not in blob
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_count_mismatch_fails_without_sync_mark(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "rebuild-mismatch.db")
    await database.create_all()
    try:
        await _seed_job(database, raw_suffix="mismatch")
        driver = FakeDriver()
        # Force parity read to lie about job ids after real projection.
        original = driver.default_records

        def lying_records(query: str, params: Any) -> list[dict[str, Any]]:
            if "collect(j.id)" in query:
                return [{"job_ids": ["not-a-real-job-id"]}]
            return original(query, params)

        driver.record_provider = lying_records
        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(driver),
            database=database,
            embedding_service=FakeEmbeddingService(),
        )
        assert report.exit_code == rebuild.EXIT_FAILURE
        statuses = {s.name: s for s in report.stages}
        assert statuses[rebuild.StageName.VERIFY_ENTITY_COUNTS].status == (
            rebuild.StageStatus.FAILED
        )
        assert statuses[rebuild.StageName.VERIFY_ENTITY_COUNTS].detail == (
            "parity_job_ids_mismatch"
        )
        assert statuses[rebuild.StageName.UPDATE_SYNC_STATES].status == (
            rebuild.StageStatus.SKIPPED
        )
        async with database.session_scope() as session:
            jobs = await JobPostRepository(session).list_graph_eligible_page()
            assert jobs
            assert jobs[0].graph_sync_status != GraphSyncStatus.SYNCED.value
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_clear_failure_is_sanitized_and_exits_failure(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver(
        run_error=RuntimeError(
            f"auth failed password={SENTINEL_PASSWORD} uri={SENTINEL_URI}"
        )
    )
    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=_client(driver),
        embedding_service=FakeEmbeddingService(),
    )
    assert report.exit_code == rebuild.EXIT_FAILURE
    clear = report.stages[0]
    assert clear.name == rebuild.StageName.CLEAR_DERIVED
    assert clear.status == rebuild.StageStatus.FAILED
    assert clear.detail in {
        GraphErrorCode.QUERY_FAILED.value,
        "clear_failed",
        GraphErrorCode.UNAVAILABLE.value,
    }
    blob = "\n".join(
        [clear.detail, *(s.detail for s in report.stages), *report.messages]
    )
    assert SENTINEL_PASSWORD not in blob
    assert SENTINEL_PASSWORD not in str(report)


@pytest.mark.asyncio
async def test_schema_failure_sanitized(rebuild: ModuleType, tmp_path: Path) -> None:
    database = create_session_manager(tmp_path / "schema-fail.db")
    await database.create_all()
    try:
        driver = FakeDriver()
        client = _client(driver)

        async def boom(_client: Neo4jClient) -> None:
            raise GraphError(GraphErrorCode.SCHEMA_FAILED)

        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=client,
            database=database,
            embedding_service=FakeEmbeddingService(),
            ensure_schema=boom,
        )
        assert report.exit_code == rebuild.EXIT_FAILURE
        assert report.stages[0].status == rebuild.StageStatus.COMPLETED
        assert report.stages[1].status == rebuild.StageStatus.FAILED
        assert report.stages[1].detail == GraphErrorCode.SCHEMA_FAILED.value
        for stage in report.stages[2:]:
            assert stage.status == rebuild.StageStatus.SKIPPED
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_schema_reuse_delegates_to_ensure_graph_schema(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "schema-reuse.db")
    await database.create_all()
    try:
        driver = FakeDriver()
        client = _client(driver)
        called: dict[str, Any] = {"n": 0}

        async def wrapper(c: Neo4jClient) -> None:
            called["n"] += 1
            assert c is client
            await ensure_graph_schema(c)

        await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=client,
            database=database,
            embedding_service=FakeEmbeddingService(),
            ensure_schema=wrapper,
        )
        assert called["n"] == 1
        executed_schema = [
            q.query for q in driver.queries if q.query in SCHEMA_STATEMENTS
        ]
        assert executed_schema == list(SCHEMA_STATEMENTS)
    finally:
        await database.dispose()


def test_main_destructive_complete_with_injected_deps(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    import asyncio

    async def _prepare() -> Any:
        database = create_session_manager(tmp_path / "main-destructive.db")
        await database.create_all()
        await _seed_job(database, raw_suffix="main")
        return database

    database = asyncio.run(_prepare())
    try:
        driver = FakeDriver()
        out = io.StringIO()
        err = io.StringIO()
        code = rebuild.main(
            ["--confirm-destructive"],
            stdout=out,
            stderr=err,
            client=_client(driver),
            database=database,
            embedding_service=FakeEmbeddingService(),
        )
        assert code == rebuild.EXIT_OK
        text = err.getvalue() + out.getvalue()
        assert "rebuild_mode=destructive" in text
        assert "rebuild_complete=true" in text
        assert "status=not_implemented" not in text
        assert SENTINEL_PASSWORD not in text
    finally:
        asyncio.run(database.dispose())


def test_format_report_lines_never_include_secrets(rebuild: ModuleType) -> None:
    report = rebuild.RebuildReport(
        dry_run=True,
        stages=(
            rebuild.StageResult(
                name=rebuild.StageName.CLEAR_DERIVED,
                status=rebuild.StageStatus.PLANNED,
            ),
        ),
        exit_code=0,
        messages=("ok",),
    )
    lines = rebuild.format_report_lines(report)
    blob = "\n".join(lines)
    assert SENTINEL_PASSWORD not in blob
    assert "neo4j+s://" not in blob


def test_no_database_wide_delete_in_module_source(rebuild: ModuleType) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "MATCH (n) DETACH DELETE" not in source or "FORBIDDEN" in source
    for statement in rebuild.CLEAR_STATEMENTS:
        assert statement.startswith("MATCH (n:")
        assert "DETACH DELETE" in statement


def test_rebuild_logic_not_god_file_in_cli() -> None:
    """CLI stays thin; job load/verify live under app.graph."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "load_rebuild_snapshot" in source
    assert "project_jobs_for_rebuild" in source
    assert "verify_rebuild_parity" in source
    assert "mark_rebuild_sync_states" in source
    # Projection Cypher must not be duplicated in the CLI.
    assert "MERGE (j:Job" not in source
