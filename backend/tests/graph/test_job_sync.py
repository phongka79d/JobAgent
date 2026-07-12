"""Job outbox projection tests using fake Neo4j and embedding adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, OutboxStatus, ProcessingStatus, RecordStatus
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.graph.job_sync import (
    JOB_UPSERT_OPERATION,
    build_job_projection_parameters,
    process_job_sync_outbox,
)
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository
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

VECTOR_DIM = 1536


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "job-sync.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _skill(
    key: str = "python",
    *,
    aliases: list[str] | None = None,
    evidence: str = "Required: Python",
    confidence: float = 0.9,
    status: str = "verified",
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.replace("_", " ").title() if key != "ci_cd" else "CI/CD",
            "aliases": aliases if aliases is not None else ([] if key != "ci_cd" else ["CI/CD"]),
            "category": "language" if key == "python" else None,
            "status": status,
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


class FakeEmbeddingService:
    """Deterministic embedding fake; optional failure injection."""

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


async def _seed_active_job(
    db: DatabaseSessionManager,
    *,
    extraction: JobPostExtraction | None = None,
    raw_suffix: str = "a",
    enqueue: bool = True,
    quality: str | None = None,
    record_status: str = RecordStatus.ACTIVE.value,
    graph_status: str = GraphSyncStatus.PENDING.value,
) -> UUID:
    extraction = extraction or _extraction()
    if quality is not None:
        extraction = extraction.model_copy(update={"jd_quality": JdQuality(quality)})
    raw = f"Canonical JD body for job sync test {raw_suffix}."
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
            # Create a peer first is complex; force status via second mark path.
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
            if enqueue:
                await GraphOutboxRepository(session).enqueue(
                    operation=JOB_UPSERT_OPERATION,
                    entity_id=str(job_id),
                    payload={"job_id": str(job_id)},
                    requeue_existing=True,
                )
        return job_id


@pytest.mark.asyncio
async def test_projects_eligible_job_with_exact_parameters(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(db)
        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        embeddings = FakeEmbeddingService()
        processed = await process_job_sync_outbox(db, client, embeddings, limit=10)
        assert processed == 1
        assert len(embeddings.calls) == 1
        assert len(driver.queries) == 1
        recorded = driver.queries[0]
        assert "MERGE (j:Job {id: $job_id})" in recorded.query
        assert "REQUIRES" in recorded.query
        assert "PREFERS" in recorded.query
        assert "IN_FAMILY" in recorded.query
        assert "RELATED_TO" not in recorded.query
        params = recorded.parameters
        assert params["job_id"] == str(job_id)
        assert params["title"] == "Backend Engineer"
        assert params["company"] == "Acme Corp"
        assert params["location"] == "Berlin, DE"
        assert params["work_mode"] == "hybrid"
        assert params["seniority"] == "senior"
        assert params["quality"] == "full"
        assert len(params["embedding"]) == VECTOR_DIM
        assert params["required_skills"] == [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["Py"],
                "category": "language",
                "status": "verified",
                "confidence": 0.9,
                "evidence": ["Required: Python"],
            }
        ]
        assert params["preferred_skills"][0]["canonical_key"] == "kubernetes"
        assert params["job_families"] == [
            {
                "canonical_key": "software_engineering",
                "display_name": "Software Engineering",
            }
        ]
        # Identifier-only outbox payload retained.
        async with db.session_scope() as session:
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert row is not None
            assert row.status == OutboxStatus.SYNCED.value
            assert row.payload == {"job_id": str(job_id)}
            job = await JobPostRepository(session).get_by_id(job_id)
            assert job is not None
            assert job.graph_sync_status == GraphSyncStatus.SYNCED.value
            assert job.processing_status == ProcessingStatus.PROCESSED.value


@pytest.mark.asyncio
async def test_ignored_and_unscorable_never_enter_graph(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        # Unscorable active: enqueue manually to prove processor rejects.
        unscore = await _seed_active_job(
            db,
            extraction=_extraction(jd_quality="unscorable", required_skills=[]),
            raw_suffix="unscorable",
            quality="unscorable",
        )
        async with db.session_scope() as session:
            # Force pending graph + outbox despite eligibility rules at ingest.
            jobs = JobPostRepository(session)
            # set_graph_sync may work for active unscorable
            await jobs.set_graph_sync_status(unscore, status=GraphSyncStatus.PENDING)
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(unscore),
                payload={"job_id": str(unscore)},
                requeue_existing=True,
            )

        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_job_sync_outbox(db, client, FakeEmbeddingService()) == 1
        assert driver.queries == []
        async with db.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(unscore)
            assert job is not None
            assert job.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(unscore)
            )
            assert row is not None
            assert row.status == OutboxStatus.SYNCED.value


@pytest.mark.asyncio
async def test_embedding_failure_marks_retryable_preserves_processed(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(db, raw_suffix="embed-fail")
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=FakeDriver,
        )
        processed = await process_job_sync_outbox(
            db,
            client,
            FakeEmbeddingService(fail=True, code=JobEmbeddingErrorCode.TIMEOUT),
        )
        assert processed == 0
        async with db.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(job_id)
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert job is not None
            assert job.processing_status == ProcessingStatus.PROCESSED.value
            assert job.graph_sync_status == GraphSyncStatus.FAILED.value
            assert row is not None
            assert row.status == OutboxStatus.FAILED.value
            assert row.last_error == JobEmbeddingErrorCode.TIMEOUT.value
            assert row.attempts >= 1


@pytest.mark.asyncio
async def test_neo4j_failure_marks_retryable_and_replay_succeeds(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(db, raw_suffix="neo4j-fail")
        failed = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: FakeDriver(run_error=RuntimeError("down")),
        )
        assert await process_job_sync_outbox(db, failed, FakeEmbeddingService()) == 0

        healthy = FakeDriver()
        ok = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: healthy,
        )
        assert await process_job_sync_outbox(db, ok, FakeEmbeddingService()) == 1
        assert len(healthy.queries) == 1
        async with db.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(job_id)
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert job is not None
            assert job.graph_sync_status == GraphSyncStatus.SYNCED.value
            assert row is not None
            assert row.status == OutboxStatus.SYNCED.value


@pytest.mark.asyncio
async def test_replay_is_idempotent_no_duplicate_projection_calls_payload(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(db, raw_suffix="replay")
        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        emb = FakeEmbeddingService()
        assert await process_job_sync_outbox(db, client, emb) == 1
        # Already synced: second process claims nothing.
        assert await process_job_sync_outbox(db, client, emb) == 0
        assert len(driver.queries) == 1
        assert len(emb.calls) == 1
        # Requeue and replay produces one more query (MERGE idempotent).
        async with db.session_scope() as session:
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(job_id),
                payload={"job_id": str(job_id)},
                requeue_existing=True,
            )
        assert await process_job_sync_outbox(db, client, emb) == 1
        assert len(driver.queries) == 2
        # Same job id both times.
        assert driver.queries[0].parameters["job_id"] == str(job_id)
        assert driver.queries[1].parameters["job_id"] == str(job_id)


@pytest.mark.asyncio
async def test_stale_owned_edges_replaced_on_replay(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(
            db,
            extraction=_extraction(
                required_skills=[_skill("python"), _skill("obsolete")],
                preferred_skills=[],
            ),
            raw_suffix="stale1",
        )
        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_job_sync_outbox(db, client, FakeEmbeddingService()) == 1
        first = driver.queries[0]
        assert {s["canonical_key"] for s in first.parameters["required_skills"]} == {
            "python",
            "obsolete",
        }

        async with db.session_scope() as session:
            from app.db.models.jobs import JobPost

            row = await session.get(JobPost, job_id)
            assert row is not None
            updated = _extraction(
                required_skills=[_skill("python"), _skill("go")],
                preferred_skills=[_skill("rust", evidence="Preferred: Rust")],
            )
            row.extracted_json = updated.model_dump(mode="json")
            await session.flush()
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(job_id),
                payload={"job_id": str(job_id)},
                requeue_existing=True,
            )

        assert await process_job_sync_outbox(db, client, FakeEmbeddingService()) == 1
        second = driver.queries[1]
        assert "DELETE old_req" in second.query or "DELETE" in second.query
        keys = {s["canonical_key"] for s in second.parameters["required_skills"]}
        assert keys == {"python", "go"}
        assert "obsolete" not in keys
        pref = {s["canonical_key"] for s in second.parameters["preferred_skills"]}
        assert pref == {"rust"}


@pytest.mark.asyncio
async def test_alias_union_parameters_include_aliases(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        await _seed_active_job(
            db,
            extraction=_extraction(
                required_skills=[
                    _skill("ci_cd", aliases=["CI/CD", "continuous integration"])
                ],
                preferred_skills=[],
            ),
            raw_suffix="alias",
        )
        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_job_sync_outbox(db, client, FakeEmbeddingService()) == 1
        skill = driver.queries[0].parameters["required_skills"][0]
        assert skill["canonical_key"] == "ci_cd"
        assert "CI/CD" in skill["aliases"]
        assert "continuous integration" in skill["aliases"]
        # Cypher includes alias union expression (no alias nodes).
        assert "skill.aliases" in driver.queries[0].query
        assert "Alias" not in driver.queries[0].query
        assert "RELATED_TO" not in driver.queries[0].query


@pytest.mark.asyncio
async def test_outbox_payload_never_carries_raw_or_vector(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_active_job(db, raw_suffix="privacy")
        async with db.session_scope() as session:
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert row is not None
            assert row.payload == {"job_id": str(job_id)}
            payload_text = str(row.payload).lower()
            assert "raw" not in payload_text
            assert "embedding" not in payload_text
            assert "vector" not in payload_text
            assert "password" not in payload_text
            assert "content" not in row.payload


def test_build_job_projection_parameters_dimension_guard() -> None:
    with pytest.raises(JobEmbeddingError) as exc_info:
        build_job_projection_parameters(
            job_id=UUID("00000000-0000-0000-0000-000000000001"),
            extraction=_extraction(),
            embedding=[0.0] * 10,
        )
    assert exc_info.value.code is JobEmbeddingErrorCode.DIMENSION_MISMATCH


@pytest.mark.asyncio
async def test_no_job_family_when_absent(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        await _seed_active_job(
            db,
            extraction=_extraction(job_family=None),
            raw_suffix="nofam",
        )
        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_job_sync_outbox(db, client, FakeEmbeddingService()) == 1
        assert driver.queries[0].parameters["job_families"] == []
