"""Tests for deterministic skill normalization and approval-only seed loading."""

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
from app.services.skill_normalization import (
    DEFAULT_SKILLS_SEED_PATH,
    SkillSeedError,
    dedupe_aliases,
    empty_skill_seed_catalog,
    load_skills_seed,
    normalize_candidate_skills,
    normalize_skill_match_key,
    provisional_canonical_key,
    skill_seed_catalog_from_data,
)

FIXTURE_SEED = (
    Path(__file__).resolve().parent.parent / "fixtures" / "skills_seed_test.yaml"
)


def _skill(
    *,
    display_name: str,
    canonical_key: str = "placeholder",
    aliases: list[str] | None = None,
    status: SkillStatus = SkillStatus.PROVISIONAL,
    confidence: float = 0.8,
    evidence: list[str] | None = None,
    proficiency: SkillProficiency = SkillProficiency.UNKNOWN,
    years: float | None = None,
    source: SkillSource = SkillSource.CV,
    excluded: bool = False,
    skill_evidence: list[str] | None = None,
    category: str | None = None,
) -> CandidateSkill:
    return CandidateSkill(
        skill=SkillRef(
            canonical_key=canonical_key,
            display_name=display_name,
            aliases=aliases or [],
            category=category,
            status=status,
            confidence=confidence,
            evidence=skill_evidence if skill_evidence is not None else ["Skills: listed"],
        ),
        proficiency=proficiency,
        years=years,
        source=source,
        excluded=excluded,
        evidence=evidence if evidence is not None else [],
    )


@pytest.fixture
def test_catalog() -> object:
    return load_skills_seed(FIXTURE_SEED)


# ---------------------------------------------------------------------------
# Match-key / provisional-key determinism
# ---------------------------------------------------------------------------


def test_normalize_match_key_unicode_and_separators() -> None:
    # NFKC + casefold: fullwidth / composed forms collapse.
    cafe = normalize_skill_match_key("Café")
    cafe_nfd = normalize_skill_match_key("Cafe\u0301")
    assert cafe == cafe_nfd

    assert normalize_skill_match_key("  CI/CD  ") == normalize_skill_match_key("ci_cd")
    assert normalize_skill_match_key("ci-cd") == normalize_skill_match_key("CI\\CD")
    assert normalize_skill_match_key("Node.js") == normalize_skill_match_key("node js")
    assert normalize_skill_match_key("Java\tScript") == normalize_skill_match_key(
        "java  script"
    )


def test_unicode_dash_and_middle_dot_match_ascii_hyphen() -> None:
    """ASCII hyphen, en dash, em dash, and middle dot share comparison keys."""
    ascii_hyphen = normalize_skill_match_key("CI-CD")
    en_dash = normalize_skill_match_key("CI\u2013CD")  # –
    em_dash = normalize_skill_match_key("CI\u2014CD")  # —
    middle_dot = normalize_skill_match_key("CI\u00b7CD")  # ·
    assert ascii_hyphen == en_dash == em_dash == middle_dot == "ci cd"

    ml_ascii = normalize_skill_match_key("machine-learning")
    ml_en = normalize_skill_match_key("machine\u2013learning")
    ml_em = normalize_skill_match_key("machine\u2014learning")
    ml_dot = normalize_skill_match_key("machine\u00b7learning")
    assert ml_ascii == ml_en == ml_em == ml_dot == "machine learning"


def test_unicode_dash_and_middle_dot_same_provisional_key() -> None:
    """Provisional canonical keys collapse the same Unicode separator variants."""
    ascii_hyphen = provisional_canonical_key("CI-CD")
    en_dash = provisional_canonical_key("CI\u2013CD")
    em_dash = provisional_canonical_key("CI\u2014CD")
    middle_dot = provisional_canonical_key("CI\u00b7CD")
    assert ascii_hyphen == en_dash == em_dash == middle_dot == "ci_cd"

    ml_ascii = provisional_canonical_key("machine-learning")
    ml_en = provisional_canonical_key("machine\u2013learning")
    ml_em = provisional_canonical_key("machine\u2014learning")
    ml_dot = provisional_canonical_key("machine\u00b7learning")
    assert ml_ascii == ml_en == ml_em == ml_dot == "machine_learning"


def test_plus_and_hash_preserved_as_meaningful_labels() -> None:
    """Technology labels C++ and C# keep + and # through match and provisional keys."""
    assert normalize_skill_match_key("C++") == "c++"
    assert normalize_skill_match_key("C#") == "c#"
    assert provisional_canonical_key("C++") == "c++"
    assert provisional_canonical_key("C#") == "c#"
    # Separators still collapse; +/# are not treated as separators.
    assert normalize_skill_match_key("C++ / CLI") != normalize_skill_match_key("C")
    assert "+" in provisional_canonical_key("C++")
    assert "#" in provisional_canonical_key("C#")


