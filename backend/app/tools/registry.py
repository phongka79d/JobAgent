"""Injected tool registry for the single-Agent graph (Plan 3 §7.5 / Plan 4 §7.5).

Production registers exactly the three profile tools from
:func:`app.tools.profile.build_production_profile_tools`. Tests inject
side-effect-free fakes through the same :class:`ToolRegistry` interface without
changing graph construction. Later-phase job tools and test-only interrupt
helpers are never registered here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph.sync_candidate import AsyncGraphDriver
from app.services.profile_extraction import StructuredProfileInvoker
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage


class ToolRegistry:
    """Minimal injectable registry of LangChain tools / callables.

    Does not persist, call HTTP routes, or open database sessions. Callers
    (graph factory, runner, chat deps) inject the list; production uses
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
        """True when no tools are registered."""
        return not self._tools


def production_registry(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: AttachmentStorage | None = None,
    invoker: StructuredProfileInvoker | None = None,
    normalizer: SkillNormalizer | None = None,
    driver: AsyncGraphDriver | None = None,
    extract_text_fn: Callable[[Any], Any] | None = None,
    sync_fn: Callable[..., Awaitable[None]] | None = None,
    commit_fn: Callable[..., Awaitable[Any]] | None = None,
) -> ToolRegistry:
    """Return the production registry: exactly three profile tools.

    Optional dependencies are closed over by the tools (or resolved at invoke
    time when omitted). Never registers later job tools, preference-only tools,
    or test-only interrupt helpers.
    """
    # Local import keeps this module free of eager profile service construction
    # and avoids circular import at package load.
    from app.tools.profile import build_production_profile_tools

    tools = build_production_profile_tools(
        session_factory=session_factory,
        storage=storage,
        invoker=invoker,
        normalizer=normalizer,
        driver=driver,
        extract_text_fn=extract_text_fn,
        sync_fn=sync_fn,
        commit_fn=commit_fn,
    )
    return ToolRegistry(tools)
