"""SQLite-to-fake-graph Job synchronization integration tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, OutboxStatus, ProcessingStatus, RecordStatus
from app.db.session import create_session_manager
from app.graph.candidate_sync import process_candidate_sync_outbox
from app.graph.job_sync import JOB_UPSERT_OPERATION, process_job_sync_outbox
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.job_post import JobPostExtraction
from app.services.embeddings import (
    JOB_TEXT_REPRESENTATION_VERSION,
    EmbeddingVector,
    JobEmbeddingResult,
)
from app.services.jd_source import hash_canonical_text


class StatefulJobGraph:
    """Semantic fake: MERGE Job/Skill/JobFamily and replace owned edges."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.jobs: dict[str, dict[str, object]] = {}
        self.skills: dict[str, dict[str, object]] = {}
        self.families: dict[str, dict[str, object]] = {}
        self.requires: set[tuple[str, str]] = set()
        self.prefers: set[tuple[str, str]] = set()
        self.in_family: set[tuple[str, str]] = set()
        self.related_to: set[tuple[str, str]] = set()
        self.query_count = 0

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        if self.fail:
            raise RuntimeError("neo4j unavailable")
        assert "RELATED_TO" not in query
        params = dict(parameters or {})
        # Candidate projector path
        if "Candidate" in query and "HAS_SKILL" in query:
            return
        self.query_count += 1
        job_id = str(params["job_id"])
        self.jobs[job_id] = {
            "id": job_id,
            "title": params.get("title"),
            "company": params.get("company"),
            "location": params.get("location"),
            "work_mode": params.get("work_mode"),
            "seniority": params.get("seniority"),
            "quality": params.get("quality"),
            "embedding": list(params.get("embedding") or []),
        }
        # Replace owned edges for this Job only.
        self.requires = {e for e in self.requires if e[0] != job_id}
        self.prefers = {e for e in self.prefers if e[0] != job_id}
        self.in_family = {e for e in self.in_family if e[0] != job_id}

        for skill in params.get("required_skills") or []:
            key = str(skill["canonical_key"])
            self._merge_skill(skill)
            self.requires.add((job_id, key))
        for skill in params.get("preferred_skills") or []:
            key = str(skill["canonical_key"])
            self._merge_skill(skill)
            self.prefers.add((job_id, key))
        for family in params.get("job_families") or []:
            fkey = str(family["canonical_key"])
            existing = self.families.get(fkey, {})
            self.families[fkey] = {
                "canonical_key": fkey,
                "display_name": family.get("display_name")
                or existing.get("display_name"),
            }
            self.in_family.add((job_id, fkey))

    def _merge_skill(self, skill: Mapping[str, Any]) -> None:
        key = str(skill["canonical_key"])
        existing = self.skills.get(key, {})
        old_aliases = list(existing.get("aliases") or [])  # type: ignore[arg-type]
        new_aliases = list(skill.get("aliases") or [])
        union: list[str] = list(old_aliases)
        for alias in new_aliases:
            if alias not in union:
                union.append(str(alias))
        self.skills[key] = {
            "canonical_key": key,
            "display_name": skill.get("display_name") or existing.get("display_name"),
            "aliases": union,
            "category": skill.get("category", existing.get("category")),
            "status": skill.get("status") or existing.get("status"),
        }


class FakeEmbeddingService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def embed_job(self, job: JobPostExtraction) -> JobEmbeddingResult:
        self.calls += 1
        if self.fail:
            from app.services.embeddings import JobEmbeddingError, JobEmbeddingErrorCode

            raise JobEmbeddingError(JobEmbeddingErrorCode.PROVIDER_ERROR)
        return JobEmbeddingResult(
            vectors=(
                EmbeddingVector(index=0, values=tuple(0.02 for _ in range(1536))),
            ),
            model=ALLOWED_EMBEDDING_MODEL,
            dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            representation_version=JOB_TEXT_REPRESENTATION_VERSION,
        )


def _skill(key: str, *, aliases: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": "CI/CD" if key == "ci_cd" else key,
            "aliases": list(aliases),
            "category": None,
            "status": "verified",
            "confidence": 0.8,
            "evidence": [f"Evidence for {key}"],
        },
        "confidence": 0.8,
        "evidence": [f"Evidence for {key}"],
    }


