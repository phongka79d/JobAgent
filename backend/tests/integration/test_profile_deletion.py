"""Integration coverage for retryable profile-scoped deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
)
from app.db.models.job_evaluations import JobEvaluation
from app.db.models.jobs import JobPost
from app.db.models.profiles import PROFILE_STATE_DELETING
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import attachment_text_chunks as chunks_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as documents_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.repositories.attachment_text_chunks import build_chunk_write
from app.services.profile_deletion import ProfileDeletionError, delete_profile
from app.storage.attachments import AttachmentStorage
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.graph_rebuild import FakeNeo4jDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.health import prepare_health_env


@pytest.fixture
def deletion_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, Path]:
    return prepare_health_env(monkeypatch, tmp_path)


class _FailOnceStorage(AttachmentStorage):
    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir)
        self.failed = False

    def delete(self, relative_path: str) -> bool:
        if not self.failed:
            self.failed = True
            return False
        return super().delete(relative_path)


def _candidate(marker: str) -> dict[str, object]:
    return {
        "full_name": marker,
        "location": "Hanoi",
        "summary": "Engineer",
        "current_title": "Engineer",
        "total_experience_years": 3.0,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.9,
    }


def _preferences() -> dict[str, object]:
    return {
        "target_roles": [],
        "preferred_locations": [],
        "acceptable_work_modes": [],
        "target_seniority": [],
    }


async def _create_ready_profile(
    session: AsyncSession,
    storage: AttachmentStorage,
    *,
    marker: str,
    archived: bool,
) -> tuple[str, str, str]:
    attachment_id = new_uuid()
    path = storage.write_bytes(attachment_id, b"%PDF-1.4\n")
    attachment = await att_repo.create_staged(
        session,
        attachment_id=attachment_id,
        file_hash=marker * 64,
        original_name=f"{marker}.pdf",
        size_bytes=9,
        storage_path=path,
        page_count=1,
    )
    await att_repo.mark_active(session, attachment.id, page_count=1)
    if archived:
        await att_repo.mark_archived(session, attachment.id)
    profile = await profiles_repo.create_profile(
        session,
        attachment_id=attachment.id,
        display_name=f"Profile {marker}",
        profile_json=_candidate(marker),
        location="Hanoi",
        extraction_version="v1",
        source_hash=marker * 64,
    )
    await profiles_repo.upsert_profile_preferences(
        session, profile_id=profile.id, preferences_json=_preferences()
    )
    await documents_repo.upsert_document(
        session,
        attachment_id=attachment.id,
        document_json={
            "attachment_id": attachment.id,
            "detected_languages": ["en"],
            "sections": [],
            "extraction_warnings": [],
            "extraction_confidence": 0.9,
        },
        profile_json=_candidate(marker),
        outline_json={"sections": []},
        extraction_version="v1",
        source_hash=marker * 64,
    )
    await chunks_repo.replace_for_attachment(
        session, attachment.id, [build_chunk_write(0, f"chunk-{marker}")]
    )
    conversation = await conversations_repo.create_for_profile(
        session, profile_id=profile.id
    )
    return profile.id, attachment.id, conversation.id


async def _create_pending_profile(
    session: AsyncSession,
    storage: AttachmentStorage,
    *,
    marker: str,
) -> tuple[str, str, str]:
    attachment_id = new_uuid()
    path = storage.write_bytes(attachment_id, b"%PDF-1.4\n")
    attachment = await att_repo.create_staged(
        session,
        attachment_id=attachment_id,
        file_hash=marker * 64,
        original_name=f"{marker}.pdf",
        size_bytes=9,
        storage_path=path,
        page_count=1,
    )
    profile = await profiles_repo.create_pending_profile(
        session,
        attachment_id=attachment.id,
        display_name=f"Pending {marker}",
    )
    conversation = await conversations_repo.create_bootstrap_for_profile(
        session, profile_id=profile.id
    )
    await profiles_repo.upsert_current_draft(
        session,
        draft_json={"candidate_profile": {}},
        source_attachment_id=attachment.id,
        target_profile_id=profile.id,
    )
    return profile.id, attachment.id, conversation.id


async def _add_completed_run(
    session: AsyncSession,
    conversation_id: str,
    *,
    content: str,
) -> str:
    message = await messages_repo.insert_message(
        session,
        conversation_id=conversation_id,
        role="user",
        content=content,
    )
    run = await runs_repo.create_run(session, user_message_id=message.id)
    await runs_repo.complete_run(session, run.id)
    return run.id


async def _put_checkpoint(db_path: Path, run_id: str) -> None:
    async with open_checkpointer(db_path) as saver:
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


def test_profile_delete_preserves_other_profile_global_job_and_normalizes_fallback(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                fallback_id, fallback_attachment, fallback_conversation = (
                    await _create_ready_profile(
                        session, storage, marker="b", archived=True
                    )
                )
                other_id, other_attachment, _ = await _create_ready_profile(
                    session, storage, marker="c", archived=True
                )
                target_id, target_attachment, target_conversation = (
                    await _create_ready_profile(
                        session, storage, marker="a", archived=False
                    )
                )
                base = datetime(2026, 7, 24, tzinfo=UTC)
                fallback = await profiles_repo.get_profile(session, fallback_id)
                other = await profiles_repo.get_profile(session, other_id)
                target = await profiles_repo.get_profile(session, target_id)
                assert fallback is not None and other is not None and target is not None
                fallback.last_opened_at = base + timedelta(minutes=2)
                other.last_opened_at = base + timedelta(minutes=1)
                target.last_opened_at = base
                await workspace_repo.set_active_profile_id(session, target_id)
                await profiles_repo.upsert_current_draft(
                    session,
                    draft_json={"candidate_profile": {"full_name": "a"}},
                    source_attachment_id=target_attachment,
                    target_profile_id=target_id,
                )
                run_id = await _add_completed_run(
                    session,
                    target_conversation,
                    content="profile-owned run without attachment FK",
                )
                job_id = new_uuid()
                now = datetime(2026, 7, 24, tzinfo=UTC)
                job = await jobs_repo.create_text_job(
                    session,
                    raw_content="global job",
                    raw_content_hash="d" * 64,
                )
                job_id = job.id
                for profile_id, suffix in ((target_id, "a"), (fallback_id, "b")):
                    session.add(
                        JobEvaluation(
                            job_id=job_id,
                            profile_id=profile_id,
                            evaluation_context_hash=suffix * 64,
                            job_revision=now,
                            profile_revision=now,
                            preferences_revision=now,
                            cv_source_hash=suffix * 64,
                            matching_contract_version="v1",
                            result_json={"score": 1},
                        )
                    )
                await session.commit()

            await _put_checkpoint(db_path, run_id)
            driver = FakeNeo4jDriver()
            driver.candidates.update({target_id, fallback_id})
            driver.jobs.add(job_id)
            driver.skills.add("python")
            result = await delete_profile(
                profile_id=target_id,
                session_factory=factory,
                storage=storage,
                graph_driver=driver,
                sqlite_path=db_path,
            )
            assert result.active_profile is not None
            assert result.active_profile.id == fallback_id
            assert result.selected_conversation is not None
            assert result.selected_conversation.id == fallback_conversation

            async with factory() as session:
                assert await profiles_repo.get_profile(session, target_id) is None
                assert await profiles_repo.get_profile(session, fallback_id) is not None
                assert await profiles_repo.get_profile(session, other_id) is not None
                fallback_row = await att_repo.get_by_id(session, fallback_attachment)
                other_row = await att_repo.get_by_id(session, other_attachment)
                assert fallback_row is not None
                assert fallback_row.state == ATTACHMENT_STATE_ACTIVE
                assert other_row is not None
                assert other_row.state == ATTACHMENT_STATE_ARCHIVED
                assert await session.get(JobPost, job_id) is not None
                evaluations = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(JobEvaluation)
                        .where(JobEvaluation.job_id == job_id)
                    )
                    or 0
                )
                assert evaluations == 1
                assert await runs_repo.get_run(session, run_id) is None
            assert not storage.exists(target_attachment)
            assert storage.exists(fallback_attachment)
            assert driver.jobs == {job_id}
            assert driver.skills == {"python"}
            async with open_checkpointer(db_path) as saver:
                assert not await thread_has_checkpoints(saver, run_id)
        finally:
            await engine.dispose()

    run_async(body())


def test_pending_profile_discard_skips_graph_and_restores_ready_fallback(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                fallback_id, fallback_attachment, _ = await _create_ready_profile(
                    session, storage, marker="r", archived=False
                )
                pending_id, pending_attachment, pending_conversation = (
                    await _create_pending_profile(session, storage, marker="p")
                )
                await workspace_repo.set_active_profile_id(session, pending_id)
                run_id = await _add_completed_run(
                    session, pending_conversation, content="pending extraction"
                )
                await session.commit()
            await _put_checkpoint(db_path, run_id)
            driver = FakeNeo4jDriver()
            result = await delete_profile(
                profile_id=pending_id,
                session_factory=factory,
                storage=storage,
                graph_driver=driver,
                sqlite_path=db_path,
            )
            assert result.active_profile is not None
            assert result.active_profile.id == fallback_id
            assert driver.queries == []
            assert not storage.exists(pending_attachment)
            async with factory() as session:
                assert await profiles_repo.get_profile(session, pending_id) is None
                fallback = await att_repo.get_by_id(session, fallback_attachment)
                assert fallback is not None
                assert fallback.state == ATTACHMENT_STATE_ACTIVE
        finally:
            await engine.dispose()

    run_async(body())


def test_file_delete_false_leaves_incomplete_profile_retryable_and_unique(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = _FailOnceStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                pending_id, attachment_id, _ = await _create_pending_profile(
                    session, storage, marker="f"
                )
                await workspace_repo.set_active_profile_id(session, pending_id)
                await session.commit()
            driver = FakeNeo4jDriver()
            with pytest.raises(ProfileDeletionError) as exc_info:
                await delete_profile(
                    profile_id=pending_id,
                    session_factory=factory,
                    storage=storage,
                    graph_driver=driver,
                    sqlite_path=db_path,
                )
            assert exc_info.value.code == "PROFILE_DELETE_RETRYABLE"
            assert str(files) not in exc_info.value.summary
            assert driver.queries == []
            async with factory() as session:
                pending = await profiles_repo.get_profile(session, pending_id)
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert pending is not None
                assert pending.state == PROFILE_STATE_DELETING
                assert pending.profile_json is None
                assert attachment is not None
                assert attachment.state == ATTACHMENT_STATE_DELETING
                incomplete = await profiles_repo.get_incomplete_profile(session)
                assert incomplete is not None and incomplete.id == pending_id

            await delete_profile(
                profile_id=pending_id,
                session_factory=factory,
                storage=storage,
                graph_driver=driver,
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await profiles_repo.get_profile(session, pending_id) is None
        finally:
            await engine.dispose()

    run_async(body())


def test_approved_profile_requires_graph_driver_and_retries_without_leaking_error(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile_id, attachment_id, _ = await _create_ready_profile(
                    session, storage, marker="g", archived=False
                )
                await workspace_repo.set_active_profile_id(session, profile_id)
                await session.commit()
            with pytest.raises(ProfileDeletionError) as exc_info:
                await delete_profile(
                    profile_id=profile_id,
                    session_factory=factory,
                    storage=storage,
                    graph_driver=None,
                    sqlite_path=db_path,
                )
            assert exc_info.value.code == "PROFILE_DELETE_RETRYABLE"
            assert "driver" not in exc_info.value.summary.lower()
            async with factory() as session:
                profile = await profiles_repo.get_profile(session, profile_id)
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert profile is not None
                assert profile.state == PROFILE_STATE_DELETING
                assert profile.profile_json == _candidate("g")
                assert attachment is not None
                assert attachment.state == ATTACHMENT_STATE_DELETING

            await delete_profile(
                profile_id=profile_id,
                session_factory=factory,
                storage=storage,
                graph_driver=FakeNeo4jDriver(),
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await profiles_repo.get_profile(session, profile_id) is None
        finally:
            await engine.dispose()

    run_async(body())


def test_approved_graph_failure_is_safe_and_retryable(
    deletion_env: tuple[Path, Path],
) -> None:
    db_path, files = deletion_env
    storage = AttachmentStorage(files)

    async def body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile_id, attachment_id, _ = await _create_ready_profile(
                    session, storage, marker="h", archived=False
                )
                await workspace_repo.set_active_profile_id(session, profile_id)
                await session.commit()
            with pytest.raises(ProfileDeletionError) as exc_info:
                await delete_profile(
                    profile_id=profile_id,
                    session_factory=factory,
                    storage=storage,
                    graph_driver=FakeNeo4jDriver(fail_on_run=True),
                    sqlite_path=db_path,
                )
            assert exc_info.value.code == "PROFILE_DELETE_RETRYABLE"
            assert "neo4j" not in exc_info.value.summary.lower()
            assert str(files) not in exc_info.value.summary
            async with factory() as session:
                profile = await profiles_repo.get_profile(session, profile_id)
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert profile is not None
                assert profile.state == PROFILE_STATE_DELETING
                assert attachment is not None
                assert attachment.state == ATTACHMENT_STATE_DELETING

            await delete_profile(
                profile_id=profile_id,
                session_factory=factory,
                storage=storage,
                graph_driver=FakeNeo4jDriver(),
                sqlite_path=db_path,
            )
            async with factory() as session:
                assert await profiles_repo.get_profile(session, profile_id) is None
        finally:
            await engine.dispose()

    run_async(body())
