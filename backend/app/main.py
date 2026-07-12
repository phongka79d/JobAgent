"""FastAPI application entrypoint with foundation lifecycle and health.

Import must not call ShopAIKey or load the user-owned root ``.env``. Settings
and resource ownership are established in the application lifespan. Neo4j
startup failure never mutates or deletes SQLite/filesystem state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.api.attachments import router as attachments_router
from app.api.chat import router as chat_router
from app.api.health import DEFAULT_PROBE_TIMEOUT_SECONDS
from app.api.health import router as health_router
from app.api.profile import router as profile_router
from app.config import Settings, load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.candidate_sync import process_candidate_sync_outbox
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError
from app.graph.schema import ensure_graph_schema
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.chat_service import ChatService
from app.services.cv_ingestion import CvIngestionService
from app.services.jd_ingestion import JDIngestionService
from app.services.profile_service import ProfileCommitService
from app.services.shopaikey_chat import ShopAIKeyChatAdapter
from app.services.url_fetcher import UrlFetcher
from app.tools.candidate_context import (
    CandidateContextToolService,
    create_candidate_context_tool,
)
from app.tools.profile_commit import (
    ProfileCommitToolService,
    create_profile_commit_tool,
)
from app.tools.profile_draft import ProfileDraftToolService, create_profile_draft_tools
from app.tools.query_jobs import QueryJobsToolService, create_query_jobs_tool
from app.tools.registry import create_production_registry
from app.tools.save_job import SaveJobToolService, create_save_job_tool

SettingsLoader = Callable[[], Settings]


class ExactOriginCORSMiddleware(BaseHTTPMiddleware):
    """CORS middleware that reflects only the exact configured frontend origin.

    Origin is read from ``app.state.frontend_origin`` (set during lifespan) so
    production import does not require loading root settings at module import.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            response: Response = Response(status_code=204)
        else:
            response = await call_next(request)

        allowed = getattr(request.app.state, "frontend_origin", None)
        if (
            origin is not None
            and isinstance(allowed, str)
            and allowed
            and origin == allowed
        ):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            acrh = request.headers.get("access-control-request-headers")
            if acrh:
                response.headers["Access-Control-Allow-Headers"] = acrh
            else:
                response.headers["Access-Control-Allow-Headers"] = "content-type"
            response.headers["Vary"] = "Origin"
        return response


def create_app(
    *,
    settings: Settings | None = None,
    settings_loader: SettingsLoader | None = None,
    session_manager: DatabaseSessionManager | None = None,
    storage: FilesystemAttachmentStorage | None = None,
    neo4j_client: Neo4jClient | None = None,
    chat_service: ChatService | None = None,
    run_schema_setup: bool = True,
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> FastAPI:
    """Build the FastAPI application with lifecycle-managed foundation deps.

    Parameters support test injection of synthetic settings and fake clients.
    Production uses ``create_app()`` with no arguments; settings load only inside
    the lifespan from the process/root environment contract. Chat service is
    constructed in lifespan (or injected) so import never opens a provider.
    """
    if probe_timeout_seconds <= 0:
        raise ValueError("probe_timeout_seconds must be positive")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings
        if cfg is None:
            loader = settings_loader if settings_loader is not None else load_settings
            cfg = loader()

        db = session_manager
        if db is None:
            db = create_session_manager(cfg.sqlite_path)

        store = storage
        if store is None:
            store = FilesystemAttachmentStorage(cfg.files_dir)

        graph = neo4j_client
        if graph is None:
            graph = Neo4jClient.from_settings(cfg)

        chat = chat_service
        if chat is None:
            # Adapter stores settings only; ChatOpenAI is built on first use.
            decision = ShopAIKeyChatAdapter.from_settings(cfg)
            ingestion = CvIngestionService(
                db,
                store,
                max_size_bytes=cfg.max_pdf_size_mb * 1024 * 1024,
                max_pages=cfg.max_pdf_pages,
                profile_adapter=decision,
            )
            draft_tools = create_profile_draft_tools(
                ProfileDraftToolService(db, ingestion)
            )
            commit_tool = create_profile_commit_tool(
                ProfileCommitToolService(ProfileCommitService(db, store))
            )
            jd_ingestion = JDIngestionService(
                db,
                chat_adapter=decision,
                url_fetcher=UrlFetcher.from_settings(cfg),
            )
            registry = create_production_registry(
                [
                    create_candidate_context_tool(CandidateContextToolService(db)),
                    *draft_tools,
                    commit_tool,
                    create_save_job_tool(SaveJobToolService(jd_ingestion)),
                    create_query_jobs_tool(QueryJobsToolService(db)),
                ]
            )
            chat = ChatService(
                db,
                sqlite_path=cfg.sqlite_path,
                decision=decision,
                registry=registry,
            )

        app.state.settings = cfg
        app.state.db = db
        app.state.storage = store
        app.state.files_dir = Path(store.files_dir)
        app.state.neo4j = graph
        app.state.chat_service = chat
        app.state.frontend_origin = cfg.frontend_origin
        app.state.embedding_dimensions = cfg.embedding_dimensions
        app.state.probe_timeout_seconds = probe_timeout_seconds
        app.state.schema_ready = False

        # Best-effort idempotent schema setup. Neo4j failure must not touch
        # SQLite or filesystem state and must not prevent the API from serving.
        if run_schema_setup:
            schema_ok = False
            try:
                await ensure_graph_schema(
                    graph,
                    embedding_dimensions=cfg.embedding_dimensions,
                )
                schema_ok = True
            except GraphError:
                schema_ok = False
            except Exception:
                schema_ok = False
            app.state.schema_ready = schema_ok

        try:
            await process_candidate_sync_outbox(db, graph)
        except Exception:
            pass

        try:
            yield
        finally:
            # Always release graph then database. Swallowed failures never
            # include secret-bearing messages in this process path.
            try:
                await graph.close()
            except Exception:
                pass
            try:
                await db.dispose()
            except Exception:
                pass

    application = FastAPI(
        title="JobAgent",
        version="0.1.0",
        description="JobAgent backend foundation",
        lifespan=lifespan,
    )
    application.add_middleware(ExactOriginCORSMiddleware)
    application.include_router(health_router)
    application.include_router(attachments_router)
    application.include_router(profile_router)
    application.include_router(chat_router)
    return application


app = create_app()


def run() -> None:
    """Production-shaped local server command (localhost only)."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
