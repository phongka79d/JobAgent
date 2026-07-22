"""Pure semantic guard tests using repository-authored synthetic JD data."""

from __future__ import annotations

import importlib
import json
from dataclasses import fields
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from app.services.jd_extraction import ExtractedJobPost
from app.services.skill_normalization import SkillNormalizer, load_skill_taxonomy

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "jd_extraction_golden.json"
)
GUARD_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "services"
    / "jd_extraction_guard.py"
)

EXPECTED_CODES = (
    "EVIDENCE_NOT_IN_SOURCE",
    "RESPONSIBILITY_NOT_IN_SOURCE",
    "METADATA_NOT_IN_SOURCE",
    "COMPOUND_SKILL_LABEL",
    "DUPLICATE_SKILL",
    "SKILL_GROUP_CONFLICT",
)


def _guard_module() -> ModuleType:
    try:
        return importlib.import_module("app.services.jd_extraction_guard")
    except ModuleNotFoundError:
        pytest.fail("pure JD extraction guard is not implemented", pytrace=False)


@pytest.fixture(scope="module")
def normalizer() -> SkillNormalizer:
    return SkillNormalizer.production()


@pytest.fixture(scope="module")
def empty_normalizer() -> SkillNormalizer:
    return SkillNormalizer(load_skill_taxonomy({"skills": [], "relationships": []}))


@pytest.fixture(scope="module")
def corpus() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _extracted(payload: dict[str, Any]) -> ExtractedJobPost:
    return ExtractedJobPost.model_validate(payload)


def _guard(
    raw_jd: str,
    extracted: ExtractedJobPost,
    normalizer: SkillNormalizer,
) -> Any:
    return _guard_module().guard_extracted_job_post(raw_jd, extracted, normalizer)


def _issue_dicts(result: Any) -> list[dict[str, Any]]:
    return [
        {
            "code": issue.code,
            "field_path": issue.field_path,
            "count": issue.count,
        }
        for issue in result.issues
    ]


def test_fixture_is_synthetic_bilingual_and_assertions_are_safe(
    corpus: dict[str, Any],
) -> None:
    assert corpus["provenance"] == "repository-authored synthetic"
    cases = corpus["cases"]
    assert {case["language"] for case in cases} == {"en", "vi"}
    assert len({case["id"] for case in cases}) == len(cases)
    assert any("one_line" in case["id"] for case in cases)
    assert any("sectioned" in case["id"] for case in cases)
    assert any("contact_only" in case["id"] for case in cases)
    for case in cases:
        for expected in case["expected_issues"]:
            assert set(expected) == {"code", "field_path", "count"}
            assert expected["code"] in set(EXPECTED_CODES)
            assert isinstance(expected["count"], int)
        assert "provider" not in case
        assert "prompt" not in case
        assert "transcript" not in case


def test_issue_vocabulary_and_structure_are_exact() -> None:
    module = _guard_module()
    assert module.ISSUE_CODES == EXPECTED_CODES
    assert {f.name for f in fields(module.GuardIssue)} == {
        "code",
        "field_path",
        "count",
    }


def test_guard_normalization_is_exact_nfkc_whitespace_and_casefold() -> None:
    module = _guard_module()
    normalize = module.normalize_guard_text
    assert normalize("  Ｐｙｔｈｏｎ\n  KỸ SƯ  ") == "python kỹ sư"
    assert normalize("React.JS") != normalize("react-js")
    assert normalize("C/C++") == "c/c++"


@pytest.mark.parametrize(
    "case_id",
    [
        "en_sectioned_atomic",
        "vi_one_line_nfkc",
        "en_missing_grounding",
        "vi_compound_labels",
        "en_duplicates_and_conflicts",
        "en_contact_only",
    ],
)
def test_synthetic_corpus_contract(
    case_id: str,
    corpus: dict[str, Any],
    normalizer: SkillNormalizer,
) -> None:
    case = next(item for item in corpus["cases"] if item["id"] == case_id)
    extracted = _extracted(case["extraction"])
    result = _guard(case["raw_jd"], extracted, normalizer)
    assert _issue_dicts(result) == case["expected_issues"]
    if result.accepted:
        assert result.omitted_issue_count == 0
        assert result.extraction is extracted
    else:
        assert result.extraction is None


def test_blank_grounded_fields_are_ignored_and_summary_is_not_grounded(
    normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "not copied from the retained source",
            "responsibilities": ["  \n  "],
            "required_skills": [
                {
                    "name": "Rust",
                    "confidence": 0.8,
                    "evidence": ["Rust"],
                }
            ],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.7,
        }
    )
    result = _guard("Synthetic source mentioning Rust.", extracted, normalizer)
    assert result.accepted
    assert result.issues == ()


@pytest.mark.parametrize(
    "label",
    ["Service Design/Research", "Revenue.Funnel+", "Quản trị-rủi ro"],
)
def test_unknown_contiguous_punctuation_labels_pass_without_seed_membership(
    label: str,
    empty_normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "Synthetic.",
            "responsibilities": [],
            "required_skills": [
                {"name": label, "confidence": 0.8, "evidence": [label]}
            ],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.7,
        }
    )
    result = _guard(
        f"Required capability: {label}.",
        extracted,
        empty_normalizer,
    )
    assert result.accepted


