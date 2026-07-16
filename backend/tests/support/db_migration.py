"""Shared Alembic/SQLite integration harness for migration tests.

Single owner for sanitized env setup, Alembic config/upgrade, async runners,
and fixtures. Schema parity helpers live in ``schema_parity``.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from alembic import command
from alembic.config import Config
from app.core import settings as settings_module
from app.core.settings import clear_settings_cache
from app.db.seed import APPLICATION_TABLE_NAMES
from app.db.session import dispose_engine, sqlite_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Re-export parity API so integration tests keep one import surface.
from tests.support.schema_parity import (  # noqa: F401
    assert_migrated_matches_accepted_models,
    expected_indexes,
    expected_named_constraints,
    observe_schema,
)

T = TypeVar("T")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_HEAD = "0002_add_attachment_text_chunks"
EXPECTED_FRESH_TABLES: frozenset[str] = APPLICATION_TABLE_NAMES | {
    "alembic_version"
}
SANITIZED_ENV: dict[str, str] = {
    "FRONTEND_ORIGIN": "http://localhost:5173",
    "FILES_DIR": "/tmp/jobagent-files-migration-test",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "test-neo4j-password-not-real",
    "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
    "SHOPAIKEY_API_KEY": "test-shopaikey-secret-not-real",
}
_CLEARABLE_ENV = list(SANITIZED_ENV) + [
    "APP_ENV",
    "SQLITE_PATH",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "MAX_PDF_SIZE_MB",
    "MAX_PDF_PAGES",
    "URL_FETCH_TIMEOUT_SECONDS",
    "URL_MAX_RESPONSE_MB",
    "TOOL_LOOP_LIMIT",
]


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine on a fresh event loop (pytest-friendly)."""
    return asyncio.run(coro)


def alembic_config(db_path: Path) -> Config:
    """Build Alembic Config for an isolated temporary SQLite file."""
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    return cfg


def upgrade_to_head(db_path: Path) -> None:
    """Apply Alembic migrations through head on ``db_path``."""
    command.upgrade(alembic_config(db_path), "head")


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Short-lived async session factory bound to ``engine``."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def bind_isolated_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    db_name: str = "integration-test.db",
) -> Path:
    """Sanitize env/settings and return an isolated SQLite path (no upgrade)."""
    db = tmp_path / db_name
    clear_settings_cache()
    run_async(dispose_engine())
    for key in _CLEARABLE_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        settings_module, "root_env_path", lambda: tmp_path / "no.env"
    )
    for key, value in SANITIZED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SQLITE_PATH", str(db))
    return db


def cleanup_isolated_sqlite() -> None:
    """Dispose cached engine and clear settings after an isolated test."""
    run_async(dispose_engine())
    clear_settings_cache()


@pytest.fixture
def isolated_sqlite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    """Isolated temporary SQLite path with sanitized settings (no upgrade)."""
    db = bind_isolated_sqlite(monkeypatch, tmp_path)
    yield db
    cleanup_isolated_sqlite()


@pytest.fixture
def migrated_sqlite(isolated_sqlite: Path) -> Path:
    """Isolated SQLite path upgraded to Alembic head before the test body."""
    upgrade_to_head(isolated_sqlite)
    return isolated_sqlite
