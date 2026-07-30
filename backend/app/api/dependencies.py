"""FastAPI dependency providers for thin chat transport routes.

Owns injectable seams for the chat Agent model, tool registry, and SQLite path
so tests can override production defaults without registering synthetic tools
in production. Routes stay free of construction and business logic.

Production chat deps wire eight tools through
:func:`~app.tools.registry.production_registry`
with request-scoped storage and Neo4j driver from app lifespan state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings, get_settings
from app.db.session import get_session_factory
from app.services.cv_document_extraction import (
    ShopAIKeyStructuredCVDocumentInvoker,
)
from app.services.cv_tailoring import TailoringCoordinator
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.storage.cv_tailoring import TailoringArtifactStorage
from app.tools.registry import ToolRegistry, production_registry

# Injectable chat model type (production adapter or test fakes).
ChatModelLike = BaseChatModel | Runnable[Any, Any]


@dataclass(frozen=True, slots=True)
class ChatAgentDeps:
    """Request-scoped Agent injection points for turn/resume streams.

    ``model`` may be ``None`` so the runner builds the production ShopAIKey
    adapter from settings. Tests override :func:`get_chat_agent_deps` to inject
    a fake model and optional synthetic or focused registry.
    """

    model: ChatModelLike | None
    registry: ToolRegistry
    sqlite_path: str | Path
    include_assistant_status: bool = True


@dataclass(frozen=True, slots=True)
class CVTailoringDeps:
    coordinator: TailoringCoordinator
    storage: TailoringArtifactStorage
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class ProfileReextractDeps:
    session_factory: async_sessionmaker[AsyncSession]
    storage: AttachmentStorage
    document_invoker: Any
    normalizer: SkillNormalizer
    settings: Settings
    sqlite_path: str | Path
    graph_driver: Any | None = None


def get_settings_dep(request: Request) -> Settings:
    """Return process settings (from app.state after lifespan, else cache)."""
    state = getattr(request.app, "state", None)
    settings = getattr(state, "settings", None) if state is not None else None
    if isinstance(settings, Settings):
        return settings
    return get_settings()


def get_chat_agent_deps(request: Request) -> ChatAgentDeps:
    """Production chat deps: eight tools, deferred model, SQLite path.

    Tools receive session factory, storage, and Neo4j driver from the process
    / lifespan seams. Model construction is deferred to the runner so this
    provider never opens provider connections at dependency resolution.
    """
    settings = get_settings_dep(request)
    state = getattr(request.app, "state", None)
    storage = getattr(state, "storage", None) if state is not None else None
    if not isinstance(storage, AttachmentStorage):
        storage = AttachmentStorage(settings.FILES_DIR)
    driver = getattr(state, "neo4j_driver", None) if state is not None else None
    factory = get_session_factory()
    tailoring_storage = TailoringArtifactStorage(settings.FILES_DIR)
    tailoring_coordinator = TailoringCoordinator(
        session_factory=factory,
        storage=tailoring_storage,
        settings=settings,
        sqlite_path=settings.SQLITE_PATH,
    )

    return ChatAgentDeps(
        model=None,
        registry=production_registry(
            session_factory=factory,
            storage=storage,
            driver=driver,
            tailoring_coordinator=tailoring_coordinator,
        ),
        sqlite_path=settings.SQLITE_PATH,
        include_assistant_status=True,
    )


def get_cv_tailoring_deps(request: Request) -> CVTailoringDeps:
    settings = get_settings_dep(request)
    factory = get_session_factory()
    storage = TailoringArtifactStorage(settings.FILES_DIR)
    coordinator = TailoringCoordinator(
        session_factory=factory,
        storage=storage,
        settings=settings,
        sqlite_path=settings.SQLITE_PATH,
    )
    return CVTailoringDeps(
        coordinator=coordinator,
        storage=storage,
        settings=settings,
        session_factory=factory,
    )


def get_profile_reextract_deps(request: Request) -> ProfileReextractDeps:
    settings = get_settings_dep(request)
    state = getattr(request.app, "state", None)
    storage = getattr(state, "storage", None) if state is not None else None
    if not isinstance(storage, AttachmentStorage):
        storage = AttachmentStorage(settings.FILES_DIR)
    return ProfileReextractDeps(
        session_factory=get_session_factory(),
        storage=storage,
        document_invoker=ShopAIKeyStructuredCVDocumentInvoker(),
        normalizer=SkillNormalizer.production(),
        settings=settings,
        sqlite_path=settings.SQLITE_PATH,
        graph_driver=(
            getattr(state, "neo4j_driver", None) if state is not None else None
        ),
    )


__all__ = [
    "ChatAgentDeps",
    "ChatModelLike",
    "CVTailoringDeps",
    "ProfileReextractDeps",
    "get_cv_tailoring_deps",
    "get_chat_agent_deps",
    "get_profile_reextract_deps",
    "get_settings_dep",
]
