"""Integration coverage for checkpoint-safe conversation deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.services.conversation_deletion import delete_conversation
from app.storage.attachments import AttachmentStorage
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import func, select

from tests.support.db_migration import run_async, session_factory
from tests.support.health import prepare_health_env


@pytest.fixture
def deletion_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path]:
    return prepare_health_env(monkeypatch, tmp_path)


async def _create_ready_profile(
    session: object,
    storage: AttachmentStorage,
    *,
    marker: str,
) -> tuple[str, str]:
    attachment_id = new_uuid()
    storage_path = storage.write_bytes(attachment_id, b"%PDF-1.4\n")
    attachment = await att_repo.create_staged(
        session,  # type: ignore[arg-type]
        attachment_id=attachment_id,
        file_hash=marker * 64,
        original_name=f"{marker}.pdf",
        size_bytes=9,
        storage_path=storage_path,
        page_count=1,
    )
    await att_repo.mark_active(session, attachment.id, page_count=1)  # type: ignore[arg-type]
    await att_repo.mark_archived(session, attachment.id)  # type: ignore[arg-type]
    profile = await profiles_repo.create_profile(
        session,  # type: ignore[arg-type]
        attachment_id=attachment.id,
        display_name=f"Profile {marker}",
        profile_json={"full_name": marker},
        location=None,
        extraction_version="v1",
        source_hash=marker * 64,
    )
    conversation = await conversations_repo.create_for_profile(
        session, profile_id=profile.id  # type: ignore[arg-type]
    )
    return profile.id, conversation.id


def test_delete_conversation_removes_only_owned_rows_and_checkpoints(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile_a, conversation_a1 = await _create_ready_profile(
                    session, storage, marker="a"
                )
                conversation_a2 = await conversations_repo.create_for_profile(
                    session, profile_id=profile_a
                )
                _profile_b, conversation_b = await _create_ready_profile(
                    session, storage, marker="b"
                )
                base = datetime(2026, 7, 24, tzinfo=UTC)
                row_a1 = await conversations_repo.get_owned(
                    session, conversation_id=conversation_a1
                )
                row_a2 = await conversations_repo.get_owned(
                    session, conversation_id=conversation_a2.id
                )
                assert row_a1 is not None and row_a2 is not None
                row_a1.last_opened_at = base
                row_a2.last_opened_at = base + timedelta(minutes=1)
                message_a = await messages_repo.insert_message(
                    session,
                    conversation_id=conversation_a1,
                    role="user",
                    content="delete this conversation",
                )
                message_b = await messages_repo.insert_message(
                    session,
                    conversation_id=conversation_b,
                    role="user",
                    content="preserve this conversation",
                )
                run_a = await runs_repo.create_run(
                    session, user_message_id=message_a.id
                )
                run_b = await runs_repo.create_run(
                    session, user_message_id=message_b.id
                )
                await runs_repo.complete_run(session, run_a.id)
                await runs_repo.complete_run(session, run_b.id)
                await session.commit()

            async with open_checkpointer(db_path) as saver:
                for run_id in (run_a.id, run_b.id):
                    await saver.aput(
                        {
                            "configurable": {
                                "thread_id": run_id,
                                "checkpoint_ns": "",
                            }
                        },
                        empty_checkpoint(),
                        {},
                        {},
                    )

            result = await delete_conversation(
                conversation_id=conversation_a1,
                session_factory=factory,
                sqlite_path=db_path,
            )
            assert result.selected_conversation.id == conversation_a2.id
            assert result.replacement_conversation_id is None

            async with factory() as session:
                assert (
                    await conversations_repo.get_owned(
                        session, conversation_id=conversation_a1
                    )
                    is None
                )
                assert await messages_repo.get_by_id(session, message_a.id) is None
                assert await runs_repo.get_run(session, run_a.id) is None
                assert await messages_repo.get_by_id(session, message_b.id) is not None
                assert await runs_repo.get_run(session, run_b.id) is not None

            async with open_checkpointer(db_path) as saver:
                assert not await thread_has_checkpoints(saver, run_a.id)
                assert await thread_has_checkpoints(saver, run_b.id)
        finally:
            await engine.dispose()

    run_async(body())


def test_delete_last_conversation_creates_exactly_one_empty_replacement(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile_id, conversation_id = await _create_ready_profile(
                    session, storage, marker="c"
                )
                await messages_repo.insert_message(
                    session,
                    conversation_id=conversation_id,
                    role="user",
                    content="only message",
                )
                await session.commit()

            result = await delete_conversation(
                conversation_id=conversation_id,
                session_factory=factory,
                sqlite_path=db_path,
            )
            assert result.replacement_conversation_id == result.selected_conversation.id
            assert result.selected_conversation.title == "Chat mới"

            async with factory() as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(conversations_repo.Conversation)
                    .where(conversations_repo.Conversation.profile_id == profile_id)
                )
                messages = await messages_repo.list_messages(
                    session,
                    conversation_id=result.selected_conversation.id,
                )
                assert count == 1
                assert messages == []
        finally:
            await engine.dispose()

    run_async(body())
