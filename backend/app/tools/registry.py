"""Injected tool registry for the single-Agent graph (Plan 3 §7.5).

Production Phase 2 ships an empty registry — no domain tools and no test-only
helpers. Tests inject side-effect-free fakes through the same interface without
changing graph construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ToolRegistry:
    """Minimal injectable registry of LangChain tools / callables.

    Does not persist, call HTTP routes, or open database sessions. Callers
    (graph factory, later runner) inject the list; production uses
    :func:`production_registry`.
    """

    def __init__(self, tools: Sequence[Any] | None = None) -> None:
        self._tools: list[Any] = list(tools or ())

    def list_tools(self) -> list[Any]:
        """Return a shallow copy of registered tools in registration order."""
        return list(self._tools)

    def tool_names(self) -> list[str]:
        """Return registered tool names (empty when nothing is registered)."""
        names: list[str] = []
        for tool in self._tools:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name.strip():
                names.append(name)
            elif callable(tool):
                fn_name = getattr(tool, "__name__", "")
                if fn_name:
                    names.append(fn_name)
        return names

    def is_empty(self) -> bool:
        """True when no tools are registered (production Phase 2 default)."""
        return not self._tools


def production_registry() -> ToolRegistry:
    """Return the shipped production registry: zero tools.

    Domain or test-only tools must never be registered here. Tests construct
    :class:`ToolRegistry` with injected fakes only.
    """
    return ToolRegistry()
