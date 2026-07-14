"""Integration tests for idempotent Job/Skill Neo4j sync (Plan 5 / 03A).

Uses a deterministic fake async driver only — no live Neo4j required.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.graph import sync_job as sync_mod
from app.graph import sync_shared as shared_mod
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    JobSyncError,
    sync_job,
)
from app.graph.sync_shared import (
    project_seed_skills_and_related,
    related_to_param_rows,
    seed_skill_param_rows,
)
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS
from app.schemas.jobs import parse_job_post_extraction
from app.services.skill_normalization import SkillNormalizer

from tests.support.db_migration import run_async

# ---------------------------------------------------------------------------
# Fake Neo4j driver (records parameterized Cypher)
# ---------------------------------------------------------------------------


class _FakeResult:
    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return []


class _FakeSession:
    def __init__(self, driver: FakeNeo4jDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        del kwargs
        if self._driver.fail_on_run:
            raise OSError("simulated neo4j write failure")
        self._driver.queries.append(query)
        self._driver.parameters.append(
            dict(parameters) if parameters is not None else {}
        )
        return _FakeResult()


class FakeNeo4jDriver:
    """Async-driver stand-in capturing Cypher + bound parameters."""

    def __init__(self, *, fail_on_run: bool = False) -> None:
        self.fail_on_run = fail_on_run
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.session_enter = 0
        self.session_exit = 0

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)


def _skills_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"


def _vector(seed: float = 0.01) -> list[float]:
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


def _extraction(*, unknown: bool = False):
    required: list[dict[str, Any]] = [
        {
            "skill": {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["python3", "py"],
                "category": "language",
            },
            "confidence": 0.91,
            "evidence": ["Required: Python 3+"],
        }
    ]
    preferred: list[dict[str, Any]] = [
        {
            "skill": {
                "canonical_key": "fastapi",
                "display_name": "FastAPI",
                "aliases": ["fast api"],
                "category": "framework",
            },
            "confidence": 0.7,
            "evidence": ["Preferred: FastAPI"],
        }
    ]
    if unknown:
        required.append(
            {
                "skill": {
                    "canonical_key": "obscure_lib",
                    "display_name": "Obscure Lib",
                    "aliases": [],
                    "category": None,
                },
                "confidence": 0.55,
                "evidence": ["Mentioned once"],
            }
        )
    return parse_job_post_extraction(
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "summary": "Build APIs.",
            "responsibilities": ["Design services"],
            "required_skills": required,
            "preferred_skills": preferred,
            "seniority": "mid",
            "min_experience_years": 3.0,
            "max_experience_years": 5.0,
            "location": "Berlin",
            "work_mode": "hybrid",
            "extraction_confidence": 0.85,
        }
    )


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------


def test_sync_merges_job_requires_prefers_and_seed_related() -> None:
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction(unknown=True)
    updated = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    job_id = "11111111-1111-4111-8111-111111111111"
    vector = _vector(0.02)

    async def _body() -> None:
        await sync_job(
            driver,
            job_id=job_id,
            extraction=extraction,
            jd_quality="full",
            embedding=vector,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    run_async(_body())

    joined = "\n".join(driver.queries)
    assert "MERGE (j:Job {id: $job_id})" in joined
    assert "REQUIRES" in joined
    assert "PREFERS" in joined
    assert "RELATED_TO" in joined
    assert "source_updated_at" in joined
    assert "REQUIRES|PREFERS" in joined  # scoped clear of this Job only

    first = driver.parameters[0]
    assert first["job_id"] == job_id
    assert first["title"] == "Backend Engineer"
    assert first["company"] == "Acme"
    assert first["location"] == "Berlin"
    assert first["work_mode"] == "hybrid"
    assert first["seniority"] == "mid"
    assert first["quality"] == "full"
    assert first["embedding"] == vector
    assert len(first["embedding"]) == LOCKED_EMBEDDING_DIMENSIONS
    assert all(isinstance(x, float) for x in first["embedding"])
    assert "2024-06-01" in first["source_updated_at"]

    requires = first["requires"]
    prefers = first["prefers"]
    req_keys = {row["skill"]["canonical_key"] for row in requires}
    pref_keys = {row["skill"]["canonical_key"] for row in prefers}
    assert "python" in req_keys
    assert "obscure_lib" in req_keys
    assert "fastapi" in pref_keys
    py = next(r for r in requires if r["skill"]["canonical_key"] == "python")
    assert py["rel"]["confidence"] == 0.91
    assert py["rel"]["evidence"] == ["Required: Python 3+"]

    # Seed RELATED_TO from shared projection; unknown skill invents no edge.
    related_payload: list[dict[str, Any]] = []
    for p in driver.parameters:
        if "related" in p:
            related_payload = p["related"]
            break
    pairs = {(e["from_key"], e["to_key"]) for e in related_payload}
    assert ("python", "fastapi") in pairs
    assert not any(e["from_key"] == "obscure_lib" for e in related_payload)
    assert not any(e["to_key"] == "obscure_lib" for e in related_payload)


def test_sync_idempotent_repeated_identical_payload() -> None:
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 7, 1, tzinfo=UTC)
    job_id = "22222222-2222-4222-8222-222222222222"
    vector = _vector(0.03)

    async def _once() -> None:
        await sync_job(
            driver,
            job_id=job_id,
            extraction=extraction,
            jd_quality="partial",
            embedding=vector,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    run_async(_once())
    first_queries = list(driver.queries)
    first_params = [dict(p) for p in driver.parameters]
    driver.queries.clear()
    driver.parameters.clear()
    run_async(_once())
    assert driver.queries == first_queries
    assert driver.parameters == first_params
    assert any("DELETE" in q and "REQUIRES|PREFERS" in q for q in first_queries)


def test_sync_failure_raises_neo4j_sync_failed_with_rebuild() -> None:
    driver = FakeNeo4jDriver(fail_on_run=True)
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 1, 1, tzinfo=UTC)

    async def _body() -> None:
        with pytest.raises(JobSyncError) as ei:
            await sync_job(
                driver,
                job_id="33333333-3333-4333-8333-333333333333",
                extraction=extraction,
                jd_quality="full",
                embedding=_vector(),
                source_updated_at=updated,
                normalizer=normalizer,
            )
        err = ei.value
        assert err.code == NEO4J_SYNC_FAILED
        assert err.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION
        assert "password" not in str(err).lower()
        assert "raw_content" not in str(err).lower()

    run_async(_body())


def test_sync_rejects_non_finite_or_wrong_dimension_embedding() -> None:
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 1, 1, tzinfo=UTC)

    async def _short() -> None:
        with pytest.raises(JobSyncError) as ei:
            await sync_job(
                driver,
                job_id="id",
                extraction=extraction,
                jd_quality="full",
                embedding=[0.1, 0.2],
                source_updated_at=updated,
                normalizer=normalizer,
            )
        err = ei.value
        assert err.code == NEO4J_SYNC_FAILED
        # Sanitized: no vector length/provider detail in the public message.
        assert "1536" not in str(err)
        assert "DIMENSION" not in str(err)
        assert "MALFORMED" not in str(err)

    async def _nan() -> None:
        bad = _vector()
        bad[0] = float("nan")
        with pytest.raises(JobSyncError) as ei:
            await sync_job(
                driver,
                job_id="id",
                extraction=extraction,
                jd_quality="full",
                embedding=bad,
                source_updated_at=updated,
                normalizer=normalizer,
            )
        assert ei.value.code == NEO4J_SYNC_FAILED

    run_async(_short())
    run_async(_nan())
    assert driver.queries == []
    assert driver.session_enter == 0


def test_sync_rejects_unscorable_and_unknown_quality_with_zero_graph_io() -> None:
    """Non-scorable qualities must not open a session or run Cypher."""
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 1, 1, tzinfo=UTC)
    vector = _vector()

    for quality in ("unscorable", "unknown_quality", "failed"):
        driver.queries.clear()
        driver.parameters.clear()
        driver.session_enter = 0

        async def _body(q: str = quality) -> None:
            with pytest.raises(JobSyncError) as ei:
                await sync_job(
                    driver,
                    job_id="44444444-4444-4444-8444-444444444444",
                    extraction=extraction,
                    jd_quality=q,
                    embedding=vector,
                    source_updated_at=updated,
                    normalizer=normalizer,
                )
            assert ei.value.code == NEO4J_SYNC_FAILED
            assert "full" in str(ei.value).lower() or "partial" in str(ei.value).lower()

        run_async(_body())
        assert driver.queries == [], f"quality={quality!r} ran graph statements"
        assert driver.session_enter == 0, f"quality={quality!r} opened a session"


def test_sync_accepts_full_and_partial_quality() -> None:
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 1, 1, tzinfo=UTC)

    for quality in ("full", "partial"):
        driver = FakeNeo4jDriver()

        async def _body(q: str = quality) -> None:
            await sync_job(
                driver,
                job_id="55555555-5555-4555-8555-555555555555",
                extraction=extraction,
                jd_quality=q,
                embedding=_vector(),
                source_updated_at=updated,
                normalizer=normalizer,
            )

        run_async(_body())
        assert driver.queries, f"quality={quality!r} should project"
        assert driver.session_enter >= 1
        assert driver.parameters[0]["quality"] == quality


def test_shared_embedding_validator_is_production_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sync_job must call shared validate_finite_vector, not a local copy."""
    src = inspect.getsource(sync_mod)
    assert "validate_finite_vector" in src
    assert "_validate_embedding" not in src
    assert "app.schemas.embeddings" in src or "validate_finite_vector" in src

    from app.schemas import embeddings as emb_mod

    calls: list[Any] = []
    original = emb_mod.validate_finite_vector

    def _spy(vec: Any) -> list[float]:
        calls.append(vec)
        return original(vec)

    monkeypatch.setattr(sync_mod, "validate_finite_vector", _spy)

    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    extraction = _extraction()
    updated = datetime(2024, 1, 1, tzinfo=UTC)
    vector = _vector(0.04)

    async def _ok() -> None:
        await sync_job(
            driver,
            job_id="66666666-6666-4666-8666-666666666666",
            extraction=extraction,
            jd_quality="full",
            embedding=vector,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    run_async(_ok())
    assert len(calls) == 1
    assert calls[0] == vector
    assert driver.queries

    # Invalid vector still hits the shared owner and never opens a session.
    driver2 = FakeNeo4jDriver()
    calls.clear()

    async def _bad() -> None:
        with pytest.raises(JobSyncError) as ei:
            await sync_job(
                driver2,
                job_id="id",
                extraction=extraction,
                jd_quality="full",
                embedding=[0.1],
                source_updated_at=updated,
                normalizer=normalizer,
            )
        assert ei.value.code == NEO4J_SYNC_FAILED

    run_async(_bad())
    assert len(calls) == 1
    assert driver2.queries == []
    assert driver2.session_enter == 0


def test_seed_projection_works_without_candidate() -> None:
    """Approved seed Skill/RELATED_TO can project with no Candidate present."""
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    seeds = seed_skill_param_rows(normalizer)
    related = related_to_param_rows(normalizer)
    assert seeds
    assert related

    async def _body() -> None:
        async with driver.session() as session:
            await project_seed_skills_and_related(
                session,
                seed_skills=seeds,
                related=related,
            )

    run_async(_body())
    joined = "\n".join(driver.queries)
    assert "RELATED_TO" in joined
    assert "Candidate" not in joined
    assert "HAS_SKILL" not in joined


def test_shared_constants_not_copied_between_owners() -> None:
    assert sync_mod.NEO4J_SYNC_FAILED is shared_mod.NEO4J_SYNC_FAILED
    assert sync_mod.NEO4J_REBUILD_INSTRUCTION is shared_mod.NEO4J_REBUILD_INSTRUCTION
    # Candidate re-exports the same shared objects (single owner).
    from app.graph import sync_candidate as cand

    assert cand.NEO4J_SYNC_FAILED is shared_mod.NEO4J_SYNC_FAILED
    assert cand.NEO4J_REBUILD_INSTRUCTION is shared_mod.NEO4J_REBUILD_INSTRUCTION


def test_sync_source_uses_parameters_no_raw_jd() -> None:
    src = inspect.getsource(sync_mod)
    assert "NEO4J_SYNC_FAILED" in src
    assert "MERGE" in src
    assert "REQUIRES" in src
    assert "PREFERS" in src
    assert "RELATED_TO" in src
    assert "source_updated_at" in src
    assert "session.run" in src
    templates = "".join(sync_mod.cypher_statement_templates())
    assert "$job_id" in src or "$job_id" in templates
    assert "raw_content" not in src
    assert "NEO4J_PASSWORD" not in src
    assert "get_secret_value" not in src
    assert "commit(" not in src
