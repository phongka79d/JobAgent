"""Failure injection and sanitized upload/pipeline outcomes for Phase 3 exit."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.db.enums import AttachmentState
from app.db.models.outbox import GraphSyncOutbox
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import iter_byte_chunks
from app.services.cv_ingestion import CvIngestionError, CvIngestionService
from app.services.profile_service import ProfileCommitError, ProfileCommitService
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.fakes.agent_tools import ScriptedDecision, decision_text
from tests.fixtures.cv_pdfs import (
    build_multipage_text_pdf,
    build_synthetic_image_only_pdf,
    build_synthetic_text_pdf,
)
from tests.integration.profile_workflow.support import (
    CV_BODY,
    assert_no_contact,
    build_app,
    build_tools,
    migrated_db,
    oversized_pdf_bytes,
    profile_adapter_pair,
    upload_cv,
)
from tests.tools.profile_tool_helpers import preferences, profile


@pytest.mark.asyncio
async def test_replacement_failures_preserve_prior_or_new_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with migrated_db(tmp_path) as (_db_path, manager, _settings, storage):
        old_id = uuid4()
        new_id = uuid4()
        old_bytes = b"%PDF-1.4 old-active-cv-bytes"
        new_bytes = b"%PDF-1.4 new-staged-cv-bytes"

        old_staged = await storage.stage(old_id, iter_byte_chunks(old_bytes))
        new_staged = await storage.stage(new_id, iter_byte_chunks(new_bytes))

        async with manager.session_scope() as session:
            await AttachmentRepository(session).add_staged(
                StagedAttachmentInput(
                    id=old_id,
                    file_hash=old_id.hex,
                    original_name="old.pdf",
                    mime_type="application/pdf",
                    size_bytes=len(old_bytes),
                    storage_path=old_staged.storage_path,
                    page_count=1,
                )
            )
            old_active = await storage.promote(old_staged.storage_path)
            await AttachmentRepository(session).mark_active(
                old_id, storage_path=old_active
            )
            await AttachmentRepository(session).add_staged(
                StagedAttachmentInput(
                    id=new_id,
                    file_hash=new_id.hex,
                    original_name="new.pdf",
                    mime_type="application/pdf",
                    size_bytes=len(new_bytes),
                    storage_path=new_staged.storage_path,
                    page_count=1,
                )
            )
            await ProfileRepository(session).replace(
                profile("Old approved"),
                active_attachment_id=old_id,
            )
            await PreferencesRepository(session).replace(preferences("OldRole"))

        doc = ProfileDraftDocument(
            profile=profile("New approved"),
            preferences=preferences("NewRole"),
            approval_summary=build_approval_summary(
                profile("New approved"), preferences=preferences("NewRole")
            ),
        )
        async with manager.session_scope() as session:
            draft = await ProfileDraftRepository(session).create(
                doc, source_attachment_id=new_id
            )
            draft_id = draft.id

        async def _read(path: str) -> bytes:
            stream = await storage.open(path)
            return b"".join([chunk async for chunk in stream])

        for owner, method in (
            (AttachmentRepository, "mark_active"),
            (ProfileRepository, "replace"),
            (PreferencesRepository, "replace"),
            (ProfileDraftRepository, "delete"),
            (GraphOutboxRepository, "enqueue"),
        ):
            injected = method

            async def fail(
                *_a: Any, _injected: str = injected, **_k: Any
            ) -> Any:
                raise RuntimeError(f"injected {_injected}")

            monkeypatch.setattr(owner, method, fail)
            with pytest.raises(ProfileCommitError):
                await ProfileCommitService(manager, storage).commit_draft(draft_id)
            monkeypatch.undo()

            async with manager.session_scope() as session:
                approved = await ProfileRepository(session).get()
                assert approved is not None
                assert approved.profile.summary == "Old approved"
                assert approved.active_attachment_id == old_id
                prefs_row = await PreferencesRepository(session).get()
                assert prefs_row is not None
                assert prefs_row.target_roles == ["OldRole"]
                source = await AttachmentRepository(session).get_by_id(new_id)
                assert source is not None
                assert source.state == AttachmentState.STAGED.value
                assert await ProfileDraftRepository(session).get(draft_id) is not None
                assert await _read(source.storage_path) == new_bytes
                old = await AttachmentRepository(session).get_by_id(old_id)
                assert old is not None
                assert await _read(old.storage_path) == old_bytes

        original_delete = storage.delete

        async def fail_old_delete(storage_path: str) -> None:
            if storage_path.endswith(str(old_id)):
                raise OSError("injected cleanup")
            await original_delete(storage_path)

        monkeypatch.setattr(storage, "delete", fail_old_delete)
        result = await ProfileCommitService(manager, storage).commit_draft(draft_id)
        assert result.cleanup_pending is True
        async with manager.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "New approved"
            assert approved.active_attachment_id == new_id
            assert await AttachmentRepository(session).get_by_id(old_id) is not None
        monkeypatch.setattr(storage, "delete", original_delete)
        assert await ProfileCommitService(manager, storage).retry_cleanup(limit=10) == 1
        async with manager.session_scope() as session:
            assert await AttachmentRepository(session).get_by_id(old_id) is None


@pytest.mark.asyncio
async def test_oversized_pdf_rejected_with_zero_side_effects(tmp_path: Path) -> None:
    """Configured byte ceiling rejects oversized PDF; no durable writes."""

    async with migrated_db(tmp_path, MAX_PDF_SIZE_MB="1") as (
        db_path,
        manager,
        settings,
        storage,
    ):
        assert settings.max_pdf_size_mb == 1
        limit_bytes = settings.max_pdf_size_mb * 1024 * 1024
        tools, _ = build_tools(
            manager, storage, settings, extraction_responses=[]
        )
        application = build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            storage=storage,
            decision=ScriptedDecision([decision_text("unused")]),
            tools=tools,
        )
        payload = oversized_pdf_bytes(limit_bytes=limit_bytes)
        assert len(payload) > limit_bytes

        with TestClient(application) as client:
            response = client.post(
                "/api/attachments/cv",
                files={"file": ("huge.pdf", payload, "application/pdf")},
            )
            assert response.status_code == 413
            assert response.json() == {"detail": {"code": "PDF_TOO_LARGE"}}
            assert_no_contact(response.text)

        async with manager.session_scope() as session:
            assert await ProfileRepository(session).get() is None
            assert await ProfileDraftRepository(session).get_pending() is None
            from app.db.models.attachments import Attachment

            attachments = int(
                (
                    await session.execute(
                        select(func.count()).select_from(Attachment)
                    )
                ).scalar_one()
            )
            outbox = int(
                (
                    await session.execute(
                        select(func.count()).select_from(GraphSyncOutbox)
                    )
                ).scalar_one()
            )
            assert attachments == 0
            assert outbox == 0
        staged_dir = Path(settings.files_dir) / "staged"
        active_dir = Path(settings.files_dir) / "active"
        if staged_dir.exists():
            assert list(staged_dir.iterdir()) == []
        if active_dir.exists():
            assert list(active_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_and_pipeline_failures_are_sanitized(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.DEBUG)
    async with migrated_db(tmp_path) as (db_path, manager, settings, storage):
        tools, factory = build_tools(
            manager,
            storage,
            settings,
            extraction_responses=[RuntimeError("provider failed")],
        )
        application = build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            storage=storage,
            decision=ScriptedDecision([decision_text("unused")]),
            tools=tools,
        )
        with TestClient(application) as client:
            bad_type = client.post(
                "/api/attachments/cv",
                files={"file": ("cv.txt", b"not-pdf", "text/plain")},
            )
            assert bad_type.status_code == 415
            assert bad_type.json() == {"detail": {"code": "UNSUPPORTED_MEDIA_TYPE"}}

            bad_magic = client.post(
                "/api/attachments/cv",
                files={"file": ("cv.pdf", b"not-a-pdf", "application/pdf")},
            )
            assert bad_magic.status_code == 400
            assert bad_magic.json()["detail"]["code"] == "INVALID_PDF_MAGIC"

            ok_name = upload_cv(
                client,
                build_synthetic_text_pdf("Safe Body"),
                name="../../etc/passwd.pdf",
            )
            assert ok_name["status"] == 201
            assert ok_name["body"]["original_name"] == "passwd.pdf"
            assert_no_contact(ok_name["text"])

            image_up = upload_cv(
                client, build_synthetic_image_only_pdf(), name="image.pdf"
            )
            assert image_up["status"] == 201
            image_id = image_up["body"]["id"]

            over = client.post(
                "/api/attachments/cv",
                files={
                    "file": (
                        "big.pdf",
                        build_multipage_text_pdf(page_count=11),
                        "application/pdf",
                    )
                },
            )
            assert over.status_code == 400
            assert over.json()["detail"]["code"] == "PDF_PAGE_LIMIT_EXCEEDED"

            text_up = upload_cv(
                client, build_synthetic_text_pdf(CV_BODY), name="text.pdf"
            )
            assert text_up["status"] == 201
            text_id = text_up["body"]["id"]

        adapter, _ = profile_adapter_pair([RuntimeError("provider failed")])
        ingestion = CvIngestionService(
            manager,
            storage,
            max_size_bytes=settings.max_pdf_size_mb * 1024 * 1024,
            max_pages=settings.max_pdf_pages,
            profile_adapter=adapter,
        )

        with pytest.raises(CvIngestionError) as raised:
            await ingestion.propose_profile_from_cv(UUID(image_id))
        assert raised.value.code == "NO_EXTRACTABLE_TEXT"

        with pytest.raises(CvIngestionError) as raised2:
            await ingestion.propose_profile_from_cv(UUID(text_id))
        assert "shopaikey" in raised2.value.code or "provider" in raised2.value.code

        bad_payload = {"summary": "bad"}
        adapter2, factory2 = profile_adapter_pair([bad_payload, bad_payload])
        ingestion2 = CvIngestionService(
            manager,
            storage,
            max_size_bytes=settings.max_pdf_size_mb * 1024 * 1024,
            max_pages=settings.max_pdf_pages,
            profile_adapter=adapter2,
        )
        with TestClient(
            build_app(
                manager=manager,
                settings=settings,
                db_path=db_path,
                storage=storage,
                decision=ScriptedDecision([decision_text("x")]),
                tools=tools,
            )
        ) as client:
            third = upload_cv(
                client, build_synthetic_text_pdf(CV_BODY), name="r.pdf"
            )
            assert third["status"] == 201
            third_id = third["body"]["id"]
        with pytest.raises(CvIngestionError):
            await ingestion2.propose_profile_from_cv(UUID(third_id))
        assert len(factory2.model.structured_calls) >= 1
        for call in factory2.model.structured_calls:
            assert_no_contact(repr(call))

        async with manager.session_scope() as session:
            assert await ProfileRepository(session).get() is None

        assert_no_contact(caplog.text, str(raised.value), str(raised2.value))
        for call in factory.model.structured_calls:
            assert_no_contact(repr(call))
