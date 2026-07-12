"""Tests for the dependency-injected production tool registry."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.tools.registry import (
    LATER_PHASE_DOMAIN_TOOL_NAMES,
    ToolRegistry,
    ToolRegistryError,
    create_production_registry,
)
from langchain_core.tools import StructuredTool
from tests.fakes.agent_tools import make_echo_label_tool


def test_production_registry_contains_only_current_candidate_tools() -> None:
    tools = [
        StructuredTool.from_function(func=lambda: "ok", name=name, description=name)
        for name in (
            "get_candidate_context",
            "propose_profile_from_cv",
            "propose_profile_update",
            "commit_profile_draft",
        )
    ]
    registry = create_production_registry(tools)
    assert registry.names() == {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
    }


def test_register_and_list_is_sorted_and_gettable() -> None:
    registry = ToolRegistry()
    echo = make_echo_label_tool()
    other = StructuredTool.from_function(
        func=lambda x: x,
        name="alpha_tool",
        description="alpha",
    )
    registry.register(echo)
    registry.register(other)
    names = [t.name for t in registry.list_tools()]
    assert names == sorted(names)
    assert registry.get("echo_label") is echo
    assert "echo_label" in registry
    assert registry.get("missing") is None


def test_duplicate_registration_rejected() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_label_tool())
    with pytest.raises(ToolRegistryError, match="duplicate"):
        registry.register(make_echo_label_tool())


def test_invalid_tool_rejected() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolRegistryError):
        registry.register(object())  # type: ignore[arg-type]


def test_replace_all_and_clear_for_test_isolation() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_label_tool())
    assert len(registry) == 1
    registry.replace_all([])
    assert len(registry) == 0
    registry.register_many([make_echo_label_tool()])
    registry.clear()
    assert len(registry) == 0


def test_later_phase_domain_tool_names_are_documented_not_registered() -> None:
    expected = {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
    }
    assert LATER_PHASE_DOMAIN_TOOL_NAMES == expected
    assert {"save_job", "query_jobs", "match_jobs"} <= LATER_PHASE_DOMAIN_TOOL_NAMES


def test_synthetic_tool_not_imported_by_production_app_modules() -> None:
    """Synthetic helpers live under tests/; production app must not import them."""
    app_root = Path(__file__).resolve().parents[2] / "app"
    pattern = re.compile(r"tests\.fakes\.agent_tools|make_echo_label_tool|echo_label")
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(app_root.parent)))
    assert offenders == []


def test_production_tools_do_not_call_internal_http() -> None:
    """Candidate tools reuse services and never call the app's HTTP surface."""
    app_root = Path(__file__).resolve().parents[2] / "app" / "tools"
    pattern = re.compile(r"requests\.|httpx\.|/api/attachments|/api/chat")
    hits: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            hits.append(f"{path}:{match.group(0)}")
    assert hits == []
