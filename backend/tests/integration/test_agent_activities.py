from __future__ import annotations

from pathlib import Path

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.chat import CHAT_MESSAGE_ROLE_USER
from app.db.session import build_async_engine, session_scope
from app.repositories import agent_activities as activity_repo
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.services.agent_activity import AgentActivityService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.db_migration import run_async, session_factory


async def _seed_run(session: AsyncSession) -> str:
    attachment_id = new_uuid()
    profile_id = new_uuid()
    conversation_id = new_uuid()
    now = utc_now()
    await session.execute(
        text(
            "INSERT INTO attachments ("
            "id, file_hash, original_name, mime_type, size_bytes, page_count, "
            "storage_path, state, created_at, updated_at) VALUES ("
            ":a, :h, 'activity.pdf', 'application/pdf', 1, 1, :p, "
            "'archived', :n, :n)"
        ),
        {
            "a": attachment_id,
            "h": f"activity-{attachment_id}",
            "p": f"activity/{attachment_id}.pdf",
            "n": now,
        },
    )
    await session.execute(
        text(
            "INSERT INTO profiles ("
            "id, attachment_id, display_name, profile_json, extraction_version, "
            "source_hash, state, created_at, updated_at, last_opened_at) VALUES ("
            ":p, :a, 'Activity profile', '{}', 'v1', :h, 'ready', :n, :n, :n)"
        ),
        {"p": profile_id, "a": attachment_id, "h": f"source-{attachment_id}", "n": now},
    )
    await session.execute(
        text(
            "INSERT INTO conversations ("
            "id, profile_id, title, created_at, updated_at, last_opened_at) "
            "VALUES (:c, :p, 'Activity', :n, :n, :n)"
        ),
        {"c": conversation_id, "p": profile_id, "n": now},
    )
    user = await messages_repo.insert_message(
        session,
        conversation_id=conversation_id,
        role=CHAT_MESSAGE_ROLE_USER,
        content="activity turn",
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    return run.id


async def _seed(factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_scope(factory) as session:
        return await _seed_run(session)


def test_service_allocates_order_and_finishes_assistant(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            run_id = await _seed(factory)
            service = AgentActivityService(factory)
            assistant = await service.start_assistant(
                run_id=run_id,
                label="Generating reply",
                technical_name="response_generation",
            )
            tool = await service.record_tool(
                run_id=run_id,
                activity_id=new_uuid(),
                label="Search jobs",
                technical_name="query_jobs",
                state="running",
                duration_ms=None,
                error_code=None,
            )
            terminal = await service.finish(
                activity_id=assistant.activity_id,
                state="completed",
                duration_ms=25,
                error_code=None,
            )
            assert (assistant.sequence, tool.sequence) == (0, 1)
            assert terminal.activity_id == assistant.activity_id
            assert terminal.sequence == 0 and terminal.state == "completed"
            async with factory() as session:
                rows = await activity_repo.list_for_run_ids(session, [run_id])
            assert [row.id for row in rows] == [assistant.activity_id, tool.activity_id]
        finally:
            await engine.dispose()

    run_async(_body())


def test_tool_upsert_keeps_one_row_and_sequence(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            run_id = await _seed(factory)
            activity_id = new_uuid()
            service = AgentActivityService(factory)
            running = await service.record_tool(
                run_id=run_id,
                activity_id=activity_id,
                label="Search jobs",
                technical_name="query_jobs",
                state="running",
                duration_ms=None,
                error_code=None,
            )
            completed = await service.record_tool(
                run_id=run_id,
                activity_id=activity_id,
                label="Search jobs",
                technical_name="query_jobs",
                state="completed",
                duration_ms=10,
                error_code=None,
            )
            async with factory() as session:
                rows = await activity_repo.list_for_run_ids(session, [run_id])
            assert len(rows) == 1
            assert completed.sequence == running.sequence == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_deleting_run_cascades_activities(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            run_id = await _seed(factory)
            await AgentActivityService(factory).start_assistant(
                run_id=run_id,
                label="Generating reply",
                technical_name="response_generation",
            )
            async with session_scope(factory) as session:
                assert await runs_repo.delete_run(session, run_id)
            async with factory() as session:
                assert await activity_repo.list_for_run_ids(session, [run_id]) == []
        finally:
            await engine.dispose()

    run_async(_body())
