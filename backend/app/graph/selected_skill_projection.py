"""Read-only exact relationship projection for one Candidate and selected Job."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    AsyncGraphReadDriver,
)
from app.graph.sync_candidate import (
    candidate_skill_param_row,
    non_excluded_skills,
)
from app.graph.sync_job import job_skill_param_row
from app.schemas.jobs import JobPostExtraction, JobSkill
from app.schemas.profile import CandidateProfile, CandidateSkill

SelectedRelationshipType = Literal["HAS_SKILL", "REQUIRES", "PREFERS"]

_CANDIDATE_SKILLS_CYPHER: Final[str] = (
    "MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill) "
    "RETURN type(r) AS relationship_type, "
    "s.canonical_key AS canonical_key, r.confidence AS confidence, "
    "r.years AS years, r.proficiency AS proficiency, r.evidence AS evidence "
    "ORDER BY canonical_key LIMIT 201"
)
_JOB_SKILLS_CYPHER: Final[str] = (
    "MATCH (j:Job {id: $job_id})-[r:REQUIRES|PREFERS]->(s:Skill) "
    "RETURN type(r) AS relationship_type, "
    "s.canonical_key AS canonical_key, r.confidence AS confidence, "
    "null AS years, null AS proficiency, r.evidence AS evidence "
    "ORDER BY relationship_type, canonical_key LIMIT 201"
)


@dataclass(frozen=True, slots=True)
class SelectedSkillRelationship:
    relationship_type: SelectedRelationshipType
    canonical_key: str
    confidence: float
    years: float | None
    proficiency: str | None
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectedSkillRelationshipSnapshot:
    candidate: tuple[SelectedSkillRelationship, ...]
    job: tuple[SelectedSkillRelationship, ...]


@dataclass(frozen=True, slots=True)
class SelectedSkillIntegrityResult:
    is_consistent: bool
    error_code: str | None
    message: str


def _candidate_relationship(skill: CandidateSkill) -> SelectedSkillRelationship:
    row = candidate_skill_param_row(skill)
    rel = row["rel"]
    return SelectedSkillRelationship(
        relationship_type="HAS_SKILL",
        canonical_key=str(row["skill"]["canonical_key"]),
        confidence=float(rel["confidence"]),
        years=None if rel["years"] is None else float(rel["years"]),
        proficiency=str(rel["proficiency"]),
        evidence=tuple(str(item) for item in rel["evidence"]),
    )


def _job_relationship(
    skill: JobSkill,
    relationship_type: Literal["REQUIRES", "PREFERS"],
) -> SelectedSkillRelationship:
    row = job_skill_param_row(skill)
    rel = row["rel"]
    return SelectedSkillRelationship(
        relationship_type=relationship_type,
        canonical_key=str(row["skill"]["canonical_key"]),
        confidence=float(rel["confidence"]),
        years=None,
        proficiency=None,
        evidence=tuple(str(item) for item in rel["evidence"]),
    )


def build_expected_selected_skill_snapshot(
    profile: CandidateProfile,
    extraction: JobPostExtraction,
) -> SelectedSkillRelationshipSnapshot:
    """Build the exact relationship payload written by the shared sync owners."""
    return SelectedSkillRelationshipSnapshot(
        candidate=tuple(
            _candidate_relationship(skill) for skill in non_excluded_skills(profile)
        ),
        job=(
            *(
                _job_relationship(skill, "REQUIRES")
                for skill in extraction.required_skills
            ),
            *(
                _job_relationship(skill, "PREFERS")
                for skill in extraction.preferred_skills
            ),
        ),
    )


def _number(value: object, *, nullable: bool) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("relationship numeric property is invalid")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("relationship numeric property is invalid")
    return number


def _parse_relationship(
    row: Mapping[str, Any],
    *,
    allowed_types: frozenset[str],
) -> SelectedSkillRelationship:
    relationship_type = row.get("relationship_type")
    canonical_key = row.get("canonical_key")
    evidence = row.get("evidence")
    if relationship_type not in allowed_types:
        raise ValueError("relationship type is invalid")
    if not isinstance(canonical_key, str) or not canonical_key.strip():
        raise ValueError("canonical key is invalid")
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) for item in evidence
    ):
        raise ValueError("relationship evidence is invalid")
    years = _number(row.get("years"), nullable=True)
    proficiency = row.get("proficiency")
    if proficiency is not None and not isinstance(proficiency, str):
        raise ValueError("relationship proficiency is invalid")
    if relationship_type != "HAS_SKILL" and (
        years is not None or proficiency is not None
    ):
        raise ValueError("Job relationship has Candidate-only properties")
    confidence = _number(row.get("confidence"), nullable=False)
    assert confidence is not None
    return SelectedSkillRelationship(
        relationship_type=relationship_type,
        canonical_key=canonical_key,
        confidence=confidence,
        years=years,
        proficiency=proficiency,
        evidence=tuple(evidence),
    )


async def _load_actual_snapshot(
    driver: AsyncGraphReadDriver,
    *,
    job_id: str,
) -> SelectedSkillRelationshipSnapshot:
    async with driver.session() as session:
        candidate_result = await session.run(
            _CANDIDATE_SKILLS_CYPHER,
            {"candidate_id": CANDIDATE_PROFILE_ID},
        )
        job_result = await session.run(_JOB_SKILLS_CYPHER, {"job_id": job_id})
        candidate_rows = await candidate_result.data()
        job_rows = await job_result.data()
    return SelectedSkillRelationshipSnapshot(
        candidate=tuple(
            _parse_relationship(row, allowed_types=frozenset({"HAS_SKILL"}))
            for row in candidate_rows
        ),
        job=tuple(
            _parse_relationship(
                row,
                allowed_types=frozenset({"REQUIRES", "PREFERS"}),
            )
            for row in job_rows
        ),
    )


def _same_complete_multisets(
    expected: SelectedSkillRelationshipSnapshot,
    actual: SelectedSkillRelationshipSnapshot,
) -> bool:
    return (
        Counter(expected.candidate) == Counter(actual.candidate)
        and Counter(expected.job) == Counter(actual.job)
    )


async def check_selected_skill_relationship_integrity(
    driver: AsyncGraphReadDriver,
    *,
    job_id: str,
    profile: CandidateProfile,
    extraction: JobPostExtraction,
) -> SelectedSkillIntegrityResult:
    """Compare complete selected relationships; never write or repair Neo4j."""
    expected = build_expected_selected_skill_snapshot(profile, extraction)
    try:
        actual = await _load_actual_snapshot(driver, job_id=job_id)
    except ValueError:
        return SelectedSkillIntegrityResult(
            is_consistent=False,
            error_code=NEO4J_REBUILD_REQUIRED,
            message="Selected Neo4j skill relationship data is invalid.",
        )
    except Exception:
        return SelectedSkillIntegrityResult(
            is_consistent=False,
            error_code=NEO4J_UNAVAILABLE,
            message="Neo4j is unavailable for selected skill integrity check.",
        )
    if not _same_complete_multisets(expected, actual):
        return SelectedSkillIntegrityResult(
            is_consistent=False,
            error_code=NEO4J_REBUILD_REQUIRED,
            message="Selected Candidate/Job skill relationships differ from SQLite.",
        )
    return SelectedSkillIntegrityResult(
        is_consistent=True,
        error_code=None,
        message="Selected Candidate/Job skill relationships match SQLite.",
    )


def assert_selected_skill_queries_read_only() -> None:
    """Raise when a selected relationship template contains a write clause."""
    for query in (_CANDIDATE_SKILLS_CYPHER, _JOB_SKILLS_CYPHER):
        normalized = f" {' '.join(query.upper().split())} "
        for token in (" MERGE ", " CREATE ", " DELETE ", " DETACH ", " SET "):
            if token in normalized:
                raise AssertionError(f"selected skill query contains {token.strip()}")


__all__ = [
    "SelectedSkillIntegrityResult",
    "SelectedSkillRelationship",
    "SelectedSkillRelationshipSnapshot",
    "assert_selected_skill_queries_read_only",
    "build_expected_selected_skill_snapshot",
    "check_selected_skill_relationship_integrity",
]
