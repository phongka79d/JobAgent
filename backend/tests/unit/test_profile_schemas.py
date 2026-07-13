"""Unit tests for profile/skill/preference/draft Pydantic contracts (Plan 4 §7.1)."""

from __future__ import annotations

from typing import Any, get_args

import pytest
from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    JobPreferences,
    LanguageItem,
    ProfileDraftPayload,
    SkillProficiency,
    SkillSource,
    TargetSeniority,
    WorkMode,
    parse_candidate_profile,
    parse_job_preferences,
    parse_profile_draft_payload,
)
from app.schemas.skills import SkillRef, parse_skill_ref
from pydantic import ValidationError

# --- field ownership (exact Master contracts) ---------------------------------

_SKILL_REF_FIELDS = {"canonical_key", "display_name", "aliases", "category"}
_CANDIDATE_SKILL_FIELDS = {
    "skill",
    "confidence",
    "proficiency",
    "years",
    "source",
    "excluded",
    "evidence",
}
_EXPERIENCE_FIELDS = {
    "title",
    "company",
    "start_date_text",
    "end_date_text",
    "summary",
}
_EDUCATION_FIELDS = {"institution", "degree", "field", "graduation_year"}
_LANGUAGE_FIELDS = {"name", "proficiency"}
_PROFILE_FIELDS = {
    "summary",
    "current_title",
    "total_experience_years",
    "skills",
    "experiences",
    "education",
    "languages",
    "extraction_confidence",
}
_PREFERENCES_FIELDS = {
    "target_roles",
    "preferred_locations",
    "acceptable_work_modes",
    "target_seniority",
}
_DRAFT_FIELDS = {"candidate_profile", "job_preferences"}


def _skill_ref(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "canonical_key": "python",
        "display_name": "Python",
        "aliases": ["python3"],
        "category": "language",
    }
    base.update(overrides)
    return base


def _candidate_skill(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "skill": _skill_ref(),
        "confidence": 0.9,
        "proficiency": "advanced",
        "years": 5.0,
        "source": "cv",
        "excluded": False,
        "evidence": ["5 years Python development"],
    }
    base.update(overrides)
    return base


def _experience(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Software Engineer",
        "company": "Acme",
        "start_date_text": "2020-01",
        "end_date_text": "present",
        "summary": "Built APIs",
    }
    base.update(overrides)
    return base


def _education(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "institution": "State University",
        "degree": "BSc",
        "field": "Computer Science",
        "graduation_year": 2019,
    }
    base.update(overrides)
    return base


def _language(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"name": "English", "proficiency": "fluent"}
    base.update(overrides)
    return base


