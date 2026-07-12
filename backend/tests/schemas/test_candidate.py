"""Strict Candidate / skill / nested display-fact contract tests."""

from __future__ import annotations

import math
from typing import Any

import pytest
from app.schemas.candidate import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    LanguageItem,
    SkillProficiency,
    SkillRef,
    SkillSource,
    SkillStatus,
)
from pydantic import ValidationError


def _skill_ref(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "canonical_key": "python",
        "display_name": "Python",
        "aliases": ["python3"],
        "category": "language",
        "status": "verified",
        "confidence": 0.9,
        "evidence": ["Python (5 years) — Skills section"],
    }
    data.update(overrides)
    return data


def _candidate_skill(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "skill": _skill_ref(),
        "proficiency": "advanced",
        "years": 5.0,
        "source": "cv",
        "excluded": False,
        "evidence": ["2019–2024 Python backend roles"],
    }
    data.update(overrides)
    return data


def _minimal_profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Backend engineer.",
        "current_title": None,
        "total_experience_years": None,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.5,
    }
    data.update(overrides)
    return data


def _full_profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Senior backend engineer with distributed systems experience.",
        "current_title": "Senior Backend Engineer",
        "total_experience_years": 8.0,
        "skills": [_candidate_skill()],
        "experiences": [
            {
                "title": "Backend Engineer",
                "organization": "Acme",
                "date_range": "2019–2024",
                "summary": "APIs and data pipelines.",
                "evidence": ["Backend Engineer, Acme (2019–2024)"],
            }
        ],
        "education": [
            {
                "institution": "State University",
                "credential": "BSc",
                "field_of_study": "Computer Science",
                "date_range": "2015–2019",
                "evidence": ["BSc Computer Science, State University"],
            }
        ],
        "languages": [
            {
                "language": "English",
                "proficiency": "fluent",
                "evidence": ["Languages: English (fluent)"],
            }
        ],
        "extraction_confidence": 0.85,
    }
    data.update(overrides)
    return data


def test_minimal_profile_valid() -> None:
    profile = CandidateProfile.model_validate(_minimal_profile())
    assert profile.summary == "Backend engineer."
    assert profile.skills == []
    assert profile.total_experience_years is None
    assert profile.extraction_confidence == 0.5


def test_full_profile_valid_with_nested_display_facts() -> None:
    profile = CandidateProfile.model_validate(_full_profile())
    assert profile.current_title == "Senior Backend Engineer"
    assert profile.skills[0].skill.canonical_key == "python"
    assert profile.skills[0].proficiency is SkillProficiency.ADVANCED
    assert profile.experiences[0].organization == "Acme"
    assert profile.education[0].credential == "BSc"
    assert profile.languages[0].language == "English"
    dumped = profile.model_dump(mode="json")
    assert "preferred_locations" not in dumped
    assert "score" not in dumped
    assert "related_to" not in dumped


@pytest.mark.parametrize("status", ["verified", "provisional"])
def test_skill_status_enum(status: str) -> None:
    ref = SkillRef.model_validate(_skill_ref(status=status))
    assert ref.status == SkillStatus(status)


@pytest.mark.parametrize(
    "proficiency",
    ["beginner", "intermediate", "advanced", "unknown"],
)
def test_proficiency_enum(proficiency: str) -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(proficiency=proficiency, years=None, evidence=[])
    )
    assert skill.proficiency == SkillProficiency(proficiency)


@pytest.mark.parametrize("source", ["cv", "user_correction"])
def test_source_enum(source: str) -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(source=source, years=None, evidence=[])
    )
    assert skill.source == SkillSource(source)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_bounds_accept(confidence: float) -> None:
    ref = SkillRef.model_validate(_skill_ref(confidence=confidence))
    assert ref.confidence == confidence
    profile = CandidateProfile.model_validate(
        _minimal_profile(extraction_confidence=confidence)
    )
    assert profile.extraction_confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0])
def test_confidence_bounds_reject(confidence: float) -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(confidence=confidence))
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            _minimal_profile(extraction_confidence=confidence)
        )


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_confidence_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(confidence=bad))
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(_minimal_profile(extraction_confidence=bad))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0])
def test_non_finite_or_negative_years_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(
            _candidate_skill(years=bad, evidence=["timeline"])
        )
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            _full_profile(total_experience_years=bad)
        )


def test_precise_skill_years_without_evidence_rejected() -> None:
    with pytest.raises(ValidationError, match="timeline evidence"):
        CandidateSkill.model_validate(_candidate_skill(years=3.0, evidence=[]))


