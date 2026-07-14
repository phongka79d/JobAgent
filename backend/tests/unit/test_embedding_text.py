"""Unit tests for embedding whitespace normalizer and Job v1 text (Plan 5 §7.5)."""

from __future__ import annotations

from typing import Any

from app.schemas.jobs import JobPostExtraction, JobSkill
from app.schemas.skills import SkillRef
from app.services.embedding_text import (
    JOB_EMBEDDING_TEXT_VERSION,
    build_job_embedding_text_v1,
    normalize_embedding_whitespace,
)


def _skill(
    display_name: str,
    *,
    key: str | None = None,
    confidence: float = 0.9,
) -> JobSkill:
    canonical = key or display_name.casefold().replace(" ", "_")
    return JobSkill(
        skill=SkillRef(
            canonical_key=canonical,
            display_name=display_name,
            aliases=[],
            category="language",
        ),
        confidence=confidence,
        evidence=["from jd"],
    )


def _extraction(**overrides: Any) -> JobPostExtraction:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs.",
        "responsibilities": ["Design services", "Review code"],
        "required_skills": [_skill("Python"), _skill("FastAPI")],
        "preferred_skills": [_skill("PostgreSQL")],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": None,
        "location": "Remote",
        "work_mode": "remote",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return JobPostExtraction.model_validate(base)


# ---------------------------------------------------------------------------
# Whitespace normalizer
# ---------------------------------------------------------------------------


def test_normalize_collapses_and_strips() -> None:
    assert normalize_embedding_whitespace("  hello   world\t\n") == "hello world"


def test_normalize_empty_and_none_like() -> None:
    assert normalize_embedding_whitespace("") == ""
    assert normalize_embedding_whitespace("   \n\t  ") == ""


def test_normalize_preserves_case_and_punctuation() -> None:
    # Embedding whitespace only — not skill NFKC/casefold.
    assert normalize_embedding_whitespace("  React.js  ") == "React.js"
    assert normalize_embedding_whitespace("C++") == "C++"


# ---------------------------------------------------------------------------
# Versioned Job representation
# ---------------------------------------------------------------------------


def test_version_marker() -> None:
    assert JOB_EMBEDDING_TEXT_VERSION == "v1"


def test_field_order_and_canonical_display_names() -> None:
    text = build_job_embedding_text_v1(_extraction())
    # Sections appear in exact approved order.
    title_i = text.index("title:")
    summary_i = text.index("summary:")
    resp_i = text.index("responsibilities:")
    req_i = text.index("required_skills:")
    pref_i = text.index("preferred_skills:")
    assert title_i < summary_i < resp_i < req_i < pref_i

    assert "Backend Engineer" in text
    assert "Build APIs." in text
    assert "- Design services" in text
    assert "- Review code" in text
    assert "Python" in text
    assert "FastAPI" in text
    assert "PostgreSQL" in text
    # Canonical display names, not aliases/keys alone as the skill label source.
    assert "python" not in text.split("required_skills:")[1].split("preferred")[0]


def test_equivalent_inputs_byte_identical() -> None:
    a = build_job_embedding_text_v1(_extraction())
    b = build_job_embedding_text_v1(_extraction())
    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")


def test_whitespace_in_fields_normalized_deterministically() -> None:
    messy = _extraction(
        title="  Backend   Engineer  ",
        summary="Build\n\nAPIs.",
        responsibilities=["  Design   services  ", "Review\tcode"],
        required_skills=[_skill("  Python  ")],
    )
    text = build_job_embedding_text_v1(messy)
    clean = build_job_embedding_text_v1(
        _extraction(
            title="Backend Engineer",
            summary="Build APIs.",
            responsibilities=["Design services", "Review code"],
            required_skills=[_skill("Python")],
        )
    )
    assert text == clean


def test_null_title_and_empty_lists() -> None:
    text = build_job_embedding_text_v1(
        _extraction(
            title=None,
            responsibilities=[],
            required_skills=[],
            preferred_skills=[],
        )
    )
    assert "title:" in text
    assert "summary:" in text
    assert "responsibilities:" in text
    assert "required_skills:" in text
    assert "preferred_skills:" in text
    # No company (not in approved field list).
    assert "Acme" not in text
    assert "company" not in text.lower()


def test_no_e5_prefix_no_quality_no_html() -> None:
    text = build_job_embedding_text_v1(_extraction())
    lower = text.lower()
    assert not lower.startswith("query:")
    assert not lower.startswith("passage:")
    assert "query:" not in lower
    assert "passage:" not in lower
    assert "jd_quality" not in lower
    assert "unscorable" not in lower
    assert "<html" not in lower
    assert "<p>" not in lower


def test_company_and_meta_fields_excluded() -> None:
    text = build_job_embedding_text_v1(
        _extraction(
            company="SecretCo",
            location="Berlin",
            seniority="senior",
            work_mode="hybrid",
        )
    )
    assert "SecretCo" not in text
    assert "Berlin" not in text
    assert "senior" not in text
    assert "hybrid" not in text


def test_skill_uses_display_name_not_canonical_key() -> None:
    skill = JobSkill(
        skill=SkillRef(
            canonical_key="node_js",
            display_name="Node.js",
            aliases=["nodejs"],
            category="language",
        ),
        confidence=1.0,
        evidence=["Node.js required"],
    )
    text = build_job_embedding_text_v1(_extraction(required_skills=[skill]))
    req_section = text.split("required_skills:")[1].split("preferred_skills:")[0]
    assert "Node.js" in req_section
    assert "node_js" not in req_section
    assert "nodejs" not in req_section


def test_deterministic_separators_stable() -> None:
    text = build_job_embedding_text_v1(_extraction())
    # Section labels use trailing colon; list items use "- " prefix.
    assert "\n- Design services\n- Review code" in text
    assert "Python, FastAPI" in text or "Python, FastAPI" in text.replace("\n", " ")


def test_blank_responsibility_dropped() -> None:
    text = build_job_embedding_text_v1(
        _extraction(responsibilities=["  ", "Keep one", "\t"])
    )
    assert "Keep one" in text
    # Only one bullet.
    assert text.count("- ") == 1