def _profile(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "summary": "Backend engineer",
        "current_title": "Senior Engineer",
        "total_experience_years": 6.5,
        "skills": [_candidate_skill()],
        "experiences": [_experience()],
        "education": [_education()],
        "languages": [_language()],
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return base


def _preferences(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Berlin"],
        "acceptable_work_modes": ["remote", "hybrid"],
        "target_seniority": ["mid", "senior"],
    }
    base.update(overrides)
    return base


def _draft(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate_profile": _profile(),
        "job_preferences": _preferences(),
    }
    base.update(overrides)
    return base


# --- exact fields -------------------------------------------------------------


def test_skill_ref_exact_fields() -> None:
    ref = SkillRef.model_validate(_skill_ref())
    assert set(SkillRef.model_fields) == _SKILL_REF_FIELDS
    assert set(ref.model_dump()) == _SKILL_REF_FIELDS


def test_candidate_skill_exact_fields() -> None:
    skill = CandidateSkill.model_validate(_candidate_skill())
    assert set(CandidateSkill.model_fields) == _CANDIDATE_SKILL_FIELDS
    assert set(skill.model_dump()) == _CANDIDATE_SKILL_FIELDS


def test_experience_education_language_exact_fields() -> None:
    assert set(ExperienceItem.model_fields) == _EXPERIENCE_FIELDS
    assert set(EducationItem.model_fields) == _EDUCATION_FIELDS
    assert set(LanguageItem.model_fields) == _LANGUAGE_FIELDS


def test_candidate_profile_and_preferences_and_draft_exact_fields() -> None:
    assert set(CandidateProfile.model_fields) == _PROFILE_FIELDS
    assert set(JobPreferences.model_fields) == _PREFERENCES_FIELDS
    assert set(ProfileDraftPayload.model_fields) == _DRAFT_FIELDS


# --- nullability --------------------------------------------------------------


def test_skill_ref_category_nullable_aliases_required_list() -> None:
    ref = SkillRef.model_validate(_skill_ref(category=None, aliases=[]))
    assert ref.category is None
    assert ref.aliases == []


def test_candidate_skill_years_nullable() -> None:
    skill = CandidateSkill.model_validate(_candidate_skill(years=None))
    assert skill.years is None


def test_experience_nullable_fields() -> None:
    item = ExperienceItem.model_validate(
        _experience(company=None, start_date_text=None, end_date_text=None)
    )
    assert item.company is None
    assert item.start_date_text is None
    assert item.end_date_text is None


def test_education_and_language_nullability() -> None:
    edu = EducationItem.model_validate(
        _education(degree=None, field=None, graduation_year=None)
    )
    assert edu.degree is None
    assert edu.field is None
    assert edu.graduation_year is None
    lang = LanguageItem.model_validate(_language(proficiency=None))
    assert lang.proficiency is None


def test_profile_nullable_title_and_years() -> None:
    profile = CandidateProfile.model_validate(
        _profile(current_title=None, total_experience_years=None)
    )
    assert profile.current_title is None
    assert profile.total_experience_years is None


def test_empty_lists_valid_on_profile_and_preferences() -> None:
    profile = CandidateProfile.model_validate(
        _profile(skills=[], experiences=[], education=[], languages=[])
    )
    prefs = JobPreferences.model_validate(
        _preferences(
            target_roles=[],
            preferred_locations=[],
            acceptable_work_modes=[],
            target_seniority=[],
        )
    )
    assert profile.skills == []
    assert prefs.target_roles == []
    assert prefs.acceptable_work_modes == []


# --- enums --------------------------------------------------------------------


def test_skill_proficiency_and_source_enum_values() -> None:
    assert set(get_args(SkillProficiency)) == {
        "beginner",
        "intermediate",
        "advanced",
        "unknown",
    }
    assert set(get_args(SkillSource)) == {"cv", "user_correction"}
    for value in get_args(SkillProficiency):
        CandidateSkill.model_validate(_candidate_skill(proficiency=value))
    for value in get_args(SkillSource):
        CandidateSkill.model_validate(_candidate_skill(source=value))


def test_work_mode_and_seniority_enum_values() -> None:
    assert set(get_args(WorkMode)) == {"remote", "hybrid", "onsite"}
    assert set(get_args(TargetSeniority)) == {
        "intern",
        "junior",
        "mid",
        "senior",
        "lead",
        "unknown",
    }
    JobPreferences.model_validate(
        _preferences(
            acceptable_work_modes=list(get_args(WorkMode)),
            target_seniority=list(get_args(TargetSeniority)),
        )
    )


def test_rejects_unknown_proficiency_source_work_mode_seniority() -> None:
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(proficiency="expert"))
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(source="llm"))
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(
            _preferences(acceptable_work_modes=["wfh"])
        )
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(
            _preferences(target_seniority=["principal"])
        )


# --- confidence [0, 1] --------------------------------------------------------


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_bounds_accepted(confidence: float) -> None:
    skill = CandidateSkill.model_validate(_candidate_skill(confidence=confidence))
    profile = CandidateProfile.model_validate(
        _profile(extraction_confidence=confidence)
    )
    assert skill.confidence == confidence
    assert profile.extraction_confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(confidence=confidence))
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            _profile(extraction_confidence=confidence)
        )


# --- unknown fields / strict config -------------------------------------------


def test_all_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SkillRef.model_validate(_skill_ref(extra=True))
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(weight=1.0))
    with pytest.raises(ValidationError):
        ExperienceItem.model_validate(_experience(location="Berlin"))
    with pytest.raises(ValidationError):
        EducationItem.model_validate(_education(gpa=4.0))
    with pytest.raises(ValidationError):
        LanguageItem.model_validate(_language(certified=True))
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(_profile(address="1 Main St"))
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(_preferences(salary_min=100000))
    with pytest.raises(ValidationError):
        ProfileDraftPayload.model_validate(_draft(notes="keep"))


# --- evidence shape -----------------------------------------------------------


def test_evidence_is_list_of_strings() -> None:
    skill = CandidateSkill.model_validate(
        _candidate_skill(evidence=["snippet A", "snippet B"])
    )
    assert skill.evidence == ["snippet A", "snippet B"]
    empty = CandidateSkill.model_validate(_candidate_skill(evidence=[]))
    assert empty.evidence == []


def test_evidence_rejects_non_string_items() -> None:
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(
            _candidate_skill(evidence=[{"text": "no"}])
        )
    with pytest.raises(ValidationError):
        CandidateSkill.model_validate(_candidate_skill(evidence=[1, 2]))