def test_semantic_skill_name_is_accepted_when_evidence_is_grounded(
    normalizer: SkillNormalizer,
) -> None:
    semantic = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "Synthetic.",
            "responsibilities": [],
            "required_skills": [
                {
                    "name": "Stakeholder Facilitation",
                    "confidence": 0.8,
                    "evidence": ["Lead stakeholder workshops"],
                }
            ],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.7,
        }
    )
    result = _guard(
        "Responsibilities: Lead stakeholder workshops.",
        semantic,
        normalizer,
    )
    assert result.accepted

    alias_grounded = _extracted(
        {
            **semantic.model_dump(mode="json"),
            "required_skills": [
                {
                    "name": "Python",
                    "confidence": 0.8,
                    "evidence": ["python3"],
                }
            ],
        }
    )
    assert _guard("Required: python3.", alias_grounded, normalizer).accepted


@pytest.mark.parametrize(
    ("label", "count"),
    [
        ("Rust, Go", 2),
        ("Docker or Kubernetes", 2),
        ("Research / Measurement", 2),
        ("AWS hoặc Terraform", 2),
    ],
)
def test_clear_structural_enumerations_are_reported_without_rewrite(
    label: str,
    count: int,
    normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "Synthetic.",
            "responsibilities": [],
            "required_skills": [
                {"name": label, "confidence": 0.8, "evidence": [label]}
            ],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.7,
        }
    )
    before = extracted.model_dump(mode="json")
    result = _guard(f"Required capability: {label}.", extracted, normalizer)
    assert _issue_dicts(result) == [
        {
            "code": "COMPOUND_SKILL_LABEL",
            "field_path": "required_skills[0].name",
            "count": count,
        }
    ]
    assert extracted.model_dump(mode="json") == before


def test_issues_are_ordered_by_provider_field_index_then_rule(
    normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": "Missing Title",
            "company": "Missing Company",
            "summary": "Not checked.",
            "responsibilities": ["Missing responsibility"],
            "required_skills": [
                {
                    "name": "Python, FastAPI",
                    "confidence": 0.8,
                    "evidence": ["Missing evidence"],
                },
                {"name": "python3", "confidence": 0.7, "evidence": []},
                {"name": "Python", "confidence": 0.6, "evidence": []},
            ],
            "preferred_skills": [
                {"name": "Py", "confidence": 0.5, "evidence": []},
            ],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": "Missing Location",
            "work_mode": "unknown",
            "extraction_confidence": 0.3,
        }
    )
    result = _guard("Retained synthetic source.", extracted, normalizer)
    assert [issue["code"] for issue in _issue_dicts(result)] == [
        "METADATA_NOT_IN_SOURCE",
        "METADATA_NOT_IN_SOURCE",
        "RESPONSIBILITY_NOT_IN_SOURCE",
        "COMPOUND_SKILL_LABEL",
        "EVIDENCE_NOT_IN_SOURCE",
        "DUPLICATE_SKILL",
        "SKILL_GROUP_CONFLICT",
        "METADATA_NOT_IN_SOURCE",
    ]
    assert [issue["field_path"] for issue in _issue_dicts(result)] == [
        "title",
        "company",
        "responsibilities[0]",
        "required_skills[0].name",
        "required_skills[0].evidence[0]",
        "required_skills[2].name",
        "preferred_skills[0].name",
        "location",
    ]


def test_issue_list_is_bounded_with_safe_omitted_count(
    normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "Synthetic.",
            "responsibilities": [
                f"Missing responsibility {index}" for index in range(25)
            ],
            "required_skills": [],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.2,
        }
    )
    result = _guard("Retained synthetic source.", extracted, normalizer)
    module = _guard_module()
    assert len(result.issues) == module.MAX_GUARD_ISSUES
    assert module.MAX_GUARD_ISSUES == 20
    assert result.omitted_issue_count == 5
    assert result.issues[-1].field_path == "responsibilities[19]"


def test_guard_is_deterministic_non_mutating_and_has_safe_reprs(
    normalizer: SkillNormalizer,
) -> None:
    extracted = _extracted(
        {
            "title": None,
            "company": None,
            "summary": "provider-summary-marker",
            "responsibilities": [],
            "required_skills": [
                {
                    "name": "Python private-label-marker",
                    "confidence": 0.8,
                    "evidence": ["private-evidence-marker"],
                }
            ],
            "preferred_skills": [],
            "seniority": "unknown",
            "min_experience_years": None,
            "max_experience_years": None,
            "location": None,
            "work_mode": "unknown",
            "extraction_confidence": 0.5,
        }
    )
    before = extracted.model_dump(mode="json")
    first = _issue_dicts(
        _guard("retained-source-marker", extracted, normalizer)
    )
    second = _issue_dicts(
        _guard("retained-source-marker", extracted, normalizer)
    )
    assert first == second
    assert extracted.model_dump(mode="json") == before
    result = _guard("retained-source-marker", extracted, normalizer)
    safe_repr = repr(result) + repr(result.issues)
    forbidden = (
        "retained-source-marker",
        "provider-summary-marker",
        "private-label-marker",
        "private-evidence-marker",
    )
    assert all(marker not in safe_repr for marker in forbidden)


def test_guard_import_hygiene() -> None:
    module = _guard_module()
    assert module.__name__ == "app.services.jd_extraction_guard"
    source = GUARD_SOURCE.read_text(encoding="utf-8")
    forbidden_prefixes = (
        "app.adapters",
        "app.api",
        "app.db",
        "app.graph",
        "fastapi",
        "httpx",
        "langchain",
        "logging",
        "neo4j",
        "sqlalchemy",
    )
    assert not any(
        f"import {prefix}" in source or f"from {prefix}" in source
        for prefix in forbidden_prefixes
    )
    assert "_PUNCTUATION_EXCEPTIONS" not in source
    assert "_contains_token_sequence" not in source
    assert "token_labels" not in source
    assert "from app.services.skill_assertion_guard import" in source