def _extraction(**overrides: Any) -> JobPostExtraction:
    data: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build systems.",
        "responsibilities": ["Ship features"],
        "required_skills": [_skill("python", aliases=["Py"])],
        "preferred_skills": [_skill("go")],
        "seniority": "mid",
        "min_experience_years": None,
        "max_experience_years": None,
        "location": "Remote",
        "work_mode": "remote",
        "employment_type": "full_time",
        "education_requirements": [],
        "language_requirements": [],
        "salary_text": None,
        "job_family": "Engineering",
        "extraction_confidence": 0.8,
        "jd_quality": "partial",
    }
    data.update(overrides)
    return JobPostExtraction.model_validate(data)


async def _create_eligible_job(
    db: Any,
    *,
    extraction: JobPostExtraction | None = None,
    suffix: str = "1",
) -> UUID:
    extraction = extraction or _extraction()
    raw = f"Integration job body {suffix} with unique content."
    async with db.session_scope() as session:
        jobs = JobPostRepository(session)
        created = await jobs.create_received(
            source_type="text",
            raw_content=raw,
            raw_content_hash=hash_canonical_text(raw),
        )
        job_id = created.record.id
        await jobs.mark_processing(job_id)
        await jobs.mark_processed(
            job_id,
            extraction=extraction,
            quality_reasons=["partial"] if extraction.jd_quality.value != "full" else None,
            force_new=True,
        )
        await jobs.set_embedding_identity(
            job_id,
            embedding_model=ALLOWED_EMBEDDING_MODEL,
            embedding_dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
        )
        await jobs.set_graph_sync_status(job_id, status=GraphSyncStatus.PENDING)
        await GraphOutboxRepository(session).enqueue(
            operation=JOB_UPSERT_OPERATION,
            entity_id=str(job_id),
            payload={"job_id": str(job_id)},
            requeue_existing=True,
        )
        return job_id


