"""Conversation repository: singleton, ordered history, bounds, validation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.base import SINGLETON_PK
from app.db.enums import MessageRole
from app.db.models.conversation import ChatMessage, Conversation
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.conversations import (
    ConversationMessageError,
    ConversationPayloadError,
    ConversationRepository,
    ConversationRepositoryError,
    validate_structured_payload,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "conversations.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


@pytest.mark.asyncio
async def test_ensure_singleton_first_and_repeated_returns_same_row(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            first = await repo.ensure_singleton()
            second = await repo.ensure_singleton()
            assert first.id == SINGLETON_PK
            assert second.id == first.id
            count = (
                await session.execute(select(func.count()).select_from(Conversation))
            ).scalar_one()
            assert count == 1

        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            again = await repo.ensure_singleton()
            assert again.id == SINGLETON_PK
            count = (
                await session.execute(select(func.count()).select_from(Conversation))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_cannot_create_second_conversation_row(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            await repo.ensure_singleton()

        session = db.session_factory()
        try:
            session.add(Conversation(id=SINGLETON_PK))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        finally:
            await session.close()

        # CHECK constraint rejects any non-singleton primary key.
        session = db.session_factory()
        try:
            session.add(Conversation(id=2))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(Conversation))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_concurrent_ensure_singleton_independent_sessions_one_row(
    tmp_path: Path,
) -> None:
    """Independent sessions racing ensure_singleton each get the same row.

    Exercises the conflict-safe insert/select path: concurrent first creates
    (and follow-up ensures) return SINGLETON_PK without caller retry, and
    exactly one durable conversation row remains.
    """
    async with temporary_db(tmp_path) as db:

        async def ensure_in_own_transaction() -> int:
            async with db.session_scope() as session:
                row = await ConversationRepository(session).ensure_singleton()
                return row.id

        ids = await asyncio.gather(
            ensure_in_own_transaction(),
            ensure_in_own_transaction(),
            ensure_in_own_transaction(),
        )
        assert ids == [SINGLETON_PK, SINGLETON_PK, SINGLETON_PK]

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(Conversation))
            ).scalar_one()
            assert count == 1
            again = await ConversationRepository(session).ensure_singleton()
            assert again.id == SINGLETON_PK


@pytest.mark.asyncio
async def test_ensure_singleton_conflict_path_returns_existing_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When lookup misses an already-durable singleton, insert conflicts safely.

    Simulates the concurrent miss: first get returns None while the row already
    exists; ON CONFLICT DO NOTHING + select still returns SINGLETON_PK without
    raising or requiring a caller retry/rollback.
    """
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            await ConversationRepository(session).ensure_singleton()

        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            real_get = repo.get_singleton
            calls = {"n": 0}

            async def miss_then_real() -> Conversation | None:
                calls["n"] += 1
                if calls["n"] == 1:
                    return None
                return await real_get()

            monkeypatch.setattr(repo, "get_singleton", miss_then_real)
            row = await repo.ensure_singleton()
            assert row.id == SINGLETON_PK
            # Initial miss + post-insert select.
            assert calls["n"] >= 2

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(Conversation))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_append_and_list_history_are_stable_and_ordered(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            m1 = await repo.append_message(role=MessageRole.USER, content="hello")
            m2 = await repo.append_message(
                role="assistant",
                content="hi there",
                structured_payload={"card": "greeting"},
            )
            m3 = await repo.append_message(role=MessageRole.USER, content="next")

            history = await repo.list_history()
            assert [m.id for m in history] == [m1.id, m2.id, m3.id]
            assert [m.role for m in history] == ["user", "assistant", "user"]
            assert history[1].structured_payload == {"card": "greeting"}

            limited = await repo.list_history(limit=2)
            assert [m.id for m in limited] == [m1.id, m2.id]


@pytest.mark.asyncio
async def test_list_recent_for_context_enforces_bound(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            ids = []
            for i in range(5):
                row = await repo.append_message(
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"msg-{i}",
                )
                ids.append(row.id)

            recent = await repo.list_recent_for_context(limit=3)
            assert len(recent) == 3
            # Newest three, returned in chronological order for Agent context.
            assert [m.id for m in recent] == ids[-3:]
            assert [m.content for m in recent] == ["msg-2", "msg-3", "msg-4"]

            # Full history remains available for UI/history path separately.
            full = await repo.list_history()
            assert len(full) == 5
            assert len(await repo.list_recent_for_context(limit=1)) == 1

            with pytest.raises(ConversationRepositoryError, match="invalid limit"):
                await repo.list_recent_for_context(limit=0)
            with pytest.raises(ConversationRepositoryError, match="invalid limit"):
                await repo.list_recent_for_context(limit=101)
            with pytest.raises(ConversationRepositoryError, match="invalid limit"):
                await repo.list_history(limit=0)


@pytest.mark.asyncio
async def test_invalid_role_fails_before_durable_commit(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            await repo.ensure_singleton()
            with pytest.raises(ConversationMessageError, match="invalid role"):
                await repo.append_message(role="narrator", content="nope")

            count = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert count == 0

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_invalid_payload_fails_before_durable_commit(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            with pytest.raises(ConversationPayloadError):
                await repo.append_message(
                    role="user",
                    content="ok",
                    structured_payload={"raw_content": "full document body"},
                )
            with pytest.raises(ConversationPayloadError):
                await repo.append_message(
                    role="assistant",
                    content="ok",
                    structured_payload={"path": "C:/secrets/cv.pdf"},
                )
            with pytest.raises(ConversationPayloadError):
                await repo.append_message(
                    role="user",
                    content="ok",
                    structured_payload={"note": "Bearer sk-secret-token"},
                )

            count = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert count == 0

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_blank_content_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            with pytest.raises(ConversationMessageError, match="invalid content"):
                await repo.append_message(role="user", content="   ")


@pytest.mark.asyncio
async def test_append_does_not_commit_implicitly(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        session_a: AsyncSession = db.session_factory()
        try:
            repo = ConversationRepository(session_a)
            row = await repo.append_message(role="user", content="uncommitted")
            assert row.id is not None
            assert await repo.get_message(row.id) is not None

            session_b = db.session_factory()
            try:
                repo_b = ConversationRepository(session_b)
                assert await repo_b.get_message(row.id) is None
            finally:
                await session_b.close()
        finally:
            await session_a.rollback()
            await session_a.close()

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(ChatMessage))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_rollback_discards_partial_message(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        session = db.session_factory()
        try:
            repo = ConversationRepository(session)
            await repo.append_message(role="user", content="will rollback")
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            assert await repo.list_history() == []
            # Conversation singleton insert is also rolled back with the unit.
            assert await repo.get_singleton() is None


@pytest.mark.asyncio
async def test_wrong_conversation_id_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            with pytest.raises(ConversationMessageError, match="conversation_id"):
                await repo.append_message(
                    role="user",
                    content="x",
                    conversation_id=999,
                )


def test_validate_structured_payload_accepts_cards() -> None:
    assert validate_structured_payload(None) is None
    assert validate_structured_payload({}) == {}
    assert validate_structured_payload(
        {"intent": "chat", "items": [1, "ok"], "flag": True}
    ) == {"intent": "chat", "items": [1, "ok"], "flag": True}


def test_validate_structured_payload_rejects_non_mapping() -> None:
    with pytest.raises(ConversationPayloadError):
        validate_structured_payload(["not", "a", "mapping"])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_message_by_id(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ConversationRepository(session)
            row = await repo.append_message(role="system", content="note")
            loaded = await repo.get_message(row.id)
            assert loaded is not None
            assert loaded.content == "note"
            assert await repo.get_message(uuid4()) is None
