"""Conversation-path ownership regressions for Task 4."""

from __future__ import annotations

from pathlib import Path

from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.services.chat_turns import create_user_turn
from sqlalchemy import text

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async, session_factory
from tests.support.health import FakeDriver
from tests.support.public_api import (
    ai_text,
    client_with_fake_chat,
    parse_sse_wire,
)


async def _seed_owner_pair(factory: object) -> tuple[str, str, str]:
    async with factory() as session:  # type: ignore[operator]
        attachment_a, attachment_b = new_uuid(), new_uuid()
        now = "2026-07-23 00:00:00+00:00"
        for attachment_id, file_hash in (
            (attachment_a, "a" * 64),
            (attachment_b, "b" * 64),
        ):
            await session.execute(
                text(
                    "INSERT INTO attachments "
                    "(id, file_hash, original_name, mime_type, size_bytes, "
                    "page_count, storage_path, state, created_at, updated_at) "
                    "VALUES (:id, :hash, 'cv.pdf', 'application/pdf', 10, 1, "
                    ":path, 'archived', :now, :now)"
                ),
                {
                    "id": attachment_id,
                    "hash": file_hash,
                    "path": f"{attachment_id}.pdf",
                    "now": now,
                },
            )
        profile_a = await profiles_repo.create_profile(
            session,
            attachment_id=attachment_a,
            display_name="Profile A",
            profile_json={},
            location=None,
            extraction_version="v1",
            source_hash="source-a",
        )
        profile_b = await profiles_repo.create_profile(
            session,
            attachment_id=attachment_b,
            display_name="Profile B",
            profile_json={},
            location=None,
            extraction_version="v1",
            source_hash="source-b",
        )
        conversation_a = await conversations_repo.create_for_profile(
            session, profile_id=profile_a.id
        )
        conversation_b = await conversations_repo.create_for_profile(
            session, profile_id=profile_b.id
        )
        await session.commit()
        return conversation_a.id, conversation_b.id, attachment_b


def test_http_history_and_turns_stay_with_durable_owner(
    chat_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _files, _fake = chat_env

    async def seed() -> tuple[str, str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            return await _seed_owner_pair(factory)
        finally:
            await engine.dispose()

    conversation_a, conversation_b, attachment_b = run_async(seed())
    model = FakeChatModel(
        responses=[ai_text("A assistant only"), ai_text("B assistant only")]
    )
    with client_with_fake_chat(db_path, model) as client:
        mismatch = client.post(
            f"/api/conversations/{conversation_a}/turns",
            json={"message": "foreign attachment", "attachment_ids": [attachment_b]},
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"]["code"] == "CONVERSATION_PROFILE_MISMATCH"

        turn_a = client.post(
            f"/api/conversations/{conversation_a}/turns",
            json={"message": "A user only", "attachment_ids": []},
        )
        assert turn_a.status_code == 200
        assert parse_sse_wire(turn_a.text)[-1]["event"] == "run_completed"

        turn_b = client.post(
            f"/api/conversations/{conversation_b}/turns",
            json={"message": "B user only", "attachment_ids": []},
        )
        assert turn_b.status_code == 200
        assert parse_sse_wire(turn_b.text)[-1]["event"] == "run_completed"

        history_a = client.get(f"/api/conversations/{conversation_a}/history")
        history_b = client.get(f"/api/conversations/{conversation_b}/history")

    assert history_a.status_code == 200
    assert history_b.status_code == 200
    contents_a = [item["content"] for item in history_a.json()["items"]]
    contents_b = [item["content"] for item in history_b.json()["items"]]
    assert contents_a == ["A user only", "A assistant only"]
    assert contents_b == ["B user only", "B assistant only"]
    assert not set(contents_a).intersection(contents_b)


def test_first_nonempty_user_message_sets_title_once(migrated_sqlite: Path) -> None:
    async def body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            conversation_a, _, _ = await _seed_owner_pair(factory)
            await create_user_turn(
                conversation_id=conversation_a,
                message="  A   normalized first message  ",
                attachment_ids=[],
                session_factory=factory,
            )
            async with factory() as session:
                row = await conversations_repo.get_owned(
                    session, conversation_id=conversation_a
                )
                assert row is not None
                assert row.title == "A normalized first message"
        finally:
            await engine.dispose()

    run_async(body())
