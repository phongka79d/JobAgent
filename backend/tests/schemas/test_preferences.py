"""JobPreferences contract separation and enum tests."""

from __future__ import annotations

from typing import Any

import pytest
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences, TargetSeniority, WorkMode
from pydantic import ValidationError


def _prefs(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote", "hybrid"],
        "target_seniority": ["senior", "lead"],
    }
    data.update(overrides)
    return data


def test_minimal_empty_preferences_valid() -> None:
    prefs = JobPreferences.model_validate({})
    assert prefs.target_roles == []
    assert prefs.preferred_locations == []
    assert prefs.acceptable_work_modes == []
    assert prefs.target_seniority == []


def test_full_preferences_valid() -> None:
    prefs = JobPreferences.model_validate(_prefs())
    assert prefs.target_roles == ["Backend Engineer"]
    assert WorkMode.REMOTE in prefs.acceptable_work_modes
    assert TargetSeniority.SENIOR in prefs.target_seniority


@pytest.mark.parametrize("mode", ["remote", "hybrid", "onsite"])
def test_work_mode_enum(mode: str) -> None:
    prefs = JobPreferences.model_validate(
        _prefs(acceptable_work_modes=[mode], target_seniority=[])
    )
    assert prefs.acceptable_work_modes == [WorkMode(mode)]


@pytest.mark.parametrize(
    "level",
    ["intern", "junior", "mid", "senior", "lead", "unknown"],
)
def test_seniority_enum(level: str) -> None:
    prefs = JobPreferences.model_validate(
        _prefs(target_seniority=[level], acceptable_work_modes=[])
    )
    assert prefs.target_seniority == [TargetSeniority(level)]


def test_invalid_work_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(_prefs(acceptable_work_modes=["anywhere"]))


def test_invalid_seniority_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(_prefs(target_seniority=["principal"]))


def test_extra_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(
            _prefs(score=0.9, raw_document="cv address Paris")
        )


def test_blank_list_items_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(_prefs(target_roles=["  "]))


def test_duplicate_modes_deduped() -> None:
    prefs = JobPreferences.model_validate(
        _prefs(acceptable_work_modes=["remote", "remote", "hybrid"])
    )
    assert prefs.acceptable_work_modes == [WorkMode.REMOTE, WorkMode.HYBRID]


def test_profile_does_not_accept_preference_fields() -> None:
    """Profile facts and job preferences remain separate documents."""
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {
                "summary": "Engineer",
                "current_title": None,
                "total_experience_years": None,
                "skills": [],
                "experiences": [],
                "education": [],
                "languages": [],
                "extraction_confidence": 0.5,
                "target_roles": ["Backend"],
                "preferred_locations": ["Paris"],
                "acceptable_work_modes": ["remote"],
            }
        )


def test_preferences_do_not_accept_profile_skill_fields() -> None:
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(
            _prefs(skills=[{"name": "Python"}], summary="profile leak")
        )


def test_serialization_roundtrip() -> None:
    prefs = JobPreferences.model_validate(_prefs())
    again = JobPreferences.model_validate(prefs.model_dump(mode="json"))
    assert again == prefs
