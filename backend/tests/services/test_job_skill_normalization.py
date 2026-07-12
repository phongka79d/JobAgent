"""Job skill normalization + Candidate/Job parity (Plan 5 §7.5 / Master §9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.schemas.candidate import (
    CandidateSkill,
    SkillProficiency,
    SkillRef,
    SkillSource,
    SkillStatus,
)
from app.schemas.job_post import JobSkill
from app.services.skill_normalization import (
    DEFAULT_SKILLS_SEED_PATH,
    load_skills_seed,
    normalize_candidate_skills,
    normalize_job_skill_lists,
    normalize_job_skills,
    normalize_skill_match_key,
    provisional_canonical_key,
    resolve_skill_ref,
)

FIXTURE_SEED = (
    Path(__file__).resolve().parent.parent / "fixtures" / "skills_seed_test.yaml"
)


def _skill_ref(
    *,
    display_name: str,
    canonical_key: str = "placeholder",
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.PROVISIONAL,
    confidence: float = 0.8,
    evidence: list[str] | None = None,
    category: str | None = None,
) -> SkillRef:
    return SkillRef(
        canonical_key=canonical_key,
        display_name=display_name,
        aliases=aliases or [],
        category=category,
        status=status,
        confidence=confidence,
        evidence=evidence if evidence is not None else ["Skills: listed"],
    )


def _job_skill(
    *,
    display_name: str,
    canonical_key: str = "placeholder",
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.PROVISIONAL,
    skill_confidence: float = 0.8,
    skill_evidence: list[str] | None = None,
    relationship_confidence: float = 0.85,
    relationship_evidence: list[str] | None = None,
    category: str | None = None,
) -> JobSkill:
    return JobSkill(
        skill=_skill_ref(
            display_name=display_name,
            canonical_key=canonical_key,
            aliases=aliases,
            status=status,
            confidence=skill_confidence,
            evidence=skill_evidence,
            category=category,
        ),
        confidence=relationship_confidence,
        evidence=(
            relationship_evidence
            if relationship_evidence is not None
            else ["Required: listed"]
        ),
    )


def _candidate_skill(
    *,
    display_name: str,
    canonical_key: str = "placeholder",
    confidence: float = 0.8,
    skill_evidence: list[str] | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=_skill_ref(
            display_name=display_name,
            canonical_key=canonical_key,
            confidence=confidence,
            evidence=skill_evidence,
        ),
        proficiency=SkillProficiency.UNKNOWN,
        years=None,
        source=SkillSource.CV,
        excluded=False,
        evidence=[],
    )


@pytest.fixture
def test_catalog() -> object:
    return load_skills_seed(FIXTURE_SEED)


# ---------------------------------------------------------------------------
# Shared resolve_skill_ref
# ---------------------------------------------------------------------------


def test_resolve_skill_ref_verified_from_seed(test_catalog: object) -> None:
    catalog = test_catalog
    resolved = resolve_skill_ref(
        _skill_ref(display_name="python3", confidence=0.71),
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert resolved.canonical_key == "python"
    assert resolved.display_name == "Python"
    assert resolved.status is SkillStatus.VERIFIED
    assert resolved.confidence == 0.71
    assert resolved.category == "programming_language"


def test_resolve_skill_ref_provisional_unknown(test_catalog: object) -> None:
    catalog = test_catalog
    resolved = resolve_skill_ref(
        _skill_ref(display_name="Zig", canonical_key="zig_raw"),
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert resolved.status is SkillStatus.PROVISIONAL
    assert resolved.canonical_key == "zig"
    assert resolved.display_name == "Zig"


def test_resolve_skill_ref_reuses_existing_without_verification(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    resolved = resolve_skill_ref(
        _skill_ref(display_name="Rust Lang", canonical_key="new_rust"),
        catalog=catalog,  # type: ignore[arg-type]
        existing_canonical_keys=["rust_lang"],
    )
    assert resolved.canonical_key == "rust_lang"
    assert resolved.status is SkillStatus.PROVISIONAL


# ---------------------------------------------------------------------------
# normalize_job_skills
# ---------------------------------------------------------------------------


def test_job_verified_alias_from_seed(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [_job_skill(display_name="python3", skill_confidence=0.7)],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "python"
    assert out[0].skill.display_name == "Python"
    assert out[0].skill.status is SkillStatus.VERIFIED
    assert out[0].skill.confidence == 0.7
    assert out[0].skill.category == "programming_language"


def test_job_unresolved_is_provisional(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [_job_skill(display_name="Zig", canonical_key="zig_raw")],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.status is SkillStatus.PROVISIONAL
    assert out[0].skill.canonical_key == "zig"


def test_job_preserves_relationship_confidence_and_evidence(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [
            _job_skill(
                display_name="python3",
                skill_confidence=0.91,
                skill_evidence=["Skills: Python"],
                relationship_confidence=0.66,
                relationship_evidence=["Required: 3+ years Python"],
            )
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].confidence == 0.66
    assert out[0].evidence == ["Required: 3+ years Python"]
    assert out[0].skill.confidence == 0.91
    assert out[0].skill.evidence == ["Skills: Python"]
    assert out[0].skill.status is SkillStatus.VERIFIED


def test_job_duplicate_aliases_collapse_first_wins(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [
            _job_skill(
                display_name="Python",
                relationship_confidence=0.5,
                relationship_evidence=["first"],
            ),
            _job_skill(
                display_name="python3",
                relationship_confidence=0.9,
                relationship_evidence=["second"],
            ),
            _job_skill(
                display_name="PY",
                relationship_confidence=0.1,
                relationship_evidence=["third"],
            ),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "python"
    assert out[0].confidence == 0.5
    assert out[0].evidence == ["first"]


def test_job_stable_ordering_by_canonical_key(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [
            _job_skill(display_name="Zig"),
            _job_skill(display_name="Python"),
            _job_skill(display_name="Rust"),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    keys = [s.skill.canonical_key for s in out]
    assert keys == sorted(keys)


def test_job_existing_canonical_key_reused_not_verified(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [_job_skill(display_name="Rust Lang", canonical_key="new_rust")],
        catalog=catalog,  # type: ignore[arg-type]
        existing_canonical_keys=["rust_lang"],
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "rust_lang"
    assert out[0].skill.status is SkillStatus.PROVISIONAL


def test_job_empty_production_seed_all_provisional() -> None:
    catalog = load_skills_seed(DEFAULT_SKILLS_SEED_PATH)
    out = normalize_job_skills(
        [
            _job_skill(display_name="Python"),
            _job_skill(display_name="JavaScript"),
        ],
        catalog=catalog,
    )
    assert all(s.skill.status is SkillStatus.PROVISIONAL for s in out)
    assert {s.skill.canonical_key for s in out} == {"python", "javascript"}


def test_job_no_related_to_or_graph_trust_fields(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_job_skills(
        [_job_skill(display_name="Python")],
        catalog=catalog,  # type: ignore[arg-type]
    )
    dumped = out[0].model_dump()
    assert "related_to" not in dumped
    assert "related_to" not in dumped["skill"]
    assert "weight" not in dumped
    JobSkill.model_validate(dumped)


def test_job_same_input_same_seed_same_output(test_catalog: object) -> None:
    catalog = test_catalog
    skills = [
        _job_skill(display_name="CI/CD"),
        _job_skill(display_name="Zig"),
        _job_skill(display_name="python3"),
        _job_skill(display_name="  zig  "),
    ]
    a = normalize_job_skills(skills, catalog=catalog)  # type: ignore[arg-type]
    b = normalize_job_skills(skills, catalog=catalog)  # type: ignore[arg-type]
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]


# ---------------------------------------------------------------------------
# required / preferred list adapter
# ---------------------------------------------------------------------------


def test_job_skill_lists_dedupe_and_required_wins_over_preferred(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    required, preferred = normalize_job_skill_lists(
        required_skills=[
            _job_skill(
                display_name="python3",
                relationship_confidence=0.9,
                relationship_evidence=["Required: Python"],
            ),
            _job_skill(
                display_name="Python",
                relationship_confidence=0.1,
                relationship_evidence=["dup"],
            ),
        ],
        preferred_skills=[
            _job_skill(
                display_name="JS",
                relationship_confidence=0.7,
                relationship_evidence=["Nice: JavaScript"],
            ),
            _job_skill(
                display_name="python3",
                relationship_confidence=0.5,
                relationship_evidence=["also preferred"],
            ),
            _job_skill(
                display_name="Kubernetes",
                relationship_confidence=0.6,
                relationship_evidence=["Nice: K8s"],
            ),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert [s.skill.canonical_key for s in required] == ["python"]
    assert required[0].confidence == 0.9
    preferred_keys = [s.skill.canonical_key for s in preferred]
    assert preferred_keys == sorted(preferred_keys)
    assert "python" not in preferred_keys
    assert "javascript" in preferred_keys
    assert "kubernetes" in preferred_keys


# ---------------------------------------------------------------------------
# Candidate ↔ Job parity
# ---------------------------------------------------------------------------


def test_candidate_job_parity_seed_canonical_status_aliases(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    surfaces = ["python3", "CI/CD", "java script", "Zig"]

    candidate_out = normalize_candidate_skills(
        [_candidate_skill(display_name=name) for name in surfaces],
        catalog=catalog,  # type: ignore[arg-type]
    )
    job_out = normalize_job_skills(
        [_job_skill(display_name=name) for name in surfaces],
        catalog=catalog,  # type: ignore[arg-type]
    )

    candidate_by_key = {s.skill.canonical_key: s.skill for s in candidate_out}
    job_by_key = {s.skill.canonical_key: s.skill for s in job_out}
    assert set(candidate_by_key) == set(job_by_key)

    for key in candidate_by_key:
        c_ref = candidate_by_key[key]
        j_ref = job_by_key[key]
        assert c_ref.canonical_key == j_ref.canonical_key
        assert c_ref.display_name == j_ref.display_name
        assert c_ref.status is j_ref.status
        assert c_ref.category == j_ref.category
        assert c_ref.aliases == j_ref.aliases


def test_candidate_job_parity_provisional_keys(test_catalog: object) -> None:
    catalog = test_catalog
    unknown = "Machine Learning Ops"
    expected_key = provisional_canonical_key(unknown)

    candidate_out = normalize_candidate_skills(
        [_candidate_skill(display_name=unknown)],
        catalog=catalog,  # type: ignore[arg-type]
    )
    job_out = normalize_job_skills(
        [_job_skill(display_name=unknown)],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert candidate_out[0].skill.canonical_key == expected_key
    assert job_out[0].skill.canonical_key == expected_key
    assert candidate_out[0].skill.status is SkillStatus.PROVISIONAL
    assert job_out[0].skill.status is SkillStatus.PROVISIONAL


def test_candidate_job_parity_existing_canonical_reuse(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    existing = ["rust_lang"]
    candidate_out = normalize_candidate_skills(
        [_candidate_skill(display_name="Rust Lang", canonical_key="new_rust")],
        catalog=catalog,  # type: ignore[arg-type]
        existing_canonical_keys=existing,
    )
    job_out = normalize_job_skills(
        [_job_skill(display_name="Rust Lang", canonical_key="new_rust")],
        catalog=catalog,  # type: ignore[arg-type]
        existing_canonical_keys=existing,
    )
    assert candidate_out[0].skill.canonical_key == "rust_lang"
    assert job_out[0].skill.canonical_key == "rust_lang"
    assert candidate_out[0].skill.status is SkillStatus.PROVISIONAL
    assert job_out[0].skill.status is SkillStatus.PROVISIONAL


def test_candidate_exclusions_unchanged_by_job_adapter(
    test_catalog: object,
) -> None:
    """Job path has no exclusion semantics; Candidate exclusions still work."""
    catalog = test_catalog
    candidate_out = normalize_candidate_skills(
        [
            _candidate_skill(display_name="python3"),
            _candidate_skill(display_name="Zig"),
        ],
        catalog=catalog,  # type: ignore[arg-type]
        excluded_canonical_keys=["python"],
    )
    keys = {s.skill.canonical_key for s in candidate_out}
    assert "python" not in keys
    assert "zig" in keys

    job_out = normalize_job_skills(
        [
            _job_skill(display_name="python3"),
            _job_skill(display_name="Zig"),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    job_keys = {s.skill.canonical_key for s in job_out}
    assert "python" in job_keys
    assert "zig" in job_keys


def test_production_seed_remains_empty() -> None:
    catalog = load_skills_seed(DEFAULT_SKILLS_SEED_PATH)
    assert len(catalog) == 0
    assert catalog.resolve(normalize_skill_match_key("python")) is None
