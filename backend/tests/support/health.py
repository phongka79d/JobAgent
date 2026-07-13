"""Focused helpers for GET /api/health integration tests (temporary resources)."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.core import settings as settings_module
from app.core.settings import clear_settings_cache
from app.db.session import dispose_engine
from app.main import create_app
from fastapi.testclient import TestClient

from tests.support.db_migration import (
    _CLEARABLE_ENV,
    SANITIZED_ENV,
    cleanup_isolated_sqlite,
    run_async,
    upgrade_to_head,
)

# Secrets/paths used only in tests; asserted absent from health payloads.
FAKE_NEO4J_PASSWORD = "health-test-neo4j-password-NOT-REAL"
FAKE_SHOPAIKEY = "health-test-shopaikey-secret-NOT-REAL"
FAKE_NEO4J_URI = "bolt://health-test-neo4j.invalid:7687"
FAKE_NEO4J_USER = "neo4j-health-test"

BACKEND_APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class _FakeSession:
    def __init__(self, driver: FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter_count += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit_count += 1

    async def run(self, query: str, parameters: Any = None, **kwargs: Any) -> None:
        self._driver.queries.append(query)


class FakeDriver:
    """Deterministic async Neo4j driver stand-in."""

    def __init__(self, *, fail_connectivity: bool = False) -> None:
        self.fail_connectivity = fail_connectivity
        self.closed = False
        self.verify_calls = 0
        self.session_enter_count = 0
        self.session_exit_count = 0
        self.queries: list[str] = []
        self.open_count = 0

    async def verify_connectivity(self) -> None:
        self.verify_calls += 1
        if self.fail_connectivity:
            raise OSError("simulated connectivity failure")

    async def close(self) -> None:
        self.closed = True

    def session(self, **config: Any) -> _FakeSession:
        return _FakeSession(self)


def prepare_health_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    migrate: bool = True,
    sqlite_path: Path | None = None,
    files_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Sanitize env to temporary SQLite + FILES_DIR; optionally migrate."""
    db_path = sqlite_path if sqlite_path is not None else tmp_path / "health.db"
    files = files_dir if files_dir is not None else tmp_path / "files"
    clear_settings_cache()
    run_async(dispose_engine())
    for key in _CLEARABLE_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        settings_module, "root_env_path", lambda: tmp_path / "no.env"
    )
    for key, value in SANITIZED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("FILES_DIR", str(files))
    monkeypatch.setenv("NEO4J_URI", FAKE_NEO4J_URI)
    monkeypatch.setenv("NEO4J_USER", FAKE_NEO4J_USER)
    monkeypatch.setenv("NEO4J_PASSWORD", FAKE_NEO4J_PASSWORD)
    monkeypatch.setenv("SHOPAIKEY_API_KEY", FAKE_SHOPAIKEY)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    if migrate:
        upgrade_to_head(db_path)
    return db_path, files


def install_fake_driver(
    monkeypatch: pytest.MonkeyPatch,
    driver: FakeDriver | None = None,
) -> FakeDriver:
    """Replace ``app.main.open_driver`` with a fake that tracks open count."""
    fake = driver if driver is not None else FakeDriver()
    open_calls = {"count": 0}

    def _open(_settings: Any) -> FakeDriver:
        open_calls["count"] += 1
        fake.open_count = open_calls["count"]
        return fake

    monkeypatch.setattr("app.main.open_driver", _open)
    return fake


def health_client() -> TestClient:
    """Build a TestClient for the application under test env."""
    return TestClient(create_app())


def assert_no_secrets(payload_text: str, files_dir: Path, db_path: Path) -> None:
    """Assert health payload text leaks no secrets, URIs, or local paths."""
    assert FAKE_NEO4J_PASSWORD not in payload_text
    assert FAKE_SHOPAIKEY not in payload_text
    assert FAKE_NEO4J_URI not in payload_text
    assert FAKE_NEO4J_USER not in payload_text
    assert str(files_dir) not in payload_text
    assert str(db_path) not in payload_text
    assert "bolt://" not in payload_text


def blocked_sqlite_path(tmp_path: Path) -> Path:
    """Return a SQLITE_PATH whose parent is a file so connections fail."""
    blocker = tmp_path / "sqlite-parent-blocker"
    blocker.write_text("not-a-directory", encoding="utf-8")
    return blocker / "health.db"


def blocked_files_dir(tmp_path: Path) -> Path:
    """Return a FILES_DIR path that is an existing file so mkdir fails."""
    path = tmp_path / "files-as-file"
    path.write_text("not-a-directory", encoding="utf-8")
    return path


def setup_unavailable_component(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    component: str,
) -> tuple[Path, Path, FakeDriver]:
    """Configure env so exactly one real dependency boundary fails."""
    if component == "sqlite":
        db_path = blocked_sqlite_path(tmp_path)
        files_dir = tmp_path / "files"
        prepare_health_env(
            monkeypatch,
            tmp_path,
            migrate=False,
            sqlite_path=db_path,
            files_dir=files_dir,
        )
        fake = install_fake_driver(monkeypatch)
        return db_path, files_dir, fake
    if component == "filesystem":
        files_dir = blocked_files_dir(tmp_path)
        db_path, _ = prepare_health_env(
            monkeypatch, tmp_path, migrate=True, files_dir=files_dir
        )
        fake = install_fake_driver(monkeypatch)
        return db_path, files_dir, fake
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch, FakeDriver(fail_connectivity=True))
    return db_path, files_dir, fake


def public_api_routes(app: Any) -> list[tuple[str, str]]:
    """Collect functional HTTP methods under ``/api`` (exclude HEAD/OPTIONS)."""
    functional: list[tuple[str, str]] = []
    for route in app.routes:
        if hasattr(route, "original_router") and hasattr(route, "include_context"):
            prefix = str(route.include_context.prefix or "")
            for nested in route.original_router.routes:
                methods = getattr(nested, "methods", None)
                path = getattr(nested, "path", None)
                if not methods or path is None:
                    continue
                full = f"{prefix}{path}"
                if full.startswith("/api"):
                    for method in methods:
                        if method not in {"HEAD", "OPTIONS"}:
                            functional.append((method, full))
            continue
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path and str(path).startswith("/api"):
            for method in methods:
                if method not in {"HEAD", "OPTIONS"}:
                    functional.append((method, path))
    return functional


def route_decorator_matches() -> list[str]:
    """Static scan of app/*.py for route decorator registrations."""
    matches: list[str] = []
    for path in BACKEND_APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                text_dec = ast.unparse(dec)
                if any(
                    t in text_dec
                    for t in (".get(", ".post(", ".put(", ".patch(", ".delete(")
                ):
                    matches.append(f"{path.name}:{node.name}:{text_dec}")
    return matches


@pytest.fixture
def health_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    """Migrated temp SQLite, temp FILES_DIR, and a healthy fake Neo4j driver."""
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()
