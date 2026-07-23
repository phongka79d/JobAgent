"""Tests for source-grounded candidate identity filtering."""

from __future__ import annotations

from importlib import import_module
from inspect import getsource
from typing import Any

from app.schemas.profile import CandidateProfile


def _profile(**overrides: Any) -> CandidateProfile:
    payload: dict[str, Any] = {
        "full_name": "Ada Lovelace",
        "location": "Ho Chi Minh City",
        "summary": "Engineer",
        "current_title": None,
        "total_experience_years": None,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.9,
    }
    payload.update(overrides)
    return CandidateProfile.model_validate(payload)


def _guard(profile: CandidateProfile, fragments: list[str]) -> CandidateProfile:
    module = import_module("app.services.profile_identity_guard")
    return module.guard_profile_identity(profile, source_fragments=fragments)


def test_direct_source_fragments_preserve_identity_case_and_whitespace() -> None:
    profile = _profile()

    guarded = _guard(
        profile,
        ["ADA   LOVELACE", "Based in Ho Chi Minh\nCity"],
    )

    assert guarded.full_name == "Ada Lovelace"
    assert guarded.location == "Ho Chi Minh City"
    assert guarded is not profile


def test_unsupported_identity_values_are_nulled_without_derivation() -> None:
    profile = _profile(full_name="Invented Name", location="Invented City")

    guarded = _guard(
        profile,
        [
            "resume_ada_lovelace.pdf",
            "ada@example.test",
            "+84 123 456 789",
            "12 Example Street, Hanoi",
        ],
    )

    assert guarded.full_name is None
    assert guarded.location is None
    assert guarded.summary == profile.summary


def test_absent_identity_remains_absent_even_when_metadata_contains_clues() -> None:
    guarded = _guard(
        _profile(full_name=None, location=None),
        ["ada@example.test", "resume-london.pdf"],
    )

    assert guarded.full_name is None
    assert guarded.location is None


def test_identity_guard_has_no_orm_or_provider_dependencies() -> None:
    source = getsource(import_module("app.services.profile_identity_guard"))
    for forbidden in ("app.db", "sqlalchemy", "shopaikey", "openai", "neo4j"):
        assert forbidden not in source