# --- nested full-document validation ------------------------------------------


def test_nested_invalid_skill_fails_full_profile() -> None:
    payload = _profile(skills=[_candidate_skill(confidence=1.5)])
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(payload)
    with pytest.raises(ValidationError):
        parse_candidate_profile(payload)


def test_nested_invalid_preferences_fail_full_draft() -> None:
    payload = _draft(
        job_preferences=_preferences(acceptable_work_modes=["office"])
    )
    with pytest.raises(ValidationError):
        ProfileDraftPayload.model_validate(payload)
    with pytest.raises(ValidationError):
        parse_profile_draft_payload(payload)


def test_parse_helpers_accept_valid_documents() -> None:
    profile = parse_candidate_profile(_profile())
    prefs = parse_job_preferences(_preferences())
    draft = parse_profile_draft_payload(_draft())
    ref = parse_skill_ref(_skill_ref(category=None, aliases=[]))
    assert isinstance(profile, CandidateProfile)
    assert isinstance(prefs, JobPreferences)
    assert isinstance(draft, ProfileDraftPayload)
    assert ref.category is None


# --- fact / preference separation + round-trip --------------------------------


def test_profile_draft_payload_json_round_trip_preserves_separation() -> None:
    """Facts stay under candidate_profile; preferences stay under job_preferences."""
    cv_city = "Munich"  # CV address/city fact must not become preferred location
    draft = ProfileDraftPayload.model_validate(
        _draft(
            candidate_profile=_profile(
                summary=f"Based in {cv_city}",
                skills=[
                    _candidate_skill(
                        source="user_correction",
                        excluded=True,
                        proficiency="unknown",
                        years=None,
                        evidence=["User removed Python from matching"],
                    )
                ],
            ),
            job_preferences=_preferences(
                preferred_locations=["Berlin"],  # explicit preference only
                target_roles=["Platform Engineer"],
            ),
        )
    )
    dumped = draft.model_dump(mode="json")
    assert set(dumped) == _DRAFT_FIELDS
    assert "preferred_locations" not in dumped["candidate_profile"]
    assert "summary" not in dumped["job_preferences"]
    assert dumped["job_preferences"]["preferred_locations"] == ["Berlin"]
    assert cv_city not in dumped["job_preferences"]["preferred_locations"]
    assert dumped["candidate_profile"]["skills"][0]["source"] == "user_correction"
    assert dumped["candidate_profile"]["skills"][0]["excluded"] is True

    restored = parse_profile_draft_payload(dumped)
    assert restored.model_dump(mode="json") == dumped
    assert restored.candidate_profile.skills[0].excluded is True
    assert restored.candidate_profile.skills[0].source == "user_correction"
    assert restored.job_preferences.preferred_locations == ["Berlin"]


def test_profile_facts_do_not_merge_into_preferences_on_construction() -> None:
    """JobPreferences rejects profile-only keys (no silent merge path)."""
    with pytest.raises(ValidationError):
        JobPreferences.model_validate(
            {
                "target_roles": [],
                "preferred_locations": [],
                "acceptable_work_modes": [],
                "target_seniority": [],
                "summary": "leaked fact",
                "skills": [],
            }
        )
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {
                **_profile(),
                "target_roles": ["Engineer"],
                "preferred_locations": ["Berlin"],
            }
        )


# --- schema modules stay pure contracts ---------------------------------------


def test_schema_modules_have_no_orm_or_io_imports() -> None:
    """Schema modules must not pull ORM/provider/fs/graph/route/agent code."""
    import app.schemas.profile as profile_mod
    import app.schemas.skills as skills_mod

    forbidden_substrings = (
        "app.db",
        "sqlalchemy",
        "fastapi",
        "httpx",
        "neo4j",
        "langgraph",
        "langchain",
        "app.agent",
        "app.api",
        "app.storage",
        "pathlib",
        "aiofiles",
    )
    for mod in (profile_mod, skills_mod):
        for name, value in vars(mod).items():
            if name.startswith("__"):
                continue
            module_name = getattr(value, "__module__", "") or ""
            for bad in forbidden_substrings:
                assert bad not in module_name, f"{mod.__name__}.{name} -> {module_name}"
        source = (mod.__file__ or "")
        assert source.endswith((".py",))
        text = open(source, encoding="utf-8").read()
        for bad in (
            "from app.db",
            "import sqlalchemy",
            "from fastapi",
            "import neo4j",
            "from app.agent",
            "from app.api",
            "from app.storage",
        ):
            assert bad not in text, f"{mod.__name__} imports {bad!r}"
