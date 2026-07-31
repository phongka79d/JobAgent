from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import app.services.profile_reextraction as profile_reextraction_service
import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachment_text_chunks import AttachmentTextChunk
from app.db.models.chat import AgentRun, ChatMessage, Conversation, ToolExecution
from app.db.models.profiles import (
    Profile,
    ProfileDraft,
    ProfileReextractOperation,
)
from app.db.session import build_async_engine
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as evaluation_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profile_reextract_operations as operation_repo
from app.repositories import profiles as profile_repo
from app.repositories import workspace_state as workspace_repo
from app.services.evaluation_context import (
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.profile_approval import commit_approved_draft
from app.services.profile_drafts import (
    propose_profile_update,
    publish_reextract_stage,
    stage_cv_document,
)
from app.services.profile_reextraction import (
    ProfileReextractError,
    ProfileReextractionCoordinator,
)
from app.storage.attachments import AttachmentStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_profile_approval import _seed_cv_document_draft
from tests.support.db_migration import run_async, session_factory
from tests.support.health import health_client, install_fake_driver, prepare_health_env
from tests.unit.test_profile_extraction import (
    CV_DIR,
    CoveringDocumentInvoker,
    _normalizer,
    _valid_profile,
)


def _preferences() -> dict[str, Any]:
    return {
        "target_roles": ["Platform Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["senior"],
    }


async def _seed_ready_profile(
    session: AsyncSession,
    *,
    attachment_id: str,
    file_hash: str,
) -> Profile:
    await att_repo.create_staged(
        session,
        file_hash=file_hash,
        original_name=f"{file_hash}.pdf",
        size_bytes=10,
        storage_path=f"{attachment_id}.pdf",
        page_count=1,
        attachment_id=attachment_id,
    )
    return await profile_repo.create_profile(
        session,
        attachment_id=attachment_id,
        display_name=file_hash,
        profile_json=_valid_profile().model_dump(mode="json"),
        location=None,
        extraction_version="test-v1",
        source_hash=file_hash,
    )


async def _seed_stream_fixture(
    session: AsyncSession, storage: AttachmentStorage, pdf: Path
) -> tuple[Profile, str]:
    attachment_id = new_uuid()
    rel = storage.write_bytes(attachment_id, pdf.read_bytes())
    await att_repo.create_staged(
        session,
        file_hash=f"stream-{attachment_id}",
        original_name="ready.pdf",
        size_bytes=pdf.stat().st_size,
        storage_path=rel,
        page_count=1,
        attachment_id=attachment_id,
    )
    await att_repo.mark_active(session, attachment_id)
    profile = await profile_repo.create_profile(
        session,
        attachment_id=attachment_id,
        display_name="Ready",
        profile_json=_valid_profile().model_dump(mode="json"),
        location=None,
        extraction_version="old-v1",
        source_hash=f"source-{attachment_id}",
    )
    await workspace_repo.set_active_profile_id(session, profile.id)
    return profile, rel


async def _collect_profile_events(
    stream: Any,
) -> list[Any]:
    return [event async for event in stream]


def test_drafts_are_isolated_by_explicit_profile_owner(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_a = new_uuid()
                attachment_b = new_uuid()
                profile_a = await _seed_ready_profile(
                    session, attachment_id=attachment_a, file_hash="draft-owner-a"
                )
                profile_b = await _seed_ready_profile(
                    session, attachment_id=attachment_b, file_hash="draft-owner-b"
                )
                draft_a = {"owner": "A", "revision": 1}
                draft_b = {"owner": "B", "revision": 1}

                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_a.id,
                    draft_json=draft_a,
                    source_attachment_id=attachment_a,
                )
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_b.id,
                    draft_json=draft_b,
                    source_attachment_id=attachment_b,
                )
                stored_a = await profile_repo.get_draft_for_profile(
                    session, profile_a.id
                )
                stored_b = await profile_repo.get_draft_for_profile(
                    session, profile_b.id
                )
                assert stored_a is not None
                assert stored_a.draft_json == draft_a
                assert stored_b is not None
                assert stored_b.draft_json == draft_b

                updated_a = {"owner": "A", "revision": 2}
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_a.id,
                    draft_json=updated_a,
                    source_attachment_id=attachment_a,
                )
                stored_b = await profile_repo.get_draft_for_profile(
                    session, profile_b.id
                )
                assert stored_b is not None
                assert stored_b.draft_json == draft_b
                assert (
                    await profile_repo.delete_draft_for_profile(
                        session, profile_id=profile_a.id
                    )
                    is True
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_a.id)
                    is None
                )
                stored_b = await profile_repo.get_draft_for_profile(
                    session, profile_b.id
                )
                assert stored_b is not None
                assert stored_b.draft_json == draft_b
        finally:
            await engine.dispose()

    run_async(_body())


