"""Guarded commit_profile_draft authorization and idempotency tests."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import (
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from app.services.profile_service import ProfileCommitService
from app.tools.profile_commit import (
    ProfileCommitToolService,
    create_profile_commit_tool,
)
from tests.tools.profile_tool_helpers import profile, temporary_db


async def _seed_pending_draft(
    database: object,
    storage: FilesystemAttachmentStorage,
    *,
    summary: str = "Ready to commit",
) -> UUID:
    attachment_id = uuid4()
    staged = await storage.stage(attachment_id, iter_byte_chunks(b"%PDF-1.4 seed"))
    document = ProfileDraftDocument(
        profile=profile(summary),
        approval_summary=build_approval_summary(profile(summary)),
    )
    async with database.session_scope() as session:  # type: ignore[attr-defined]
        from app.repositories.attachments import (
            AttachmentRepository,
            StagedAttachmentInput,
        )

        await AttachmentRepository(session).add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=attachment_id.hex,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=12,
                storage_path=staged.storage_path,
                page_count=1,
            )
        )
        draft = await ProfileDraftRepository(session).create(
            document,
            source_attachment_id=attachment_id,
        )
        return draft.id


def _auth(*, draft_id: UUID, key: str, run_id: str = "run-1") -> dict[str, str]:
    return {
        "action": "commit",
        "draft_id": str(draft_id),
        "resume_idempotency_key": key,
        "run_id": run_id,
    }


@pytest.mark.asyncio
async def test_direct_commit_without_authorization_changes_nothing(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        draft_id = await _seed_pending_draft(database, storage)
        service = ProfileCommitToolService(ProfileCommitService(database, storage))

        result = await service.commit_draft(
            draft_id=draft_id,
            idempotency_key="direct-1",
            authorization=None,
        )

        assert "COMMIT_UNAUTHORIZED" in result
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None
            assert await ProfileDraftRepository(session).get(draft_id) is not None


@pytest.mark.asyncio
async def test_forged_and_mismatched_authorization_refused(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        draft_id = await _seed_pending_draft(database, storage)
        service = ProfileCommitToolService(ProfileCommitService(database, storage))

        forged = await service.commit_draft(
            draft_id=draft_id,
            idempotency_key="k1",
            authorization={
                "action": "commit",
                "draft_id": str(uuid4()),
                "resume_idempotency_key": "k1",
                "run_id": "run-1",
            },
        )
        mismatched_key = await service.commit_draft(
            draft_id=draft_id,
            idempotency_key="k1",
            authorization=_auth(draft_id=draft_id, key="other-key"),
        )
        mismatched_run = await service.commit_draft(
            draft_id=draft_id,
            idempotency_key="k1",
            authorization=_auth(draft_id=draft_id, key="k1", run_id="other-run"),
            run_id="run-1",
        )

        assert "COMMIT_UNAUTHORIZED" in forged
        assert "COMMIT_UNAUTHORIZED" in mismatched_key
        assert "COMMIT_UNAUTHORIZED" in mismatched_run
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None


@pytest.mark.asyncio
async def test_authorized_commit_once_and_duplicate_key_is_idempotent(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        draft_id = await _seed_pending_draft(database, storage)
        service = ProfileCommitToolService(ProfileCommitService(database, storage))
        auth = _auth(draft_id=draft_id, key="resume-key-1")

        first = json.loads(
            await service.commit_draft(
                draft_id=draft_id,
                idempotency_key="resume-key-1",
                authorization=auth,
                run_id="run-1",
            )
        )
        second = json.loads(
            await service.commit_draft(
                draft_id=draft_id,
                idempotency_key="resume-key-1",
                authorization=auth,
                run_id="run-1",
            )
        )

        assert first["ok"] is True
        assert first["status"] == "committed"
        assert second["ok"] is True
        assert second.get("idempotent") is True
        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert await ProfileDraftRepository(session).get(draft_id) is None


@pytest.mark.asyncio
async def test_same_client_key_commits_distinct_runs_and_stays_idempotent_per_run(
    tmp_path: Path,
) -> None:
    """Bare resume keys must not collide across authorized runs/drafts."""
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        draft_a = await _seed_pending_draft(database, storage, summary="Draft A")
        service = ProfileCommitToolService(ProfileCommitService(database, storage))
        shared_key = "client-resume-key"

        first = json.loads(
            await service.commit_draft(
                draft_id=draft_a,
                idempotency_key=shared_key,
                authorization=_auth(draft_id=draft_a, key=shared_key, run_id="run-a"),
                run_id="run-a",
            )
        )
        assert first["ok"] is True
        assert first["status"] == "committed"

        # Same key on a later authorized run/draft must still commit.
        draft_b = await _seed_pending_draft(database, storage, summary="Draft B")
        second = json.loads(
            await service.commit_draft(
                draft_id=draft_b,
                idempotency_key=shared_key,
                authorization=_auth(draft_id=draft_b, key=shared_key, run_id="run-b"),
                run_id="run-b",
            )
        )
        assert second["ok"] is True
        assert second["status"] == "committed"
        assert second.get("idempotent") is not True

        # Duplicate for the original run/draft remains idempotent.
        replay_a = json.loads(
            await service.commit_draft(
                draft_id=draft_a,
                idempotency_key=shared_key,
                authorization=_auth(draft_id=draft_a, key=shared_key, run_id="run-a"),
                run_id="run-a",
            )
        )
        assert replay_a["ok"] is True
        assert replay_a.get("idempotent") is True

        async with database.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "Draft B"
            assert await ProfileDraftRepository(session).get(draft_a) is None
            assert await ProfileDraftRepository(session).get(draft_b) is None


@pytest.mark.asyncio
async def test_tool_wrapper_refuses_without_injected_authorization(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        storage = FilesystemAttachmentStorage(tmp_path / "files")
        draft_id = await _seed_pending_draft(database, storage)
        tool = create_profile_commit_tool(
            ProfileCommitToolService(ProfileCommitService(database, storage))
        )
        # Direct invoke without graph InjectedState must not write.
        # StructuredTool may reject missing state; either way no commit.
        try:
            raw = await tool.ainvoke(
                {
                    "draft_id": str(draft_id),
                    "idempotency_key": "no-auth",
                    "state": {},
                }
            )
        except Exception:
            raw = 'ERROR:{"code":"COMMIT_UNAUTHORIZED","ok":false}'
        assert "COMMIT_UNAUTHORIZED" in str(raw) or "Error" in str(raw)
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None
