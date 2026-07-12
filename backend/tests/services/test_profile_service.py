"""Atomic profile commit service behavior."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.db.enums import AttachmentState
from app.db.models.profile import ProfileDraft as ProfileDraftRow
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.repositories.graph_outbox import (
    CANDIDATE_SYNC_OPERATION,
    GraphOutboxRepository,
)
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import (
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from app.services.profile_service import ProfileCommitError, ProfileCommitService
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def _database(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    database = create_session_manager(tmp_path / "profile-service.db")
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


def _profile(summary: str) -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "summary": summary,
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": [],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.8,
        }
    )


def _preferences(role: str) -> JobPreferences:
    return JobPreferences.model_validate(
        {
            "target_roles": [role],
            "preferred_locations": ["Remote"],
            "acceptable_work_modes": ["remote"],
            "target_seniority": ["mid"],
        }
    )


def _document(summary: str, *, role: str | None = None) -> ProfileDraftDocument:
    profile = _profile(summary)
    preferences = _preferences(role) if role is not None else None
    approval = build_approval_summary(profile, preferences=preferences)
    if preferences is None:
        return ProfileDraftDocument(profile=profile, approval_summary=approval)
    return ProfileDraftDocument(
        profile=profile,
        preferences=preferences,
        approval_summary=approval,
    )


async def _add_source(
    database: DatabaseSessionManager,
    storage: FilesystemAttachmentStorage,
    *,
    content: bytes,
    state: str = AttachmentState.STAGED.value,
) -> UUID:
    attachment_id = uuid4()
    stored = await storage.stage(attachment_id, iter_byte_chunks(content))
    async with database.session_scope() as session:
        repository = AttachmentRepository(session)
        await repository.add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=(content.hex() + "0" * 64)[:64],
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=len(content),
                storage_path=stored.storage_path,
                page_count=1,
            )
        )
        if state == AttachmentState.ACTIVE.value:
            active_path = await storage.promote(stored.storage_path)
            await repository.mark_active(attachment_id, storage_path=active_path)
    return attachment_id


async def _add_draft(
    database: DatabaseSessionManager,
    attachment_id: UUID,
    document: ProfileDraftDocument,
) -> UUID:
    async with database.session_scope() as session:
        return (
            await ProfileDraftRepository(session).create(
                document,
                source_attachment_id=attachment_id,
            )
        ).id


async def _read_bytes(
    storage: FilesystemAttachmentStorage, storage_path: str
) -> bytes:
    stream = await storage.open(storage_path)
    return b"".join([chunk async for chunk in stream])


@pytest.mark.asyncio
async def test_commit_promotes_and_atomically_replaces_state(tmp_path: Path) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        source_id = await _add_source(database, storage, content=b"new")
        draft_id = await _add_draft(database, source_id, _document("New", role="Platform"))

        result = await ProfileCommitService(database, storage).commit_draft(draft_id)

        assert result.active_attachment_id == source_id
        assert result.cleanup_pending is False
        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "New"
            assert approved.active_attachment_id == source_id
            assert (await PreferencesRepository(session).get()).target_roles == ["Platform"]  # type: ignore[union-attr]
            assert await ProfileDraftRepository(session).get(draft_id) is None
            source = await AttachmentRepository(session).get_by_id(source_id)
            assert source is not None
            assert source.state == AttachmentState.ACTIVE.value
            assert await _read_bytes(storage, source.storage_path) == b"new"
            outbox = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert outbox is not None
            assert outbox.payload == {"candidate_id": "1"}


@pytest.mark.asyncio
async def test_active_context_keeps_file_and_omitted_preferences(tmp_path: Path) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        active_id = await _add_source(
            database, storage, content=b"same", state=AttachmentState.ACTIVE.value
        )
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("Old"), active_attachment_id=active_id
            )
            await PreferencesRepository(session).replace(_preferences("Keep"))
        draft_id = await _add_draft(database, active_id, _document("Corrected"))

        result = await ProfileCommitService(database, storage).commit_draft(draft_id)

        assert result.active_attachment_id == active_id
        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "Corrected"
            assert (await PreferencesRepository(session).get()).target_roles == ["Keep"]  # type: ignore[union-attr]
            attachment = await AttachmentRepository(session).get_by_id(active_id)
            assert attachment is not None
            assert await _read_bytes(storage, attachment.storage_path) == b"same"


@pytest.mark.asyncio
async def test_precommit_failure_restores_staged_source_and_old_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
        draft_id = await _add_draft(database, new_id, _document("New"))

        async def fail_delete(self: ProfileDraftRepository, draft: UUID) -> bool:
            raise RuntimeError("injected draft delete")

        monkeypatch.setattr(ProfileDraftRepository, "delete", fail_delete)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "Old"
            assert approved.active_attachment_id == old_id
            source = await AttachmentRepository(session).get_by_id(new_id)
            assert source is not None
            assert source.state == AttachmentState.STAGED.value
            assert await ProfileDraftRepository(session).get(draft_id) is not None
            assert await _read_bytes(storage, source.storage_path) == b"new"
            old = await AttachmentRepository(session).get_by_id(old_id)
            assert old is not None
            assert await _read_bytes(storage, old.storage_path) == b"old"


@pytest.mark.asyncio
async def test_cancellation_after_promotion_restores_readable_staged_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        source_id = await _add_source(database, storage, content=b"new")
        draft_id = await _add_draft(database, source_id, _document("New"))

        async def cancel_replace(*args: Any, **kwargs: Any) -> Any:
            raise asyncio.CancelledError

        monkeypatch.setattr(ProfileRepository, "replace", cancel_replace)
        with pytest.raises(asyncio.CancelledError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        monkeypatch.undo()
        async with database.session_scope() as session:
            source = await AttachmentRepository(session).get_by_id(source_id)
            assert source is not None
            assert source.state == AttachmentState.STAGED.value
            assert await ProfileDraftRepository(session).get(draft_id) is not None
            assert await _read_bytes(storage, source.storage_path) == b"new"


@pytest.mark.asyncio
async def test_cleanup_failure_leaves_retryable_unreferenced_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
        draft_id = await _add_draft(database, new_id, _document("New"))
        original_delete = storage.delete

        async def fail_old_delete(storage_path: str) -> None:
            if storage_path.endswith(str(old_id)):
                raise OSError("injected cleanup")
            await original_delete(storage_path)

        monkeypatch.setattr(storage, "delete", fail_old_delete)
        result = await ProfileCommitService(database, storage).commit_draft(draft_id)
        assert result.cleanup_pending is True

        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.active_attachment_id == new_id
            assert await AttachmentRepository(session).get_by_id(old_id) is not None

        monkeypatch.setattr(storage, "delete", original_delete)
        assert await ProfileCommitService(database, storage).retry_cleanup(limit=10) == 1
        async with database.session_scope() as session:
            assert await AttachmentRepository(session).get_by_id(old_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner", "method"),
    [
        (AttachmentRepository, "mark_active"),
        (ProfileRepository, "replace"),
        (PreferencesRepository, "replace"),
        (ProfileDraftRepository, "delete"),
        (GraphOutboxRepository, "enqueue"),
    ],
)
async def test_each_transaction_mutation_failure_restores_old_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: type[Any],
    method: str,
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
            await PreferencesRepository(session).replace(_preferences("OldRole"))
        draft_id = await _add_draft(database, new_id, _document("New", role="NewRole"))

        async def fail(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(f"injected {method}")

        monkeypatch.setattr(owner, method, fail)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        monkeypatch.undo()
        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "Old"
            assert approved.active_attachment_id == old_id
            assert (await PreferencesRepository(session).get()).target_roles == ["OldRole"]  # type: ignore[union-attr]
            source = await AttachmentRepository(session).get_by_id(new_id)
            assert source is not None
            assert source.state == AttachmentState.STAGED.value
            assert await ProfileDraftRepository(session).get(draft_id) is not None
            assert await _read_bytes(storage, source.storage_path) == b"new"


@pytest.mark.asyncio
async def test_promotion_failure_changes_no_sqlite_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        source_id = await _add_source(database, storage, content=b"new")
        draft_id = await _add_draft(database, source_id, _document("New"))

        async def fail_promote(storage_path: str) -> str:
            raise OSError("injected promotion")

        monkeypatch.setattr(storage, "promote", fail_promote)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None
            source = await AttachmentRepository(session).get_by_id(source_id)
            assert source is not None
            assert source.state == AttachmentState.STAGED.value
            assert await ProfileDraftRepository(session).get(draft_id) is not None


@pytest.mark.asyncio
async def test_invalid_draft_fails_before_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        source_id = await _add_source(database, storage, content=b"new")
        draft_id = await _add_draft(database, source_id, _document("New"))
        async with database.session_scope() as session:
            row = await session.get(ProfileDraftRow, draft_id)
            assert row is not None
            row.draft_json = {"invalid": True}

        promoted = False

        async def observe_promote(storage_path: str) -> str:
            nonlocal promoted
            promoted = True
            return storage_path

        monkeypatch.setattr(storage, "promote", observe_promote)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)
        assert promoted is False


@pytest.mark.asyncio
async def test_commit_failure_restores_promoted_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        source_id = await _add_source(database, storage, content=b"new")
        draft_id = await _add_draft(database, source_id, _document("New"))
        original_commit = AsyncSession.commit
        attempts = 0

        async def fail_once(session: AsyncSession) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("injected commit")
            await original_commit(session)

        monkeypatch.setattr(AsyncSession, "commit", fail_once)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        async with database.session_scope() as session:
            source = await AttachmentRepository(session).get_by_id(source_id)
            assert source is not None
            assert source.state == AttachmentState.STAGED.value
            assert await _read_bytes(storage, source.storage_path) == b"new"
            assert await ProfileDraftRepository(session).get(draft_id) is not None


@pytest.mark.asyncio
async def test_restore_failure_records_active_recoverable_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
        draft_id = await _add_draft(database, new_id, _document("New"))

        async def fail_delete(self: ProfileDraftRepository, draft: UUID) -> bool:
            raise RuntimeError("injected mutation")

        async def fail_restore(storage_path: str) -> str:
            raise OSError("injected restore")

        monkeypatch.setattr(ProfileDraftRepository, "delete", fail_delete)
        monkeypatch.setattr(storage, "restore", fail_restore)
        with pytest.raises(ProfileCommitError):
            await ProfileCommitService(database, storage).commit_draft(draft_id)

        monkeypatch.undo()
        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.active_attachment_id == old_id
            source = await AttachmentRepository(session).get_by_id(new_id)
            assert source is not None
            assert source.state == AttachmentState.ACTIVE.value
            assert await ProfileDraftRepository(session).get(draft_id) is not None
            assert await _read_bytes(storage, source.storage_path) == b"new"


@pytest.mark.asyncio
async def test_metadata_cleanup_failure_is_removed_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
        draft_id = await _add_draft(database, new_id, _document("New"))
        original_delete = AttachmentRepository.delete
        failed = False

        async def fail_once(repository: AttachmentRepository, attachment_id: UUID) -> bool:
            nonlocal failed
            if attachment_id == old_id and not failed:
                failed = True
                raise RuntimeError("injected metadata cleanup")
            return await original_delete(repository, attachment_id)

        monkeypatch.setattr(AttachmentRepository, "delete", fail_once)
        result = await ProfileCommitService(database, storage).commit_draft(draft_id)
        assert result.cleanup_pending is True
        assert await ProfileCommitService(database, storage).retry_cleanup(limit=10) == 1


@pytest.mark.asyncio
async def test_old_attachment_referenced_by_another_draft_is_not_cleaned(
    tmp_path: Path,
) -> None:
    async with _database(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        old_id = await _add_source(
            database, storage, content=b"old", state=AttachmentState.ACTIVE.value
        )
        new_id = await _add_source(database, storage, content=b"new")
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(_profile("Old"), active_attachment_id=old_id)
        await _add_draft(database, old_id, _document("Other pending"))
        commit_id = await _add_draft(database, new_id, _document("New"))

        result = await ProfileCommitService(database, storage).commit_draft(commit_id)

        assert result.cleanup_pending is False
        async with database.session_scope() as session:
            old = await AttachmentRepository(session).get_by_id(old_id)
            assert old is not None
            assert await _read_bytes(storage, old.storage_path) == b"old"
