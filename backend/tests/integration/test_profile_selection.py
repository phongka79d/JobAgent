from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.ids import new_uuid
from app.db.models.chat import CHAT_MESSAGE_ROLE_USER
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import conversations as conversation_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.services.activity_gate import ActivityBlockedError, assert_workspace_idle
from sqlalchemy import text

from tests.support.db_migration import run_async, session_factory


def _attachment_sql(attachment_id: str, file_hash: str) -> tuple[str, dict[str, str]]:
    return (
        "INSERT INTO attachments (id, file_hash, original_name, mime_type, "
        "size_bytes, page_count, storage_path, state, created_at, updated_at) "
        "VALUES (:id, :hash, 'cv.pdf', 'application/pdf', 10, 1, :path, "
        "'archived', :now, :now)",
        {
            "id": attachment_id,
            "hash": file_hash,
            "path": f"{attachment_id}.pdf",
            "now": "2026-07-23 00:00:00+00:00",
        },
    )


def test_profile_conversation_selection_owner_and_activity_gate(
    migrated_sqlite: Path,
) -> None:
    async def body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_a, attachment_b = new_uuid(), new_uuid()
                for attachment_id, file_hash in (
                    (attachment_a, "a" * 64),
                    (attachment_b, "b" * 64),
                ):
                    sql, params = _attachment_sql(attachment_id, file_hash)
                    await session.execute(text(sql), params)
                profile_a = await profiles_repo.create_profile(
                    session,
                    attachment_id=attachment_a,
                    display_name="A",
                    profile_json={},
                    location=None,
                    extraction_version="v1",
                    source_hash="source-a",
                )
                profile_b = await profiles_repo.create_profile(
                    session,
                    attachment_id=attachment_b,
                    display_name="B",
                    profile_json={},
                    location=None,
                    extraction_version="v1",
                    source_hash="source-b",
                )
                first = await conversation_repo.create_for_profile(
                    session, profile_id=profile_a.id
                )
                recent = await conversation_repo.create_for_profile(
                    session, profile_id=profile_a.id
                )
                foreign = await conversation_repo.create_for_profile(
                    session, profile_id=profile_b.id
                )
                base = datetime(2026, 7, 23, tzinfo=UTC)
                first.last_opened_at = base
                recent.last_opened_at = base + timedelta(seconds=1)
                await workspace_repo.set_active_profile_id(session, profile_a.id)
                own_message = await messages_repo.insert_message(
                    session,
                    conversation_id=recent.id,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="A only",
                )
                await messages_repo.insert_message(
                    session,
                    conversation_id=foreign.id,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="B only",
                )
                run = await runs_repo.create_run(
                    session, user_message_id=own_message.id
                )
                await session.commit()

            async with factory() as session:
                selected = await conversation_repo.most_recent_for_profile(
                    session, profile_id=profile_a.id
                )
                assert selected is not None and selected.id == recent.id
                owner = await conversation_repo.resolve_owner(session, recent.id)
                assert owner is not None
                assert owner.profile_id == profile_a.id
                assert owner.attachment_id == attachment_a
                rows = await messages_repo.list_messages(
                    session, conversation_id=foreign.id
                )
                assert [row.content for row in rows] == ["B only"]
                resolved = await runs_repo.resolve_run_owner(session, run.id)
                assert resolved == owner
                try:
                    await assert_workspace_idle(session)
                except ActivityBlockedError as error:
                    assert error.code == "PROFILE_SWITCH_BLOCKED"
                else:
                    raise AssertionError("running run must block workspace mutation")
                await runs_repo.interrupt_run(
                    session,
                    run.id,
                    pending_approval_json={"kind": "profile_commit"},
                )
                try:
                    await assert_workspace_idle(session)
                except ActivityBlockedError as error:
                    assert error.code == "PROFILE_SWITCH_BLOCKED"
                else:
                    raise AssertionError(
                        "interrupted run must block workspace mutation"
                    )
        finally:
            await engine.dispose()

    run_async(body())
