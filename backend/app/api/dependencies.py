"""FastAPI dependency providers for thin chat transport routes.

Owns injectable seams for the chat Agent model, tool registry, and SQLite path
so tests can override production defaults without registering synthetic tools
in production. Routes stay free of construction and business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.core.settings import Settings, get_settings
from app.tools.registry import ToolRegistry, production_registry

# Injectable chat model type (production adapter or test fakes).
ChatModelLike = BaseChatModel | Runnable[Any, Any]


@dataclass(frozen=True, slots=True)
class ChatAgentDeps:
    """Request-scoped Agent injection points for turn/resume streams.

    ``model`` may be ``None`` so the runner builds the production ShopAIKey
    adapter from settings. Tests override :func:`get_chat_agent_deps` to inject
    a fake model and optional synthetic registry.
    """

    model: ChatModelLike | None
    registry: ToolRegistry
    sqlite_path: str | Path
    include_assistant_status: bool = False


def get_settings_dep(request: Request) -> Settings:
    """Return process settings (from app.state after lifespan, else cache)."""
    state = getattr(request.app, "state", None)
    settings = getattr(state, "settings", None) if state is not None else None
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def get_chat_agent_deps(request: Request) -> ChatAgentDeps:
    """Production chat deps: empty registry, deferred model, configured SQLite.

    No synthetic or domain tools. Model construction is deferred to the runner
    so this provider never opens provider connections at dependency resolution.
    """
    settings = get_settings_dep(request)
    return ChatAgentDeps(
        model=None,
        registry=production_registry(),
        sqlite_path=settings.SQLITE_PATH,
        include_assistant_status=False,
    )


__all__ = [
    "ChatAgentDeps",
    "ChatModelLike",
    "get_chat_agent_deps",
    "get_settings_dep",
]
