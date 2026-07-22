"""Profession-neutral pure primitives for CV/JD skill assertion guards."""

from __future__ import annotations

import ast
import importlib
import importlib.util
from dataclasses import fields
from pathlib import Path
from types import ModuleType


def _module() -> ModuleType:
    assert importlib.util.find_spec("app.services.skill_assertion_guard") is not None, (
        "shared skill assertion guard module is missing"
    )
    return importlib.import_module("app.services.skill_assertion_guard")


def test_normalization_and_source_grounding_are_nfkc_whitespace_casefold() -> None:
    module = _module()
    normalize = getattr(module, "normalize_assertion_text", None)
    grounded = getattr(module, "is_source_grounded", None)
    assert callable(normalize)
    assert callable(grounded)
    assert normalize("  Stra\u00dfe\u00a0\uff21\uff24\uff33  ") == "strasse ads"
    source = "Revenue  FORECASTING and budget planning"
    assert grounded("revenue forecasting", source) is True
    assert grounded("risk analysis", source) is False
    assert grounded("\t", source) is True


def test_heading_comparison_is_exact_and_profession_neutral() -> None:
    module = _module()
    matches_heading = getattr(module, "matches_heading", None)
    assert callable(matches_heading)
    headings = [" \uff23\uff4f\uff52\uff45 Competencies ", "EXPERIENCE"]
    assert matches_heading("core competencies", headings) is True
    assert matches_heading("Core Competencies - SEO", headings) is False


def test_group_prefix_detection_requires_a_colon_and_nonempty_suffix() -> None:
    module = _module()
    is_group_prefix = getattr(module, "is_group_label_in_source", None)
    assert callable(is_group_prefix)
    source = "Campaign Methods: Audience Research and measurement"
    assert is_group_prefix("Campaign Methods", source) is True
    assert is_group_prefix("Audience Research", source) is False
    assert is_group_prefix("Campaign Methods", "Campaign Methods") is False
    assert (
        is_group_prefix("Service Design/Research", "Service Design/Research") is False
    )


def test_structural_compound_detection_uses_shape_not_skill_dictionary() -> None:
    module = _module()
    count_parts = getattr(module, "structural_compound_part_count", None)
    assert callable(count_parts)
    assert count_parts("Campaign Strategy, Content Planning") == 2
    assert count_parts("Budgeting | Revenue Forecasting | Risk Analysis") == 3
    assert count_parts("SEO / SEM") == 2
    assert count_parts("SEO/SEM") is None
    assert count_parts("Research and Development") is None
    assert count_parts("C/C++") is None
    assert (
        count_parts(
            "Research, Development",
            approved_atomic_labels=("Research, Development",),
        )
        is None
    )


def test_safe_issue_projection_contains_only_structural_fields() -> None:
    module = _module()
    issue_type = getattr(module, "StructuralSkillIssue", None)
    make_issue = getattr(module, "structural_issue", None)
    assert issue_type is not None
    assert callable(make_issue)
    assert {item.name for item in fields(issue_type)} == {
        "code",
        "field_path",
        "count",
    }
    issue = make_issue("COMPOUND_SKILL_LABEL", "assertions[2].name", count=3)
    assert issue.code == "COMPOUND_SKILL_LABEL"
    assert issue.field_path == "assertions[2].name"
    assert issue.count == 3
    assert "private-source-value" not in repr(issue)


def test_shared_guard_module_has_pure_import_boundary() -> None:
    module = _module()
    path = Path(module.__file__).resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not imports.intersection(
        {
            "app",
            "fastapi",
            "logging",
            "neo4j",
            "pydantic",
            "sqlalchemy",
        }
    )
