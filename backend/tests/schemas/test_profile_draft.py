"""Profile draft envelope: omit vs replace preferences, safe summary."""

from __future__ import annotations

from typing import Any

import pytest
from app.schemas.profile_draft import (
    ProfileApprovalSummary,
    ProfileDraftDocument,
    build_approval_summary,
)
from pydantic import ValidationError


def _minimal_profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Backend engineer.",
        "current_title": "Engineer",
        "total_experience_years": None,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.7,
    }
    data.update(overrides)
    return data


def _prefs(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target_roles": ["Backend"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }
    data.update(overrides)
    return data


def _summary(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Review proposed Engineer",
        "current_title": "Engineer",
        "skill_names": [],
        "experience_count": 0,
        "education_count": 0,
        "has_preference_changes": False,
        "target_roles_preview": [],
    }
    data.update(overrides)
    return data


def test_draft_without_preferences_means_unchanged() -> None:
    draft = ProfileDraftDocument.model_validate(
        {
            "profile": _minimal_profile(),
            "approval_summary": _summary(has_preference_changes=False),
        }
    )
    assert draft.replaces_preferences() is False
    assert draft.preferences is None
    stored = draft.to_storage_dict()
    assert "preferences" not in stored
    assert "profile" in stored
    assert "approval_summary" in stored

    reloaded = ProfileDraftDocument.from_storage_dict(stored)
    assert reloaded.replaces_preferences() is False


def test_draft_with_preferences_means_explicit_replacement() -> None:
    draft = ProfileDraftDocument.model_validate(
        {
            "profile": _minimal_profile(),
            "preferences": _prefs(),
            "approval_summary": _summary(
                has_preference_changes=True,
                target_roles_preview=["Backend"],
            ),
        }
    )
    assert draft.replaces_preferences() is True
    assert draft.preferences is not None
    assert draft.preferences.target_roles == ["Backend"]
    stored = draft.to_storage_dict()
    assert "preferences" in stored
    assert stored["preferences"]["target_roles"] == ["Backend"]

    reloaded = ProfileDraftDocument.from_storage_dict(stored)
    assert reloaded.replaces_preferences() is True
    assert reloaded.preferences is not None


def test_null_preferences_rejected() -> None:
    with pytest.raises(ValidationError, match="omitted"):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(),
                "preferences": None,
                "approval_summary": _summary(),
            }
        )


def test_summary_flag_must_match_preference_presence() -> None:
    with pytest.raises(ValidationError, match="has_preference_changes"):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(),
                "preferences": _prefs(),
                "approval_summary": _summary(has_preference_changes=False),
            }
        )
    with pytest.raises(ValidationError, match="has_preference_changes"):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(),
                "approval_summary": _summary(has_preference_changes=True),
            }
        )


def test_untyped_provider_extras_rejected_on_draft() -> None:
    with pytest.raises(ValidationError):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(),
                "approval_summary": _summary(),
                "provider_raw": {"foo": 1},
                "repair_attempts": 2,
                "document_text": "full cv",
            }
        )


def test_untyped_extras_rejected_on_approval_summary() -> None:
    with pytest.raises(ValidationError):
        ProfileApprovalSummary.model_validate(
            _summary(draft_id="secret", storage_path="/data/files/x.pdf")
        )


def test_invalid_nested_profile_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(extraction_confidence=2.0),
                "approval_summary": _summary(),
            }
        )


def test_invalid_nested_preferences_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileDraftDocument.model_validate(
            {
                "profile": _minimal_profile(),
                "preferences": _prefs(acceptable_work_modes=["teleport"]),
                "approval_summary": _summary(has_preference_changes=True),
            }
        )


def test_build_approval_summary_helper() -> None:
    from app.schemas.candidate import CandidateProfile
    from app.schemas.preferences import JobPreferences

    profile = CandidateProfile.model_validate(
        _minimal_profile(
            skills=[
                {
                    "skill": {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": [],
                        "category": None,
                        "status": "provisional",
                        "confidence": 0.6,
                        "evidence": ["Python listed"],
                    },
                    "proficiency": "intermediate",
                    "years": None,
                    "source": "cv",
                    "excluded": False,
                    "evidence": [],
                }
            ]
        )
    )
    prefs = JobPreferences.model_validate(_prefs())
    summary = build_approval_summary(profile, preferences=prefs)
    assert summary.has_preference_changes is True
    assert "Python" in summary.skill_names
    assert summary.target_roles_preview == ["Backend"]

    summary_no_prefs = build_approval_summary(profile)
    assert summary_no_prefs.has_preference_changes is False
    assert summary_no_prefs.target_roles_preview == []


def test_serialization_distinguishes_omit_vs_replace() -> None:
    omit = ProfileDraftDocument.model_validate(
        {
            "profile": _minimal_profile(),
            "approval_summary": _summary(has_preference_changes=False),
        }
    )
    replace = ProfileDraftDocument.model_validate(
        {
            "profile": _minimal_profile(),
            "preferences": _prefs(),
            "approval_summary": _summary(
                has_preference_changes=True,
                target_roles_preview=["Backend"],
            ),
        }
    )
    omit_json = omit.to_storage_dict()
    replace_json = replace.to_storage_dict()
    assert "preferences" not in omit_json
    assert "preferences" in replace_json
    # model_dump alone would emit preferences=null for omit if defaulted;
    # storage helper is the authoritative omit-vs-replace wire form.
    assert omit_json.keys() == {"profile", "approval_summary"}
    assert replace_json.keys() == {"profile", "preferences", "approval_summary"}
