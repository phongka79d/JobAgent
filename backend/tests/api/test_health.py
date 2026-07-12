"""API tests for sanitized GET /api/health (fakes only; no live Compose/.env)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.config import Settings, load_settings
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.client import Neo4jClient
from app.main import create_app
from app.services.attachment_storage import FilesystemAttachmentStorage
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.graph.fakes import FakeDriver

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit-health"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit-health"
SENTINEL_URI = "bolt://health-test.invalid:7687"
LEAK_TOKENS = (
    SENTINEL_API_KEY,
    SENTINEL_NEO4J_PASSWORD,
    SENTINEL_URI,
    "Traceback",
    "Authorization",
    "password",
    "NEO4J_PASSWORD",
    "SHOPAIKEY_API_KEY",
)


def _settings(tmp_path: Path, **overrides: str) -> Settings:
    values: dict[str, str] = {
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
    values.update(overrides)
    return load_settings(environ=values)


def _build_app(
    tmp_path: Path,
    *,
    driver: FakeDriver | None = None,
    session_manager: DatabaseSessionManager | None = None,
    storage: FilesystemAttachmentStorage | None = None,
    neo4j_client: Neo4jClient | None = None,
    probe_timeout_seconds: float = 2.0,
    run_schema_setup: bool = True,
    frontend_origin: str = "http://localhost:5173",
) -> FastAPI:
    settings = _settings(tmp_path, FRONTEND_ORIGIN=frontend_origin)
    db = session_manager or create_session_manager(settings.sqlite_path)
    store = storage or FilesystemAttachmentStorage(settings.files_dir)
    if neo4j_client is None:
        fake = driver if driver is not None else FakeDriver()
        neo4j_client = Neo4jClient.from_settings(
            settings,
            driver_factory=lambda: fake,
            health_timeout_seconds=0.2,
        )
    return create_app(
        settings=settings,
        session_manager=db,
        storage=store,
        neo4j_client=neo4j_client,
        run_schema_setup=run_schema_setup,
        probe_timeout_seconds=probe_timeout_seconds,
    )


@pytest.fixture
def healthy_client(tmp_path: Path) -> Iterator[TestClient]:
    application = _build_app(tmp_path)
    with TestClient(application) as client:
        yield client


def _assert_no_leaks(payload: str, extra: tuple[str, ...] = ()) -> None:
    lowered = payload.lower()
    for token in LEAK_TOKENS + extra:
        assert token.lower() not in lowered
        assert token not in payload


def test_health_healthy_response_shape(healthy_client: TestClient) -> None:
    response = healthy_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["sqlite"] == {"status": "up", "code": None}
    assert body["filesystem"] == {"status": "up", "code": None}
    assert body["neo4j"] == {"status": "up", "code": None}
    assert set(body.keys()) == {"status", "sqlite", "filesystem", "neo4j"}
    _assert_no_leaks(response.text)


def test_public_app_endpoints_match_current_phase(healthy_client: TestClient) -> None:
    # FastAPI 0.139 nests include_router routes; OpenAPI paths are authoritative.
    # Plan 4 Task 02B adds the sole attachment upload to the accepted chat/health surface.
    paths = set(healthy_client.app.openapi()["paths"])  # type: ignore[attr-defined]
    assert paths == {
        "/api/health",
        "/api/attachments/cv",
        "/api/chat/history",
        "/api/chat/turns",
        "/api/chat/runs/{run_id}/resume",
    }
    assert "get" in healthy_client.app.openapi()["paths"]["/api/health"]  # type: ignore[attr-defined]
    assert not any(any(marker in path for marker in ("profile", "jobs", "match")) for path in paths)


def test_sqlite_failure_is_degraded_and_sanitized(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    # Point manager at an impossible path by disposing after startup injection.
    db = create_session_manager(tmp_path / "ok.db")

    class BrokenDB(DatabaseSessionManager):
        @property
        def engine(self) -> Any:  # type: ignore[override]
            raise RuntimeError(
                f"secret-db-fail {SENTINEL_NEO4J_PASSWORD} {settings.sqlite_path}"
            )

    broken = BrokenDB(db.engine)
    application = _build_app(tmp_path, session_manager=broken, run_schema_setup=False)
    with TestClient(application) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["sqlite"]["status"] == "down"
    assert body["sqlite"]["code"] == "sqlite_unavailable"
    _assert_no_leaks(response.text, extra=(str(tmp_path), settings.sqlite_path))


def test_filesystem_failure_is_degraded_and_sanitized(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    # Use a plain file as the storage root so the writable-directory probe fails.
    not_a_dir = tmp_path / "not-a-dir-file"
    not_a_dir.write_text("x", encoding="utf-8")

    class StubStorage:
        def __init__(self, root: Path) -> None:
            self.files_dir = root

    application = create_app(
        settings=settings,
        session_manager=create_session_manager(settings.sqlite_path),
        storage=StubStorage(not_a_dir),  # type: ignore[arg-type]
        neo4j_client=Neo4jClient.from_settings(
            settings,
            driver_factory=FakeDriver,
            health_timeout_seconds=0.2,
        ),
        run_schema_setup=False,
        probe_timeout_seconds=0.5,
    )
    with TestClient(application) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["filesystem"]["status"] == "down"
    assert body["filesystem"]["code"] == "filesystem_unavailable"
    _assert_no_leaks(response.text, extra=(str(not_a_dir), str(tmp_path)))


def test_neo4j_failure_is_degraded_without_leaks(tmp_path: Path) -> None:
    driver = FakeDriver(verify_error=RuntimeError(
        f"bolt auth failed {SENTINEL_NEO4J_PASSWORD} {SENTINEL_URI}"
    ))
    application = _build_app(tmp_path, driver=driver, run_schema_setup=False)
    with TestClient(application) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["neo4j"]["status"] == "down"
    assert body["neo4j"]["code"] in {
        "neo4j_unavailable",
        "neo4j_timeout",
        "neo4j_query_failed",
    }
    assert body["sqlite"]["status"] == "up"
    assert body["filesystem"]["status"] == "up"
    _assert_no_leaks(response.text, extra=(str(tmp_path),))


def test_neo4j_timeout_code(tmp_path: Path) -> None:
    driver = FakeDriver(verify_delay_seconds=1.0)
    application = _build_app(
        tmp_path,
        driver=driver,
        probe_timeout_seconds=0.05,
        run_schema_setup=False,
    )
    with TestClient(application) as client:
        response = client.get("/api/health")
    body = response.json()
    assert body["status"] == "degraded"
    assert body["neo4j"]["status"] == "down"
    assert body["neo4j"]["code"] == "neo4j_timeout"
    _assert_no_leaks(response.text)


def test_cors_exact_origin_allowed(healthy_client: TestClient) -> None:
    response = healthy_client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_cors_other_origin_not_reflected(healthy_client: TestClient) -> None:
    response = healthy_client.get(
        "/api/health",
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_exact_origin(tmp_path: Path) -> None:
    application = _build_app(tmp_path)
    with TestClient(application) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_response_never_includes_absolute_paths_or_uris(tmp_path: Path) -> None:
    driver = FakeDriver(
        verify_error=OSError(f"connect {SENTINEL_URI} path={tmp_path / 'secret.db'}")
    )
    application = _build_app(tmp_path, driver=driver, run_schema_setup=False)
    with TestClient(application) as client:
        response = client.get("/api/health")
    text = response.text
    _assert_no_leaks(text, extra=(str(tmp_path), "secret.db", "connect "))
    # Component down codes only.
    body = response.json()
    for key in ("sqlite", "filesystem", "neo4j"):
        assert set(body[key].keys()) == {"status", "code"}


def test_health_endpoint_stays_responsive_under_slow_neo4j(tmp_path: Path) -> None:
    driver = FakeDriver(verify_delay_seconds=5.0)
    application = _build_app(
        tmp_path,
        driver=driver,
        probe_timeout_seconds=0.05,
        run_schema_setup=False,
    )
    with TestClient(application) as client:
        t0 = time.perf_counter()
        response = client.get("/api/health")
        elapsed = time.perf_counter() - t0
    assert response.status_code == 200
    assert elapsed < 1.0
    assert response.json()["neo4j"]["status"] == "down"
