"""Registration / runtime seam for Agent tools.

Production starts empty: later domain tools register through this seam only.
Synthetic transport-proof tools must live in tests and be injected at graph
build time — never registered on the production default instance at import or
application startup.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from langchain_core.tools import BaseTool

# Master §13 seven domain tools — registration names reserved for later phases.
# ``match_jobs`` remains reserved only; production must not implement it here.
LATER_PHASE_DOMAIN_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
    }
)


class ToolRegistryError(ValueError):
    """Tool registration failed closed (stable message; no secrets)."""


class ToolRegistry:
    """In-memory name → tool registry used by the single Agent graph builder."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register one tool by its ``name``. Rejects duplicates and empty names."""
        if not isinstance(tool, BaseTool):
            raise ToolRegistryError("tool must be a BaseTool")
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ToolRegistryError("tool name required")
        key = name.strip()
        if key in self._tools:
            raise ToolRegistryError("duplicate tool name")
        self._tools[key] = tool

    def register_many(self, tools: Iterable[BaseTool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> BaseTool | None:
        if not isinstance(name, str):
            return None
        return self._tools.get(name.strip())

    def list_tools(self) -> list[BaseTool]:
        """Stable sorted tool list for ``bind_tools`` / ``ToolNode``."""
        return [self._tools[k] for k in sorted(self._tools)]

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip() in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def clear(self) -> None:
        """Remove all registrations (test isolation only)."""
        self._tools.clear()

    def replace_all(self, tools: Sequence[BaseTool]) -> None:
        """Replace the full set (test injection)."""
        self.clear()
        self.register_many(tools)


# Four accepted Candidate tools (Plan 4) retained as a named subset.
CURRENT_PROFILE_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
    }
)

# Production Agent surface after Plan 5 Batch04: four Candidate + two Job tools.
# ``match_jobs`` is intentionally absent (reserved only).
PRODUCTION_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
    }
)


def create_production_registry(tools: Iterable[BaseTool]) -> ToolRegistry:
    """Register exactly the six production tools implemented at this boundary."""
    registry = ToolRegistry()
    registry.register_many(tools)
    if registry.names() != PRODUCTION_TOOL_NAMES:
        raise ToolRegistryError("invalid production tool set")
    if "match_jobs" in registry:
        raise ToolRegistryError("match_jobs must not be registered")
    return registry


__all__ = [
    "CURRENT_PROFILE_TOOL_NAMES",
    "LATER_PHASE_DOMAIN_TOOL_NAMES",
    "PRODUCTION_TOOL_NAMES",
    "ToolRegistry",
    "ToolRegistryError",
    "create_production_registry",
]
