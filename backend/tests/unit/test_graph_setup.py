"""Unit tests for Neo4j driver lifecycle and idempotent base schema (03B).

Uses deterministic fakes only — no live Neo4j, credentials, or root .env.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.core.settings import Settings
from app.graph import constraints as constraints_mod
from app.graph.constraints import (
    CANDIDATE_ID_UNIQUE,
    JOB_EMBEDDING_VECTOR_INDEX,
    JOB_ID_UNIQUE,
    SCHEMA_STATEMENTS,
    SKILL_CANONICAL_KEY_UNIQUE,
    VECTOR_DIMENSIONS,
    VECTOR_SIMILARITY,
    ensure_base_schema,
)
from app.graph.driver import check_connectivity, close_driver, open_driver
from pydantic import AnyHttpUrl, SecretStr

# Secrets used only inside this module for fake settings; never asserted as
# substrings of Cypher, exception text, or public representations.
_FAKE_PASSWORD = "unit-test-neo4j-password-NOT-A-REAL-SECRET"
_FAKE_URI = "bolt://graph-unit-test:7687"
_FAKE_USER = "neo4j-unit"


def _settings(*, password: str = _FAKE_PASSWORD) -> Settings:
    return Settings(
        FRONTEND_ORIGIN="http://127.0.0.1:5173",
        SQLITE_PATH=":memory:",
        FILES_DIR="files",
        NEO4J_URI=_FAKE_URI,
        NEO4J_USER=_FAKE_USER,
        NEO4J_PASSWORD=SecretStr(password),
        SHOPAIKEY_BASE_URL=AnyHttpUrl("https://example.test/v1"),
        SHOPAIKEY_API_KEY=SecretStr("unit-test-shopaikey-not-real"),
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
        assert parameters is None or parameters == {}
        assert not kwargs
        self._driver.queries.append(query)


class FakeDriver:
    """Deterministic async-driver stand-in for unit tests."""

    def __init__(self, *, fail_connectivity: bool = False) -> None:
        self.fail_connectivity = fail_connectivity
        self.closed = False
        self.verify_calls = 0
        self.session_enter_count = 0
        self.session_exit_count = 0
        self.queries: list[str] = []
        self.session_kwargs: list[dict[str, Any]] = []

    async def verify_connectivity(self) -> None:
        self.verify_calls += 1
        if self.fail_connectivity:
            raise OSError("simulated connectivity failure")

    async def close(self) -> None:
        self.closed = True

    def session(self, **config: Any) -> _FakeSession:
        self.session_kwargs.append(dict(config))
        return _FakeSession(self)


def test_open_driver_uses_settings_uri_user_and_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake = FakeDriver()

    def _factory(uri: str, *, auth: Any = None, **config: Any) -> FakeDriver:
        captured["uri"] = uri
        captured["auth"] = auth
        captured["config"] = config
        return fake

    monkeypatch.setattr(
        "app.graph.driver.AsyncGraphDatabase.driver",
        _factory,
    )
    settings = _settings()
    driver = open_driver(settings)
    assert driver is fake
    assert captured["uri"] == _FAKE_URI
    assert captured["auth"] == (_FAKE_USER, _FAKE_PASSWORD)
    # Password must not appear as a free-standing config dump field.
    assert _FAKE_PASSWORD not in repr(captured["config"])


@pytest.mark.asyncio
async def test_close_driver_closes_underlying_driver() -> None:
    driver = FakeDriver()
    await close_driver(driver)  # type: ignore[arg-type]
    assert driver.closed is True


@pytest.mark.asyncio
async def test_check_connectivity_success() -> None:
    driver = FakeDriver(fail_connectivity=False)
    assert await check_connectivity(driver) is True  # type: ignore[arg-type]
    assert driver.verify_calls == 1


@pytest.mark.asyncio
async def test_check_connectivity_failure_returns_false_without_password() -> None:
    driver = FakeDriver(fail_connectivity=True)
    assert await check_connectivity(driver) is False  # type: ignore[arg-type]
    assert driver.verify_calls == 1
    # Connectivity API returns bool only; no password channel.
    assert _FAKE_PASSWORD not in str(driver)


@pytest.mark.asyncio
async def test_ensure_base_schema_issues_exact_statements_once() -> None:
    driver = FakeDriver()
    await ensure_base_schema(driver)  # type: ignore[arg-type]
    assert driver.queries == list(SCHEMA_STATEMENTS)
    assert driver.session_enter_count == 1
    assert driver.session_exit_count == 1


@pytest.mark.asyncio
async def test_ensure_base_schema_is_repeat_safe() -> None:
    driver = FakeDriver()
    await ensure_base_schema(driver)  # type: ignore[arg-type]
    await ensure_base_schema(driver)  # type: ignore[arg-type]
    # Two full passes of the same IF NOT EXISTS statements; no extra DDL.
    assert driver.queries == list(SCHEMA_STATEMENTS) * 2
    assert all("IF NOT EXISTS" in q for q in driver.queries)
    assert len(driver.queries) == 8


def test_schema_statements_exact_constraints_and_vector_index() -> None:
    assert SCHEMA_STATEMENTS == (
        CANDIDATE_ID_UNIQUE,
        JOB_ID_UNIQUE,
        SKILL_CANONICAL_KEY_UNIQUE,
        JOB_EMBEDDING_VECTOR_INDEX,
    )
    assert len(SCHEMA_STATEMENTS) == 4

    assert CANDIDATE_ID_UNIQUE == (
        "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS "
        "FOR (c:Candidate) REQUIRE c.id IS UNIQUE"
    )
    assert JOB_ID_UNIQUE == (
        "CREATE CONSTRAINT job_id_unique IF NOT EXISTS "
        "FOR (j:Job) REQUIRE j.id IS UNIQUE"
    )
    assert SKILL_CANONICAL_KEY_UNIQUE == (
        "CREATE CONSTRAINT skill_canonical_key_unique IF NOT EXISTS "
        "FOR (s:Skill) REQUIRE s.canonical_key IS UNIQUE"
    )

    assert "CREATE VECTOR INDEX job_embedding_vector IF NOT EXISTS" in (
        JOB_EMBEDDING_VECTOR_INDEX
    )
    assert "FOR (j:Job) ON (j.embedding)" in JOB_EMBEDDING_VECTOR_INDEX
    assert "`vector.dimensions`: 1536" in JOB_EMBEDDING_VECTOR_INDEX
    assert "`vector.similarity_function`: 'cosine'" in JOB_EMBEDDING_VECTOR_INDEX
    assert VECTOR_DIMENSIONS == 1536
    assert VECTOR_SIMILARITY == "cosine"
    assert VECTOR_DIMENSIONS == Settings.model_fields["EMBEDDING_DIMENSIONS"].default


def test_schema_statements_contain_no_runtime_secrets_or_parameters() -> None:
    joined = "\n".join(SCHEMA_STATEMENTS)
    assert "$" not in joined  # no Cypher parameters in fixed DDL
    assert _FAKE_PASSWORD not in joined
    assert "password" not in joined.lower()
    # Fixed DDL must not own domain writes, relationships, or rebuild logic.
    forbidden = (
        "HAS_SKILL",
        "REQUIRES",
        "PREFERS",
        "RELATED_TO",
        "source_updated_at",
        "rebuild",
        "MERGE",
        "CREATE (",
        "DELETE",
        "SET ",
    )
    for token in forbidden:
        assert token not in joined


def test_base_ddl_modules_own_only_constraints_and_driver_lifecycle() -> None:
    """Precise ownership: constraints/driver stay free of domain graph writes."""
    graph_dir = Path(__file__).resolve().parents[2] / "app" / "graph"
    base_modules = ("constraints.py", "driver.py", "__init__.py")
    domain_tokens = (
        "HAS_SKILL",
        "REQUIRES",
        "PREFERS",
        "RELATED_TO",
        "source_updated_at",
        "rebuild_neo4j",
        "sync_job",
        "sync_candidate",
    )
    for name in base_modules:
        text = (graph_dir / name).read_text(encoding="utf-8")
        for token in domain_tokens:
            assert token not in text, f"{name} must not contain {token!r}"

    # Domain sync owners may project relationships; fixed DDL stays in constraints.
    sync_shared = (graph_dir / "sync_shared.py").read_text(encoding="utf-8")
    sync_candidate = (graph_dir / "sync_candidate.py").read_text(encoding="utf-8")
    sync_job = (graph_dir / "sync_job.py").read_text(encoding="utf-8")
    assert "RELATED_TO" in sync_shared
    assert "HAS_SKILL" in sync_candidate
    assert "REQUIRES" in sync_job and "PREFERS" in sync_job
    # constraints remains the sole SCHEMA_STATEMENTS owner.
    assert "SCHEMA_STATEMENTS" in (graph_dir / "constraints.py").read_text(
        encoding="utf-8"
    )
    assert "SCHEMA_STATEMENTS" not in sync_job
    assert "SCHEMA_STATEMENTS" not in sync_candidate


def test_graph_modules_do_not_import_sqlite_sessions_or_http_writers() -> None:
    """Precise ownership: only approved rebuild modules open SQLite seams.

    Always forbidden for every graph module: storage/API/FastAPI/ingestion.
    SQLAlchemy session factories and repository packages are allowed only in:
    * ``rebuild_snapshot.py`` — read-only SQLite snapshot + embedding preflight
    * ``rebuild.py`` — public service/CLI session-factory wiring

    ``app.db`` model/constant imports remain allowed for domain sync owners
    (prior Plan 4/03A boundary) but stay forbidden for base DDL modules and for
    ``rebuild_ops.py`` / ``rebuild_target.py`` (no SQLite ownership there).
    """
    graph_dir = Path(__file__).resolve().parents[2] / "app" / "graph"
    always_forbidden = (
        "app.storage",
        "app.api",
        "fastapi",
        "app.services.jd_ingestion",
        "app.services.profile_approval",
    )
    # Exact approved modules for sqlalchemy / repositories (SQLite I/O seams).
    sqlite_io_allowed = frozenset({"rebuild.py", "rebuild_snapshot.py"})
    # Base DDL + rebuild ops/target must not import app.db at all.
    app_db_forbidden = frozenset(
        {
            "constraints.py",
            "driver.py",
            "__init__.py",
            "rebuild_ops.py",
            "rebuild_target.py",
        }
    )
    for path in sorted(graph_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        prefixes = list(always_forbidden)
        if path.name not in sqlite_io_allowed:
            prefixes.extend(("sqlalchemy", "app.repositories"))
        if path.name in app_db_forbidden:
            prefixes.append("app.db")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in prefixes:
                        assert not alias.name.startswith(prefix), (
                            f"{path.name} must not import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in prefixes:
                    assert not node.module.startswith(prefix), (
                        f"{path.name} must not import {node.module}"
                    )


def test_password_not_in_settings_repr_used_by_driver() -> None:
    settings = _settings(password="super-secret-graph-password-xyz")
    rendered = repr(settings)
    assert "super-secret-graph-password-xyz" not in rendered
    assert isinstance(settings.NEO4J_PASSWORD, SecretStr)


def test_open_driver_does_not_log_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory receives secret only via auth tuple; nothing else holds it."""
    seen: list[Any] = []

    def _factory(uri: str, *, auth: Any = None, **config: Any) -> MagicMock:
        seen.append((uri, auth, config))
        return MagicMock(name="AsyncDriver")

    monkeypatch.setattr(
        "app.graph.driver.AsyncGraphDatabase.driver",
        _factory,
    )
    secret = "another-unit-only-secret-value"
    settings = _settings(password=secret)
    open_driver(settings)
    assert len(seen) == 1
    uri, auth, config = seen[0]
    assert uri == _FAKE_URI
    assert auth == (_FAKE_USER, secret)
    assert secret not in repr(config)
    assert secret not in str(config)


def test_vector_index_statement_is_source_constant_not_runtime_format() -> None:
    # Dimensions are fixed source constants, not settings interpolation at call.
    assert constraints_mod.VECTOR_DIMENSIONS == 1536
    assert "1536" in JOB_EMBEDDING_VECTOR_INDEX
    assert "cosine" in JOB_EMBEDDING_VECTOR_INDEX
