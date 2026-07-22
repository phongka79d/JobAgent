"""Selected-JD skill-map projection and exact graph-integrity tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from app.graph.consistency import NEO4J_REBUILD_REQUIRED, NEO4J_UNAVAILABLE
from app.graph.selected_skill_projection import (
    SelectedSkillRelationship,
    assert_selected_skill_queries_read_only,
    build_expected_selected_skill_snapshot,
    check_selected_skill_relationship_integrity,
)
from app.schemas.jobs import JobPostExtraction, JobSkill
from app.schemas.observability import SelectedJobSkillMap
from app.schemas.profile import CandidateProfile, CandidateSkill
from app.schemas.skills import SkillRef
from app.services.skill_compatibility import (
    MAX_SKILL_MAP_ITEMS,
    SkillCompatibilityError,
    build_skill_compatibility,
)
from app.services.skill_normalization import SkillNormalizer, load_skill_taxonomy
from pydantic import ValidationError


def _ref(key: str, display: str | None = None) -> SkillRef:
    return SkillRef(
        canonical_key=key,
        display_name=display or key,
        aliases=[],
        category=None,
    )


def _candidate(
    key: str,
    *,
    display: str | None = None,
    excluded: bool = False,
    confidence: float = 0.9,
    evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_ref(key, display),
        confidence=confidence,
        proficiency="advanced",
        years=3.0,
        source="cv",
        excluded=excluded,
        evidence=evidence or [f"candidate-{key}"],
    )


def _job(
    key: str,
    *,
    display: str | None = None,
    confidence: float = 0.8,
    evidence: list[str] | None = None,
) -> JobSkill:
    return JobSkill(
        skill=_ref(key, display),
        confidence=confidence,
        evidence=evidence or [f"job-{key}"],
    )


def _profile(skills: list[CandidateSkill]) -> CandidateProfile:
    return CandidateProfile(
        summary="Synthetic profile",
        current_title="Synthetic title",
        total_experience_years=4.0,
        skills=skills,
        experiences=[],
        education=[],
        languages=[],
        extraction_confidence=0.9,
    )


def _extraction(
    *,
    required: list[JobSkill],
    preferred: list[JobSkill],
) -> JobPostExtraction:
    return JobPostExtraction(
        title="Synthetic role",
        company="Synthetic company",
        summary="Synthetic summary",
        responsibilities=[],
        required_skills=required,
        preferred_skills=preferred,
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        extraction_confidence=0.8,
    )


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer(
        load_skill_taxonomy(
            {
                "skills": [
                    {
                        "canonical_key": "related_from",
                        "display_name": "Related source",
                        "aliases": [],
                        "category": None,
                    },
                    {
                        "canonical_key": "related_to",
                        "display_name": "Related target",
                        "aliases": [],
                        "category": None,
                    },
                ],
                "relationships": [
                    {
                        "from": "related_from",
                        "to": "related_to",
                        "weight": 0.75,
                        "source": "seed",
                    }
                ],
            }
        )
    )


def test_projection_reuses_matching_facts_and_preserves_source_order() -> None:
    direct = _candidate("direct", display="Direct candidate")
    related = _candidate("related_from", display="Related candidate")
    additional = _candidate("additional", display="Additional candidate")
    profile = _profile(
        [direct, related, additional, _candidate("excluded", excluded=True)]
    )
    extraction = _extraction(
        required=[
            _job("direct", display="Direct job"),
            _job("missing_required", display="Missing required"),
        ],
        preferred=[
            _job("related_to", display="Related job"),
            _job("missing_preferred", display="Missing preferred"),
        ],
    )

    result = build_skill_compatibility(profile, extraction, _normalizer())

    assert [item.match_type for item in result.items] == [
        "direct",
        "missing_required",
        "related",
        "missing_preferred",
        "candidate_only",
    ]
    assert [item.requirement for item in result.items] == [
        "required",
        "required",
        "preferred",
        "preferred",
        "none",
    ]
    assert [item.strength for item in result.items] == [1.0, 0.0, 0.6, 0.0, 0.0]
    assert result.items[0].candidate_skill is not None
    assert result.items[0].candidate_skill.display_name == "Direct candidate"
    assert result.items[0].job_skill is not None
    assert result.items[0].job_skill.display_name == "Direct job"
    assert result.items[2].relationship is not None
    assert result.items[2].relationship.from_key == "related_from"
    assert result.items[2].relationship.to_key == "related_to"
    assert result.items[2].relationship.weight == 0.75
    assert result.items[4].candidate_skill is not None
    assert result.items[4].candidate_skill.display_name == "Additional candidate"
    assert result.items[4].job_skill is None
    assert result.counts.as_dict() == {
        "direct": 1,
        "related": 1,
        "missing_required": 1,
        "missing_preferred": 1,
        "candidate_only": 1,
    }


def test_projection_fails_above_item_bound_without_partial_result() -> None:
    profile = _profile([_candidate(f"skill_{index}") for index in range(201)])

    with pytest.raises(SkillCompatibilityError) as exc_info:
        build_skill_compatibility(
            profile,
            _extraction(required=[], preferred=[]),
            _normalizer(),
        )

    assert MAX_SKILL_MAP_ITEMS == 200
    assert exc_info.value.code == "SKILL_MAP_LIMIT_EXCEEDED"


def _ready_response_payload() -> dict[str, Any]:
    return {
        "status": "ready",
        "code": None,
        "summary": "Selected map is ready.",
        "rebuild_instruction": None,
        "candidate": {
            "id": "active",
            "attachment_id": "11111111-2222-4333-8444-555555555555",
            "current_title": "Synthetic profile",
            "revision": datetime(2024, 1, 1, tzinfo=UTC),
        },
        "job": {
            "id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "title": "Synthetic role",
            "company": "Synthetic company",
            "revision": datetime(2024, 1, 2, tzinfo=UTC),
        },
        "items": [
            {
                "match_type": "direct",
                "requirement": "required",
                "strength": 1.0,
                "candidate_skill": {
                    "canonical_key": "source_key",
                    "display_name": "Source label",
                    "confidence": 0.9,
                    "evidence": ["candidate evidence"],
                },
                "job_skill": {
                    "canonical_key": "source_key",
                    "display_name": "Job label",
                    "confidence": 0.8,
                    "evidence": ["job evidence"],
                },
                "relationship": None,
            }
        ],
        "counts": {
            "direct": 1,
            "related": 0,
            "missing_required": 0,
            "missing_preferred": 0,
            "candidate_only": 0,
        },
        "checked_at": datetime(2024, 1, 3, tzinfo=UTC),
    }


def test_selected_map_schema_enforces_status_item_and_count_coupling() -> None:
    payload = _ready_response_payload()
    ready = SelectedJobSkillMap.model_validate(payload)
    assert ready.status == "ready"
    assert ready.counts.direct == 1

    invalid_payloads = [
        {**payload, "extra_internal": "forbidden"},
        {
            **payload,
            "items": [{**payload["items"][0], "strength": 0.6}],
        },
        {
            **payload,
            "counts": {**payload["counts"], "direct": 0},
        },
        {
            **payload,
            "status": "stale",
            "code": NEO4J_REBUILD_REQUIRED,
            "rebuild_instruction": "Run rebuild.",
        },
    ]
    for invalid in invalid_payloads:
        with pytest.raises(ValidationError):
            SelectedJobSkillMap.model_validate(invalid)


def test_selected_map_schema_enforces_related_and_empty_state_contracts() -> None:
    payload = _ready_response_payload()
    related_item = {
        **payload["items"][0],
        "match_type": "related",
        "strength": 0.6,
        "relationship": {
            "from_key": "source_key",
            "to_key": "target_key",
            "weight": 0.75,
            "source": "seed",
        },
    }
    related = SelectedJobSkillMap.model_validate(
        {
            **payload,
            "items": [related_item],
            "counts": {**payload["counts"], "direct": 0, "related": 1},
        }
    )
    assert related.items[0].relationship is not None

    stale = SelectedJobSkillMap.model_validate(
        {
            **payload,
            "status": "stale",
            "code": NEO4J_REBUILD_REQUIRED,
            "rebuild_instruction": "Run rebuild.",
            "items": [],
            "counts": {key: 0 for key in payload["counts"]},
        }
    )
    assert stale.items == []

    unavailable = SelectedJobSkillMap.model_validate(
        {
            **payload,
            "status": "unavailable",
            "code": NEO4J_UNAVAILABLE,
            "rebuild_instruction": None,
            "items": [],
            "counts": {key: 0 for key in payload["counts"]},
        }
    )
    assert unavailable.items == []


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def data(self) -> list[dict[str, Any]]:
        return list(self.rows)


class _Session:
    def __init__(self, driver: _Driver) -> None:
        self.driver = driver

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        del kwargs
        self.driver.queries.append(query)
        self.driver.parameters.append(dict(parameters or {}))
        if self.driver.fail:
            raise OSError("simulated Neo4j outage")
        if "HAS_SKILL" in query:
            return _Result(self.driver.candidate_rows)
        return _Result(self.driver.job_rows)


class _Driver:
    def __init__(
        self,
        *,
        candidate_rows: list[dict[str, Any]],
        job_rows: list[dict[str, Any]],
        fail: bool = False,
    ) -> None:
        self.candidate_rows = candidate_rows
        self.job_rows = job_rows
        self.fail = fail
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []

    def session(self, **config: Any) -> _Session:
        del config
        return _Session(self)


def _actual(row: SelectedSkillRelationship) -> dict[str, Any]:
    return {
        "relationship_type": row.relationship_type,
        "canonical_key": row.canonical_key,
        "confidence": row.confidence,
        "years": row.years,
        "proficiency": row.proficiency,
        "evidence": list(row.evidence),
    }


def _integrity_inputs() -> tuple[CandidateProfile, JobPostExtraction]:
    return (
        _profile([_candidate("direct", evidence=["candidate evidence"])]),
        _extraction(
            required=[_job("direct", evidence=["required evidence"])],
            preferred=[_job("preferred", evidence=["preferred evidence"])],
        ),
    )


def test_selected_relationship_integrity_accepts_exact_sync_projection() -> None:
    profile, extraction = _integrity_inputs()
    expected = build_expected_selected_skill_snapshot(profile, extraction)
    driver = _Driver(
        candidate_rows=[_actual(row) for row in expected.candidate],
        job_rows=[_actual(row) for row in expected.job],
    )

    result = asyncio.run(
        check_selected_skill_relationship_integrity(
            driver,
            job_id="11111111-2222-4333-8444-555555555555",
            profile=profile,
            extraction=extraction,
        )
    )

    assert result.is_consistent
    assert result.error_code is None
    assert driver.parameters == [
        {"candidate_id": "active"},
        {"job_id": "11111111-2222-4333-8444-555555555555"},
    ]
    assert len(driver.queries) == 2
    assert all(
        " LIMIT 201" in f" {' '.join(query.upper().split())}"
        for query in driver.queries
    )
    assert_selected_skill_queries_read_only()


def test_selected_relationship_integrity_withholds_oversized_actual_rows() -> None:
    profile, extraction = _integrity_inputs()
    expected = build_expected_selected_skill_snapshot(profile, extraction)
    driver = _Driver(
        candidate_rows=[_actual(expected.candidate[0])] * 201,
        job_rows=[_actual(row) for row in expected.job],
    )

    result = asyncio.run(
        check_selected_skill_relationship_integrity(
            driver,
            job_id="11111111-2222-4333-8444-555555555555",
            profile=profile,
            extraction=extraction,
        )
    )

    assert not result.is_consistent
    assert result.error_code == NEO4J_REBUILD_REQUIRED


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "relationship_type",
        "confidence",
        "evidence",
        "years",
        "proficiency",
    ],
)
def test_selected_relationship_integrity_withholds_every_mismatch(
    mutation: str,
) -> None:
    profile, extraction = _integrity_inputs()
    expected = build_expected_selected_skill_snapshot(profile, extraction)
    candidate_rows = [_actual(row) for row in expected.candidate]
    job_rows = [_actual(row) for row in expected.job]
    if mutation == "missing":
        job_rows.pop()
    elif mutation == "extra":
        job_rows.append(
            {
                "relationship_type": "REQUIRES",
                "canonical_key": "graph_only",
                "confidence": 0.5,
                "years": None,
                "proficiency": None,
                "evidence": [],
            }
        )
    elif mutation == "duplicate":
        candidate_rows.append(dict(candidate_rows[0]))
    elif mutation == "relationship_type":
        candidate_rows[0] = {
            **candidate_rows[0],
            "relationship_type": "PREFERS",
        }
    elif mutation == "confidence":
        candidate_rows[0] = {**candidate_rows[0], "confidence": 0.1}
    elif mutation == "evidence":
        candidate_rows[0] = {**candidate_rows[0], "evidence": ["other"]}
    elif mutation == "years":
        candidate_rows[0] = {**candidate_rows[0], "years": 1.0}
    else:
        candidate_rows[0] = {**candidate_rows[0], "proficiency": "beginner"}
    driver = _Driver(candidate_rows=candidate_rows, job_rows=job_rows)

    result = asyncio.run(
        check_selected_skill_relationship_integrity(
            driver,
            job_id="11111111-2222-4333-8444-555555555555",
            profile=profile,
            extraction=extraction,
        )
    )

    assert not result.is_consistent
    assert result.error_code == NEO4J_REBUILD_REQUIRED


def test_selected_relationship_integrity_maps_driver_failure_to_unavailable() -> None:
    profile, extraction = _integrity_inputs()
    driver = _Driver(candidate_rows=[], job_rows=[], fail=True)

    result = asyncio.run(
        check_selected_skill_relationship_integrity(
            driver,
            job_id="11111111-2222-4333-8444-555555555555",
            profile=profile,
            extraction=extraction,
        )
    )

    assert not result.is_consistent
    assert result.error_code == NEO4J_UNAVAILABLE
