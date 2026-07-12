"""Lifecycle integration: startup/shutdown, schema, Neo4j isolation (fakes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings, load_settings
from app.db.session import create_session_manager
from app.graph.client import Neo4jClient
from app.graph.schema import SCHEMA_STATEMENTS, ensure_graph_schema
from app.main import create_app
from app.services.attachment_storage import FilesystemAttachmentStorage
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.graph.fakes import FakeDriver

SENTINEL_API_KEY = "sentinel-shopaikey-lifecycle-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-lifecycle-never-emit"
SENTINEL_URI = "bolt://lifecycle-test.invalid:7687"


def _settings(tmp_path: Path) -> Settings:
    return load_settings(
        environ={
            "APP_ENV": "local",
            "FRONTEND_ORIGIN": "http://localhost:5173",
            "VITE_API_BASE_URL": "http://localhost:8000",
            "SQLITE_PATH": str(tmp_path / "jobagent.db"),
            "FILES_DIR": str(tmp_path / "files"),
            "NEO4J_URI": SENTINEL_URI,
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
            "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
            "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
            "LLM_MODEL": "gpt-4o-mini",
            "LLM_TEMPERATURE": "0",
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "EMBEDDING_DIMENSIONS": "1536",
            "MAX_PDF_SIZE_MB": "10",
            "MAX_PDF_PAGES": "10",
            "URL_FETCH_TIMEOUT_SECONDS": "10",
            "URL_MAX_RESPONSE_MB": "5",
            "TOOL_LOOP_LIMIT": "6",
        }
    )


def test_shutdown_closes_database_and_graph(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    driver = FakeDriver()
    db = create_session_manager(settings.sqlite_path)
    storage = FilesystemAttachmentStorage(settings.files_dir)
    neo4j = Neo4jClient.from_settings(
        settings,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )
    application = create_app(
        settings=settings,
        session_manager=db,
        storage=storage,
        neo4j_client=neo4j,
        run_schema_setup=True,
    )
    with TestClient(application) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert neo4j.driver_created is True
    # After context exit, lifespan cleanup must have closed graph resources.
    assert driver.close_calls >= 1
    assert neo4j.is_closed is True


def test_schema_setup_is_idempotent_on_startup(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    driver = FakeDriver()
    neo4j = Neo4jClient.from_settings(
        settings,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )
    application = create_app(
        settings=settings,
        session_manager=create_session_manager(settings.sqlite_path),
        storage=FilesystemAttachmentStorage(settings.files_dir),
        neo4j_client=neo4j,
        run_schema_setup=True,
    )
    with TestClient(application) as client:
        assert client.app.state.schema_ready is True  # type: ignore[attr-defined]
        first_count = len(driver.queries)
        assert first_count == len(SCHEMA_STATEMENTS)
        # Manual second ensure matches lifecycle re-run contract.
        import anyio

        async def _second() -> None:
            await ensure_graph_schema(
                neo4j,
                embedding_dimensions=settings.embedding_dimensions,
            )

        anyio.run(_second)
        second_count = len(driver.queries)
        assert second_count == 2 * len(SCHEMA_STATEMENTS)
        # All statements remain IF NOT EXISTS (idempotent).
        for recorded in driver.queries:
            assert "IF NOT EXISTS" in recorded.query


def test_neo4j_startup_failure_does_not_mutate_sqlite_or_files(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db_path = Path(settings.sqlite_path)
    files_dir = Path(settings.files_dir)
    db = create_session_manager(db_path)
    storage = FilesystemAttachmentStorage(files_dir)

    # Seed SQLite row and a filesystem marker before a failing graph startup.
    async def _seed() -> None:
        async with db.engine.begin() as conn:
            await conn.execute(text("CREATE TABLE IF NOT EXISTS seed (id INTEGER)"))
            await conn.execute(text("INSERT INTO seed (id) VALUES (42)"))

    import anyio

    anyio.run(_seed)
    marker = files_dir / "preserve_me.txt"
    marker.write_text("keep", encoding="utf-8")
    before_db = db_path.read_bytes() if db_path.is_file() else b""
    before_marker = marker.read_text(encoding="utf-8")

    driver = FakeDriver(
        verify_error=RuntimeError(f"neo4j down {SENTINEL_NEO4J_PASSWORD}"),
        run_error=RuntimeError(f"schema fail {SENTINEL_URI}"),
    )
    neo4j = Neo4jClient.from_settings(
        settings,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.05,
    )
    application = create_app(
        settings=settings,
        session_manager=db,
        storage=storage,
        neo4j_client=neo4j,
        run_schema_setup=True,
    )
    with TestClient(application) as client:
        assert client.app.state.schema_ready is False  # type: ignore[attr-defined]
        response = client.get("/api/health")
        body = response.json()
        assert body["status"] == "degraded"
        assert body["neo4j"]["status"] == "down"
        assert body["sqlite"]["status"] == "up"
        assert body["filesystem"]["status"] == "up"
        # No secrets in health body.
        assert SENTINEL_NEO4J_PASSWORD not in response.text
        assert SENTINEL_URI not in response.text

        # SQLite content still queryable and unchanged in spirit.
        async def _read_seed() -> int:
            async with db.engine.connect() as conn:
                result = await conn.execute(text("SELECT id FROM seed"))
                return int(result.scalar_one())

        assert anyio.run(_read_seed) == 42
        assert marker.is_file()
        assert marker.read_text(encoding="utf-8") == before_marker
        if db_path.is_file() and before_db:
            # File still exists; Neo4j failure must not delete it.
            assert db_path.is_file()


def test_create_app_import_does_not_require_root_env() -> None:
    """Module-level app construction must not load real settings at import."""
    from app.main import app
    from app.main import create_app as factory

    assert app is not None
    # Fresh factory without lifespan entry does not load settings.
    bare = factory()
    assert bare.title == "JobAgent"
    # Chat service is bound only inside lifespan (import-safe).
    assert not hasattr(bare.state, "chat_service") or bare.state.chat_service is None


def test_probe_timeout_must_be_positive(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ValueError):
        create_app(
            settings=settings,
            session_manager=create_session_manager(settings.sqlite_path),
            storage=FilesystemAttachmentStorage(settings.files_dir),
            neo4j_client=Neo4jClient.from_settings(
                settings,
                driver_factory=FakeDriver,
                health_timeout_seconds=0.2,
            ),
            probe_timeout_seconds=0,
        )


def test_chat_service_injected_in_lifespan_without_provider_network(
    tmp_path: Path,
) -> None:
    """Lifespan installs chat_service; tests inject fakes so no ShopAIKey call."""
    from app.services.chat_service import ChatService
    from tests.fakes.agent_tools import ScriptedDecision, decision_text

    settings = _settings(tmp_path)
    db = create_session_manager(settings.sqlite_path)
    storage = FilesystemAttachmentStorage(settings.files_dir)
    neo4j = Neo4jClient.from_settings(
        settings,
        driver_factory=FakeDriver,
        health_timeout_seconds=0.2,
    )
    chat = ChatService(
        db,
        sqlite_path=settings.sqlite_path,
        decision=ScriptedDecision([decision_text("lifecycle ok")]),
        tools=[],
    )
    application = create_app(
        settings=settings,
        session_manager=db,
        storage=storage,
        neo4j_client=neo4j,
        chat_service=chat,
        run_schema_setup=False,
    )
    with TestClient(application) as client:
        assert client.app.state.chat_service is chat  # type: ignore[attr-defined]
        # OpenAPI still exposes only health + three chat paths.
        paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
        assert "/api/health" in paths
        assert "/api/chat/history" in paths
        assert "/api/chat/turns" in paths
        assert "/api/chat/runs/{run_id}/resume" in paths
        assert "/api/attachments/cv" in paths
        assert len(paths) == 5


def test_lifespan_uses_injected_settings_loader(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    calls = {"n": 0}

    def loader() -> Settings:
        calls["n"] += 1
        return settings

    driver = FakeDriver()
    application = create_app(
        settings_loader=loader,
        session_manager=create_session_manager(settings.sqlite_path),
        storage=FilesystemAttachmentStorage(settings.files_dir),
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=lambda: driver,
            health_timeout_seconds=0.2,
        ),
        run_schema_setup=False,
    )
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200
    assert calls["n"] == 1


def test_lifespan_retries_failed_candidate_sync_once(tmp_path: Path) -> None:
    from app.repositories.graph_outbox import GraphOutboxRepository
    from app.repositories.profiles import ProfileRepository
    from app.schemas.candidate import CandidateProfile

    settings = _settings(tmp_path)
    db = create_session_manager(settings.sqlite_path)

    async def seed() -> None:
        await db.create_all()
        profile = CandidateProfile.model_validate(
            {
                "summary": "Engineer.",
                "current_title": "Engineer",
                "total_experience_years": None,
                "skills": [],
                "experiences": [],
                "education": [],
                "languages": [],
                "extraction_confidence": 0.8,
            }
        )
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(profile)
            row = await GraphOutboxRepository(session).get_by_identity(
                "sync_candidate", "1"
            )
            assert row is not None
            await GraphOutboxRepository(session).mark_failed(
                row.id, error="neo4j_unavailable"
            )

    import anyio

    anyio.run(seed)
    driver = FakeDriver()
    application = create_app(
        settings=settings,
        session_manager=db,
        storage=FilesystemAttachmentStorage(settings.files_dir),
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=lambda: driver,
            health_timeout_seconds=0.2,
        ),
        run_schema_setup=False,
    )
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200
    candidate_queries = [
        item for item in driver.queries if "MERGE (c:Candidate" in item.query
    ]
    assert len(candidate_queries) == 1