def test_delete_draft_for_profile_normalizes_revision_cas_to_utc(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            async with factory() as session:
                profile = await _seed_ready_profile(
                    session,
                    attachment_id=attachment_id,
                    file_hash="draft-revision-cas",
                )
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile.id,
                    draft_json={"owner": "revision"},
                    source_attachment_id=attachment_id,
                )
                await session.commit()
                profile_id = profile.id

            async with factory() as session:
                draft = await profile_repo.get_draft_for_profile(session, profile_id)
                assert draft is not None
                revision = draft.updated_at.replace(tzinfo=UTC)
                assert (
                    await profile_repo.delete_draft_for_profile(
                        session,
                        profile_id=profile_id,
                        expected_revision=revision.replace(year=revision.year - 1),
                    )
                    is False
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is not None
                )
                assert (
                    await profile_repo.delete_draft_for_profile(
                        session,
                        profile_id=profile_id,
                        expected_revision=revision,
                    )
                    is True
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_operation_draft_lookup_requires_profile_and_operation_owner(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_a = new_uuid()
                attachment_b = new_uuid()
                profile_a = await _seed_ready_profile(
                    session, attachment_id=attachment_a, file_hash="operation-owner-a"
                )
                profile_b = await _seed_ready_profile(
                    session, attachment_id=attachment_b, file_hash="operation-owner-b"
                )
                now = datetime.now(UTC)
                operation = ProfileReextractOperation(
                    id=new_uuid(),
                    profile_id=profile_a.id,
                    source_attachment_id=attachment_a,
                    base_profile_updated_at=profile_a.updated_at,
                    base_workspace_updated_at=now,
                    state="running",
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                other_operation = ProfileReextractOperation(
                    id=new_uuid(),
                    profile_id=profile_b.id,
                    source_attachment_id=attachment_b,
                    base_profile_updated_at=profile_b.updated_at,
                    base_workspace_updated_at=now,
                    state="running",
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add_all([operation, other_operation])
                await session.flush()
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_a.id,
                    draft_json={"owner": "A"},
                    source_attachment_id=attachment_a,
                    reextract_operation_id=operation.id,
                )

                assert (
                    await profile_repo.get_draft_for_operation(
                        session, profile_a.id, operation.id
                    )
                    is not None
                )
                assert (
                    await profile_repo.get_draft_for_operation(
                        session, profile_b.id, operation.id
                    )
                    is None
                )
                assert (
                    await profile_repo.get_draft_for_operation(
                        session, profile_a.id, other_operation.id
                    )
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_operation_draft_rejects_ownership_mutations_without_mutating_rows(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_a = new_uuid()
                attachment_b = new_uuid()
                attachment_c = new_uuid()
                profile_a = await _seed_ready_profile(
                    session,
                    attachment_id=attachment_a,
                    file_hash="operation-mutation-a",
                )
                profile_b = await _seed_ready_profile(
                    session,
                    attachment_id=attachment_b,
                    file_hash="operation-mutation-b",
                )
                await _seed_ready_profile(
                    session,
                    attachment_id=attachment_c,
                    file_hash="operation-mutation-c",
                )
                now = datetime.now(UTC)
                operation_a = ProfileReextractOperation(
                    id=new_uuid(),
                    profile_id=profile_a.id,
                    source_attachment_id=attachment_a,
                    base_profile_updated_at=profile_a.updated_at,
                    base_workspace_updated_at=now,
                    state="running",
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                operation_b = ProfileReextractOperation(
                    id=new_uuid(),
                    profile_id=profile_b.id,
                    source_attachment_id=attachment_b,
                    base_profile_updated_at=profile_b.updated_at,
                    base_workspace_updated_at=now,
                    state="running",
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add_all([operation_a, operation_b])
                await session.flush()
                session.add(
                    ProfileDraft(
                        id=new_uuid(),
                        target_profile_id=profile_a.id,
                        reextract_operation_id=operation_a.id,
                        source_attachment_id=attachment_a,
                        draft_json={"owner": "A", "source": "original"},
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.add(
                    ProfileDraft(
                        id=new_uuid(),
                        target_profile_id=profile_b.id,
                        source_attachment_id=attachment_b,
                        draft_json={"owner": "B", "source": "ordinary"},
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()

                profile_a_id = profile_a.id
                profile_b_id = profile_b.id
                operation_a_id = operation_a.id
                operation_b_id = operation_b.id
                await session.commit()

            async def assert_operation_draft_unchanged(
                *,
                profile_id: str,
                attempted_source_attachment_id: str,
                attempted_operation_id: str | None,
                expected_source_attachment_id: str,
                expected_operation_id: str | None,
                expected_draft_json: dict[str, str],
            ) -> None:
                async with factory() as session:
                    with pytest.raises(profile_repo.ProfileRepositoryError):
                        await profile_repo.upsert_draft_for_profile(
                            session,
                            profile_id=profile_id,
                            draft_json={"invalid": "mutation"},
                            source_attachment_id=attempted_source_attachment_id,
                            reextract_operation_id=attempted_operation_id,
                        )
                    assert not session.new
                    assert not session.dirty
                    stored = await profile_repo.get_draft_for_profile(
                        session, profile_id
                    )
                    assert stored is not None
                    assert stored.source_attachment_id == expected_source_attachment_id
                    assert stored.reextract_operation_id == expected_operation_id
                    assert stored.draft_json == expected_draft_json

            await assert_operation_draft_unchanged(
                profile_id=profile_b_id,
                attempted_source_attachment_id=attachment_b,
                attempted_operation_id=operation_b_id,
                expected_source_attachment_id=attachment_b,
                expected_operation_id=None,
                expected_draft_json={"owner": "B", "source": "ordinary"},
            )
            await assert_operation_draft_unchanged(
                profile_id=profile_a_id,
                attempted_source_attachment_id=attachment_a,
                attempted_operation_id=None,
                expected_source_attachment_id=attachment_a,
                expected_operation_id=operation_a_id,
                expected_draft_json={"owner": "A", "source": "original"},
            )
            await assert_operation_draft_unchanged(
                profile_id=profile_a_id,
                attempted_source_attachment_id=attachment_a,
                attempted_operation_id=operation_b_id,
                expected_source_attachment_id=attachment_a,
                expected_operation_id=operation_a_id,
                expected_draft_json={"owner": "A", "source": "original"},
            )
            await assert_operation_draft_unchanged(
                profile_id=profile_b_id,
                attempted_source_attachment_id=attachment_b,
                attempted_operation_id=operation_a_id,
                expected_source_attachment_id=attachment_b,
                expected_operation_id=None,
                expected_draft_json={"owner": "B", "source": "ordinary"},
            )
            await assert_operation_draft_unchanged(
                profile_id=profile_a_id,
                attempted_source_attachment_id=attachment_c,
                attempted_operation_id=operation_a_id,
                expected_source_attachment_id=attachment_a,
                expected_operation_id=operation_a_id,
                expected_draft_json={"owner": "A", "source": "original"},
            )

            async with factory() as session:
                updated = {"owner": "A", "source": "updated"}
                stored = await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_a_id,
                    draft_json=updated,
                    source_attachment_id=attachment_a,
                    reextract_operation_id=operation_a_id,
                )
                assert stored.draft_json == updated
                stored = await profile_repo.get_draft_for_operation(
                    session, profile_a_id, operation_a_id
                )
                assert stored is not None
                assert stored.draft_json == updated
        finally:
            await engine.dispose()

    run_async(_body())


async def _seed_running_publish_case(
    session: AsyncSession,
    storage: AttachmentStorage,
    *,
    pdf: Path,
    file_hash: str,
) -> tuple[Any, Profile, ProfileReextractOperation]:
    attachment_id = new_uuid()
    storage_path = storage.write_bytes(attachment_id, pdf.read_bytes())
    attachment = await att_repo.create_staged(
        session,
        file_hash=file_hash,
        original_name="ready.pdf",
        size_bytes=pdf.stat().st_size,
        storage_path=storage_path,
        page_count=1,
        attachment_id=attachment_id,
    )
    await att_repo.mark_active(session, attachment_id)
    profile = await profile_repo.create_profile(
        session,
        attachment_id=attachment_id,
        display_name="Ready",
        profile_json=_valid_profile().model_dump(mode="json"),
        location=None,
        extraction_version="old-v1",
        source_hash="old-source-hash",
    )
    workspace = await workspace_repo.set_active_profile_id(session, profile.id)
    await _seed_cv_document_draft(
        session,
        attachment_id=attachment_id,
        profile_json=profile.profile_json,
        chunk_text="existing canonical chunk",
    )
    operation = await operation_repo.claim_operation(
        session,
        profile_id=profile.id,
        source_attachment_id=attachment_id,
        base_profile_updated_at=profile.updated_at,
        base_workspace_updated_at=workspace.updated_at,
    )
    return attachment, profile, operation


def test_publish_replaces_artifacts_and_creates_operation_owned_review(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment, profile, operation = await _seed_running_publish_case(
                    session,
                    storage,
                    pdf=pdf,
                    file_hash="publish-success",
                )
                await session.commit()

            staged = await stage_cv_document(
                attachment=attachment,
                storage=storage,
                invoker=CoveringDocumentInvoker(),
                normalizer=_normalizer(),
            )
            result = await publish_reextract_stage(
                session_factory=factory,
                profile_id=profile.id,
                operation_id=operation.id,
                staged=staged,
            )
            assert result.state == "review_ready"
            assert result.revision is not None

            async with factory() as session:
                rows = await chunk_repo.list_for_attachment(session, attachment.id)
                assert [(row.ordinal, row.text) for row in rows] == [
                    (chunk.ordinal, chunk.text) for chunk in staged.chunks
                ]
                assert all(row.text != "existing canonical chunk" for row in rows)
                document = await cv_doc_repo.get_draft(session, attachment.id)
                assert document is not None
                assert document.document_json == staged.document_json
                assert document.profile_json == staged.profile_json
                assert document.outline_json == staged.outline_json
                assert document.extraction_version == staged.extraction_version
                assert document.source_hash == staged.source_hash
                draft = await profile_repo.get_draft_for_operation(
                    session, profile.id, operation.id
                )
                assert draft is not None
                assert draft.reextract_operation_id == operation.id
                assert draft.source_attachment_id == attachment.id
                assert draft.draft_json == staged.draft_payload.model_dump(mode="json")
                stored_operation = await operation_repo.get_operation(
                    session, profile_id=profile.id, operation_id=operation.id
                )
                assert stored_operation is not None
                assert stored_operation.state == "review_ready"
        finally:
            await engine.dispose()

    run_async(_body())


def test_publish_post_write_cas_failure_rolls_back_then_marks_stale(
    migrated_sqlite: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment, profile, operation = await _seed_running_publish_case(
                    session,
                    storage,
                    pdf=pdf,
                    file_hash="publish-post-write-cas",
                )
                before_chunks = [
                    (
                        row.ordinal,
                        row.text,
                        row.preview,
                        row.char_count,
                        row.token_estimate,
                    )
                    for row in (
                        await session.scalars(
                            select(AttachmentTextChunk)
                            .where(AttachmentTextChunk.attachment_id == attachment.id)
                            .order_by(AttachmentTextChunk.ordinal)
                        )
                    ).all()
                ]
                before_document = await cv_doc_repo.get_draft(session, attachment.id)
                assert before_document is not None
                before_document_values = (
                    before_document.document_json,
                    before_document.profile_json,
                    before_document.outline_json,
                    before_document.extraction_version,
                    before_document.source_hash,
                )
                await session.commit()

            staged = await stage_cv_document(
                attachment=attachment,
                storage=storage,
                invoker=CoveringDocumentInvoker(),
                normalizer=_normalizer(),
            )
            real_transition = operation_repo.transition_running_operation

            async def fail_review_ready_then_delegate_stale(
                session: AsyncSession,
                *,
                profile_id: str,
                operation_id: str,
                to_state: str,
                error_code: str | None,
            ) -> bool:
                if to_state == "review_ready":
                    rows = await chunk_repo.list_for_attachment(session, attachment.id)
                    assert [(row.ordinal, row.text) for row in rows] == [
                        (chunk.ordinal, chunk.text) for chunk in staged.chunks
                    ]
                    document = await cv_doc_repo.get_draft(session, attachment.id)
                    assert document is not None
                    assert document.document_json == staged.document_json
                    draft = await profile_repo.get_draft_for_operation(
                        session, profile.id, operation.id
                    )
                    assert draft is not None
                    assert draft.reextract_operation_id == operation.id
                    return False
                return await real_transition(
                    session,
                    profile_id=profile_id,
                    operation_id=operation_id,
                    to_state=to_state,  # type: ignore[arg-type]
                    error_code=error_code,
                )

            monkeypatch.setattr(
                operation_repo,
                "transition_running_operation",
                fail_review_ready_then_delegate_stale,
            )
            result = await publish_reextract_stage(
                session_factory=factory,
                profile_id=profile.id,
                operation_id=operation.id,
                staged=staged,
            )
            assert result.state == "stale"
            assert result.revision is None

            async with factory() as session:
                assert (
                    await profile_repo.get_draft_for_operation(
                        session, profile.id, operation.id
                    )
                    is None
                )
                after_document = await cv_doc_repo.get_draft(session, attachment.id)
                assert after_document is not None
                assert (
                    after_document.document_json,
                    after_document.profile_json,
                    after_document.outline_json,
                    after_document.extraction_version,
                    after_document.source_hash,
                ) == before_document_values
                after_chunks = [
                    (
                        row.ordinal,
                        row.text,
                        row.preview,
                        row.char_count,
                        row.token_estimate,
                    )
                    for row in (
                        await session.scalars(
                            select(AttachmentTextChunk)
                            .where(AttachmentTextChunk.attachment_id == attachment.id)
                            .order_by(AttachmentTextChunk.ordinal)
                        )
                    ).all()
                ]
                assert after_chunks == before_chunks
                stored_operation = await operation_repo.get_operation(
                    session, profile_id=profile.id, operation_id=operation.id
                )
                assert stored_operation is not None
                assert stored_operation.state == "stale"
                assert stored_operation.error_code == "PROFILE_REEXTRACT_STALE"
        finally:
            await engine.dispose()

    run_async(_body())


def test_publish_marks_operation_stale_without_partial_writes_when_workspace_revision_changes(  # noqa: E501
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            storage_path = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                attachment = await att_repo.create_staged(
                    session,
                    file_hash="publish-cas-workspace",
                    original_name="ready.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=storage_path,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile().model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                workspace = await workspace_repo.set_active_profile_id(
                    session, profile.id
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=attachment_id,
                    profile_json=profile.profile_json,
                    chunk_text="existing canonical chunk",
                )
                operation = await operation_repo.claim_operation(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment_id,
                    base_profile_updated_at=profile.updated_at,
                    base_workspace_updated_at=workspace.updated_at,
                )
                await session.commit()

                before_chunks = [
                    (
                        row.ordinal,
                        row.text,
                        row.preview,
                        row.char_count,
                        row.token_estimate,
                    )
                    for row in (
                        await session.scalars(
                            select(AttachmentTextChunk)
                            .where(AttachmentTextChunk.attachment_id == attachment_id)
                            .order_by(AttachmentTextChunk.ordinal)
                        )
                    ).all()
                ]
                before_document = await cv_doc_repo.get_draft(session, attachment_id)
                assert before_document is not None
                before_document_values = (
                    before_document.document_json,
                    before_document.profile_json,
                    before_document.outline_json,
                    before_document.extraction_version,
                    before_document.source_hash,
                )
                profile_id = profile.id
                operation_id = operation.id

            staged = await stage_cv_document(
                attachment=attachment,
                storage=storage,
                invoker=CoveringDocumentInvoker(),
                normalizer=_normalizer(),
            )
            async with factory() as session:
                workspace = await workspace_repo.get_state(session)
                assert workspace is not None
                workspace.updated_at = utc_now()
                await session.commit()

            result = await publish_reextract_stage(
                session_factory=factory,
                profile_id=profile_id,
                operation_id=operation_id,
                staged=staged,
            )
            assert result.state == "stale"

            async with factory() as session:
                assert (
                    await profile_repo.get_draft_for_operation(
                        session, profile_id, operation_id
                    )
                    is None
                )
                after_document = await cv_doc_repo.get_draft(session, attachment_id)
                assert after_document is not None
                assert (
                    after_document.document_json,
                    after_document.profile_json,
                    after_document.outline_json,
                    after_document.extraction_version,
                    after_document.source_hash,
                ) == before_document_values
                after_chunks = [
                    (
                        row.ordinal,
                        row.text,
                        row.preview,
                        row.char_count,
                        row.token_estimate,
                    )
                    for row in (
                        await session.scalars(
                            select(AttachmentTextChunk)
                            .where(AttachmentTextChunk.attachment_id == attachment_id)
                            .order_by(AttachmentTextChunk.ordinal)
                        )
                    ).all()
                ]
                assert after_chunks == before_chunks
                operation = await operation_repo.get_operation(
                    session, profile_id=profile_id, operation_id=operation_id
                )
                assert operation is not None
                assert operation.state == "stale"
                assert operation.error_code == "PROFILE_REEXTRACT_STALE"
        finally:
            await engine.dispose()

    run_async(_body())


def test_publish_compares_profile_workspace_attachment_and_operation(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """A changed claimed attachment owner cannot publish a proposal."""
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment, profile, operation = await _seed_running_publish_case(
                    session,
                    storage,
                    pdf=pdf,
                    file_hash="publish-attachment-cas",
                )
                await session.commit()
            staged = await stage_cv_document(
                attachment=attachment,
                storage=storage,
                invoker=CoveringDocumentInvoker(),
                normalizer=_normalizer(),
            )
            staged = replace(staged, attachment_id=new_uuid())
            result = await publish_reextract_stage(
                session_factory=factory,
                profile_id=profile.id,
                operation_id=operation.id,
                staged=staged,
            )
            assert result.state == "stale"
            async with factory() as session:
                stored_operation = await operation_repo.get_operation(
                    session, profile_id=profile.id, operation_id=operation.id
                )
                assert stored_operation is not None
                assert stored_operation.error_code == "PROFILE_REEXTRACT_STALE"
        finally:
            await engine.dispose()

    run_async(_body())


def test_agent_profile_update_draft_can_be_reviewed_and_discarded(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="agent-review-draft",
                    original_name="agent-review.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile(
                        phone="+1 (202) 555-0147",
                        email="ready@example.test",
                        github_url="https://github.com/ready-user",
                    ).model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                await profile_repo.upsert_profile_preferences(
                    session,
                    profile_id=profile.id,
                    preferences_json=_preferences(),
                )
                proposed = _valid_profile(
                    phone="+1 (202) 555-0147",
                    email="ready@example.test",
                    github_url="https://github.com/ready-user",
                )
                proposed.summary = "Updated summary from chat"
                draft = await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile.id,
                    draft_json={
                        "candidate_profile": proposed.model_dump(mode="json"),
                        "job_preferences": _preferences(),
                    },
                    source_attachment_id=None,
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                await session.commit()
                profile_id = profile.id
                revision = draft.updated_at

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            review = await coordinator.get_review(profile_id)
            assert review.profile_id == profile_id
            assert review.revision == revision.replace(tzinfo=UTC)
            assert review.current.summary != review.proposed.summary
            assert review.proposed.summary == "Updated summary from chat"

            await coordinator.discard(profile_id, revision=review.revision)
            async with factory() as session:
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
                document = await cv_doc_repo.get_document(session, attachment_id)
                assert document is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_source_backed_reextract_draft_accepts_agent_correction_before_approval(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="source-backed-agent-correction",
                    original_name="ready.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile(
                        phone="+1 (202) 555-0147",
                        email="ready@example.test",
                        github_url="https://github.com/ready-user",
                    ).model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                await profile_repo.upsert_profile_preferences(
                    session,
                    profile_id=profile.id,
                    preferences_json=_preferences(),
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                await session.commit()
                profile_id = profile.id

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            events = [event async for event in coordinator.stream(profile_id)]
            assert events[-1].event == "reextract_review_ready"

            correction = await propose_profile_update(
                session_factory=factory,
                normalizer=_normalizer(),
                expected_profile_id=profile_id,
                profile_changes={"summary": "Corrected summary from chat"},
            )
            assert correction.tool_result.ok is True
            assert correction.source_attachment_id == attachment_id

            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile_id
                )
                assert operation is not None
                operation_id = operation.id
            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            assert review.proposed.summary == "Corrected summary from chat"

            approved = await coordinator.approve(
                profile_id,
                operation_id=operation_id,
                revision=review.revision,
            )
            assert approved.approved is True

            async with factory() as session:
                refreshed = await profile_repo.get_profile(session, profile_id)
                document = await cv_doc_repo.get_document(session, attachment_id)
                assert refreshed is not None
                assert document is not None
                assert refreshed.profile_json["summary"] == (
                    "Corrected summary from chat"
                )
                assert document.profile_json["summary"] == (
                    "Corrected summary from chat"
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
                assert await cv_doc_repo.get_draft(session, attachment_id) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_preference_only_profile_review_discloses_preference_changes(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="preference-only-review",
                    original_name="ready.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile(
                        phone="+1 (202) 555-0147",
                        email="ready@example.test",
                        github_url="https://github.com/ready-user",
                    ).model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                await profile_repo.upsert_profile_preferences(
                    session,
                    profile_id=profile.id,
                    preferences_json=_preferences(),
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                await session.commit()
                profile_id = profile.id

            correction = await propose_profile_update(
                session_factory=factory,
                normalizer=_normalizer(),
                expected_profile_id=profile_id,
                preference_changes={
                    "target_roles": ["ML Platform Engineer"],
                    "preferred_locations": ["Remote"],
                    "acceptable_work_modes": ["remote"],
                    "target_seniority": ["senior"],
                },
            )
            assert correction.tool_result.ok is True

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            review = await coordinator.get_review(profile_id)

            assert review.changed_fields == []
            assert [
                (change.field, change.before, change.after)
                for change in review.preference_changes
            ] == [
                (
                    "target_roles",
                    ["Platform Engineer"],
                    ["ML Platform Engineer"],
                )
            ]
        finally:
            await engine.dispose()

    run_async(_body())


def test_duplicate_requests_perform_one_staging_and_provider_call(
    migrated_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"
    invoker = CoveringDocumentInvoker()
    scorer = Mock(side_effect=AssertionError("re-extraction must not score"))
    monkeypatch.setattr("app.services.job_evaluation.project_single_job_match", scorer)

    async def _unexpected_activation(*args: object, **kwargs: object) -> None:
        raise AssertionError("ready re-extraction must not activate attachments")

    async def _unexpected_archive(*args: object, **kwargs: object) -> None:
        raise AssertionError("ready re-extraction must not archive attachments")

    monkeypatch.setattr(
        "app.services.profile_approval.activate_selected_attachment",
        _unexpected_activation,
    )
    monkeypatch.setattr(
        "app.services.profile_approval.att_repo.mark_archived",
        _unexpected_archive,
    )

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="ready-reextract",
                    original_name="ready.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile(
                        phone="+1 (202) 555-0147",
                        email="ready@example.test",
                        github_url="https://github.com/ready-user",
                    ).model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                preference_row = await profile_repo.upsert_profile_preferences(
                    session,
                    profile_id=profile.id,
                    preferences_json=_preferences(),
                )
                first = await conversations_repo.create_for_profile(
                    session, profile_id=profile.id, title="First"
                )
                second = await conversations_repo.create_for_profile(
                    session, profile_id=profile.id, title="Second"
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                job = await jobs_repo.create_text_job(
                    session,
                    raw_content="Synthetic retained JD",
                    raw_content_hash="ready-reextract-job",
                )
                old_facts = EvaluationContextFacts(
                    job_id=job.id,
                    job_revision=job.updated_at,
                    active_attachment_id=attachment_id,
                    cv_source_hash=profile.source_hash,
                    profile_revision=profile.updated_at,
                    preferences_revision=preference_row.updated_at,
                )
                old_context_hash = evaluation_context_hash(old_facts)
                await evaluation_repo.insert_evaluation(
                    session,
                    job_id=job.id,
                    profile_id=profile.id,
                    evaluation_context_hash=old_context_hash,
                    job_revision=old_facts.job_revision,
                    profile_revision=old_facts.profile_revision,
                    preferences_revision=old_facts.preferences_revision,
                    cv_source_hash=old_facts.cv_source_hash,
                    matching_contract_version=old_facts.matching_contract_version,
                    result={
                        "job_id": job.id,
                        "title": "Platform Engineer",
                        "company": None,
                        "location": None,
                        "work_mode": "unknown",
                        "source_url": None,
                        "final_score": 0.5,
                        "quality_multiplier": 1.0,
                        "components": {
                            "semantic_similarity": 0.5,
                            "skill_score": None,
                            "seniority_score": None,
                            "experience_score": None,
                            "location_score": None,
                            "work_mode_score": None,
                        },
                        "effective_weights": {"semantic_similarity": 1.0},
                        "matched_required_skills": [],
                        "matched_preferred_skills": [],
                        "related_skills": [],
                        "missing_required_skills": [],
                        "summary": "Historical evaluation",
                    },
                )
                old_revision = profile.updated_at
                old_preferences_revision = preference_row.updated_at
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert attachment is not None
                old_attachment_revision = attachment.updated_at
                await session.commit()
                profile_id = profile.id
                conversation_ids = {first.id, second.id}
                job_id = job.id

            async with factory() as session:
                before_counts: list[int | None] = []
                for model in (ChatMessage, AgentRun, ToolExecution, Conversation):
                    before_counts.append(
                        await session.scalar(select(func.count()).select_from(model))
                    )

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=invoker,
                graph_driver=None,
            )
            original_stage = profile_reextraction_service.stage_cv_document
            stage_started = asyncio.Event()
            release_stage = asyncio.Event()
            stage_calls = 0

            async def blocked_stage(**kwargs: Any) -> Any:
                nonlocal stage_calls
                stage_calls += 1
                stage_started.set()
                await release_stage.wait()
                return await original_stage(**kwargs)

            monkeypatch.setattr(
                profile_reextraction_service,
                "stage_cv_document",
                blocked_stage,
            )
            winner_task = asyncio.create_task(
                _collect_profile_events(coordinator.stream(profile_id))
            )
            await stage_started.wait()
            async with factory() as session:
                running = await operation_repo.list_running_operations(
                    session, profile_id
                )
                assert len(running) == 1
                winner_operation_id = running[0].id

            loser_task = asyncio.create_task(
                _collect_profile_events(coordinator.stream(profile_id))
            )
            with pytest.raises(ProfileReextractError) as duplicate:
                await loser_task
            assert duplicate.value.code == "PROFILE_REEXTRACT_IN_PROGRESS"
            assert duplicate.value.operation_id == winner_operation_id
            assert stage_calls == 1
            release_stage.set()
            events = await winner_task
            assert [event.event for event in events] == [
                "reextract_progress",
                "reextract_progress",
                "reextract_progress",
                "reextract_progress",
                "reextract_review_ready",
            ]
            assert [
                event.payload.stage
                for event in events[:-1]
                if hasattr(event.payload, "stage")
            ] == [
                "validating_source",
                "extracting_document",
                "projecting_profile",
                "publishing_review",
            ]
            with pytest.raises(ProfileReextractError) as second_reextract:
                provider_calls = len(invoker.calls)
                _ = [event async for event in coordinator.stream(profile_id)]
            assert second_reextract.value.code == "PROFILE_REVIEW_PENDING"
            assert provider_calls > 0
            assert len(invoker.calls) == provider_calls
            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile_id
                )
                assert operation is not None
                operation_id = operation.id
            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            with pytest.raises(ProfileReextractError) as stale_discard:
                await coordinator.discard(
                    profile_id,
                    operation_id=operation_id,
                    revision=datetime(2000, 1, 1, tzinfo=UTC),
                )
            assert stale_discard.value.code == "PROFILE_REEXTRACT_CONFLICT"
            await coordinator.discard(
                profile_id, operation_id=operation_id, revision=review.revision
            )
            async with factory() as session:
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
                assert await cv_doc_repo.get_draft(session, attachment_id) is None
            republished = [event async for event in coordinator.stream(profile_id)]
            assert republished[-1].event == "reextract_review_ready"
            async with factory() as session:
                after_counts: list[int | None] = []
                for model in (ChatMessage, AgentRun, ToolExecution, Conversation):
                    after_counts.append(
                        await session.scalar(select(func.count()).select_from(model))
                    )
                assert after_counts == before_counts
                draft = await profile_repo.get_draft_for_profile(session, profile_id)
                assert draft is not None
                original_draft_revision = draft.updated_at
                assert draft.target_profile_id == profile_id
                assert draft.draft_json["job_preferences"] == _preferences()
                approved_before_approval = await profile_repo.get_profile(
                    session, profile_id
                )
                assert approved_before_approval is not None
                assert approved_before_approval.profile_json["phone"] == "+12025550147"
                assert (
                    approved_before_approval.profile_json["email"]
                    == "ready@example.test"
                )
                assert (
                    approved_before_approval.profile_json["github_url"]
                    == "https://github.com/ready-user"
                )
                changed = dict(draft.draft_json)
                changed_profile = dict(changed["candidate_profile"])
                changed_profile["full_name"] = "Unsupported Person"
                changed["candidate_profile"] = changed_profile
                changed["job_preferences"] = {
                    "target_roles": ["Injected Draft Role"],
                    "preferred_locations": ["Injected Draft Location"],
                    "acceptable_work_modes": ["onsite"],
                    "target_seniority": ["junior"],
                }
                changed_draft = await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_id,
                    draft_json=changed,
                    source_attachment_id=attachment_id,
                    reextract_operation_id=draft.reextract_operation_id,
                )
                await session.commit()

            async def no_sync() -> None:
                return None

            conflicted = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
                expected_profile_id=profile_id,
                expected_draft_updated_at=original_draft_revision,
                expected_operation_id=draft.reextract_operation_id,
            )
            assert conflicted.ok is False
            assert conflicted.code == "PROFILE_REEXTRACT_CONFLICT"

            approved = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
                expected_profile_id=profile_id,
                expected_draft_updated_at=changed_draft.updated_at,
                expected_operation_id=changed_draft.reextract_operation_id,
            )
            assert approved.ok is True
            assert approved.profile_id == profile_id

            async with factory() as session:
                refreshed = await profile_repo.get_profile(session, profile_id)
                prefs = await profile_repo.get_profile_preferences(session, profile_id)
                document = await cv_doc_repo.get_document(session, attachment_id)
                conversations = await conversations_repo.list_for_profile(
                    session, profile_id=profile_id, limit=50, before=None
                )
                assert refreshed is not None
                assert prefs is not None
                assert document is not None
                assert refreshed.attachment_id == attachment_id
                assert refreshed.display_name == "Ready"
                refreshed_revision = refreshed.updated_at.replace(tzinfo=None)
                assert refreshed_revision != old_revision.replace(tzinfo=None)
                assert refreshed.source_hash == document.source_hash
                assert refreshed.source_hash != "old-source-hash"
                assert refreshed.profile_json["full_name"] is None
                assert prefs.preferences_json == _preferences()
                assert prefs.updated_at.replace(
                    tzinfo=None
                ) == old_preferences_revision.replace(tzinfo=None)
                assert {item.id for item in conversations.rows} == conversation_ids
                assert await workspace_repo.get_active_profile_id(session) == profile_id
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert attachment is not None
                assert attachment.state == "active"
                assert attachment.updated_at.replace(
                    tzinfo=None
                ) == old_attachment_revision.replace(tzinfo=None)
                job = await jobs_repo.get_by_id(session, job_id)
                assert job is not None
                current_facts = EvaluationContextFacts(
                    job_id=job.id,
                    job_revision=job.updated_at.replace(tzinfo=UTC),
                    active_attachment_id=attachment_id,
                    cv_source_hash=refreshed.source_hash,
                    profile_revision=refreshed.updated_at.replace(tzinfo=UTC),
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC),
                )
                lookup = await evaluation_repo.lookup_for_job(
                    session,
                    job_id=job_id,
                    profile_id=profile_id,
                    current_context_hash=evaluation_context_hash(current_facts),
                )
                assert lookup.currentness == "stale"
                assert lookup.evaluation is not None
                assert lookup.evaluation.evaluation_context_hash == old_context_hash
            scorer.assert_not_called()
        finally:
            await engine.dispose()

    run_async(_body())


def test_status_read_reconciles_review_ready_to_stale_and_agent_cannot_edit(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(
                    session, storage, CV_DIR / "digital_cv_01.pdf"
                )
                await session.commit()
                profile_id = profile.id

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            await _collect_profile_events(coordinator.stream(profile_id))
            async with factory() as session:
                stored = await profile_repo.get_profile(session, profile_id)
                assert stored is not None
                stored.updated_at = utc_now()
                await session.commit()
                operation = (
                    await operation_repo.get_latest_operation_for_profile(
                        session, profile_id
                    )
                )
                assert operation is not None
                operation_id = operation.id

            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            assert review.operation_state == "stale"
            assert review.can_approve is False
            assert review.can_discard is True
            from app.repositories import chat_messages as messages_repo
            from app.tools.profile import build_propose_profile_update_tool

            async with factory() as session:
                conversation = await conversations_repo.create_for_profile(
                    session, profile_id=profile_id
                )
                user = await messages_repo.insert_message(
                    session,
                    conversation_id=conversation.id,
                    role="user",
                    content="correct profile",
                )
                run = AgentRun(
                    id=new_uuid(), user_message_id=user.id, state="running"
                )
                session.add(run)
                await session.commit()
                run_id = run.id
            tool = build_propose_profile_update_tool(
                session_factory=factory, normalizer=_normalizer()
            )
            raw = await tool.ainvoke(
                {
                    "type": "tool_call",
                    "id": "stale-operation-edit",
                    "name": tool.name,
                    "args": {
                        "profile_changes": {"summary": "must be rejected"},
                        "state": {"run_id": run_id, "profile_id": profile_id},
                    },
                }
            )
            payload = raw.content if hasattr(raw, "content") else raw
            if isinstance(payload, str):
                import json

                payload = json.loads(payload)
            assert payload["code"] == "PROFILE_REEXTRACT_STALE"
        finally:
            await engine.dispose()

    run_async(_body())


def test_approve_and_discard_require_matching_operation_and_revision(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(
                    session, storage, CV_DIR / "digital_cv_01.pdf"
                )
                await session.commit()
                profile_id = profile.id

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            await _collect_profile_events(coordinator.stream(profile_id))
            async with factory() as session:
                operation = (
                    await operation_repo.get_latest_operation_for_profile(
                        session, profile_id
                    )
                )
                assert operation is not None
                operation_id = operation.id

            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            with pytest.raises(ProfileReextractError) as wrong_operation:
                await coordinator.discard(
                    profile_id,
                    operation_id=new_uuid(),
                    revision=review.revision,
                )
            assert wrong_operation.value.code == "PROFILE_REEXTRACT_CONFLICT"
            approved = await coordinator.approve(
                profile_id,
                operation_id=operation_id,
                revision=review.revision,
            )
            assert approved.approved is True
            async with factory() as session:
                assert (
                    await operation_repo.get_operation(
                        session, profile_id=profile_id, operation_id=operation_id
                    )
                    is None
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_operation_linked_consumption_requires_explicit_operation_identity(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(
                    session, storage, CV_DIR / "digital_cv_01.pdf"
                )
                await session.commit()
                profile_id = profile.id
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            await _collect_profile_events(coordinator.stream(profile_id))
            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile_id
                )
                assert operation is not None
                operation_id = operation.id
            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            with pytest.raises(ProfileReextractError) as missing_review_identity:
                await coordinator.get_review(profile_id)
            assert missing_review_identity.value.code == "PROFILE_REEXTRACT_CONFLICT"
            with pytest.raises(ProfileReextractError) as missing_approve_identity:
                await coordinator.approve(profile_id, revision=review.revision)
            assert missing_approve_identity.value.code == "PROFILE_REEXTRACT_CONFLICT"
            with pytest.raises(ProfileReextractError) as missing_discard_identity:
                await coordinator.discard(profile_id, revision=review.revision)
            assert missing_discard_identity.value.code == "PROFILE_REEXTRACT_CONFLICT"
        finally:
            await engine.dispose()

    run_async(_body())


def test_stale_discard_rolls_back_when_document_draft_is_missing(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(
                    session, storage, CV_DIR / "digital_cv_01.pdf"
                )
                await session.commit()
                profile_id = profile.id
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
                graph_driver=None,
            )
            await _collect_profile_events(coordinator.stream(profile_id))
            async with factory() as session:
                stored = await profile_repo.get_profile(session, profile_id)
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile_id
                )
                assert stored is not None and operation is not None
                stored.updated_at = utc_now()
                await session.commit()
                operation_id = operation.id
            review = await coordinator.get_review(
                profile_id, operation_id=operation_id
            )
            async with factory() as session:
                draft = await profile_repo.get_draft_for_profile(session, profile_id)
                assert draft is not None
                assert draft.source_attachment_id is not None
                assert await cv_doc_repo.delete_draft(
                    session, draft.source_attachment_id
                )
                await session.commit()
            with pytest.raises(ProfileReextractError) as missing_document:
                await coordinator.discard(
                    profile_id,
                    operation_id=operation_id,
                    revision=review.revision,
                )
            assert missing_document.value.code == "PROFILE_REEXTRACT_CONFLICT"
            async with factory() as session:
                assert await profile_repo.get_draft_for_profile(session, profile_id)
                stored_operation = await operation_repo.get_operation(
                    session, profile_id=profile_id, operation_id=operation_id
                )
                assert stored_operation is not None
                assert stored_operation.state == "stale"
        finally:
            await engine.dispose()

    run_async(_body())


def test_claim_rejects_incomplete_profile_setup_before_operation_or_provider(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(session, storage, pdf)
                pending_attachment_id = new_uuid()
                await att_repo.create_staged(
                    session,
                    file_hash="pending-setup",
                    original_name="pending.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=f"{pending_attachment_id}.pdf",
                    page_count=1,
                    attachment_id=pending_attachment_id,
                )
                pending = Profile(
                    id=new_uuid(),
                    attachment_id=pending_attachment_id,
                    display_name="Pending",
                    profile_json=None,
                    location=None,
                    extraction_version=None,
                    source_hash=None,
                    state="pending",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                    last_opened_at=None,
                )
                session.add(pending)
                await session.commit()

            invoker = Mock(side_effect=AssertionError("provider must not run"))
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=invoker,
            )
            with pytest.raises(ProfileReextractError) as caught:
                await anext(coordinator.stream(profile.id))
            assert caught.value.code == "PROFILE_SETUP_IN_PROGRESS"
            assert invoker.call_count == 0
            async with factory() as session:
                assert (
                    await operation_repo.list_running_operations(session, profile.id)
                    == []
                )
                assert (
                    await profile_repo.get_draft_for_profile(session, profile.id)
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_cancelled_real_stage_persists_interrupted_after_fresh_session_close(
    migrated_sqlite: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(session, storage, pdf)
                await session.commit()

            started = asyncio.Event()
            release = asyncio.Event()
            original_stage = profile_reextraction_service.stage_cv_document

            async def blocked_stage(**kwargs: Any) -> Any:
                started.set()
                await release.wait()
                return await original_stage(**kwargs)

            monkeypatch.setattr(
                profile_reextraction_service,
                "stage_cv_document",
                blocked_stage,
            )
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
            )
            task = asyncio.create_task(
                _collect_profile_events(coordinator.stream(profile.id))
            )
            await started.wait()
            async with factory() as session:
                running = await operation_repo.list_running_operations(
                    session, profile.id
                )
                assert len(running) == 1
                operation_id = running[0].id
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async with factory() as session:
                operation = await operation_repo.get_operation(
                    session, profile_id=profile.id, operation_id=operation_id
                )
                assert operation is not None
                assert operation.state == "interrupted"
                assert operation.error_code == "PROFILE_REEXTRACT_INTERRUPTED"
                assert (
                    await profile_repo.get_draft_for_profile(session, profile.id)
                    is None
                )
            assert "no active connection" not in caplog.text.lower()
            assert "checked out" not in caplog.text.lower()
            assert "pool" not in caplog.text.lower()
        finally:
            await engine.dispose()

    run_async(_body())


def test_retained_file_failure_marks_exact_operation_failed_without_draft(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, rel = await _seed_stream_fixture(session, storage, pdf)
                await session.commit()
            assert storage.delete(rel)
            invoker = CoveringDocumentInvoker()
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=invoker,
            )
            with pytest.raises(ProfileReextractError) as caught:
                await anext(coordinator.stream(profile.id))
            assert caught.value.code == "CV_FILE_UNAVAILABLE"
            assert invoker.calls == []
            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile.id
                )
                assert operation is not None
                assert operation.state == "failed"
                assert operation.error_code == "CV_FILE_UNAVAILABLE"
                assert (
                    await profile_repo.get_draft_for_profile(session, profile.id)
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_missing_retained_file_fails_before_sse_and_persists_failed_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    install_fake_driver(monkeypatch)
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="missing-retained-api",
                    original_name="missing.pdf",
                    size_bytes=10,
                    storage_path=attachment_id,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Missing retained file",
                    profile_json=_valid_profile().model_dump(mode="json"),
                    location=None,
                    extraction_version="test-v1",
                    source_hash="missing-retained-source",
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                await session.commit()
                return profile.id, attachment_id
        finally:
            await engine.dispose()

    profile_id, attachment_id = run_async(_seed())
    stage = Mock(side_effect=AssertionError("staging must not run"))
    monkeypatch.setattr(profile_reextraction_service, "stage_cv_document", stage)

    with health_client() as client:
        response = client.post(f"/api/profiles/{profile_id}/reextract", json={})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CV_FILE_UNAVAILABLE"
    stage.assert_not_called()

    async def _assert_state() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile_id
                )
                assert operation is not None
                assert operation.state == "failed"
                assert operation.error_code == "CV_FILE_UNAVAILABLE"
                assert (
                    await profile_repo.get_draft_for_profile(session, profile_id)
                    is None
                )
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert attachment is not None
                assert attachment.state == "active"
        finally:
            await engine.dispose()

    run_async(_assert_state())


def test_provider_failure_marks_exact_operation_failed_without_draft(
    migrated_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, _ = await _seed_stream_fixture(session, storage, pdf)
                await session.commit()

            async def failed_stage(**_kwargs: Any) -> Any:
                raise RuntimeError("provider failed")

            monkeypatch.setattr(
                profile_reextraction_service,
                "stage_cv_document",
                failed_stage,
            )
            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=CoveringDocumentInvoker(),
            )
            events = await _collect_profile_events(coordinator.stream(profile.id))
            assert events[-1].event == "reextract_failed"
            assert events[-1].payload.code == "PROFILE_REEXTRACT_FAILED"
            async with factory() as session:
                operation = await operation_repo.get_latest_operation_for_profile(
                    session, profile.id
                )
                assert operation is not None
                assert operation.state == "failed"
                assert operation.error_code == "PROFILE_REEXTRACT_FAILED"
                assert (
                    await profile_repo.get_draft_for_profile(session, profile.id)
                    is None
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_approval_cannot_read_another_profiles_draft(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="cross-profile-draft",
                    original_name="cross-profile.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                profile = await profile_repo.create_pending_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Cross-profile draft test",
                )
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile.id,
                    draft_json={
                        "candidate_profile": _valid_profile().model_dump(mode="json"),
                        "job_preferences": _preferences(),
                    },
                    source_attachment_id=attachment_id,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=attachment_id,
                    profile_json=_valid_profile().model_dump(mode="json"),
                )
                await session.commit()

            async def no_sync() -> None:
                return None

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
                expected_profile_id=new_uuid(),
            )
            assert result.ok is False
            assert result.code == "DRAFT_NOT_FOUND"
        finally:
            await engine.dispose()

    run_async(_body())
