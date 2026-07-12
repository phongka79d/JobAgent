"""Unit tests for bounded read-only query_jobs tool."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.db.base import new_uuid, utc_now
from app.db.enums import (
    GraphSyncStatus,
    JobSourceType,
    ProcessingStatus,
    RecordStatus,
)
from app.db.models.jobs import JobPost
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.job_posts import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    JobPostRepository,
)
from app.schemas.job_post import JobPostExtraction
from app.schemas.matching import MATCH_RESULT_CONTRACT_VERSION, MatchResult
from app.schemas.score_breakdown import COMPONENT_ORDER
from app.services.jd_quality import apply_jd_quality
from app.services.jd_source import hash_canonical_text
from app.tools.query_jobs import (
    QueryJobsInput,
    QueryJobsToolService,
    create_query_jobs_tool,
)
from pydantic import ValidationError


def _valid_score_cache(job_id: object, *, score: float = 0.82) -> dict[str, Any]:
    """Bounded versioned MatchResult payload suitable for score_cache."""
    components = [
        {
            "name": name.value,
            "available": True,
            "value": 0.8,
            "effective_weight": weight,
        }
        for name, weight in zip(
            COMPONENT_ORDER,
            (0.30, 0.40, 0.10, 0.10, 0.05, 0.05),
            strict=True,
        )
    ]
    return MatchResult.model_validate(
        {
            "job_id": str(job_id),
            "title": "Staff Engineer",
            "company": "Acme",
            "location": "Remote",
            "work_mode": "remote",
            "final_score": score,
            "quality": "full",
            "components": components,
            "matched_required_skills": [],
            "related_skills": [],
            "missing_required_skills": [],
            "explanation_lines": ["Semantic similarity available"],
            "source_url": None,
            "seed_config_version": "hybrid_seed_v1",
            "contract_version": MATCH_RESULT_CONTRACT_VERSION,
        }
    ).model_dump(mode="json")


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    database = create_session_manager(tmp_path / "query-jobs.db")
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


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
            "status": "provisional",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


async def _seed_job(
    database: DatabaseSessionManager,
    *,
    raw: str,
    title: str = "Engineer",
    company: str = "Acme",
    location: str = "Remote",
    quality: str = "full",
    record_status: str = RecordStatus.ACTIVE.value,
    score_cache: dict[str, Any] | None = None,
) -> object:
    extraction = JobPostExtraction.model_validate(
        {
            "title": title,
            "company": company,
            "summary": "Build systems and ship APIs for the platform.",
            "responsibilities": ["Ship features", "Own production services"],
            "required_skills": [_skill()],
            "preferred_skills": [],
            "seniority": "mid",
            "min_experience_years": 3.0,
            "max_experience_years": None,
            "location": location,
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
            score_cache=score_cache,
            processing_status=ProcessingStatus.PROCESSED.value,
            jd_quality=(
                extraction.jd_quality.value
                if hasattr(extraction.jd_quality, "value")
                else str(extraction.jd_quality)
            ),
            graph_sync_status=GraphSyncStatus.PENDING.value,
            record_status=record_status,
            duplicate_of_job_id=None,
            embedding_model=None,
            embedding_dimensions=None,
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return job_id


def test_query_jobs_input_rejects_id_plus_filters() -> None:
    with pytest.raises(ValidationError):
        QueryJobsInput(
            job_id=uuid4(),
            processing_status="processed",
        )
    QueryJobsInput(job_id=uuid4())
    QueryJobsInput(record_status="active", limit=10)
    with pytest.raises(ValidationError):
        QueryJobsInput(limit=0)
    with pytest.raises(ValidationError):
        QueryJobsInput(limit=MAX_LIST_LIMIT + 1)


@pytest.mark.asyncio
async def test_query_by_id_returns_compact_view(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        job_id = await _seed_job(
            database,
            raw="Unique raw JD content that must never appear in tool output.",
            title="Staff Engineer",
            score_cache=None,
        )
        cache = _valid_score_cache(job_id, score=0.82)
        async with database.session_scope() as session:
            await JobPostRepository(session).set_score_cache(job_id, cache)
        service = QueryJobsToolService(database)
        result = await service.execute(job_id=job_id)
        data = json.loads(result)
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["limit"] == 1
        job = data["jobs"][0]
        assert job["job_id"] == str(job_id)
        assert job["display"]["title"] == "Staff Engineer"
        assert job["score_cache"]["final_score"] == 0.82
        assert job["score_cache"]["contract_version"] == MATCH_RESULT_CONTRACT_VERSION
        blob = result.lower()
        assert "unique raw jd content" not in blob
        assert "raw_content" not in blob
        assert "raw_content_hash" not in blob
        assert "error_code" not in blob
        assert "error_message" not in blob
        assert "embedding_model" not in blob
        assert "embedding_dimensions" not in blob


@pytest.mark.asyncio
async def test_query_missing_id(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        service = QueryJobsToolService(database)
        result = await service.execute(job_id=uuid4())
        assert "JOB_NOT_FOUND" in result


@pytest.mark.asyncio
async def test_filter_mode_default_limit_and_cap(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        for i in range(12):
            await _seed_job(
                database,
                raw=f"Seed JD number {i} with enough unique content for hash {i}.",
                title=f"Role {i}",
            )
        service = QueryJobsToolService(database)
        default = json.loads(await service.execute())
        assert default["ok"] is True
        assert default["limit"] == DEFAULT_LIST_LIMIT
        assert default["count"] == DEFAULT_LIST_LIMIT
        assert len(default["jobs"]) == DEFAULT_LIST_LIMIT

        capped = json.loads(await service.execute(limit=MAX_LIST_LIMIT))
        assert capped["limit"] == MAX_LIST_LIMIT
        assert capped["count"] == 12

        tool = create_query_jobs_tool(service)
        with pytest.raises(ValidationError):
            await tool.ainvoke({"limit": MAX_LIST_LIMIT + 1})


@pytest.mark.asyncio
async def test_filter_by_record_status(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        active_id = await _seed_job(
            database,
            raw="Active job content for filter test one.",
            title="Active Role",
            record_status=RecordStatus.ACTIVE.value,
        )
        await _seed_job(
            database,
            raw="Ignored job content for filter test two.",
            title="Ignored Role",
            record_status=RecordStatus.IGNORED_DUPLICATE.value,
        )
        service = QueryJobsToolService(database)
        data = json.loads(
            await service.execute(record_status=RecordStatus.ACTIVE.value)
        )
        assert data["count"] == 1
        assert data["jobs"][0]["job_id"] == str(active_id)
        assert data["jobs"][0]["record_status"] == "active"
        assert "score_cache" not in data["jobs"][0]


@pytest.mark.asyncio
async def test_score_cache_never_computed(tmp_path: Path) -> None:
    """query_jobs may surface existing score_cache but must not invent scores."""
    async with temporary_db(tmp_path) as database:
        job_id = await _seed_job(
            database,
            raw="No score cache on this job row content body.",
            title="Unscored",
            score_cache=None,
        )
        service = QueryJobsToolService(database)
        data = json.loads(await service.execute(job_id=job_id))
        assert "score_cache" not in data["jobs"][0]
        async with database.session_scope() as session:
            record = await JobPostRepository(session).get_by_id(job_id)
            assert record is not None
            assert record.score_cache is None


@pytest.mark.asyncio
async def test_invalid_score_cache_not_exposed(tmp_path: Path) -> None:
    """Malformed/stale score_cache is omitted; never returned unvalidated."""
    async with temporary_db(tmp_path) as database:
        job_id = await _seed_job(
            database,
            raw="Job with invalid score cache blob that must stay hidden.",
            title="Cached Bad",
            score_cache={"overall": 0.99, "raw_jd": "LEAK"},
        )
        service = QueryJobsToolService(database)
        data = json.loads(await service.execute(job_id=job_id))
        assert "score_cache" not in data["jobs"][0]
        assert "LEAK" not in json.dumps(data)


@pytest.mark.asyncio
async def test_tool_name_is_query_jobs(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        tool = create_query_jobs_tool(QueryJobsToolService(database))
        assert tool.name == "query_jobs"
