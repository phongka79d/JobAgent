"""Attachment metadata repository: staged/active transitions and transactions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.db.enums import AttachmentState
from app.db.models.attachments import Attachment
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.attachments import (
    AttachmentDuplicateError,
    AttachmentNotFoundError,
    AttachmentRepository,
    AttachmentRepositoryError,
    AttachmentStateError,
    StagedAttachmentInput,
    require_canonical_service_path,
)
from app.services.attachment_storage import (
    ACTIVE_AREA,
    STAGED_AREA,
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "attachments.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _staged_input(
    *,
    attachment_id: UUID | None = None,
    storage_path: str | None = None,
    file_hash: str | None = None,
    size_bytes: int = 10,
) -> StagedAttachmentInput:
    aid = attachment_id or uuid4()
    path = storage_path if storage_path is not None else f"{STAGED_AREA}/{aid}"
    return StagedAttachmentInput(
        id=aid,
        file_hash=file_hash or uuid4().hex,
        original_name="cv.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
        storage_path=path,
        page_count=None,
    )


@pytest.mark.asyncio
async def test_add_staged_and_mark_active_round_trip(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        staged_path = f"{STAGED_AREA}/{attachment_id}"
        active_path = f"{ACTIVE_AREA}/{attachment_id}"
        payload = StagedAttachmentInput(
            id=attachment_id,
            file_hash="a" * 64,
            original_name="cv.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            storage_path=staged_path,
            page_count=2,
        )

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            row = await repo.add_staged(payload)
            assert row.state == AttachmentState.STAGED.value
            assert row.storage_path == staged_path
            assert row.page_count == 2

            loaded = await repo.get_by_id(attachment_id)
            assert loaded is not None
            assert loaded.file_hash == payload.file_hash

            by_hash = await repo.get_by_hash(payload.file_hash)
            assert by_hash is not None
            assert by_hash.id == attachment_id

            active = await repo.mark_active(attachment_id, storage_path=active_path)
            assert active.state == AttachmentState.ACTIVE.value
            assert active.storage_path == active_path

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            again = await repo.get_by_id(attachment_id)
            assert again is not None
            assert again.state == AttachmentState.ACTIVE.value
            assert again.storage_path == active_path


@pytest.mark.asyncio
async def test_mark_active_rejects_invalid_transitions(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        staged_path = f"{STAGED_AREA}/{attachment_id}"
        active_path = f"{ACTIVE_AREA}/{attachment_id}"
        payload = StagedAttachmentInput(
            id=attachment_id,
            file_hash="a" * 64,
            original_name="cv.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            storage_path=staged_path,
        )

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(payload)
            await repo.mark_active(attachment_id, storage_path=active_path)
            with pytest.raises(AttachmentStateError):
                await repo.mark_active(attachment_id, storage_path=active_path)

        missing = uuid4()
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentNotFoundError):
                await repo.mark_active(
                    missing, storage_path=f"{ACTIVE_AREA}/{missing}"
                )


@pytest.mark.asyncio
async def test_repository_rejects_unsafe_and_wrong_area_paths(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentRepositoryError):
                await repo.add_staged(
                    _staged_input(storage_path="../etc/passwd")
                )
            with pytest.raises(AttachmentRepositoryError):
                await repo.add_staged(
                    _staged_input(storage_path=str(tmp_path / "abs.pdf"))
                )
            attachment_id = uuid4()
            with pytest.raises(AttachmentRepositoryError):
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=attachment_id,
                        file_hash="b" * 64,
                        original_name="cv.pdf",
                        mime_type="application/pdf",
                        size_bytes=1,
                        storage_path=f"{ACTIVE_AREA}/{attachment_id}",
                    )
                )

            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="b" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )
            with pytest.raises(AttachmentRepositoryError):
                await repo.mark_active(
                    attachment_id,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )


@pytest.mark.asyncio
async def test_path_identity_requires_matching_uuid_leaf(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        other = uuid4()
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            # Mismatched UUID leaf
            with pytest.raises(AttachmentRepositoryError, match="identity|invalid"):
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=attachment_id,
                        file_hash="c" * 64,
                        original_name="cv.pdf",
                        mime_type="application/pdf",
                        size_bytes=1,
                        storage_path=f"{STAGED_AREA}/{other}",
                    )
                )
            # Non-UUID leaf
            with pytest.raises(AttachmentRepositoryError):
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=attachment_id,
                        file_hash="d" * 64,
                        original_name="cv.pdf",
                        mime_type="application/pdf",
                        size_bytes=1,
                        storage_path=f"{STAGED_AREA}/not-a-uuid",
                    )
                )
            # Percent-encoded / reserved / malformed leaves
            for leaf in (
                f"%2e%2e/{attachment_id}",
                "CON",
                "nul",
                f"{{{attachment_id}}}",
                f"urn:uuid:{attachment_id}",
                str(attachment_id).upper(),
            ):
                # Multi-segment percent path rejected by parse; single leaf cases apply.
                if "/" in leaf:
                    bad_path = f"{STAGED_AREA}/../{attachment_id}"
                else:
                    bad_path = f"{STAGED_AREA}/{leaf}"
                with pytest.raises(AttachmentRepositoryError):
                    await repo.add_staged(
                        StagedAttachmentInput(
                            id=attachment_id,
                            file_hash=uuid4().hex,
                            original_name="cv.pdf",
                            mime_type="application/pdf",
                            size_bytes=1,
                            storage_path=bad_path,
                        )
                    )

            # mark_active also requires matching active leaf
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="e" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )
            with pytest.raises(AttachmentRepositoryError):
                await repo.mark_active(
                    attachment_id,
                    storage_path=f"{ACTIVE_AREA}/{other}",
                )


def test_require_canonical_service_path_unit() -> None:
    aid = uuid4()
    assert (
        require_canonical_service_path(
            f"staged/{aid}", aid, expected_area="staged"
        )
        == f"staged/{aid}"
    )
    with pytest.raises(AttachmentRepositoryError):
        require_canonical_service_path(f"staged/{aid}", aid, expected_area="active")
    with pytest.raises(AttachmentRepositoryError):
        require_canonical_service_path(f"staged/{uuid4()}", aid, expected_area="staged")


@pytest.mark.asyncio
async def test_duplicate_id_and_hash_raise_domain_errors(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        first_id = uuid4()
        second_id = uuid4()
        file_hash = "f" * 64

        # Commit a durable row first.
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=first_id,
                    file_hash=file_hash,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    storage_path=f"{STAGED_AREA}/{first_id}",
                )
            )

        # Duplicate hash against committed row.
        session = db.session_factory()
        try:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentDuplicateError) as ei_hash:
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=second_id,
                        file_hash=file_hash,
                        original_name="other.pdf",
                        mime_type="application/pdf",
                        size_bytes=2,
                        storage_path=f"{STAGED_AREA}/{second_id}",
                    )
                )
            assert ei_hash.value.kind in {"hash", "unknown"}
            assert "IntegrityError" not in type(ei_hash.value).__name__
            assert "UNIQUE" not in str(ei_hash.value)
            assert ei_hash.value.__cause__ is None
            assert ei_hash.value.__context__ is None
            await session.rollback()
        finally:
            await session.close()

        # Duplicate primary key against committed row.
        session = db.session_factory()
        try:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentDuplicateError) as ei_id:
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=first_id,
                        file_hash="0" * 64,
                        original_name="cv2.pdf",
                        mime_type="application/pdf",
                        size_bytes=3,
                        storage_path=f"{STAGED_AREA}/{first_id}",
                    )
                )
            assert ei_id.value.kind in {"id", "unknown"}
            assert ei_id.value.__cause__ is None
            assert ei_id.value.__context__ is None
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            row = await repo.get_by_id(first_id)
            assert row is not None
            assert row.file_hash == file_hash


@pytest.mark.asyncio
async def test_delete_metadata_idempotent(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="c" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=3,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )
            assert await repo.delete(attachment_id) is True
            assert await repo.delete(attachment_id) is False
            assert await repo.get_by_id(attachment_id) is None


@pytest.mark.asyncio
async def test_transaction_rollback_discards_staged_row(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        session = db.session_factory()
        try:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="d" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=4,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            assert await repo.get_by_id(attachment_id) is None
            result = await session.execute(select(Attachment))
            assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_mark_active_rollback_restores_staged_state(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="1" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=4,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )

        session = db.session_factory()
        try:
            repo = AttachmentRepository(session)
            await repo.mark_active(
                attachment_id,
                storage_path=f"{ACTIVE_AREA}/{attachment_id}",
            )
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            row = await repo.get_by_id(attachment_id)
            assert row is not None
            assert row.state == AttachmentState.STAGED.value
            assert row.storage_path == f"{STAGED_AREA}/{attachment_id}"


@pytest.mark.asyncio
async def test_repository_does_not_commit_implicitly(tmp_path: Path) -> None:
    """Flush is visible in-session; without commit another session sees nothing."""
    async with temporary_db(tmp_path) as db:
        attachment_id = uuid4()
        session_a: AsyncSession = db.session_factory()
        try:
            repo = AttachmentRepository(session_a)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="e" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=5,
                    storage_path=f"{STAGED_AREA}/{attachment_id}",
                )
            )
            assert await repo.get_by_id(attachment_id) is not None

            session_b = db.session_factory()
            try:
                repo_b = AttachmentRepository(session_b)
                assert await repo_b.get_by_id(attachment_id) is None
            finally:
                await session_b.close()
        finally:
            await session_a.rollback()
            await session_a.close()


@pytest.mark.asyncio
async def test_duplicate_failed_flush_requires_caller_rollback(
    tmp_path: Path,
) -> None:
    """Repository must not hide that a failed flush needs caller rollback."""
    async with temporary_db(tmp_path) as db:
        first_id = uuid4()
        second_id = uuid4()
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=first_id,
                    file_hash="2" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    storage_path=f"{STAGED_AREA}/{first_id}",
                )
            )

        session = db.session_factory()
        try:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentDuplicateError):
                await repo.add_staged(
                    StagedAttachmentInput(
                        id=first_id,
                        file_hash="3" * 64,
                        original_name="x.pdf",
                        mime_type="application/pdf",
                        size_bytes=1,
                        storage_path=f"{STAGED_AREA}/{first_id}",
                    )
                )
            # Session is in a failed state until caller rolls back — further
            # work on the same session should not be silently committed by repo.
            # After explicit rollback, a new insert of a different id works.
            await session.rollback()
            await repo.add_staged(
                StagedAttachmentInput(
                    id=second_id,
                    file_hash="4" * 64,
                    original_name="y.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    storage_path=f"{STAGED_AREA}/{second_id}",
                )
            )
            await session.commit()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            assert await repo.get_by_id(second_id) is not None
            assert await repo.get_by_id(first_id) is not None


@pytest.mark.asyncio
async def test_storage_and_repository_promote_together(tmp_path: Path) -> None:
    """Filesystem promote + metadata mark_active in one caller-owned transaction."""
    files_root = tmp_path / "files"
    storage = FilesystemAttachmentStorage(files_root)
    attachment_id = uuid4()
    payload = b"integrated-bytes"
    stored = await storage.stage(attachment_id, iter_byte_chunks(payload))

    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            await repo.add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash="f" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=stored.size_bytes,
                    storage_path=stored.storage_path,
                )
            )
            active_path = await storage.promote(stored.storage_path)
            row = await repo.mark_active(attachment_id, storage_path=active_path)
            assert row.state == AttachmentState.ACTIVE.value
            assert row.storage_path == active_path

        stream = await storage.open(active_path)
        chunks: list[bytes] = []
        async for chunk in stream:
            chunks.append(chunk)
        assert b"".join(chunks) == payload


@pytest.mark.asyncio
async def test_path_non_disclosure_in_repository_errors(tmp_path: Path) -> None:
    abs_path = str((tmp_path / "secret.pdf").resolve())
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = AttachmentRepository(session)
            with pytest.raises(AttachmentRepositoryError) as ei:
                await repo.add_staged(_staged_input(storage_path=abs_path))
            assert abs_path not in str(ei.value)
            assert abs_path not in repr(ei.value)
            assert str(tmp_path) not in str(ei.value)
            assert ei.value.__cause__ is None


def test_no_content_policy_helpers_on_repository() -> None:
    """Plan 4 owns MIME/magic/page policy — repository must not implement it."""
    names = set(dir(AttachmentRepository))
    for forbidden in (
        "validate_mime",
        "check_magic",
        "validate_pdf",
        "replace_profile",
        "approve",
    ):
        assert forbidden not in names
