"""Deterministic JD quality classifier boundary tests (Master §7.5)."""

from __future__ import annotations

from typing import Any

from app.schemas.job_post import JdQuality, JobPostExtraction
from app.services.jd_quality import (
    REASON_CONTACT_ONLY,
    REASON_MISSING_DESCRIPTION,
    REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE,
    REASON_MISSING_SEMANTIC,
    REASON_MISSING_SKILL_SIGNALS,
    REASON_MISSING_TITLE,
    REASON_SCORING_FIELDS_INSUFFICIENT,
    apply_jd_quality,
    classify_jd_quality,
    majority_scoring_groups_populated,
    populated_scoring_field_groups,
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
            "status": "provisional",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _base(**overrides: Any) -> JobPostExtraction:
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
        # Classifier must ignore the incoming value.
        "jd_quality": "full",
    }
    data.update(overrides)
    return JobPostExtraction.model_validate(data)


def _full_fixture() -> JobPostExtraction:
    return _base(
        title="Senior Backend Engineer",
        company="Acme",
        summary="Own backend services and APIs.",
        responsibilities=["Design REST APIs", "Mentor engineers"],
        required_skills=[_skill()],
        preferred_skills=[
            _skill(key="kubernetes", evidence="Preferred: Kubernetes", confidence=0.7)
        ],
        seniority="senior",
        min_experience_years=5.0,
        max_experience_years=10.0,
        location="Berlin",
        work_mode="hybrid",
        employment_type="full_time",
        education_requirements=["BS CS"],
        language_requirements=["English"],
        job_family="software_engineering",
        extraction_confidence=0.9,
        salary_text="EUR 90k",  # display-only; must not affect scoring groups
        jd_quality="unscorable",
    )


def test_full_classification_has_empty_reasons() -> None:
    extraction = _full_fixture()
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.FULL
    assert result.reasons == ()
    assert result.reason_list == []
    assert majority_scoring_groups_populated(extraction)


def test_apply_overwrites_llm_quality() -> None:
    extraction = _full_fixture()
    assert extraction.jd_quality is JdQuality.UNSCORABLE
    updated, assessment = apply_jd_quality(extraction)
    assert assessment.quality is JdQuality.FULL
    assert updated.jd_quality is JdQuality.FULL


def test_partial_missing_majority_scoring_groups() -> None:
    # Title + description + skill evidence, but few scoring groups.
    extraction = _base(
        title="Engineer",
        summary="Build things with Python.",
        required_skills=[_skill()],
        seniority="unknown",
        work_mode="unknown",
        employment_type="unknown",
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.PARTIAL
    assert REASON_SCORING_FIELDS_INSUFFICIENT in result.reasons
    assert len(result.reasons) >= 1


def test_partial_missing_title_with_skills() -> None:
    extraction = _base(
        title=None,
        summary="We need Python engineers for platform work.",
        responsibilities=["Ship features"],
        required_skills=[_skill()],
        seniority="mid",
        location="Remote-friendly",
        work_mode="remote",
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.PARTIAL
    assert REASON_MISSING_TITLE in result.reasons


def test_partial_missing_description() -> None:
    extraction = _base(
        title="Python Developer",
        summary="",
        responsibilities=[],
        required_skills=[_skill()],
        location="NYC",
        seniority="junior",
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.PARTIAL
    assert REASON_MISSING_DESCRIPTION in result.reasons


def test_unscorable_contact_only() -> None:
    extraction = _base(
        title=None,
        company="Acme Recruiting",
        summary="",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.UNSCORABLE
    assert REASON_CONTACT_ONLY in result.reasons
    assert len(result.reasons) >= 1


def test_unscorable_no_skills_with_title_only() -> None:
    extraction = _base(
        title="Mystery Role",
        summary="",
        responsibilities=[],
        required_skills=[],
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.UNSCORABLE
    assert REASON_MISSING_SKILL_SIGNALS in result.reasons or (
        REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE in result.reasons
    )


def test_unscorable_empty_document() -> None:
    extraction = _base()
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.UNSCORABLE
    assert REASON_MISSING_SEMANTIC in result.reasons or REASON_CONTACT_ONLY in result.reasons
    assert result.reasons  # non-full always has reasons


def test_responsibilities_without_skills_is_not_partial() -> None:
    """Partial requires grounded skill signals; responsibilities alone are not enough."""
    extraction = _base(
        title="Ops",
        summary="Keep systems running.",
        responsibilities=["On-call rotations"],
        required_skills=[],
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.UNSCORABLE
    assert REASON_MISSING_SKILL_SIGNALS in result.reasons


def test_preferred_skills_count_as_skill_signals() -> None:
    extraction = _base(
        title="Engineer",
        summary="Platform work.",
        preferred_skills=[_skill(key="go", evidence="Nice to have: Go")],
    )
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.PARTIAL


def test_salary_does_not_populate_scoring_groups() -> None:
    extraction = _base(salary_text="USD 200000")
    groups = populated_scoring_field_groups(extraction)
    assert "salary" not in groups
    assert groups == frozenset()


def test_full_requires_majority_of_nine_groups() -> None:
    # 4 groups only → not majority of 9 (threshold 5).
    extraction = _base(
        title="Senior Engineer",
        summary="Backend services.",
        responsibilities=["Ship APIs"],
        required_skills=[_skill()],
        seniority="senior",
        location="Berlin",
        work_mode="remote",
        # skills, seniority, location, work_mode = 4
    )
    assert len(populated_scoring_field_groups(extraction)) == 4
    assert not majority_scoring_groups_populated(extraction)
    result = classify_jd_quality(extraction)
    assert result.quality is JdQuality.PARTIAL
    assert REASON_SCORING_FIELDS_INSUFFICIENT in result.reasons


def test_non_full_always_has_reasons_property() -> None:
    cases = [
        _base(),  # unscorable
        _base(
            title="Engineer",
            summary="Python work",
            required_skills=[_skill()],
        ),  # partial
    ]
    for extraction in cases:
        result = classify_jd_quality(extraction)
        assert result.quality is not JdQuality.FULL
        assert len(result.reasons) >= 1
