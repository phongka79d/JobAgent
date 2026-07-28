"""Focused helpers for GET /api/health integration tests (temporary resources)."""

# Exact AST decorator snapshots stay on one line for direct failure comparison.
# ruff: noqa: E501

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

EXPECTED_PUBLIC_API_ROUTES: tuple[tuple[str, str], ...] = (
    ("DELETE", "/api/cv-tailoring/sessions/{session_id}"),
    ("GET", "/api/cv-tailoring/sessions"),
    ("GET", "/api/cv-tailoring/sessions/{session_id}"),
    ("GET", "/api/cv-tailoring/versions/{version_id}/pdf"),
    ("GET", "/api/cv-tailoring/versions/{version_id}/source"),
    ("POST", "/api/cv-tailoring/sessions"),
    ("POST", "/api/cv-tailoring/sessions/{session_id}/ai-versions"),
    ("POST", "/api/cv-tailoring/sessions/{session_id}/manual-versions"),
    ("DELETE", "/api/conversations/{conversation_id}"),
    ("DELETE", "/api/cvs/{attachment_id}"),
    ("DELETE", "/api/jobs/{job_id}"),
    ("DELETE", "/api/profiles/{profile_id}"),
    ("DELETE", "/api/profiles/{profile_id}/reextract-draft"),
    ("GET", "/api/chat/history"),
    ("GET", "/api/cvs"),
    ("GET", "/api/cvs/{attachment_id}/file"),
    ("GET", "/api/conversations/{conversation_id}/history"),
    ("GET", "/api/health"),
    ("GET", "/api/jobs"),
    ("GET", "/api/jobs/{job_id}"),
    ("GET", "/api/observability/cvs"),
    ("GET", "/api/observability/cvs/{attachment_id}/chunks"),
    ("GET", "/api/observability/cvs/{attachment_id}/chunks/{ordinal}"),
    ("GET", "/api/observability/cvs/{attachment_id}/file"),
    ("GET", "/api/observability/graph"),
    ("GET", "/api/observability/runs"),
    ("GET", "/api/observability/skill-map"),
    ("GET", "/api/profile"),
    ("GET", "/api/profile/cv"),
    ("GET", "/api/profiles"),
    ("GET", "/api/profiles/{profile_id}"),
    ("GET", "/api/profiles/{profile_id}/reextract-draft"),
    ("GET", "/api/profiles/{profile_id}/conversations"),
    ("PATCH", "/api/profiles/{profile_id}"),
    ("POST", "/api/attachments/cv"),
    ("POST", "/api/chat/runs/{run_id}/resume"),
    ("POST", "/api/chat/turns"),
    ("POST", "/api/conversations/{conversation_id}/select"),
    ("POST", "/api/conversations/{conversation_id}/turns"),
    ("POST", "/api/jobs/save-and-evaluate"),
    ("POST", "/api/jobs/{job_id}/evaluate"),
    ("POST", "/api/jobs/{job_id}/reextract"),
    ("POST", "/api/profiles/{profile_id}/activate"),
    ("POST", "/api/profiles/{profile_id}/conversations"),
    ("POST", "/api/profiles/{profile_id}/reextract"),
    ("POST", "/api/profiles/{profile_id}/reextract-draft/approve"),
)

EXPECTED_ROUTE_DECORATORS: tuple[str, ...] = (
    "attachments.py:post_cv_upload:router.post('/attachments/cv', response_model=CvUploadResponse)",
    "chat.py:get_chat_history:router.get('/chat/history', response_model=HistoryPage)",
    "chat.py:post_chat_resume:router.post('/chat/runs/{run_id}/resume')",
    "chat.py:post_chat_turn:router.post('/chat/turns')",
    "conversations.py:create_profile_conversation:router.post('/profiles/{profile_id}/conversations', response_model=ConversationMutationResponse)",
    "conversations.py:delete_conversation:router.delete('/conversations/{conversation_id}', response_model=ConversationDeleteResponse)",
    "conversations.py:get_conversation_history:router.get('/conversations/{conversation_id}/history', response_model=HistoryPage)",
    "conversations.py:list_profile_conversations:router.get('/profiles/{profile_id}/conversations', response_model=ConversationListResponse)",
    "conversations.py:post_conversation_turn:router.post('/conversations/{conversation_id}/turns')",
    "conversations.py:select_conversation:router.post('/conversations/{conversation_id}/select', response_model=ConversationMutationResponse)",
    "cvs.py:get_cv_file:router.get('/cvs/{attachment_id}/file')",
    "cvs.py:list_cv_manager:router.get('/cvs', response_model=CvManagerListResponse)",
    "cvs.py:delete_cv_attachment:router.delete('/cvs/{attachment_id}', status_code=204, response_class=Response)",
    "health.py:get_health:router.get('/health', response_model=HealthResponse)",
    "jobs.py:delete_saved_job_route:router.delete('/jobs/{job_id}', status_code=204, response_class=Response)",
    "jobs.py:get_saved_job:router.get('/jobs/{job_id}', response_model=SavedJobDetail)",
    "jobs.py:list_saved_jobs:router.get('/jobs', response_model=SavedJobListPage)",
    "jobs.py:post_evaluate_job:router.post('/jobs/{job_id}/evaluate', response_model=EvaluateJobResponse)",
    "jobs.py:post_reextract_job:router.post('/jobs/{job_id}/reextract', response_model=ReextractJobResponse)",
    "jobs.py:post_save_and_evaluate:router.post('/jobs/save-and-evaluate', response_model=SaveAndEvaluateResponse)",
    "observability.py:get_observability_chunk_detail:router.get('/observability/cvs/{attachment_id}/chunks/{ordinal}', response_model=ChunkDetail)",
    "observability.py:get_observability_chunks:router.get('/observability/cvs/{attachment_id}/chunks', response_model=ChunkListPage)",
    "observability.py:get_observability_cv_file:router.get('/observability/cvs/{attachment_id}/file')",
    "observability.py:get_observability_cvs:router.get('/observability/cvs', response_model=CvHistoryPage)",
    "observability.py:get_observability_graph:router.get('/observability/graph', response_model=GraphSnapshot)",
    "observability.py:get_observability_runs:router.get('/observability/runs', response_model=RunHistoryPage)",
    "observability.py:get_observability_skill_map:router.get('/observability/skill-map', response_model=SelectedJobSkillMap)",
    "profile.py:get_profile:router.get('/profile', response_model=ProfileReadResponse)",
    "profile.py:get_profile_cv:router.get('/profile/cv')",
    "profiles.py:activate_profile:router.post('/profiles/{profile_id}/activate', response_model=SelectionResponse)",
    "profiles.py:delete_profile:router.delete('/profiles/{profile_id}', response_model=ProfileDeleteResponse)",
    "profiles.py:discard_profile_reextract_review:router.delete('/profiles/{profile_id}/reextract-draft', status_code=204, response_class=Response)",
    "profiles.py:get_profile:router.get('/profiles/{profile_id}', response_model=ProfileDetail)",
    "profiles.py:get_profile_reextract_review:router.get('/profiles/{profile_id}/reextract-draft', response_model=ProfileReextractReview)",
    "profiles.py:list_profiles:router.get('/profiles', response_model=ProfileListResponse)",
    "profiles.py:patch_profile:router.patch('/profiles/{profile_id}', response_model=ProfileDetail)",
    "profiles.py:reextract_profile:router.post('/profiles/{profile_id}/reextract')",
    "profiles.py:approve_profile_reextract_review:router.post('/profiles/{profile_id}/reextract-draft/approve', response_model=ProfileReextractApprovalResponse)",
)


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
