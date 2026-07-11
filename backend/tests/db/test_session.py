"""Async engine/session lifecycle, isolation, and rollback behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.db.base import SINGLETON_PK
from app.db.models.conversation import Conversation
from app.db.models.memory import MemoryFact
from app.db.session import (
    create_async_engine_for_path,
    create_session_manager,
    sqlite_url_for_path,
)
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError


def test_sqlite_url_for_absolute_and_relative_paths(tmp_path: Path) -> None:
    absolute = tmp_path / "abs.db"
    url = sqlite_url_for_path(absolute)
    assert url.startswith("sqlite+aiosqlite:///")
    assert absolute.as_posix() in url or str(absolute).replace("\\", "/") in url

    relative = Path("relative.db")
    rel_url = sqlite_url_for_path(relative)
    assert rel_url == "sqlite+aiosqlite:///relative.db"


def test_create_async_engine_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir" / "app.db"
    engine = create_async_engine_for_path(nested)
    assert nested.parent.is_dir()
    assert engine.url.drivername == "sqlite+aiosqlite"


@pytest.mark.asyncio
async def test_foreign_keys_pragma_enabled_on_connections(tmp_path: Path) -> None:
    manager = create_session_manager(tmp_path / "session.db")
    try:
        await manager.create_all()
        assert await manager.foreign_keys_enabled() is True
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_session_scope_commits_on_success(tmp_path: Path) -> None:
    manager = create_session_manager(tmp_path / "session.db")
    try:
        await manager.create_all()
        async with manager.session_scope() as session:
            session.add(Conversation(id=SINGLETON_PK))
            session.add(MemoryFact(key="k1", value_json={"v": 1}, source="test"))

        async with manager.session_scope() as session:
            fact = (
                await session.execute(select(MemoryFact).where(MemoryFact.key == "k1"))
            ).scalar_one()
            assert fact.value_json == {"v": 1}
            conv = (
                await session.execute(
                    select(Conversation).where(Conversation.id == SINGLETON_PK)
                )
            ).scalar_one()
            assert conv.id == SINGLETON_PK
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_session_scope_rollback_does_not_leak_partial_state(
    tmp_path: Path,
) -> None:
    manager = create_session_manager(tmp_path / "session.db")
    try:
        await manager.create_all()

        async with manager.session_scope() as session:
            session.add(Conversation(id=SINGLETON_PK))

        with pytest.raises(RuntimeError, match="boom"):
            async with manager.session_scope() as session:
                session.add(MemoryFact(key="partial", value_json=1, source="test"))
                await session.flush()
                raise RuntimeError("boom")

        async with manager.session_scope() as session:
            result = await session.execute(
                select(MemoryFact).where(MemoryFact.key == "partial")
            )
            assert result.scalar_one_or_none() is None
            conv = (
                await session.execute(
                    select(Conversation).where(Conversation.id == SINGLETON_PK)
                )
            ).scalar_one_or_none()
            assert conv is not None
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_explicit_rollback_on_session_factory(tmp_path: Path) -> None:
    manager = create_session_manager(tmp_path / "session.db")
    try:
        await manager.create_all()
        session = manager.session_factory()
        try:
            session.add(MemoryFact(key="rolled", value_json={"a": True}, source="test"))
            await session.flush()
            await session.rollback()
            again = await session.execute(
                select(MemoryFact).where(MemoryFact.key == "rolled")
            )
            assert again.scalar_one_or_none() is None
        finally:
            await session.close()
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_file_isolation_between_temp_databases(tmp_path: Path) -> None:
    path_a = tmp_path / "a.db"
    path_b = tmp_path / "b.db"
    mgr_a = create_session_manager(path_a)
    mgr_b = create_session_manager(path_b)
    try:
        await mgr_a.create_all()
        await mgr_b.create_all()
        async with mgr_a.session_scope() as session:
            session.add(MemoryFact(key="only_a", value_json=1, source="a"))
        async with mgr_b.session_scope() as session:
            found = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_a")
                )
            ).scalar_one_or_none()
            assert found is None
            session.add(MemoryFact(key="only_b", value_json=2, source="b"))
        async with mgr_a.session_scope() as session:
            found_b = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_b")
                )
            ).scalar_one_or_none()
            assert found_b is None
            found_a = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_a")
                )
            ).scalar_one()
            assert found_a.value_json == 1
    finally:
        await mgr_a.dispose()
        await mgr_b.dispose()


@pytest.mark.asyncio
async def test_in_memory_engine_supports_create_all_and_queries() -> None:
    manager = create_session_manager(":memory:", in_memory=True)
    try:
        await manager.create_all()
        assert await manager.foreign_keys_enabled() is True
        async with manager.session_scope() as session:
            session.add(MemoryFact(key="mem", value_json=["x"], source="mem"))
        async with manager.session_scope() as session:
            row = (
                await session.execute(select(MemoryFact).where(MemoryFact.key == "mem"))
            ).scalar_one()
            assert row.value_json == ["x"]
        async with manager.engine.connect() as conn:
            count = (
                await conn.execute(text("SELECT COUNT(*) FROM memory_facts"))
            ).scalar_one()
            assert int(count) == 1
    finally:
        await manager.dispose()


async def _peer_must_not_see_uncommitted(peer_session: object, key: str) -> None:
    """Peer session must not observe another connection's uncommitted row.

    On a real shared-cache SQLite database, concurrent access while a writer
    holds a table lock may raise ``database is locked`` / ``database table is
    locked`` instead of returning an empty result — both prove isolation.
    """
    try:
        unseen = await peer_session.execute(  # type: ignore[union-attr]
            select(MemoryFact).where(MemoryFact.key == key)
        )
        assert unseen.scalar_one_or_none() is None
    except OperationalError as exc:
        assert "locked" in str(exc).lower()
        # Failed statement leaves the peer transaction unusable until rollback.
        await peer_session.rollback()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_in_memory_simultaneous_sessions_are_transaction_isolated() -> None:
    """Distinct connections: uncommitted work is not visible or committed by peers."""
    manager = create_session_manager(":memory:", in_memory=True)
    session_1 = None
    session_2 = None
    try:
        await manager.create_all()
        assert await manager.foreign_keys_enabled() is True

        session_1 = manager.session_factory()
        session_2 = manager.session_factory()

        # Prove sessions are not sharing one physical SQLite connection.
        conn_1 = await session_1.connection()
        conn_2 = await session_2.connection()
        raw_1 = await conn_1.get_raw_connection()
        raw_2 = await conn_2.get_raw_connection()
        assert raw_1.driver_connection is not raw_2.driver_connection

        session_1.add(MemoryFact(key="s1_only", value_json=1, source="s1"))
        await session_1.flush()

        # Session 2 must not observe session 1's uncommitted row.
        await _peer_must_not_see_uncommitted(session_2, "s1_only")

        # Session 1 rollback drops only its transaction; peer never sees the row.
        await session_1.rollback()
        after_rollback = await session_2.execute(
            select(MemoryFact).where(MemoryFact.key == "s1_only")
        )
        assert after_rollback.scalar_one_or_none() is None

        # Committed data is shared within the same manager.
        session_1.add(MemoryFact(key="shared", value_json={"ok": True}, source="s1"))
        await session_1.commit()
        shared = (
            await session_2.execute(
                select(MemoryFact).where(MemoryFact.key == "shared")
            )
        ).scalar_one()
        assert shared.value_json == {"ok": True}

        # Independent rollbacks: each session only undoes its own work.
        session_1.add(MemoryFact(key="pending_a", value_json=1, source="s1"))
        await session_1.flush()
        await session_1.rollback()
        session_2.add(MemoryFact(key="pending_b", value_json=2, source="s2"))
        await session_2.flush()
        await session_2.rollback()
        remaining = (
            await session_1.execute(
                select(MemoryFact).where(
                    MemoryFact.key.in_(("pending_a", "pending_b"))
                )
            )
        ).scalars().all()
        assert remaining == []
        still_shared = (
            await session_1.execute(
                select(MemoryFact).where(MemoryFact.key == "shared")
            )
        ).scalar_one()
        assert still_shared.value_json == {"ok": True}
    finally:
        if session_1 is not None:
            await session_1.close()
        if session_2 is not None:
            await session_2.close()
        await manager.dispose()


@pytest.mark.asyncio
async def test_in_memory_managers_are_isolated_and_dispose_cleanly() -> None:
    manager_a = create_session_manager(":memory:", in_memory=True)
    manager_b = create_session_manager(":memory:", in_memory=True)
    try:
        await manager_a.create_all()
        await manager_b.create_all()
        assert await manager_a.foreign_keys_enabled() is True
        assert await manager_b.foreign_keys_enabled() is True

        async with manager_a.session_scope() as session:
            session.add(MemoryFact(key="only_a", value_json=1, source="a"))

        async with manager_b.session_scope() as session:
            found = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_a")
                )
            ).scalar_one_or_none()
            assert found is None
            session.add(MemoryFact(key="only_b", value_json=2, source="b"))

        async with manager_a.session_scope() as session:
            found_b = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_b")
                )
            ).scalar_one_or_none()
            assert found_b is None
            found_a = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_a")
                )
            ).scalar_one()
            assert found_a.value_json == 1

        # FK pragma remains on fresh connections after concurrent use.
        async with manager_a.engine.connect() as c1, manager_a.engine.connect() as c2:
            fk1 = (await c1.execute(text("PRAGMA foreign_keys"))).scalar_one()
            fk2 = (await c2.execute(text("PRAGMA foreign_keys"))).scalar_one()
            assert int(fk1) == 1
            assert int(fk2) == 1
    finally:
        await manager_a.dispose()
        await manager_b.dispose()


def test_in_memory_url_puts_uri_true_on_sqlalchemy_url() -> None:
    """Dialect only builds native SQLite URIs when uri=true is on the URL query."""
    engine = create_async_engine_for_path(":memory:", in_memory=True)
    try:
        url = engine.url
        assert url.drivername == "sqlite+aiosqlite"
        assert url.database is not None
        assert url.database.startswith("file:jobagent-")
        assert url.query.get("mode") == "memory"
        assert url.query.get("cache") == "shared"
        assert url.query.get("uri") == "true"

        filename, opts = engine.sync_engine.dialect.create_connect_args(url)
        assert opts.get("uri") is True
        assert len(filename) == 1
        assert filename[0].startswith("file:jobagent-")
        assert "mode=memory" in filename[0]
        assert "cache=shared" in filename[0]
        # Must not path-absolutize (that produced the backend/file artifact).
        assert not filename[0].startswith("/") and ":\\" not in filename[0][:3]
        assert not filename[0].lower().startswith("c:\\")
    finally:
        # Sync dispose is fine; engine was never used asynchronously.
        engine.sync_engine.dispose()


@pytest.mark.asyncio
async def test_in_memory_manager_creates_no_filesystem_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named shared-cache memory mode must not create cwd filesystem DB files."""
    monkeypatch.chdir(tmp_path)
    assert Path.cwd().resolve() == tmp_path.resolve()
    before = {p.name for p in tmp_path.iterdir()}

    manager = create_session_manager(":memory:", in_memory=True)
    session_1 = None
    session_2 = None
    try:
        await manager.create_all()
        assert await manager.foreign_keys_enabled() is True

        session_1 = manager.session_factory()
        session_2 = manager.session_factory()
        conn_1 = await session_1.connection()
        conn_2 = await session_2.connection()
        raw_1 = await conn_1.get_raw_connection()
        raw_2 = await conn_2.get_raw_connection()
        assert raw_1.driver_connection is not raw_2.driver_connection

        session_1.add(MemoryFact(key="iso_pending", value_json=1, source="s1"))
        await session_1.flush()
        await _peer_must_not_see_uncommitted(session_2, "iso_pending")

        await session_1.rollback()
        after_rollback = await session_2.execute(
            select(MemoryFact).where(MemoryFact.key == "iso_pending")
        )
        assert after_rollback.scalar_one_or_none() is None

        session_1.add(MemoryFact(key="shared_mem", value_json={"ok": True}, source="s1"))
        await session_1.commit()
        shared = (
            await session_2.execute(
                select(MemoryFact).where(MemoryFact.key == "shared_mem")
            )
        ).scalar_one()
        assert shared.value_json == {"ok": True}

        # Simultaneous connections keep foreign_keys=ON.
        async with manager.engine.connect() as c1, manager.engine.connect() as c2:
            fk1 = (await c1.execute(text("PRAGMA foreign_keys"))).scalar_one()
            fk2 = (await c2.execute(text("PRAGMA foreign_keys"))).scalar_one()
            assert int(fk1) == 1
            assert int(fk2) == 1
    finally:
        if session_1 is not None:
            await session_1.close()
        if session_2 is not None:
            await session_2.close()
        await manager.dispose()

    after = {p.name for p in tmp_path.iterdir()}
    created = after - before
    assert created == set()
    assert "file" not in after
    assert not any(
        name == "file" or name.startswith("file:") or name.endswith(".db")
        for name in after
    )


@pytest.mark.asyncio
async def test_in_memory_separate_managers_isolated_under_temp_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate managers stay isolated; no filesystem artifact under temp cwd."""
    monkeypatch.chdir(tmp_path)
    manager_a = create_session_manager(":memory:", in_memory=True)
    manager_b = create_session_manager(":memory:", in_memory=True)
    try:
        await manager_a.create_all()
        await manager_b.create_all()
        assert await manager_a.foreign_keys_enabled() is True
        assert await manager_b.foreign_keys_enabled() is True

        async with manager_a.session_scope() as session:
            session.add(MemoryFact(key="only_a_tmp", value_json=1, source="a"))

        async with manager_b.session_scope() as session:
            found = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "only_a_tmp")
                )
            ).scalar_one_or_none()
            assert found is None

        async with manager_a.engine.connect() as c1, manager_a.engine.connect() as c2:
            fk1 = (await c1.execute(text("PRAGMA foreign_keys"))).scalar_one()
            fk2 = (await c2.execute(text("PRAGMA foreign_keys"))).scalar_one()
            assert int(fk1) == 1
            assert int(fk2) == 1
    finally:
        await manager_a.dispose()
        await manager_b.dispose()

    assert list(tmp_path.iterdir()) == []
