"""Unit tests for Job extraction Pydantic contracts (Plan 5 §7.1 / Master §7.4)."""

from __future__ import annotations

from typing import Any, get_args

import pytest
from app.db.models.jobs import JOB_JD_QUALITIES
from app.schemas.jobs import (
    JobPostExtraction,
    JobSeniority,
    JobSkill,
    JobWorkMode,
    parse_job_post_extraction,
)
from app.schemas.skills import SkillRef
from pydantic import ValidationError

_SKILL_REF_FIELDS = frozenset(
    {"canonical_key", "display_name", "aliases", "category"}
)
_JOB_SKILL_FIELDS = frozenset({"skill", "confidence", "evidence"})
_JOB_POST_EXTRACTION_FIELDS = frozenset(
    {
        "title",
        "company",
        "summary",
        "responsibilities",
        "required_skills",
        "preferred_skills",
        "seniority",
        "min_experience_years",
        "max_experience_years",
        "location",
        "work_mode",
        "extraction_confidence",
    }
)


def _skill_ref(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "canonical_key": "python",
        "display_name": "Python",
        "aliases": ["python3"],
        "category": "language",
    }
    base.update(overrides)
    return base


def _job_skill(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "skill": _skill_ref(),
        "confidence": 0.9,
        "evidence": ["Required: 3+ years Python"],
    }
    base.update(overrides)
    return base


def _extraction(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services"],
        "required_skills": [_job_skill()],
        "preferred_skills": [],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return base


def test_job_skill_exact_fields() -> None:
    skill = JobSkill.model_validate(_job_skill())
    assert set(JobSkill.model_fields) == _JOB_SKILL_FIELDS
    assert set(skill.model_dump()) == _JOB_SKILL_FIELDS
    assert set(skill.skill.model_dump()) == _SKILL_REF_FIELDS
    assert isinstance(skill.skill, SkillRef)


def test_job_post_extraction_exact_fields() -> None:
    doc = JobPostExtraction.model_validate(_extraction())
    assert set(JobPostExtraction.model_fields) == _JOB_POST_EXTRACTION_FIELDS
    assert set(doc.model_dump()) == _JOB_POST_EXTRACTION_FIELDS


def test_valid_document_round_trip() -> None:
    payload = _extraction(
        preferred_skills=[
            _job_skill(
                skill=_skill_ref(
                    canonical_key="fastapi",
                    display_name="FastAPI",
                    aliases=[],
                    category=None,
                ),
                evidence=["Nice to have FastAPI"],
            )
        ]
    )
    doc = parse_job_post_extraction(payload)
    dumped = doc.model_dump(mode="json")
    again = parse_job_post_extraction(dumped)
    assert again.model_dump(mode="json") == dumped
    assert set(dumped) == _JOB_POST_EXTRACTION_FIELDS
    assert "jd_quality" not in dumped
    assert "aliases" not in dumped
    assert "relationships" not in dumped
    assert dumped["preferred_skills"][0]["skill"]["aliases"] == []


def test_jd_quality_cannot_appear_on_extraction() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(jd_quality="full"))
    serialized = JobPostExtraction.model_validate(_extraction()).model_dump(
        mode="json"
    )
    assert "jd_quality" not in serialized
    assert set(serialized.keys()).isdisjoint(JOB_JD_QUALITIES)


def test_nullable_title_company_location_and_experience() -> None:
    doc = JobPostExtraction.model_validate(
        _extraction(
            title=None,
            company=None,
            location=None,
            min_experience_years=None,
            max_experience_years=None,
        )
    )
    assert doc.title is None
    assert doc.company is None
    assert doc.location is None
    assert doc.min_experience_years is None
    assert doc.max_experience_years is None


def test_summary_required_string_and_empty_lists_valid() -> None:
    doc = JobPostExtraction.model_validate(
        _extraction(
            summary="",
            responsibilities=[],
            required_skills=[],
            preferred_skills=[],
        )
    )
    assert doc.summary == ""
    assert doc.responsibilities == []
    assert doc.required_skills == []
    assert doc.preferred_skills == []


def test_summary_null_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(summary=None))


def test_seniority_and_work_mode_enum_values() -> None:
    assert set(get_args(JobSeniority)) == {
        "intern",
        "junior",
        "mid",
        "senior",
        "lead",
        "unknown",
    }
    assert set(get_args(JobWorkMode)) == {
        "remote",
        "hybrid",
        "onsite",
        "unknown",
    }
    for value in get_args(JobSeniority):
        JobPostExtraction.model_validate(_extraction(seniority=value))
    for value in get_args(JobWorkMode):
        JobPostExtraction.model_validate(_extraction(work_mode=value))


def test_rejects_bad_seniority_and_work_mode() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(seniority="principal"))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(work_mode="wfh"))


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_bounds_accepted(confidence: float) -> None:
    skill = JobSkill.model_validate(_job_skill(confidence=confidence))
    doc = JobPostExtraction.model_validate(
        _extraction(extraction_confidence=confidence)
    )
    assert skill.confidence == confidence
    assert doc.extraction_confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(confidence=confidence))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _extraction(extraction_confidence=confidence)
        )


def test_evidence_is_list_of_strings() -> None:
    skill = JobSkill.model_validate(
        _job_skill(evidence=["snippet A", "snippet B"])
    )
    assert skill.evidence == ["snippet A", "snippet B"]
    empty = JobSkill.model_validate(_job_skill(evidence=[]))
    assert empty.evidence == []


def test_evidence_rejects_non_string_items() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=[{"text": "x"}]))
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=[1, 2]))


def test_nested_skill_ref_validated() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(
            _job_skill(skill=_skill_ref(extra_field="nope"))
        )
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(skill="python"))


def test_all_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(weight=1.0))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(jd_quality="full"))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(aliases=["x"]))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(relationships=["..."]))