def test_provisional_key_is_deterministic_and_stable() -> None:
    a = provisional_canonical_key("  Rust  ")
    b = provisional_canonical_key("rust")
    assert a == b == "rust"
    assert provisional_canonical_key("CI/CD") == provisional_canonical_key("ci_cd")
    assert provisional_canonical_key("Some Skill Name") == "some_skill_name"


def test_provisional_key_rejects_empty() -> None:
    with pytest.raises(ValueError):
        provisional_canonical_key("   ")
    with pytest.raises(ValueError):
        provisional_canonical_key("@@@")


def test_dedupe_aliases_stable_order() -> None:
    out = dedupe_aliases(["Python 3", "python3", "  PY  ", "python3", "Go"])
    # Unique by match key; ordered by match key.
    assert out == sorted(out, key=normalize_skill_match_key)
    match_keys = [normalize_skill_match_key(x) for x in out]
    assert len(match_keys) == len(set(match_keys))
    assert normalize_skill_match_key("python3") in match_keys
    assert normalize_skill_match_key("go") in match_keys


# ---------------------------------------------------------------------------
# Seed loading
# ---------------------------------------------------------------------------


def test_load_production_seed_is_empty_and_valid() -> None:
    catalog = load_skills_seed(DEFAULT_SKILLS_SEED_PATH)
    assert len(catalog) == 0
    assert catalog.resolve(normalize_skill_match_key("python")) is None


def test_load_synthetic_test_seed_aliases(test_catalog: object) -> None:
    catalog = test_catalog
    assert catalog is not None
    py = catalog.resolve(normalize_skill_match_key("python3"))  # type: ignore[attr-defined]
    assert py is not None
    assert py.canonical_key == "python"
    assert py.display_name == "Python"
    assert py.category == "programming_language"
    assert catalog.resolve(normalize_skill_match_key("JS")).canonical_key == "javascript"  # type: ignore[attr-defined]
    assert catalog.resolve(normalize_skill_match_key("CI/CD")).canonical_key == "ci_cd"  # type: ignore[attr-defined]


def test_malformed_seed_not_a_mapping() -> None:
    with pytest.raises(SkillSeedError):
        skill_seed_catalog_from_data(["not", "a", "map"])


def test_malformed_seed_skills_not_list() -> None:
    with pytest.raises(SkillSeedError, match="skills"):
        skill_seed_catalog_from_data({"skills": "python"})


def test_malformed_seed_missing_canonical_key() -> None:
    with pytest.raises(SkillSeedError, match="canonical_key"):
        skill_seed_catalog_from_data(
            {
                "skills": [
                    {"display_name": "Python", "aliases": ["py"]},
                ]
            }
        )


def test_malformed_seed_duplicate_alias_conflict() -> None:
    with pytest.raises(SkillSeedError, match="maps to both"):
        skill_seed_catalog_from_data(
            {
                "skills": [
                    {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": ["py"],
                    },
                    {
                        "canonical_key": "pytorch",
                        "display_name": "PyTorch",
                        "aliases": ["py"],
                    },
                ]
            }
        )


def test_malformed_seed_rejects_related_to() -> None:
    with pytest.raises(SkillSeedError, match="related"):
        skill_seed_catalog_from_data(
            {
                "skills": [
                    {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": [],
                        "related_to": ["java"],
                    }
                ]
            }
        )


def test_malformed_seed_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SkillSeedError, match="not found"):
        load_skills_seed(tmp_path / "nope.yaml")


def test_malformed_seed_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("skills: [\n  - canonical_key: [unterminated\n", encoding="utf-8")
    with pytest.raises(SkillSeedError, match="invalid YAML"):
        load_skills_seed(bad)


def test_empty_catalog_helper() -> None:
    catalog = empty_skill_seed_catalog()
    assert len(catalog) == 0


# ---------------------------------------------------------------------------
# normalize_candidate_skills
# ---------------------------------------------------------------------------


