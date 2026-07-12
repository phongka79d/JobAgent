"""Strict JobPostExtraction / JobSkill contract tests (Plan 5 §7.2)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from app.schemas.candidate import MAX_EVIDENCE_SNIPPET_LEN, SkillRef, SkillStatus
from app.schemas.job_post import (
    EmploymentType,
    JdQuality,
    JobPostExtraction,
    JobSeniority,
    JobSkill,
    JobWorkMode,
)
from pydantic import ValidationError


def _skill_ref(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "canonical_key": "python",
        "display_name": "Python",
        "aliases": ["python3"],
        "category": "language",
        "status": "provisional",
        "confidence": 0.9,
        "evidence": ["Required: Python"],
    }
    data.update(overrides)
    return data


def _job_skill(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "skill": _skill_ref(),
        "confidence": 0.85,
        "evidence": ["Required: Python"],
    }
    data.update(overrides)
    return data


def _minimal_extraction(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": None,
        "company": None,
        "summary": "",
        "responsibilities": [],
        "required_skills": [],
        "preferred_skills": [],
        "seniority": "unknown",
        "min_experience_years": None,
        "max_experience_years": None,
        "location": None,
        "work_mode": "unknown",
        "employment_type": "unknown",
        "education_requirements": [],
        "language_requirements": [],
        "salary_text": None,
        "job_family": None,
        "extraction_confidence": 0.5,
        "jd_quality": "unscorable",
    }
    data.update(overrides)
    return data


def _full_extraction(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs and data services.",
        "responsibilities": ["Design REST APIs", "Own production services"],
        "required_skills": [_job_skill()],
        "preferred_skills": [
            _job_skill(
                skill=_skill_ref(
                    canonical_key="kubernetes",
                    display_name="Kubernetes",
                    evidence=["Preferred: Kubernetes"],
                ),
                confidence=0.7,
                evidence=["Preferred: Kubernetes"],
            )
        ],
        "seniority": "senior",
        "min_experience_years": 5.0,
        "max_experience_years": 10.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "education_requirements": ["BS Computer Science"],
        "language_requirements": ["English"],
        "salary_text": "EUR 80k-100k",
        "job_family": "software_engineering",
        "extraction_confidence": 0.9,
        "jd_quality": "full",
    }
    data.update(overrides)
    return data


def test_minimal_extraction_valid() -> None:
    doc = JobPostExtraction.model_validate(_minimal_extraction())
    assert doc.summary == ""
    assert doc.required_skills == []
    assert doc.jd_quality is JdQuality.UNSCORABLE
    assert doc.extraction_confidence == 0.5


def test_full_extraction_valid_all_master_fields() -> None:
    doc = JobPostExtraction.model_validate(_full_extraction())
    assert doc.title == "Senior Backend Engineer"
    assert doc.company == "Acme Corp"
    assert doc.required_skills[0].skill.canonical_key == "python"
    assert doc.preferred_skills[0].skill.canonical_key == "kubernetes"
    assert doc.seniority is JobSeniority.SENIOR
    assert doc.work_mode is JobWorkMode.HYBRID
    assert doc.employment_type is EmploymentType.FULL_TIME
    assert doc.salary_text == "EUR 80k-100k"
    assert doc.job_family == "software_engineering"
    assert doc.jd_quality is JdQuality.FULL
    dumped = doc.model_dump(mode="json")
    # Exact master field inventory — no scoring/match extras.
    expected = {
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
        "employment_type",
        "education_requirements",
        "language_requirements",
        "salary_text",
        "job_family",
        "extraction_confidence",
        "jd_quality",
    }
    assert set(dumped.keys()) == expected
    assert "score" not in dumped
    assert "weight" not in dumped
    assert "related_to" not in dumped
    assert "match" not in dumped


def test_job_skill_wraps_shared_skill_ref() -> None:
    skill = JobSkill.model_validate(_job_skill())
    assert isinstance(skill.skill, SkillRef)
    assert skill.skill.status is SkillStatus.PROVISIONAL
    assert skill.confidence == 0.85
    assert skill.evidence == ["Required: Python"]


@pytest.mark.parametrize(
    "seniority",
    ["intern", "junior", "mid", "senior", "lead", "unknown"],
)
def test_seniority_enum(seniority: str) -> None:
    doc = JobPostExtraction.model_validate(_minimal_extraction(seniority=seniority))
    assert doc.seniority == JobSeniority(seniority)


@pytest.mark.parametrize("work_mode", ["remote", "hybrid", "onsite", "unknown"])
def test_work_mode_enum(work_mode: str) -> None:
    doc = JobPostExtraction.model_validate(_minimal_extraction(work_mode=work_mode))
    assert doc.work_mode == JobWorkMode(work_mode)


@pytest.mark.parametrize(
    "employment_type",
    ["full_time", "part_time", "contract", "internship", "unknown"],
)
def test_employment_type_enum(employment_type: str) -> None:
    doc = JobPostExtraction.model_validate(
        _minimal_extraction(employment_type=employment_type)
    )
    assert doc.employment_type == EmploymentType(employment_type)


@pytest.mark.parametrize("quality", ["full", "partial", "unscorable"])
def test_jd_quality_enum(quality: str) -> None:
    doc = JobPostExtraction.model_validate(_minimal_extraction(jd_quality=quality))
    assert doc.jd_quality == JdQuality(quality)


@pytest.mark.parametrize(
    "field,value",
    [
        ("seniority", "principal"),
        ("work_mode", "flexible"),
        ("employment_type", "temp"),
        ("jd_quality", "excellent"),
    ],
)
def test_invalid_enums_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_minimal_extraction(**{field: value}))


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_bounds_accept(confidence: float) -> None:
    skill = JobSkill.model_validate(_job_skill(confidence=confidence))
    assert skill.confidence == confidence
    doc = JobPostExtraction.model_validate(
        _minimal_extraction(extraction_confidence=confidence)
    )
    assert doc.extraction_confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
def test_confidence_bounds_reject(confidence: float) -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(confidence=confidence))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _minimal_extraction(extraction_confidence=confidence)
        )


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_confidence_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(confidence=bad))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _minimal_extraction(extraction_confidence=bad)
        )


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0])
def test_non_finite_or_negative_years_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _minimal_extraction(min_experience_years=bad)
        )


def test_years_above_max_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _minimal_extraction(min_experience_years=100.0)
        )


def test_min_years_exceeding_max_rejected() -> None:
    with pytest.raises(ValidationError, match="min_experience_years"):
        JobPostExtraction.model_validate(
            _minimal_extraction(
                min_experience_years=10.0,
                max_experience_years=5.0,
            )
        )


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _minimal_extraction(match_score=0.9, weight=1.0)
        )
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(weight=0.8, related_to=["java"]))


def test_overlong_evidence_rejected() -> None:
    long_snip = "x" * (MAX_EVIDENCE_SNIPPET_LEN + 1)
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=[long_snip]))


def test_empty_evidence_snippet_rejected() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=["  "]))


def test_blank_optional_strings_normalized_to_none() -> None:
    doc = JobPostExtraction.model_validate(
        _minimal_extraction(title="  ", company="", location=" \t ")
    )
    assert doc.title is None
    assert doc.company is None
    assert doc.location is None


def test_salary_is_display_only_string() -> None:
    doc = JobPostExtraction.model_validate(
        _full_extraction(salary_text="  $120,000 USD  ")
    )
    assert doc.salary_text == "$120,000 USD"
    # No numeric salary fields exist on the model.
    assert not hasattr(doc, "salary_min")
    assert not hasattr(doc, "salary_max")
