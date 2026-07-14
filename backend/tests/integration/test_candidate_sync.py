"""Integration tests for idempotent Candidate/Skill Neo4j sync (03A).

Uses a deterministic fake async driver only — no live Neo4j required.
Optional live probe is covered by test_neo4j_setup when credentials exist.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph import sync_candidate as sync_mod
from app.graph.sync_candidate import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    CandidateSyncError,
    non_excluded_skills,
    sync_candidate,
)
from app.schemas.profile import CandidateProfile, parse_candidate_profile
from app.services.skill_normalization import SkillNormalizer

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


def _profile_with_skills(
    *,
    include_excluded: bool = True,
    unknown: bool = False,
) -> CandidateProfile:
    skills: list[dict[str, Any]] = [
        {
            "skill": {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["python3", "py"],
                "category": "language",
            },
            "confidence": 0.9,
            "proficiency": "advanced",
            "years": 4.0,
            "source": "cv",
            "excluded": False,
            "evidence": ["Python backend"],
        },
        {
            "skill": {
                "canonical_key": "fastapi",
                "display_name": "FastAPI",
                "aliases": ["fast api"],
                "category": "framework",
            },
            "confidence": 0.8,
            "proficiency": "intermediate",
            "years": 2.0,
            "source": "cv",
            "excluded": False,
            "evidence": ["Built APIs"],
        },
    ]
    if include_excluded:
        skills.append(
            {
                "skill": {
                    "canonical_key": "react",
                    "display_name": "React",
                    "aliases": ["reactjs"],
                    "category": "framework",
                },
                "confidence": 0.5,
                "proficiency": "beginner",
                "years": None,
                "source": "user_correction",
                "excluded": True,
                "evidence": ["User excluded React"],
            }
        )
    if unknown:
        skills.append(
            {
                "skill": {
                    "canonical_key": "obscure_lib",
                    "display_name": "Obscure Lib",
                    "aliases": [],
                    "category": None,
                },
                "confidence": 0.6,
                "proficiency": "unknown",
                "years": None,
                "source": "cv",
                "excluded": False,
                "evidence": ["Mentioned once"],
            }
        )
    return parse_candidate_profile(
        {
            "summary": "Backend engineer",
            "current_title": "Backend Engineer",
            "total_experience_years": 4.0,
            "skills": skills,
            "experiences": [
                {
                    "title": "Engineer",
                    "company": "Co",
                    "start_date_text": "2020",
                    "end_date_text": "present",
                    "summary": "APIs",
                }
            ],
            "education": [
                {
                    "institution": "U",
                    "degree": "BSc",
                    "field": "CS",
                    "graduation_year": 2019,
                }
            ],
            "languages": [{"name": "English", "proficiency": "fluent"}],
            "extraction_confidence": 0.8,
        }
    )


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------


def test_sync_merges_candidate_has_skill_and_seed_related() -> None:
    """Parameterized MERGE path: Candidate, HAS_SKILL, RELATED_TO from seed."""
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    profile = _profile_with_skills(include_excluded=True, unknown=True)
    updated = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    async def _body() -> None:
        await sync_candidate(
            driver,
            profile=profile,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    from tests.support.db_migration import run_async

    run_async(_body())

    joined = "\n".join(driver.queries)
    assert "MERGE (c:Candidate {id: $candidate_id})" in joined
    assert "HAS_SKILL" in joined
    assert "RELATED_TO" in joined
    assert "source_updated_at" in joined

    # Parameters carry runtime values — no interpolation of secrets/raw CV.
    assert driver.parameters
    first = driver.parameters[0]
    # Identity must come from the SQLite profile constant owner, not a local literal.
    assert first["candidate_id"] == CANDIDATE_PROFILE_ID
    assert first["candidate_id"] == "active"
    assert "2024-06-01" in first["source_updated_at"]

    # Collect skill rows from any params payload that includes them.
    skill_payloads: list[dict[str, Any]] = []
    for p in driver.parameters:
        if "skills" in p:
            skill_payloads = p["skills"]
            break
    keys = {row["skill"]["canonical_key"] for row in skill_payloads}
    assert "python" in keys
    assert "fastapi" in keys
    assert "obscure_lib" in keys
    # Excluded React must not be in HAS_SKILL payload.
    assert "react" not in keys

    related_payload: list[dict[str, Any]] = []
    for p in driver.parameters:
        if "related" in p:
            related_payload = p["related"]
            break
    pairs = {(e["from_key"], e["to_key"]) for e in related_payload}
    assert ("python", "fastapi") in pairs
    assert ("typescript", "react") in pairs
    # Unknown skill never invents RELATED_TO.
    assert not any(e["from_key"] == "obscure_lib" for e in related_payload)


def test_sync_omits_excluded_skills_only_in_sqlite_json() -> None:
    profile = _profile_with_skills(include_excluded=True)
    kept = non_excluded_skills(profile)
    assert all(not s.excluded for s in kept)
    assert {s.skill.canonical_key for s in kept} == {"python", "fastapi"}
    # Profile JSON still holds the exclusion for SQLite truth.
    assert any(s.excluded for s in profile.skills)


def test_sync_idempotent_repeated_identical_payload() -> None:
    """Re-running the same sync is safe: same parameterized statements."""
    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    profile = _profile_with_skills(include_excluded=True)
    updated = datetime(2024, 7, 1, tzinfo=UTC)

    async def _once() -> None:
        await sync_candidate(
            driver,
            profile=profile,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    from tests.support.db_migration import run_async

    run_async(_once())
    first_queries = list(driver.queries)
    first_params = [dict(p) for p in driver.parameters]
    driver.queries.clear()
    driver.parameters.clear()
    run_async(_once())
    assert driver.queries == first_queries
    assert driver.parameters == first_params
    # HAS_SKILL is cleared then rebuilt each time (idempotent rebuild).
    assert any("DELETE" in q and "HAS_SKILL" in q for q in first_queries)


def test_sync_failure_raises_neo4j_sync_failed_with_rebuild() -> None:
    driver = FakeNeo4jDriver(fail_on_run=True)
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    profile = _profile_with_skills(include_excluded=False)
    updated = datetime(2024, 1, 1, tzinfo=UTC)

    async def _body() -> None:
        with pytest.raises(CandidateSyncError) as ei:
            await sync_candidate(
                driver,
                profile=profile,
                source_updated_at=updated,
                normalizer=normalizer,
            )
        err = ei.value
        assert err.code == NEO4J_SYNC_FAILED
        assert err.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION
        assert "password" not in str(err).lower()

    from tests.support.db_migration import run_async

    run_async(_body())


def test_sync_source_has_no_raw_cv_and_uses_parameters() -> None:
    src = inspect.getsource(sync_mod)
    assert "NEO4J_SYNC_FAILED" in src
    assert "MERGE" in src
    assert "HAS_SKILL" in src
    assert "RELATED_TO" in src
    assert "source_updated_at" in src
    assert "session.run" in src
    # Parameter markers present; no f-string Cypher with profile fields.
    assert "$candidate_id" in src or "$candidate_id" in "".join(
        sync_mod.cypher_statement_templates()
    )
    assert "raw_cv" not in src
    assert "raw_pdf" not in src
    assert "extract_text" not in src
    # No secrets / password interpolation.
    assert "NEO4J_PASSWORD" not in src
    assert "get_secret_value" not in src


def test_candidate_sync_reuses_profile_id_constant_owner() -> None:
    """Candidate id must bind CANDIDATE_PROFILE_ID, not a local literal."""
    src = inspect.getsource(sync_mod)
    assert "CANDIDATE_PROFILE_ID" in src
    assert "_CANDIDATE_ID" not in src
    # No local string literal for the singleton id in the production owner.
    assert ' = "active"' not in src
    assert " = 'active'" not in src

    driver = FakeNeo4jDriver()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    profile = _profile_with_skills(include_excluded=False)
    updated = datetime(2024, 8, 1, tzinfo=UTC)

    async def _body() -> None:
        await sync_candidate(
            driver,
            profile=profile,
            source_updated_at=updated,
            normalizer=normalizer,
        )

    from tests.support.db_migration import run_async

    run_async(_body())
    assert driver.parameters
    bound_id = driver.parameters[0]["candidate_id"]
    assert bound_id == CANDIDATE_PROFILE_ID
    assert sync_mod.CANDIDATE_PROFILE_ID is CANDIDATE_PROFILE_ID