def test_precise_skill_years_with_non_timeline_evidence_rejected() -> None:
    """Arbitrary nonempty evidence is not timeline evidence (A2 gate)."""
    with pytest.raises(ValidationError, match="timeline evidence"):
        CandidateSkill.model_validate(
            _candidate_skill(years=5.0, evidence=["Python listed in skills"])
        )


def test_precise_skill_years_with_date_range_evidence_allowed() -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(years=5.0, evidence=["2019–2024 Python backend roles"])
    )
    assert skill.years == 5.0


def test_precise_skill_years_with_duration_evidence_allowed() -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(years=3.0, evidence=["3 years of Python in production"])
    )
    assert skill.years == 3.0


def test_unknown_years_without_evidence_allowed() -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(years=None, evidence=[], proficiency="unknown")
    )
    assert skill.years is None


def test_precise_total_years_without_timeline_rejected() -> None:
    with pytest.raises(ValidationError, match="timeline evidence"):
        CandidateProfile.model_validate(
            _minimal_profile(total_experience_years=10.0, experiences=[])
        )


def test_precise_total_years_with_non_timeline_experience_evidence_rejected() -> None:
    """Non-timeline experience evidence must not authorize precise totals."""
    with pytest.raises(ValidationError, match="timeline evidence"):
        CandidateProfile.model_validate(
            _minimal_profile(
                total_experience_years=10.0,
                experiences=[
                    {
                        "title": "Engineer",
                        "organization": None,
                        "date_range": None,
                        "summary": None,
                        "evidence": ["Worked as engineer"],
                    }
                ],
            )
        )


def test_precise_total_years_with_experience_timeline_allowed() -> None:
    profile = CandidateProfile.model_validate(
        _minimal_profile(
            total_experience_years=10.0,
            experiences=[
                {
                    "title": "Dev",
                    "organization": None,
                    "date_range": "2014–2024",
                    "summary": None,
                    "evidence": [],
                }
            ],
        )
    )
    assert profile.total_experience_years == 10.0


def test_precise_total_years_with_timeline_evidence_snippet_allowed() -> None:
    profile = CandidateProfile.model_validate(
        _minimal_profile(
            total_experience_years=6.0,
            experiences=[
                {
                    "title": "Dev",
                    "organization": "Acme",
                    "date_range": None,
                    "summary": None,
                    "evidence": ["Backend Engineer, Acme (2018–2024)"],
                }
            ],
        )
    )
    assert profile.total_experience_years == 6.0


def test_extra_keys_rejected_on_skill_ref() -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(related_to="java", score=0.99))


def test_extra_keys_rejected_on_candidate_skill() -> None:
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(
            _candidate_skill(graph_trust=True, raw_document="SECRET")
        )


def test_extra_keys_rejected_on_profile() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            _minimal_profile(
                preferred_locations=["Paris"],
                score=1.0,
                provider_control={"repair": True},
                raw_document="full cv text",
            )
        )


def test_nested_experience_rejects_preference_and_score_fields() -> None:
    with pytest.raises(ValidationError):
        ExperienceItem.model_validate(
            {
                "title": "Dev",
                "organization": "Acme",
                "date_range": "2020",
                "summary": None,
                "evidence": ["ev"],
                "preferred_location": "Remote",
                "score": 0.8,
            }
        )


def test_nested_education_rejects_raw_document() -> None:
    with pytest.raises(ValidationError):
        EducationItem.model_validate(
            {
                "institution": "U",
                "credential": "BSc",
                "field_of_study": None,
                "date_range": None,
                "evidence": [],
                "raw_document": "transcript",
            }
        )


def test_nested_language_rejects_graph_trust() -> None:
    with pytest.raises(ValidationError):
        LanguageItem.model_validate(
            {
                "language": "French",
                "proficiency": "B2",
                "evidence": [],
                "related_to": "English",
            }
        )


def test_evidence_bounds_and_blank_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(evidence=["   "]))
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(evidence=["x" * 300]))
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(evidence=[f"e{i}" for i in range(20)]))


def test_invalid_enum_values_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(status="trusted"))
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(proficiency="expert"))
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(
            _candidate_skill(source="llm", years=None, evidence=[])
        )


def test_serialization_roundtrip() -> None:
    profile = CandidateProfile.model_validate(_full_profile())
    again = CandidateProfile.model_validate(profile.model_dump(mode="json"))
    assert again == profile
