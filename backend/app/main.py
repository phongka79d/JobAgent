"""FastAPI application entry: lifespan, health, chat, and CV upload routes.

Startup opens shared resources once. The singleton-seed safeguard runs only
after a successful SQLite availability check. Graph base-schema init runs
only when Neo4j connectivity succeeds. Filesystem root creation is not
eager at startup; the health probe owns create/access checks. Startup never
runs Alembic migrations or SQLAlchemy metadata schema creation. Cleanup
closes any opened Neo4j driver and disposes the SQLite engine on every exit
path, including partial startup failures. Public functional routes are
health, Plan 3 chat history/turn/resume, and Plan 4 CV upload.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncDriver
from sqlalchemy import text

from app.api.attachments import router as attachments_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.settings import Settings, get_settings
from app.db.seed import ensure_singleton_seeds
from app.db.session import dispose_engine, get_engine, session_scope
from app.graph.constraints import ensure_base_schema
from app.graph.driver import check_connectivity, close_driver, open_driver
from app.storage.attachments import AttachmentStorage


async def _try_singleton_seeds_if_sqlite_ready() -> None:
    """Run idempotent singleton seeds only after SQLite answers a trivial query.

    SQLite unavailability must not terminate application startup; health will
    report the component state. Does not run migrations or metadata schema creation.
    """
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return
    async with session_scope() as session:
        await ensure_singleton_seeds(session)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared resources once; seed/graph safeguards; always clean up."""
    settings: Settings = get_settings()
    driver: AsyncDriver | None = None
    engine_acquired = False

    try:
        # Process-wide async engine (PRAGMAs on connect). No metadata schema creation.
        get_engine()
        engine_acquired = True

        await _try_singleton_seeds_if_sqlite_ready()

        # Storage handle for health probes; do not eagerly ensure_root().
        storage = AttachmentStorage(settings.FILES_DIR)

        driver = open_driver(settings)
        # Graph schema init is separate from health probes. Only when reachable
        # so an unavailable Neo4j reports as a component without killing startup.
        if await check_connectivity(driver):
            await ensure_base_schema(driver)

        app.state.settings = settings
        app.state.storage = storage
        app.state.neo4j_driver = driver

        yield
    finally:
        if driver is not None:
            try:
                await close_driver(driver)
            except Exception:
                pass
        if engine_acquired:
            await dispose_engine()
        app.state.neo4j_driver = None
        app.state.storage = None


def create_app() -> FastAPI:
    """Build the FastAPI application with CORS, health, chat, and CV upload."""
    settings = get_settings()
    application = FastAPI(
        title="JobAgent",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        # Plan 3/4 need POST for turns/resume/upload; keep origin restricted.
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(attachments_router, prefix="/api")
    application.include_router(chat_router, prefix="/api")
    return application


def __getattr__(name: str) -> Any:
    """Lazy ``app`` for ``uvicorn app.main:app`` without import-time settings."""
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
