"""Fake-backed tests for match_jobs profile/outbox/limit/cache guards."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    Settings,
    load_settings,
)
from app.db.base import new_uuid, utc_now
from app.db.enums import (
    GraphSyncStatus,
    JobSourceType,
    ProcessingStatus,
    RecordStatus,
)
from app.db.models.jobs import JobPost
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.errors import GraphError, GraphErrorCode
from app.graph.schema import VECTOR_INDEX_NAME
from app.repositories.job_posts import JobPostRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.job_post import JobPostExtraction
from app.schemas.matching import MAX_MATCH_RESULTS
from app.services.embeddings import JobEmbeddingService
from app.services.jd_quality import apply_jd_quality
from app.services.jd_source import hash_canonical_text
from app.services.retrieval import MAX_RETRIEVAL_CANDIDATES
from app.tools.match_jobs import (
    DEFAULT_MATCH_LIMIT,
    MAX_SAVED_JOB_IDS,
    PROFILE_REQUIRED_GUIDANCE,
    MatchJobsInput,
    MatchJobsToolService,
    create_match_jobs_tool,
)
from app.tools.query_jobs import QueryJobsToolService
from app.tools.registry import PRODUCTION_TOOL_NAMES, create_production_registry
from langchain_core.tools import StructuredTool
from pydantic import ValidationError
from tests.services.test_embeddings import FakeEmbeddingsClient, RecordingFactory
from tests.tools.profile_tool_helpers import preferences, profile

VECTOR_DIM = ALLOWED_EMBEDDING_DIMENSIONS
SENTINEL_API_KEY = "sentinel-match-jobs-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-match-never-emit"
SENTINEL_BASE_URL = "https://provider.example/v1"


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    database = create_session_manager(tmp_path / "match-jobs.db")
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


def _settings() -> Settings:
    return load_settings(
        environ={
            "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
            "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
            "SHOPAIKEY_BASE_URL": SENTINEL_BASE_URL,
            "EMBEDDING_MODEL": ALLOWED_EMBEDDING_MODEL,
            "EMBEDDING_DIMENSIONS": str(ALLOWED_EMBEDDING_DIMENSIONS),
        }
    )


def _skill(
    *,
    key: str = "python",
    evidence: str = "Required: Python",
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.title(),
            "aliases": [],
            "category": None,
            "status": "verified",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _query_vector(seed: float = 0.01) -> list[float]:
    return [float(seed)] * VECTOR_DIM


class RecordingGraphClient:
    """Injectable graph client recording queries; optional failure injection."""

    def __init__(
        self,
        *,
        vector_rows: list[dict[str, Any]] | None = None,
        fetch_error: BaseException | None = None,
    ) -> None:
        self.vector_rows = list(vector_rows or [])
        self.fetch_error = fetch_error
        self.fetch_queries: list[tuple[str, Mapping[str, Any]]] = []
        self.run_queries: list[tuple[str, Mapping[str, Any]]] = []

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        params = dict(parameters) if parameters is not None else {}
        self.run_queries.append((query, params))

    async def fetch_records(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = dict(parameters) if parameters is not None else {}
        self.fetch_queries.append((query, params))
        if self.fetch_error is not None:
            raise self.fetch_error
        if "RELATED_TO" in query:
            return []
        if "vector.queryNodes" in query or "vector.similarity.cosine" in query:
            rows = list(self.vector_rows)
            job_ids = params.get("job_ids")
            if isinstance(job_ids, list) and job_ids:
                allowed = {str(item) for item in job_ids}
                rows = [
                    row
                    for row in rows
                    if str(row.get("job_id", "")) in allowed
                ]
            k = params.get("k")
            if isinstance(k, int) and k > 0:
                rows = rows[:k]
            return rows
        return []


async def _seed_job(
    database: DatabaseSessionManager,
    *,
    raw: str,
    title: str = "Engineer",
    quality: str = "full",
    record_status: str = RecordStatus.ACTIVE.value,
) -> UUID:
    extraction = JobPostExtraction.model_validate(
        {
            "title": title,
            "company": "Acme",
            "summary": "Build systems and ship APIs for the platform.",
            "responsibilities": ["Ship features", "Own production services"],
            "required_skills": [_skill()],
            "preferred_skills": [],
            "seniority": "mid",
            "min_experience_years": 3.0,
            "max_experience_years": None,
            "location": "Remote",
            "work_mode": "remote",
            "employment_type": "full_time",
            "education_requirements": [],
            "language_requirements": [],
            "job_family": "engineering",
            "extraction_confidence": 0.9,
            "jd_quality": quality,
        }
    )
    extraction, assessment = apply_jd_quality(extraction)
    job_id = new_uuid()
    now = utc_now()
    reasons = list(assessment.reasons) if assessment.reasons else None
    async with database.session_scope() as session:
        row = JobPost(
            id=job_id,
            source_type=JobSourceType.TEXT.value,
            source_url=None,
            raw_content=raw,
            raw_content_hash=hash_canonical_text(raw),
            normalized_key=None,
            extracted_json=extraction.model_dump(mode="json"),
            quality_reasons=reasons,
            score_cache=None,
            processing_status=ProcessingStatus.PROCESSED.value,
            jd_quality=(
                extraction.jd_quality.value
                if hasattr(extraction.jd_quality, "value")
                else str(extraction.jd_quality)
            ),
            graph_sync_status=GraphSyncStatus.SYNCED.value,
            record_status=record_status,
            duplicate_of_job_id=None,
            embedding_model=ALLOWED_EMBEDDING_MODEL,
            embedding_dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
    return job_id


async def _seed_profile(database: DatabaseSessionManager) -> None:
    async with database.session_scope() as session:
        await ProfileRepository(session).replace(profile())
        await PreferencesRepository(session).replace(preferences())


def _service(
    database: DatabaseSessionManager,
    graph: RecordingGraphClient,
) -> tuple[MatchJobsToolService, RecordingFactory, FakeEmbeddingsClient]:
    factory = RecordingFactory()
    client = FakeEmbeddingsClient()
    embedding = JobEmbeddingService.from_settings(
        _settings(),
        embeddings_factory=factory,
    )
    service = MatchJobsToolService(
        database,
        graph,
        embedding,
        embeddings_client=client,
    )
    return service, factory, client


def test_match_jobs_input_limits() -> None:
    MatchJobsInput()
    MatchJobsInput(limit=10)
    MatchJobsInput(saved_job_ids=[uuid4()])
    with pytest.raises(ValidationError):
        MatchJobsInput(limit=0)
    with pytest.raises(ValidationError):
        MatchJobsInput(limit=MAX_MATCH_RESULTS + 1)
    with pytest.raises(ValidationError):
        MatchJobsInput(saved_job_ids=[])
    too_many = [uuid4() for _ in range(MAX_SAVED_JOB_IDS + 1)]
    with pytest.raises(ValidationError):
        MatchJobsInput(saved_job_ids=too_many)
    dup = uuid4()
    with pytest.raises(ValidationError):
        MatchJobsInput(saved_job_ids=[dup, dup])


@pytest.mark.asyncio
async def test_no_profile_guidance_zero_side_effects(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        graph = RecordingGraphClient(vector_rows=[])
        service, factory, client = _service(database, graph)
        result = await service.execute()
        data = json.loads(result)
        assert data["ok"] is True
        assert data["status"] == "profile_required"
        assert data["code"] == "PROFILE_REQUIRED"
        assert data["count"] == 0
        assert data["results"] == []
        assert data["limit"] == DEFAULT_MATCH_LIMIT
        assert PROFILE_REQUIRED_GUIDANCE in data["guidance"]
        assert service.embed_calls == 0
        assert service.graph_retrieve_calls == 0
        assert service.cache_write_calls == 0
        assert factory.calls == []
        assert client.calls == []
        assert graph.fetch_queries == []
        assert graph.run_queries == []


@pytest.mark.asyncio
async def test_match_success_default_limit_and_cache(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        await _seed_profile(database)
        job_ids = [
            await _seed_job(
                database,
                raw=f"Matchable JD content number {i} unique body text.",
                title=f"Role {i}",
            )
            for i in range(3)
        ]
        graph = RecordingGraphClient(
            vector_rows=[
                {"job_id": str(job_ids[i]), "score": 0.9 - i * 0.1}
                for i in range(3)
            ]
        )
        service, factory, client = _service(database, graph)
        result = await service.execute()
        data = json.loads(result)
        assert data["ok"] is True
        assert data["status"] == "matched"
        assert data["count"] == 3
        assert data["limit"] == DEFAULT_MATCH_LIMIT
        assert len(data["results"]) == 3
        assert all(item["final_score"] is not None for item in data["results"])
        assert service.embed_calls == 1
        assert service.graph_retrieve_calls == 1
        assert service.cache_write_calls == 3
        assert factory.calls or client.calls  # provider path exercised via fake

        # query_jobs surfaces validated score details only
        query = QueryJobsToolService(database)
        qdata = json.loads(await query.execute(job_id=job_ids[0]))
        assert "score_cache" in qdata["jobs"][0]
        assert qdata["jobs"][0]["score_cache"]["job_id"] == str(job_ids[0])
        assert "raw_content" not in qdata["jobs"][0]


@pytest.mark.asyncio
async def test_result_limit_cap_and_saved_id_filter(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        await _seed_profile(database)
        job_ids = [
            await _seed_job(
                database,
                raw=f"Limit filter JD body {i} with unique content padding.",
                title=f"Limited {i}",
            )
            for i in range(5)
        ]
        graph = RecordingGraphClient(
            vector_rows=[
                {"job_id": str(jid), "score": 0.95 - idx * 0.05}
                for idx, jid in enumerate(job_ids)
            ]
        )
        service, _, _ = _service(database, graph)
        limited = json.loads(await service.execute(limit=2))
        assert limited["ok"] is True
        assert limited["count"] == 2
        assert limited["limit"] == 2
        assert len(limited["results"]) == 2

        subset = [job_ids[0], job_ids[2]]
        filtered = json.loads(await service.execute(saved_job_ids=subset))
        assert filtered["ok"] is True
        returned = {item["job_id"] for item in filtered["results"]}
        assert returned <= {str(x) for x in subset}


@pytest.mark.asyncio
async def test_neo4j_failure_no_matches(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        await _seed_profile(database)
        graph = RecordingGraphClient(
            fetch_error=GraphError(GraphErrorCode.UNAVAILABLE),
        )
        service, _, _ = _service(database, graph)
        result = await service.execute()
        assert result.startswith("ERROR:")
        assert "ok" in result and "false" in result
        assert "NEO4J" in result.upper() or "UNAVAILABLE" in result.upper()
        # No success payload with matches
        assert '"results":[' not in result or '"results":[]' in result
        assert service.cache_write_calls == 0


@pytest.mark.asyncio
async def test_tool_name_and_registry_seven(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        graph = RecordingGraphClient()
        service, _, _ = _service(database, graph)
        tool = create_match_jobs_tool(service)
        assert tool.name == "match_jobs"
        tools = [
            StructuredTool.from_function(
                func=lambda: "ok", name=name, description=name
            )
            for name in sorted(PRODUCTION_TOOL_NAMES - {"match_jobs"})
        ]
        tools.append(tool)
        registry = create_production_registry(tools)
        assert len(registry) == 7
        assert "match_jobs" in registry
        assert registry.names() == PRODUCTION_TOOL_NAMES


@pytest.mark.asyncio
async def test_duplicate_match_calls_are_idempotent_shape(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        await _seed_profile(database)
        job_id = await _seed_job(
            database,
            raw="Duplicate call JD content with enough unique text body.",
            title="Dup Role",
        )
        graph = RecordingGraphClient(
            vector_rows=[{"job_id": str(job_id), "score": 0.88}]
        )
        service, _, _ = _service(database, graph)
        first = json.loads(await service.execute())
        second = json.loads(await service.execute())
        assert first["ok"] is True and second["ok"] is True
        assert first["results"][0]["job_id"] == second["results"][0]["job_id"]
        assert first["results"][0]["final_score"] == second["results"][0]["final_score"]
        async with database.session_scope() as session:
            record = await JobPostRepository(session).get_by_id(job_id)
            assert record is not None
            assert record.score_cache is not None
            assert record.score_cache["final_score"] == first["results"][0]["final_score"]


def test_retrieval_bounds_constants_aligned() -> None:
    assert DEFAULT_MATCH_LIMIT == 10
    assert MAX_SAVED_JOB_IDS == MAX_RETRIEVAL_CANDIDATES == 50
    assert VECTOR_INDEX_NAME  # index identity exists for retrieval seam
