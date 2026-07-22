"""Unit tests for Candidate v1 embedding text (Plan 6 Batch01 01A)."""

from __future__ import annotations

from typing import Any

from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    JobPreferences,
    LanguageItem,
)
from app.schemas.skills import SkillRef
from app.services import embedding_text


def _skill_ref(
    display_name: str,
    *,
    key: str | None = None,
    aliases: list[str] | None = None,
) -> SkillRef:
    canonical = key or display_name.casefold().replace(" ", "_")
    return SkillRef(
        canonical_key=canonical,
        display_name=display_name,
        aliases=aliases or [],
        category="language",
    )


def _candidate_skill(
    display_name: str,
    *,
    key: str | None = None,
    aliases: list[str] | None = None,
    excluded: bool = False,
    evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_skill_ref(display_name, key=key, aliases=aliases),
        confidence=0.9,
        proficiency="advanced",
        years=3.0,
        source="cv",
        excluded=excluded,
        evidence=evidence or ["from approved profile"],
    )


def _experience(title: str, **overrides: Any) -> ExperienceItem:
    data: dict[str, Any] = {
        "title": title,
        "company": "Company Hidden",
        "start_date_text": "2020",
        "end_date_text": "present",
        "summary": "Experience summary must stay out.",
    }
    data.update(overrides)
    return ExperienceItem.model_validate(data)


def _profile(**overrides: Any) -> CandidateProfile:
    data: dict[str, Any] = {
        "summary": "Backend engineer focused on APIs.",
        "current_title": "Current title must stay out",
        "total_experience_years": 6.0,
        "skills": [
            _candidate_skill("Python"),
            _candidate_skill("FastAPI"),
        ],
        "experiences": [
            _experience("Senior Backend Engineer"),
            _experience("API Engineer"),
        ],
        "education": [
            EducationItem(
                institution="Hidden University",
                degree="BS",
                field="Computer Science",
                graduation_year=2018,
            )
        ],
        "languages": [
            LanguageItem(name="English", proficiency="advanced"),
        ],
        "extraction_confidence": 0.91,
    }
    data.update(overrides)
    return CandidateProfile.model_validate(data)


def _preferences(**overrides: Any) -> JobPreferences:
    data: dict[str, Any] = {
        "target_roles": ["Platform Engineer", "Backend Engineer"],
        "preferred_locations": ["Remote", "Berlin"],
        "acceptable_work_modes": ["remote", "hybrid"],
        "target_seniority": ["senior", "lead"],
    }
    data.update(overrides)
    return JobPreferences.model_validate(data)


def test_candidate_version_compatible_with_job_v1() -> None:
    assert embedding_text.CANDIDATE_EMBEDDING_TEXT_VERSION == "v1"
    assert (
        embedding_text.CANDIDATE_EMBEDDING_TEXT_VERSION
        == embedding_text.JOB_EMBEDDING_TEXT_VERSION
    )


def test_candidate_field_order_and_whitespace_contract() -> None:
    text = embedding_text.build_candidate_embedding_text_v1(
        _profile(
            summary=" Backend\nengineer   focused on APIs. ",
            skills=[
                _candidate_skill(" Python "),
                _candidate_skill(" FastAPI "),
            ],
            experiences=[
                _experience(" Senior   Backend Engineer "),
                _experience("API\tEngineer"),
            ],
        ),
        _preferences(
            target_roles=[" Platform   Engineer ", "Backend\nEngineer"],
            preferred_locations=[" Remote ", "Berlin"],
        ),
    )

    assert text == "\n".join(
        [
            "target_roles:",
            "- Platform Engineer",
            "- Backend Engineer",
            "profile_summary:",
            "Backend engineer focused on APIs.",
            "skills:",
            "Python, FastAPI",
            "experience_titles:",
            "- Senior Backend Engineer",
            "- API Engineer",
            "preferred_locations:",
            "- Remote",
            "- Berlin",
            "acceptable_work_modes:",
            "- remote",
            "- hybrid",
            "target_seniority:",
            "- senior",
            "- lead",
        ]
    )


def test_candidate_excludes_skills_marked_excluded() -> None:
    text = embedding_text.build_candidate_embedding_text_v1(
        _profile(
            skills=[
                _candidate_skill(
                    "COBOL",
                    excluded=True,
                    evidence=["RAW_CV_SECRET excluded by user"],
                ),
                _candidate_skill(
                    "Node.js",
                    key="node_js",
                    aliases=["nodejs", "raw alias"],
                ),
            ]
        ),
        _preferences(),
    )

    skill_section = text.split("skills:")[1].split("experience_titles:")[0]
    assert "Node.js" in skill_section
    assert "COBOL" not in text
    assert "RAW_CV_SECRET" not in text
    assert "node_js" not in skill_section
    assert "nodejs" not in skill_section


def test_candidate_embedding_uses_persisted_skill_rows_without_expansion() -> None:
    text = embedding_text.build_candidate_embedding_text_v1(
        _profile(
            skills=[
                _candidate_skill(
                    "Methods: Discovery/Research",
                    key="methods_discovery_research",
                ),
                _candidate_skill("Quản trị rủi ro", key="quản_trị_rủi_ro"),
            ]
        ),
        _preferences(),
    )

    skill_section = text.split("skills:")[1].split("experience_titles:")[0]
    assert skill_section.strip() == (
        "Methods: Discovery/Research, Quản trị rủi ro"
    )


def test_candidate_empty_lists_keep_stable_sections() -> None:
    text = embedding_text.build_candidate_embedding_text_v1(
        _profile(skills=[], experiences=[], education=[], languages=[]),
        _preferences(
            target_roles=[],
            preferred_locations=[],
            acceptable_work_modes=[],
            target_seniority=[],
        ),
    )

    assert text == "\n".join(
        [
            "target_roles:",
            "profile_summary:",
            "Backend engineer focused on APIs.",
            "skills:",
            "experience_titles:",
            "preferred_locations:",
            "acceptable_work_modes:",
            "target_seniority:",
        ]
    )


def test_candidate_omits_raw_cv_prefixes_and_unapproved_fields() -> None:
    text = embedding_text.build_candidate_embedding_text_v1(
        _profile(
            summary="Approved profile summary.",
            current_title="Principal Secret Title",
            experiences=[
                _experience(
                    "Visible Title",
                    company="SecretCo",
                    summary="RAW CV TEXT SHOULD NOT ENTER",
                )
            ],
            education=[
                EducationItem(
                    institution="Secret University",
                    degree="MS",
                    field="Hidden Field",
                    graduation_year=2020,
                )
            ],
            languages=[LanguageItem(name="Vietnamese", proficiency="native")],
        ),
        _preferences(),
    )
    lower = text.lower()

    assert not lower.startswith("query:")
    assert not lower.startswith("passage:")
    assert "query:" not in lower
    assert "passage:" not in lower
    assert "RAW CV TEXT" not in text
    assert "SecretCo" not in text
    assert "Secret University" not in text
    assert "Principal Secret Title" not in text
    assert "Vietnamese" not in text
    assert "Visible Title" in text


def test_candidate_identical_inputs_byte_identical() -> None:
    a = embedding_text.build_candidate_embedding_text_v1(_profile(), _preferences())
    b = embedding_text.build_candidate_embedding_text_v1(_profile(), _preferences())

    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")