def test_verified_alias_from_seed(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [_skill(display_name="python3", confidence=0.7)],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "python"
    assert out[0].skill.display_name == "Python"
    assert out[0].skill.status is SkillStatus.VERIFIED
    assert out[0].skill.confidence == 0.7
    assert out[0].skill.category == "programming_language"


def test_unresolved_skill_is_provisional(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [_skill(display_name="Zig", canonical_key="zig_raw")],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.status is SkillStatus.PROVISIONAL
    assert out[0].skill.canonical_key == "zig"
    assert out[0].skill.display_name == "Zig"


def test_empty_production_seed_marks_all_provisional() -> None:
    catalog = load_skills_seed(DEFAULT_SKILLS_SEED_PATH)
    out = normalize_candidate_skills(
        [
            _skill(display_name="Python"),
            _skill(display_name="JavaScript"),
        ],
        catalog=catalog,
    )
    assert all(s.skill.status is SkillStatus.PROVISIONAL for s in out)
    assert {s.skill.canonical_key for s in out} == {"python", "javascript"}


def test_separator_and_unicode_alias_resolution(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(display_name="CI/CD"),
            _skill(display_name="java script"),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    keys = [s.skill.canonical_key for s in out]
    assert keys == sorted(keys)
    assert "ci_cd" in keys
    assert "javascript" in keys
    assert all(s.skill.status is SkillStatus.VERIFIED for s in out)


def test_duplicate_aliases_collapse_deterministically(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(display_name="Python", confidence=0.5),
            _skill(display_name="python3", confidence=0.9),
            _skill(display_name="PY", confidence=0.1),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "python"
    # First occurrence kept when equal priority.
    assert out[0].skill.confidence == 0.5


def test_stable_ordering_by_canonical_key(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(display_name="Zig"),
            _skill(display_name="Python"),
            _skill(display_name="Rust"),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    keys = [s.skill.canonical_key for s in out]
    assert keys == sorted(keys)


def test_existing_canonical_key_preferred_over_new_provisional(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [_skill(display_name="Rust Lang", canonical_key="new_rust")],
        catalog=catalog,  # type: ignore[arg-type]
        existing_canonical_keys=["rust_lang"],
    )
    assert len(out) == 1
    assert out[0].skill.canonical_key == "rust_lang"
    assert out[0].skill.status is SkillStatus.PROVISIONAL


def test_excluded_skill_not_readded_from_cv(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(display_name="python3", source=SkillSource.CV, excluded=False),
            _skill(display_name="Zig", source=SkillSource.CV),
        ],
        catalog=catalog,  # type: ignore[arg-type]
        excluded_canonical_keys=["python"],
    )
    keys = {s.skill.canonical_key for s in out}
    assert "python" not in keys
    assert "zig" in keys


def test_excluded_user_correction_preserved_not_duplicated(
    test_catalog: object,
) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(
                display_name="Python",
                source=SkillSource.USER_CORRECTION,
                excluded=True,
                evidence=["User excluded Python"],
            ),
            _skill(
                display_name="python3",
                source=SkillSource.CV,
                excluded=False,
                evidence=["Skills section"],
            ),
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    assert out[0].excluded is True
    assert out[0].source is SkillSource.USER_CORRECTION
    assert out[0].skill.canonical_key == "python"
    assert out[0].evidence == ["User excluded Python"]


def test_preserves_proficiency_years_source_evidence(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [
            _skill(
                display_name="python3",
                proficiency=SkillProficiency.ADVANCED,
                years=5.0,
                source=SkillSource.CV,
                evidence=["2018-2023 Python backend"],
                skill_evidence=["Skills: Python 5 years"],
                confidence=0.91,
            )
        ],
        catalog=catalog,  # type: ignore[arg-type]
    )
    assert len(out) == 1
    skill = out[0]
    assert skill.proficiency is SkillProficiency.ADVANCED
    assert skill.years == 5.0
    assert skill.source is SkillSource.CV
    assert skill.excluded is False
    assert skill.evidence == ["2018-2023 Python backend"]
    assert skill.skill.evidence == ["Skills: Python 5 years"]
    assert skill.skill.confidence == 0.91
    assert skill.skill.status is SkillStatus.VERIFIED


def test_no_related_to_or_graph_trust_fields(test_catalog: object) -> None:
    catalog = test_catalog
    out = normalize_candidate_skills(
        [_skill(display_name="Python")],
        catalog=catalog,  # type: ignore[arg-type]
    )
    dumped = out[0].model_dump()
    assert "related_to" not in dumped
    assert "related_to" not in dumped["skill"]
    # Round-trip forbids extras.
    CandidateSkill.model_validate(dumped)


def test_same_input_same_seed_same_output(test_catalog: object) -> None:
    catalog = test_catalog
    skills = [
        _skill(display_name="CI/CD"),
        _skill(display_name="Zig"),
        _skill(display_name="python3"),
        _skill(display_name="  zig  "),
    ]
    a = normalize_candidate_skills(skills, catalog=catalog)  # type: ignore[arg-type]
    b = normalize_candidate_skills(skills, catalog=catalog)  # type: ignore[arg-type]
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
