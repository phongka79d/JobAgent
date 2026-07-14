"""Unit tests for the sole skill taxonomy loader/normalizer (Plan 4 §7.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.settings import repo_root
from app.schemas.profile import CandidateSkill
from app.schemas.skills import SkillRef
from app.services.skill_normalization import (
    PRODUCTION_SKILLS_SEED_RELATIVE,
    SkillNormalizer,
    SkillTaxonomyError,
    comparison_fingerprint,
    derive_unknown_canonical_key,
    load_skill_taxonomy,
    load_skill_taxonomy_from_path,
    parse_skills_seed_text,
    production_skills_seed_path,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"
)


@pytest.fixture
def normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(FIXTURE_PATH)


def test_fixture_loads_through_same_parser_path() -> None:
    taxonomy = load_skill_taxonomy_from_path(FIXTURE_PATH)
    assert [s.canonical_key for s in taxonomy.skills] == [
        "fastapi",
        "python",
        "react",
        "sql",
        "typescript",
    ]
    assert len(taxonomy.relationships) == 2


def test_production_path_constant_is_repo_infrastructure_seed() -> None:
    path = production_skills_seed_path()
    monorepo = repo_root() / PRODUCTION_SKILLS_SEED_RELATIVE
    # Sole production owner — no package-data or app/resources fallback.
    assert path == monorepo
    assert path.as_posix().endswith("infrastructure/neo4j/skills_seed.yaml")
    assert monorepo.is_file()
    assert not (
        Path(__file__).resolve().parents[2]
        / "app"
        / "resources"
        / "skills_seed.yaml"
    ).is_file()


def test_unicode_whitespace_case_punctuation_alias_resolution(
    normalizer: SkillNormalizer,
) -> None:
    # NFKC compatibility form: fullwidth letters → ASCII, then alias match.
    fullwidth_python = "Ｐｙｔｈｏｎ"
    # Whitespace collapse + casefold
    spaced = "  PyThOn   3  "
    # Punctuation / separators
    punctuated_react = "React.JS"
    hyphen_react = "react-js"
    underscored = "type_script"

    py_a = normalizer.normalize_name(fullwidth_python)
    py_b = normalizer.normalize_name(spaced)
    # "python3" is an approved alias; spaced "PyThOn 3" fingerprints to python3
    assert py_a.canonical_key == "python"
    assert py_b.canonical_key == "python"
    assert py_a == py_b
    assert py_a.display_name == "Python"
    assert py_a.aliases == ["python3", "py"]
    assert py_a.category == "language"

    r1 = normalizer.normalize_name(punctuated_react)
    r2 = normalizer.normalize_name(hyphen_react)
    r3 = normalizer.normalize_name("React")
    assert r1.canonical_key == r2.canonical_key == r3.canonical_key == "react"

    ts = normalizer.normalize_name(underscored)
    assert ts.canonical_key == "typescript"
    assert ts.category == "language"


def test_equivalent_inputs_resolve_to_one_stable_skillref(
    normalizer: SkillNormalizer,
) -> None:
    variants = ["Python", "python", "PYTHON", " python ", "python3", "Py"]
    refs = normalizer.normalize_names(variants)
    assert len({r.canonical_key for r in refs}) == 1
    assert all(r == refs[0] for r in refs)


def test_unknown_is_deterministic_without_invented_metadata(
    normalizer: SkillNormalizer,
) -> None:
    a = normalizer.normalize_name("  Neo4j  Graph  ")
    b = normalizer.normalize_name("neo4j-graph")
    assert a.canonical_key == b.canonical_key == "neo4j_graph"
    assert a.aliases == []
    assert a.category is None
    assert a.display_name == "Neo4j Graph"
    # Unknowns never appear in approved relationship projections.
    assert normalizer.relationships_for(a.canonical_key) == ()
    assert not normalizer.is_seed_skill(a.canonical_key)


def test_repeats_are_stable(normalizer: SkillNormalizer) -> None:
    first = normalizer.normalize_name("Fast API")
    second = normalizer.normalize_name("fastapi")
    third = normalizer.normalize_name("Fast API")
    assert first == second == third
    assert first.canonical_key == "fastapi"


def test_approved_relationships_only_from_seed(normalizer: SkillNormalizer) -> None:
    edges = normalizer.approved_relationships()
    pairs = {(e.from_key, e.to_key, e.weight, e.source) for e in edges}
    assert pairs == {
        ("python", "fastapi", 0.6, "seed"),
        ("typescript", "react", 0.7, "seed"),
    }
    # Unknown skill has no invented RELATED_TO edge.
    assert normalizer.relationships_for("kubernetes") == ()


def test_correction_and_exclusion_fields_preserved(
    normalizer: SkillNormalizer,
) -> None:
    original = CandidateSkill(
        skill=SkillRef(
            canonical_key="not_yet_normalized",
            display_name="python3",
            aliases=[],
            category=None,
        ),
        confidence=0.42,
        proficiency="beginner",
        years=1.5,
        source="user_correction",
        excluded=True,
        evidence=["user removed this skill"],
    )
    out = normalizer.normalize_candidate_skill(original)
    assert out.skill.canonical_key == "python"
    assert out.skill.display_name == "Python"
    assert out.confidence == 0.42
    assert out.proficiency == "beginner"
    assert out.years == 1.5
    assert out.source == "user_correction"
    assert out.excluded is True
    assert out.evidence == ["user removed this skill"]


def test_duplicate_canonical_key_fails() -> None:
    payload = {
        "skills": [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": [],
                "category": None,
            },
            {
                "canonical_key": "python",
                "display_name": "Python Dup",
                "aliases": [],
                "category": None,
            },
        ],
        "relationships": [],
    }
    with pytest.raises(SkillTaxonomyError, match="duplicate canonical_key"):
        load_skill_taxonomy(payload)


def test_colliding_alias_fails() -> None:
    payload = {
        "skills": [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["py"],
                "category": "language",
            },
            {
                "canonical_key": "pytorch",
                "display_name": "PyTorch",
                "aliases": ["py"],
                "category": "framework",
            },
        ],
        "relationships": [],
    }
    with pytest.raises(SkillTaxonomyError, match="colliding"):
        load_skill_taxonomy(payload)


def test_invalid_relationship_endpoint_fails() -> None:
    payload = {
        "skills": [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": [],
                "category": None,
            }
        ],
        "relationships": [
            {"from": "python", "to": "missing", "weight": 0.5, "source": "seed"}
        ],
    }
    with pytest.raises(SkillTaxonomyError, match="not a seed skill"):
        load_skill_taxonomy(payload)


def test_invalid_relationship_weight_fails() -> None:
    payload = {
        "skills": [
            {
                "canonical_key": "a",
                "display_name": "A",
                "aliases": [],
                "category": None,
            },
            {
                "canonical_key": "b",
                "display_name": "B",
                "aliases": [],
                "category": None,
            },
        ],
        "relationships": [{"from": "a", "to": "b", "weight": 0.0, "source": "seed"}],
    }
    with pytest.raises(SkillTaxonomyError, match="weight"):
        load_skill_taxonomy(payload)

    payload["relationships"][0]["weight"] = 1.5
    with pytest.raises(SkillTaxonomyError, match="weight"):
        load_skill_taxonomy(payload)


def test_self_loop_and_duplicate_edge_fail() -> None:
    base_skills = [
        {
            "canonical_key": "a",
            "display_name": "A",
            "aliases": [],
            "category": None,
        },
        {
            "canonical_key": "b",
            "display_name": "B",
            "aliases": [],
            "category": None,
        },
    ]
    with pytest.raises(SkillTaxonomyError, match="self-loop"):
        load_skill_taxonomy(
            {
                "skills": base_skills,
                "relationships": [
                    {"from": "a", "to": "a", "weight": 0.5, "source": "seed"}
                ],
            }
        )
    with pytest.raises(SkillTaxonomyError, match="duplicate relationship"):
        load_skill_taxonomy(
            {
                "skills": base_skills,
                "relationships": [
                    {"from": "a", "to": "b", "weight": 0.5, "source": "seed"},
                    {"from": "a", "to": "b", "weight": 0.6, "source": "seed"},
                ],
            }
        )


def test_malformed_seed_text_fails() -> None:
    with pytest.raises(SkillTaxonomyError, match="JSON-compatible"):
        parse_skills_seed_text("{ not json")


def test_missing_seed_file_fails(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(SkillTaxonomyError, match="not found"):
        load_skill_taxonomy_from_path(missing)


def test_comment_stripping_then_json(tmp_path: Path) -> None:
    path = tmp_path / "mini.yaml"
    path.write_text(
        "# header comment\n"
        + json.dumps(
            {
                "skills": [
                    {
                        "canonical_key": "sql",
                        "display_name": "SQL",
                        "aliases": [],
                        "category": "data",
                    }
                ],
                "relationships": [],
            }
        ),
        encoding="utf-8",
    )
    n = SkillNormalizer.from_path(path)
    assert n.normalize_name("SQL").canonical_key == "sql"


def test_comparison_fingerprint_and_unknown_key_helpers() -> None:
    assert comparison_fingerprint("  React.JS ") == "reactjs"
    assert comparison_fingerprint("react-js") == "reactjs"
    assert derive_unknown_canonical_key("Neo4j Graph!") == "neo4j_graph"
    with pytest.raises(SkillTaxonomyError):
        derive_unknown_canonical_key("...")


def test_empty_skill_name_rejected(normalizer: SkillNormalizer) -> None:
    with pytest.raises(SkillTaxonomyError, match="empty"):
        normalizer.normalize_name("   ")
    with pytest.raises(SkillTaxonomyError, match="empty"):
        normalizer.normalize_name("...")


def test_canonical_ordering_stable() -> None:
    taxonomy = load_skill_taxonomy_from_path(FIXTURE_PATH)
    keys = [s.canonical_key for s in taxonomy.skills]
    assert keys == sorted(keys)
    rel_keys = [(e.from_key, e.to_key, e.source) for e in taxonomy.relationships]
    assert rel_keys == sorted(rel_keys)


def test_no_second_normalizer_module_imports() -> None:
    """Hygiene: normalizer module stays free of provider/graph/route I/O."""
    import ast

    src = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "skill_normalization.py"
    )
    tree = ast.parse(src.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "neo4j",
        "fastapi",
        "httpx",
        "sqlalchemy",
        "langgraph",
        "langchain",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden_prefixes
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden_prefixes
