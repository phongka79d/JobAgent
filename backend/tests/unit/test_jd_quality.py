"""Unit tests for deterministic JD quality classification (Plan 5 / Master §7.6)."""

from __future__ import annotations

from typing import Any

import pytest
from app.db.models.jobs import (
    JOB_JD_QUALITIES,
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
)
from app.schemas.jobs import JobPostExtraction, parse_job_post_extraction
from app.services.jd_quality import classify_jd_quality


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
        "evidence": ["Required: Python"],
    }
    base.update(overrides)
    return base


def _extraction(**overrides: Any) -> dict[str, Any]:
    """Base document that is ``full`` under the executable quality rules."""
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs for the platform.",
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


def _doc(**overrides: Any) -> JobPostExtraction:
    return parse_job_post_extraction(_extraction(**overrides))


def test_quality_literals_match_orm_vocabulary() -> None:
    assert JOB_JD_QUALITY_FULL == "full"
    assert JOB_JD_QUALITY_PARTIAL == "partial"
    assert JOB_JD_QUALITY_UNSCORABLE == "unscorable"
    assert frozenset(
        {
            JOB_JD_QUALITY_FULL,
            JOB_JD_QUALITY_PARTIAL,
            JOB_JD_QUALITY_UNSCORABLE,
        }
    ) == JOB_JD_QUALITIES


def test_full_requires_title_summary_signal_and_three_scoring_groups() -> None:
    quality = classify_jd_quality(_doc())
    assert quality == JOB_JD_QUALITY_FULL


def test_full_with_exactly_three_scoring_groups() -> None:
    # Drop work_mode and one experience bound -> still 3 groups
    # (seniority, min experience, location).
    quality = classify_jd_quality(
        _doc(work_mode="unknown", max_experience_years=None)
    )
    assert quality == JOB_JD_QUALITY_FULL


def test_full_usable_signal_from_skill_evidence_only() -> None:
    quality = classify_jd_quality(
        _doc(
            responsibilities=[],
            required_skills=[],
            preferred_skills=[
                _job_skill(evidence=["Preferred: Docker experience"])
            ],
        )
    )
    assert quality == JOB_JD_QUALITY_FULL


def test_full_usable_signal_from_responsibility_only() -> None:
    quality = classify_jd_quality(
        _doc(
            responsibilities=["Own the payment pipeline"],
            required_skills=[_job_skill(evidence=[])],
            preferred_skills=[],
        )
    )
    assert quality == JOB_JD_QUALITY_FULL


def test_partial_missing_title_but_has_summary_and_signal() -> None:
    quality = classify_jd_quality(_doc(title=None))
    assert quality == JOB_JD_QUALITY_PARTIAL


def test_partial_blank_title_with_summary_and_signal() -> None:
    quality = classify_jd_quality(_doc(title="   "))
    assert quality == JOB_JD_QUALITY_PARTIAL


def test_partial_only_two_scoring_groups() -> None:
    quality = classify_jd_quality(
        _doc(
            min_experience_years=None,
            max_experience_years=None,
            work_mode="unknown",
        )
    )
    assert quality == JOB_JD_QUALITY_PARTIAL


def test_partial_no_scoring_groups_still_partial_with_signal() -> None:
    quality = classify_jd_quality(
        _doc(
            seniority="unknown",
            min_experience_years=None,
            max_experience_years=None,
            location=None,
            work_mode="unknown",
        )
    )
    assert quality == JOB_JD_QUALITY_PARTIAL


def test_unscorable_contact_only_no_signal() -> None:
    quality = classify_jd_quality(
        _doc(
            title="Contact us",
            summary="Email jobs@example.com or call +1-555-0100.",
            responsibilities=[],
            required_skills=[],
            preferred_skills=[],
            seniority="unknown",
            min_experience_years=None,
            max_experience_years=None,
            location=None,
            work_mode="unknown",
        )
    )
    assert quality == JOB_JD_QUALITY_UNSCORABLE


def test_unscorable_blank_summary_even_with_signal() -> None:
    quality = classify_jd_quality(_doc(summary=""))
    assert quality == JOB_JD_QUALITY_UNSCORABLE
    quality_ws = classify_jd_quality(_doc(summary="   \n\t"))
    assert quality_ws == JOB_JD_QUALITY_UNSCORABLE


def test_unscorable_skill_without_evidence_and_no_responsibilities() -> None:
    quality = classify_jd_quality(
        _doc(
            responsibilities=["   ", ""],
            required_skills=[_job_skill(evidence=["  ", ""])],
            preferred_skills=[],
        )
    )
    assert quality == JOB_JD_QUALITY_UNSCORABLE


def test_unscorable_is_not_processing_failure() -> None:
    """Insufficient facts classify as processed unscorable, not an exception."""
    quality = classify_jd_quality(
        _doc(
            title=None,
            summary="Hello",
            responsibilities=[],
            required_skills=[],
            preferred_skills=[],
        )
    )
    assert quality == JOB_JD_QUALITY_UNSCORABLE
    assert quality in JOB_JD_QUALITIES


def test_equivalent_inputs_always_same_quality() -> None:
    a = _doc()
    b = parse_job_post_extraction(a.model_dump(mode="json"))
    assert classify_jd_quality(a) == classify_jd_quality(b) == JOB_JD_QUALITY_FULL

    contact = _doc(
        title=None,
        summary="Call us",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
    )
    contact2 = parse_job_post_extraction(contact.model_dump(mode="json"))
    assert (
        classify_jd_quality(contact)
        == classify_jd_quality(contact2)
        == JOB_JD_QUALITY_UNSCORABLE
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, JOB_JD_QUALITY_FULL),
        ({"title": None}, JOB_JD_QUALITY_PARTIAL),
        (
            {
                "min_experience_years": None,
                "max_experience_years": None,
                "location": None,
                "work_mode": "unknown",
            },
            JOB_JD_QUALITY_PARTIAL,
        ),
        (
            {
                "responsibilities": [],
                "required_skills": [],
                "preferred_skills": [],
            },
            JOB_JD_QUALITY_UNSCORABLE,
        ),
        ({"summary": "  "}, JOB_JD_QUALITY_UNSCORABLE),
    ],
)
def test_quality_branches_parametrized(
    overrides: dict[str, Any], expected: str
) -> None:
    assert classify_jd_quality(_doc(**overrides)) == expected


def test_classify_accepts_only_validated_model() -> None:
    """Classifier operates on validated extraction, not raw dict quality keys."""
    doc = _doc()
    assert not hasattr(doc, "jd_quality")
    assert "jd_quality" not in doc.model_dump()
    assert classify_jd_quality(doc) in JOB_JD_QUALITIES
