"""Integration tests for async SQLite PRAGMAs and foreign-key enforcement.

Uses temporary SQLite files only; never opens the developer database or root
``.env``. Minimal parent/child tables are created with raw DDL (not
``create_all()``) solely to prove FK enforcement.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, TypeVar

import pytest
from app.core import settings as settings_module
from app.core.settings import clear_settings_cache, get_settings
from app.db import session as session_module
from app.db.base import NAMING_CONVENTION, Base
from app.db.session import (
    REQUIRED_BUSY_TIMEOUT_MS,
    REQUIRED_FOREIGN_KEYS,
    REQUIRED_JOURNAL_MODE,
    build_async_engine,
    dispose_engine,
    get_engine,
    get_session_factory,
    read_connection_pragmas,
    session_scope,
    sqlite_url,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

T = TypeVar("T")

SANITIZED_ENV: dict[str, str] = {
    "FRONTEND_ORIGIN": "http://localhost:5173",
    "FILES_DIR": "/tmp/jobagent-files-pragma-test",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "test-neo4j-password-not-real",
    "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
    "SHOPAIKEY_API_KEY": "test-shopaikey-secret-not-real",
}


def _run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _isolate_db_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    """Point SQLITE_PATH at a temp file and clear settings/engine caches."""
    db_path = tmp_path / "pragma-test.db"
    clear_settings_cache()
    _run(dispose_engine())

    for key in (
        "APP_ENV",
        "FRONTEND_ORIGIN",
        "SQLITE_PATH",
        "FILES_DIR",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "SHOPAIKEY_BASE_URL",
        "SHOPAIKEY_API_KEY",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "MAX_PDF_SIZE_MB",
        "MAX_PDF_PAGES",
        "URL_FETCH_TIMEOUT_SECONDS",
        "URL_MAX_RESPONSE_MB",
        "TOOL_LOOP_LIMIT",
    ):
        monkeypatch.delenv(key, raising=False)

    # Never load the real developer root .env during these tests.
    monkeypatch.setattr(
        settings_module,
        "root_env_path",
        lambda: tmp_path / "nonexistent.env",
    )
    for key, value in SANITIZED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SQLITE_PATH", str(db_path))

    yield db_path

    _run(dispose_engine())
    clear_settings_cache()


def test_sqlite_url_uses_aiosqlite_and_configured_path(tmp_path: Path) -> None:
    db_path = tmp_path / "pragma-test.db"
    url = sqlite_url(db_path)
    assert url.startswith("sqlite+aiosqlite:///")
    assert db_path.resolve().as_posix() in url

    settings = get_settings()
    assert Path(settings.SQLITE_PATH).resolve() == db_path.resolve()
    engine = get_engine()
    assert str(engine.url).startswith("sqlite+aiosqlite:///")
    assert db_path.resolve().as_posix() in str(engine.url)


def test_every_application_connection_reports_required_pragmas() -> None:
    async def _check() -> None:
        engine = get_engine()
        results: list[dict[str, Any]] = []
        # Multiple distinct connections via concurrent checkouts.
        for _ in range(3):
            async with engine.connect() as conn:
                fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
                journal = (
                    await conn.execute(text("PRAGMA journal_mode"))
                ).scalar_one()
                timeout = (
                    await conn.execute(text("PRAGMA busy_timeout"))
                ).scalar_one()
                results.append(
                    {
                        "foreign_keys": int(fk),
                        "journal_mode": str(journal).lower(),
                        "busy_timeout": int(timeout),
                    }
                )

        factory = get_session_factory()
        async with factory() as session:
            results.append(await read_connection_pragmas(session))

        assert len(results) == 4
        for row in results:
            assert row["foreign_keys"] == REQUIRED_FOREIGN_KEYS
            assert row["journal_mode"] == REQUIRED_JOURNAL_MODE
            assert row["busy_timeout"] == REQUIRED_BUSY_TIMEOUT_MS

    _run(_check())


def test_build_async_engine_applies_pragmas_on_temporary_file(
    tmp_path: Path,
) -> None:
    """Isolated engines (not the process singleton) still get PRAGMAs."""
    other = tmp_path / "other.db"

    async def _check() -> None:
        engine = build_async_engine(other)
        try:
            async with engine.connect() as conn:
                fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
                journal = (
                    await conn.execute(text("PRAGMA journal_mode"))
                ).scalar_one()
                timeout = (
                    await conn.execute(text("PRAGMA busy_timeout"))
                ).scalar_one()
            assert int(fk) == REQUIRED_FOREIGN_KEYS
            assert str(journal).lower() == REQUIRED_JOURNAL_MODE
            assert int(timeout) == REQUIRED_BUSY_TIMEOUT_MS
        finally:
            await engine.dispose()

    _run(_check())


def test_foreign_key_enforcement_on_application_connection() -> None:
    async def _check() -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE parent ("
                    "id TEXT PRIMARY KEY NOT NULL"
                    ")"
                )
            )
            await conn.execute(
                text(
                    "CREATE TABLE child ("
                    "id TEXT PRIMARY KEY NOT NULL, "
                    "parent_id TEXT NOT NULL, "
                    "FOREIGN KEY (parent_id) REFERENCES parent(id)"
                    ")"
                )
            )

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                text("INSERT INTO parent (id) VALUES (:id)"),
                {"id": "p1"},
            )
            await session.commit()

        async with factory() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    text(
                        "INSERT INTO child (id, parent_id) "
                        "VALUES (:id, :parent_id)"
                    ),
                    {"id": "c1", "parent_id": "missing"},
                )
                await session.commit()
            await session.rollback()

        async with factory() as session:
            await session.execute(
                text(
                    "INSERT INTO child (id, parent_id) "
                    "VALUES (:id, :parent_id)"
                ),
                {"id": "c1", "parent_id": "p1"},
            )
            await session.commit()
            count = (
                await session.execute(text("SELECT COUNT(*) FROM child"))
            ).scalar_one()
            assert int(count) == 1

    _run(_check())


def test_session_scope_commits_and_rolls_back() -> None:
    async def _check() -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE note (id TEXT PRIMARY KEY NOT NULL)")
            )

        factory = get_session_factory()

        async with session_scope() as session:
            await session.execute(
                text("INSERT INTO note (id) VALUES (:id)"),
                {"id": "ok"},
            )

        async with factory() as session:
            value = (
                await session.execute(
                    text("SELECT id FROM note WHERE id = :id"),
                    {"id": "ok"},
                )
            ).scalar_one()
            assert value == "ok"

        with pytest.raises(RuntimeError, match="force-fail"):
            async with session_scope() as session:
                await session.execute(
                    text("INSERT INTO note (id) VALUES (:id)"),
                    {"id": "nope"},
                )
                raise RuntimeError("force-fail")

        async with factory() as session:
            missing = (
                await session.execute(
                    text("SELECT id FROM note WHERE id = :id"),
                    {"id": "nope"},
                )
            ).scalar_one_or_none()
            assert missing is None

    _run(_check())


def test_one_declarative_base_and_naming_convention() -> None:
    assert issubclass(Base, object)
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    for key in ("pk", "fk", "uq", "ck", "ix"):
        assert key in NAMING_CONVENTION
        assert NAMING_CONVENTION[key].startswith(f"{key}_")


def test_single_session_factory_identity() -> None:
    a = get_session_factory()
    b = get_session_factory()
    assert a is b
    assert get_engine() is get_engine()


def test_no_create_all_in_db_boundary_source() -> None:
    """Application db modules must not invoke metadata.create_all at runtime."""
    base_src = inspect.getsource(Base)
    session_src = inspect.getsource(session_module)
    # Detect call sites only (docstring mentions of the policy are fine).
    assert "create_all(" not in base_src
    assert "create_all(" not in session_src


def test_process_singleton_uses_settings_sqlite_path(tmp_path: Path) -> None:
    db_path = tmp_path / "pragma-test.db"

    async def _check() -> None:
        engine: AsyncEngine = get_engine()
        assert isinstance(engine, AsyncEngine)
        factory = get_session_factory()
        async with factory() as session:
            assert isinstance(session, AsyncSession)
            pragmas = await read_connection_pragmas(session)
        assert Path(get_settings().SQLITE_PATH).resolve() == db_path.resolve()
        assert pragmas["foreign_keys"] == REQUIRED_FOREIGN_KEYS
        assert pragmas["journal_mode"] == REQUIRED_JOURNAL_MODE
        assert pragmas["busy_timeout"] == REQUIRED_BUSY_TIMEOUT_MS

    _run(_check())