@pytest.mark.asyncio
async def test_successive_job_updates_replay_to_exact_current_graph(
    tmp_path: Path,
) -> None:
    db = create_session_manager(tmp_path / "job-integration.db")
    await db.create_all()
    graph = StatefulJobGraph()
    emb = FakeEmbeddingService()
    try:
        job_id = await _create_eligible_job(
            db,
            extraction=_extraction(
                required_skills=[_skill("python"), _skill("obsolete")],
                preferred_skills=[],
            ),
            suffix="s1",
        )
        assert await process_job_sync_outbox(db, graph, emb) == 1
        assert graph.requires == {(str(job_id), "python"), (str(job_id), "obsolete")}
        assert len(graph.jobs[str(job_id)]["embedding"]) == 1536  # type: ignore[arg-type]

        async with db.session_scope() as session:
            from app.db.models.jobs import JobPost

            row = await session.get(JobPost, job_id)
            assert row is not None
            row.extracted_json = _extraction(
                required_skills=[_skill("python"), _skill("ci_cd", aliases=["CI/CD"])],
                preferred_skills=[_skill("rust")],
                job_family="Platform",
            ).model_dump(mode="json")
            await session.flush()
            await GraphOutboxRepository(session).enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(job_id),
                payload={"job_id": str(job_id)},
                requeue_existing=True,
            )

        assert await process_job_sync_outbox(db, graph, emb) == 1
        assert graph.jobs.keys() == {str(job_id)}
        assert graph.requires == {(str(job_id), "python"), (str(job_id), "ci_cd")}
        assert graph.prefers == {(str(job_id), "rust")}
        assert (str(job_id), "platform") in graph.in_family
        assert "obsolete" not in {e[1] for e in graph.requires}
        assert graph.skills["ci_cd"]["aliases"] == ["CI/CD"]
        assert graph.related_to == set()
        assert graph.query_count == 2

        async with db.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(job_id)
            outbox = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert job is not None
            assert job.graph_sync_status == GraphSyncStatus.SYNCED.value
            assert job.processing_status == ProcessingStatus.PROCESSED.value
            assert outbox is not None
            assert outbox.status == OutboxStatus.SYNCED.value
            assert outbox.payload == {"job_id": str(job_id)}
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_job_failure_preserves_sqlite_and_does_not_affect_candidate(
    tmp_path: Path,
) -> None:
    db = create_session_manager(tmp_path / "job-fail-isolation.db")
    await db.create_all()
    try:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                CandidateProfile.model_validate(
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
                                    "category": None,
                                    "status": "verified",
                                    "confidence": 0.9,
                                    "evidence": [],
                                },
                                "proficiency": "advanced",
                                "years": None,
                                "source": "cv",
                                "excluded": False,
                                "evidence": [],
                            }
                        ],
                        "experiences": [],
                        "education": [],
                        "languages": [],
                        "extraction_confidence": 0.8,
                    }
                )
            )

        class CandidateAwareGraph(StatefulJobGraph):
            def __init__(self) -> None:
                super().__init__(fail=True)
                self.candidates: set[str] = set()
                self.candidate_edges: set[tuple[str, str]] = set()

            async def run_query(
                self,
                query: str,
                parameters: Mapping[str, Any] | None = None,
            ) -> None:
                params = dict(parameters or {})
                if "Candidate" in query:
                    cid = str(params["candidate_id"])
                    self.candidates.add(cid)
                    self.candidate_edges = {
                        e for e in self.candidate_edges if e[0] != cid
                    }
                    for skill in params.get("skills") or []:
                        self.candidate_edges.add((cid, str(skill["canonical_key"])))
                    return
                await super().run_query(query, parameters)

        graph = CandidateAwareGraph()
        # Candidate projects successfully.
        assert await process_candidate_sync_outbox(db, graph) == 1
        assert graph.candidates == {"1"}
        assert graph.candidate_edges == {("1", "python")}

        job_id = await _create_eligible_job(db, suffix="fail-iso")
        assert await process_job_sync_outbox(db, graph, FakeEmbeddingService()) == 0

        async with db.session_scope() as session:
            job = await JobPostRepository(session).get_by_id(job_id)
            row = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION, str(job_id)
            )
            assert job is not None
            assert job.processing_status == ProcessingStatus.PROCESSED.value
            assert job.record_status == RecordStatus.ACTIVE.value
            assert job.graph_sync_status == GraphSyncStatus.FAILED.value
            assert row is not None
            assert row.status == OutboxStatus.FAILED.value

        # Candidate graph untouched by Job failure.
        assert graph.candidates == {"1"}
        assert graph.candidate_edges == {("1", "python")}
        assert graph.jobs == {}

        # Recovery path
        healthy = StatefulJobGraph()
        # Re-process candidate onto healthy graph for isolation check
        async with db.session_scope() as session:
            from app.db.base import SINGLETON_PK
            from app.repositories.graph_outbox import CANDIDATE_SYNC_OPERATION

            await GraphOutboxRepository(session).enqueue(
                operation=CANDIDATE_SYNC_OPERATION,
                entity_id=str(SINGLETON_PK),
                payload={"candidate_id": str(SINGLETON_PK)},
                requeue_existing=True,
            )
        assert await process_candidate_sync_outbox(db, healthy) == 1
        assert await process_job_sync_outbox(db, healthy, FakeEmbeddingService()) == 1
        assert str(job_id) in healthy.jobs
        assert healthy.related_to == set()
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_alias_union_across_job_projections(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "job-alias-union.db")
    await db.create_all()
    graph = StatefulJobGraph()
    try:
        j1 = await _create_eligible_job(
            db,
            extraction=_extraction(
                required_skills=[_skill("python", aliases=["Py"])],
                preferred_skills=[],
                job_family=None,
            ),
            suffix="alias-a",
        )
        j2 = await _create_eligible_job(
            db,
            extraction=_extraction(
                required_skills=[_skill("python", aliases=["Python3"])],
                preferred_skills=[],
                job_family=None,
            ),
            suffix="alias-b",
        )
        assert await process_job_sync_outbox(db, graph, FakeEmbeddingService()) == 2
        assert set(graph.skills["python"]["aliases"]) == {"Py", "Python3"}  # type: ignore[arg-type]
        assert graph.requires == {(str(j1), "python"), (str(j2), "python")}
        assert len(graph.jobs) == 2
    finally:
        await db.dispose()
