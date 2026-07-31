"""Bounded CV upload orchestration: guard, stream/hash, exact-hash lifecycle.

Owns the Plan 4 §7.3 order of operations for ``POST /api/attachments/cv``:

1. Interrupted-approval guard before any upload byte/metadata persistence.
2. Stream into a storage temp while hashing; enforce size bound.
3. Declared MIME ``application/pdf`` and ``%PDF-`` magic.
4. pypdf page count ``1..MAX_PDF_PAGES`` and structure before final UUID path.
5. Exact-hash resolution: active / staged / failed retry / new staged row.
6. Leaves a different staged CV/draft untouched (proposal owns replacement).

Does not call providers, Neo4j, checkpoints, or active-profile writers.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_uuid
from app.core.settings import Settings, get_settings
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.models.profiles import Profile
from app.db.session import (
    ImmediateTransactionBusy,
    get_session_factory,
    immediate_session_scope,
)
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversation_repo
from app.repositories import profiles as profile_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.attachments import (
    AttachmentPublic,
    DraftUploadSummary,
    ProfileUploadSummary,
)
from app.schemas.profile_setup import (
    CvUploadOutcome,
    CvUploadResponse,
    PendingProfileBootstrap,
)
from app.services.activity_gate import (
    ActivityBlockedError,
    assert_profile_idle,
    assert_profile_review_clear,
    assert_upload_lifecycle_clear,
    assert_workspace_idle,
)
from app.services.chat_turns import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    get_interrupted_run,
)
from app.services.pdf_extraction import PdfMalformedError, parse_page_count
from app.storage.attachments import AttachmentStorage

# Stable application codes for transport mapping.
ERROR_INVALID_MIME: str = "INVALID_MIME"
ERROR_INVALID_PDF_MAGIC: str = "INVALID_PDF_MAGIC"
ERROR_EMPTY_UPLOAD: str = "EMPTY_UPLOAD"
ERROR_PDF_TOO_LARGE: str = "PDF_TOO_LARGE"
ERROR_PDF_TOO_MANY_PAGES: str = "PDF_TOO_MANY_PAGES"
ERROR_MALFORMED_PDF: str = "MALFORMED_PDF"
ERROR_STORAGE_FAILURE: str = "STORAGE_FAILURE"
ERROR_PROFILE_SETUP_IN_PROGRESS: str = "PROFILE_SETUP_IN_PROGRESS"
ERROR_PROFILE_LIFECYCLE_BUSY: str = "PROFILE_LIFECYCLE_BUSY"

PDF_MAGIC: bytes = b"%PDF-"
_READ_CHUNK: int = 64 * 1024
_CONTROL_OR_SEP = re.compile(r"[\x00-\x1f\x7f/\\]+")


class CvUploadError(Exception):
    """Application error with a stable code for HTTP mapping."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        profile_id: str | None = None,
        review_source: str | None = None,
        operation_id: str | None = None,
        review_revision: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.profile_id = profile_id
        self.review_source = review_source
        self.operation_id = operation_id
        self.review_revision = review_revision


def sanitize_original_name(filename: str | None) -> str:
    """Return a display-only filename that cannot inject paths or headers.

    Storage paths never use this value. Empty/unsafe names fall back to
    ``cv.pdf``.
    """
    from urllib.parse import unquote

    raw = filename if isinstance(filename, str) else ""
    # Multipart clients may percent-encode display names.
    try:
        raw = unquote(raw)
    except Exception:
        pass
    # Drop any directory components (POSIX/Windows).
    name = raw.replace("\\", "/").split("/")[-1].strip()
    name = _CONTROL_OR_SEP.sub("_", name)
    # Collapse header-hostile CR/LF leftovers and trim length.
    name = name.replace("\r", "").replace("\n", "").strip(" .")
    if not name or name in {".", ".."}:
        return "cv.pdf"
    if len(name) > 200:
        name = name[:200]
    return name


def _max_bytes(settings: Settings) -> int:
    return int(settings.MAX_PDF_SIZE_MB) * 1024 * 1024


def _attachment_public(row: Attachment) -> AttachmentPublic:
    return AttachmentPublic(
        id=row.id,
        original_name=row.original_name,
        mime_type=ATTACHMENT_MIME_TYPE_PDF,  # type: ignore[arg-type]
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        state=row.state,  # type: ignore[arg-type]
        failure_code=row.failure_code,
    )


def _profile_summary(
    profile_json: dict[str, Any] | None,
    *,
    profile_id: str | None = None,
) -> ProfileUploadSummary:
    if not isinstance(profile_json, dict):
        return ProfileUploadSummary(present=False, profile_id=profile_id)
    title = profile_json.get("current_title")
    current_title = title if isinstance(title, str) and title.strip() else None
    return ProfileUploadSummary(
        present=True, profile_id=profile_id, current_title=current_title
    )


async def _assert_upload_activity_gate(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Block unrelated workspace activity before reading an upload body."""
    async with factory() as session:
        interrupted = await get_interrupted_run(session)
        incomplete = await profile_repo.get_incomplete_profile(session)
        if interrupted is not None and incomplete is None:
            raise CvUploadError(
                ERROR_APPROVAL_ACTION_REQUIRED,
                "an interrupted run requires an approval action before a new upload",
            )
        if incomplete is None:
            try:
                await assert_workspace_idle(
                    session, code=ERROR_PROFILE_SETUP_IN_PROGRESS
                )
                active_id = await workspace_repo.get_active_profile_id(session)
                if active_id is not None:
                    await assert_profile_review_clear(
                        session,
                        profile_id=active_id,
                        code="PROFILE_REVIEW_PENDING",
                    )
            except ActivityBlockedError as exc:
                raise CvUploadError(
                    exc.code,
                    exc.summary,
                    profile_id=exc.profile_id,
                    review_source=exc.review_source,
                    operation_id=exc.operation_id,
                    review_revision=exc.review_revision,
                ) from exc


async def _stream_to_temp(
    *,
    read_chunk: Callable[[], Awaitable[bytes]],
    storage: AttachmentStorage,
    max_bytes: int,
) -> tuple[Path, str, int, bytes]:
    """Stream request body to a storage temp while hashing.

    Returns ``(temp_path, sha256_hex, size_bytes, first_bytes_for_magic)``.
    Rejects empty and oversized bodies without a final UUID path.
    """
    temp_path = storage.create_temp_file()
    hasher = hashlib.sha256()
    size = 0
    head = b""
    try:
        while True:
            chunk = await read_chunk()
            if not chunk:
                break
            if not isinstance(chunk, (bytes, bytearray)):
                raise CvUploadError(
                    ERROR_EMPTY_UPLOAD,
                    "upload stream produced non-bytes",
                )
            data = bytes(chunk)
            size += len(data)
            if size > max_bytes:
                raise CvUploadError(
                    ERROR_PDF_TOO_LARGE,
                    f"PDF exceeds maximum size of {max_bytes} bytes",
                )
            hasher.update(data)
            if len(head) < len(PDF_MAGIC):
                need = len(PDF_MAGIC) - len(head)
                head += data[:need]
            with temp_path.open("ab") as handle:
                handle.write(data)
        if size <= 0:
            raise CvUploadError(ERROR_EMPTY_UPLOAD, "upload is empty")
        return temp_path, hasher.hexdigest(), size, head
    except Exception:
        storage.discard_temp(temp_path)
        raise


def _validate_mime(content_type: str | None) -> None:
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared != ATTACHMENT_MIME_TYPE_PDF:
        raise CvUploadError(
            ERROR_INVALID_MIME,
            "declared Content-Type must be application/pdf",
        )


def _validate_magic(head: bytes) -> None:
    if not head.startswith(PDF_MAGIC):
        raise CvUploadError(
            ERROR_INVALID_PDF_MAGIC,
            "file magic must begin with %PDF-",
        )


def _validate_pages(temp_path: Path, max_pages: int) -> int:
    try:
        page_count = parse_page_count(temp_path)
    except PdfMalformedError as exc:
        raise CvUploadError(ERROR_MALFORMED_PDF, str(exc)) from exc
    if page_count < 1:
        raise CvUploadError(
            ERROR_MALFORMED_PDF,
            "PDF has no pages",
        )
    if page_count > max_pages:
        raise CvUploadError(
            ERROR_PDF_TOO_MANY_PAGES,
            f"PDF has {page_count} pages; maximum is {max_pages}",
        )
    return page_count


async def _build_active_response(
    session: AsyncSession,
    row: Attachment,
) -> CvUploadResponse:
    profile = await profile_repo.get_selected_ready_profile(session)
    summary: ProfileUploadSummary | None = None
    if profile is not None:
        summary = _profile_summary(
            profile.profile_json if isinstance(profile.profile_json, dict) else None,
            profile_id=profile.id,
        )
    else:
        summary = ProfileUploadSummary(present=False, current_title=None)
    return CvUploadResponse(
        attachment=_attachment_public(row),
        outcome="existing_active",
        profile=summary,
        draft=None,
    )


async def _build_existing_profile_response(
    session: AsyncSession,
    row: Attachment,
) -> CvUploadResponse:
    profile = (
        await session.execute(
            select(Profile).where(Profile.attachment_id == row.id)
        )
    ).scalar_one_or_none()
    summary = (
        _profile_summary(
            profile.profile_json if profile is not None else None,
            profile_id=profile.id if profile is not None else None,
        )
        if profile is not None
        else ProfileUploadSummary(present=False)
    )
    return CvUploadResponse(
        attachment=_attachment_public(row),
        outcome="existing_profile",
        profile=summary,
        draft=None,
    )


async def _pending_can_start(
    session: AsyncSession,
    *,
    profile_id: str,
) -> bool:
    draft = await profile_repo.get_draft_for_profile(session, profile_id)
    if draft is not None:
        return False
    try:
        await assert_profile_review_clear(session, profile_id=profile_id)
        await assert_profile_idle(
            session,
            profile_id=profile_id,
            code=ERROR_PROFILE_SETUP_IN_PROGRESS,
        )
    except ActivityBlockedError:
        return False
    return True


async def _build_pending_response(
    session: AsyncSession,
    row: Attachment,
    *,
    outcome: CvUploadOutcome,
    start_extraction: bool,
) -> CvUploadResponse:
    profile = await profile_repo.get_profile_by_attachment_id(session, row.id)
    if profile is None or profile.state != "pending":
        raise CvUploadError(
            ERROR_PROFILE_SETUP_IN_PROGRESS,
            "pending profile setup is inconsistent",
        )
    conversation = await conversation_repo.most_recent_for_profile(
        session, profile_id=profile.id
    )
    if conversation is None:
        raise CvUploadError(
            ERROR_PROFILE_SETUP_IN_PROGRESS,
            "pending profile setup is inconsistent",
        )
    draft = await profile_repo.get_draft_for_profile(session, profile.id)
    draft_summary: DraftUploadSummary | None
    if draft is None:
        draft_summary = DraftUploadSummary(
            present=False,
            draft_id=None,
            source_attachment_id=None,
        )
    else:
        draft_summary = DraftUploadSummary(
            present=True,
            draft_id="current",
            source_attachment_id=draft.source_attachment_id,
        )
    from app.services.conversations import project_conversation
    from app.services.profile_projection import project_profile_list_item

    projected_profile = await project_profile_list_item(
        session, profile, active_id=profile.id
    )
    return CvUploadResponse(
        attachment=_attachment_public(row),
        outcome=outcome,
        profile=None,
        draft=draft_summary,
        bootstrap=PendingProfileBootstrap(
            profile=projected_profile,
            conversation=project_conversation(conversation, selected=True),
            start_extraction=start_extraction,
        ),
    )


async def upload_cv(
    *,
    content_type: str | None,
    filename: str | None,
    read_chunk: Callable[[], Awaitable[bytes]],
    storage: AttachmentStorage,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> CvUploadResponse:
    """Validate, stage, and resolve exact-hash CV upload lifecycle.

    ``read_chunk`` must not be invoked until after the interrupt guard.
    """
    cfg = settings if settings is not None else get_settings()
    factory = session_factory or get_session_factory()
    original_name = sanitize_original_name(filename)
    max_bytes = _max_bytes(cfg)
    max_pages = int(cfg.MAX_PDF_PAGES)

    # 1) Guard before any application read/persist of upload bytes/metadata.
    await _assert_upload_activity_gate(factory)

    # MIME is request metadata (not body bytes); reject early before streaming
    # finalizes anything. Still no temp/final file yet.
    _validate_mime(content_type)

    temp_path: Path | None = None
    final_relative: str | None = None
    try:
        # 2) Stream to bounded temp + SHA-256.
        temp_path, file_hash, size_bytes, head = await _stream_to_temp(
            read_chunk=read_chunk,
            storage=storage,
            max_bytes=max_bytes,
        )

        # 3) Magic bytes.
        _validate_magic(head)

        # 4) Structure + page bounds before final UUID path/row.
        page_count = _validate_pages(temp_path, max_pages)

        # 5) Exact-hash resolution.
        async with factory() as session:
            existing = await att_repo.get_by_file_hash(session, file_hash)
            incomplete = await profile_repo.get_incomplete_profile(session)

            if incomplete is not None and (
                existing is None or existing.id != incomplete.attachment_id
            ):
                raise CvUploadError(
                    ERROR_PROFILE_SETUP_IN_PROGRESS,
                    "finish or discard the pending profile setup first",
                )

            if existing is not None:
                state = existing.state
                if state == ATTACHMENT_STATE_ACTIVE:
                    response = await _build_active_response(session, existing)
                    storage.discard_temp(temp_path)
                    temp_path = None
                    return response

                if state == ATTACHMENT_STATE_STAGED:
                    profile = await profile_repo.get_profile_by_attachment_id(
                        session, existing.id
                    )
                    if profile is None:
                        raise CvUploadError(
                            ERROR_PROFILE_SETUP_IN_PROGRESS,
                            "pending profile setup is inconsistent",
                        )
                    response = await _build_pending_response(
                        session,
                        existing,
                        outcome="existing_pending",
                        start_extraction=await _pending_can_start(
                            session, profile_id=profile.id
                        ),
                    )
                    storage.discard_temp(temp_path)
                    temp_path = None
                    return response

                if state == ATTACHMENT_STATE_FAILED:
                    profile = await profile_repo.get_profile_by_attachment_id(
                        session, existing.id
                    )
                    if profile is None:
                        raise CvUploadError(
                            ERROR_PROFILE_SETUP_IN_PROGRESS,
                            "pending profile setup is inconsistent",
                        )
                    if not await _pending_can_start(
                        session, profile_id=profile.id
                    ):
                        response = await _build_pending_response(
                            session,
                            existing,
                            outcome="existing_pending",
                            start_extraction=False,
                        )
                        storage.discard_temp(temp_path)
                        temp_path = None
                        return response
                    try:
                        retried = await att_repo.retry_as_staged(
                            session, existing.id
                        )
                        if original_name != retried.original_name:
                            retried.original_name = original_name
                            await session.flush()
                        response = await _build_pending_response(
                            session,
                            retried,
                            outcome="retry_pending",
                            start_extraction=True,
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise
                    storage.discard_temp(temp_path)
                    temp_path = None
                    return response

                if state == ATTACHMENT_STATE_ARCHIVED:
                    profile = (
                        await session.execute(
                            select(Profile).where(
                                Profile.attachment_id == existing.id,
                                Profile.state.in_(("ready", "deleting")),
                            )
                        )
                    ).scalar_one_or_none()
                    if profile is not None:
                        response = await _build_existing_profile_response(
                            session, existing
                        )
                        storage.discard_temp(temp_path)
                        temp_path = None
                        return response

                raise CvUploadError(
                    ERROR_MALFORMED_PDF,
                    f"unexpected attachment state {state!r}",
                )

        # New hash: finalize UUID file, then insert staged row.
        # Promote outside any DB transaction (no FS work while session open).
        attachment_id = new_uuid()
        try:
            final_relative = storage.promote_temp(temp_path, attachment_id)
            temp_path = None  # consumed by promote
        except OSError as exc:
            raise CvUploadError(
                ERROR_STORAGE_FAILURE,
                f"failed to finalize attachment file: {exc}",
            ) from exc

        try:
            async with immediate_session_scope(factory) as session:
                try:
                    await assert_upload_lifecycle_clear(
                        session, code=ERROR_PROFILE_SETUP_IN_PROGRESS
                    )
                except ActivityBlockedError as exc:
                    raise CvUploadError(
                        exc.code,
                        exc.summary,
                        profile_id=exc.profile_id,
                        review_source=exc.review_source,
                        operation_id=exc.operation_id,
                        review_revision=exc.review_revision,
                    ) from exc
                row = await att_repo.create_staged(
                    session,
                    file_hash=file_hash,
                    original_name=original_name,
                    size_bytes=size_bytes,
                    storage_path=final_relative,
                    page_count=page_count,
                    attachment_id=attachment_id,
                )
                profile = await profile_repo.create_pending_profile(
                    session,
                    attachment_id=row.id,
                    display_name=original_name,
                )
                await conversation_repo.create_bootstrap_for_profile(
                    session, profile_id=profile.id
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                return await _build_pending_response(
                    session,
                    row,
                    outcome="new_pending",
                    start_extraction=True,
                )
        except ImmediateTransactionBusy as exc:
            if final_relative is not None:
                storage.delete(final_relative)
                final_relative = None
            raise CvUploadError(
                ERROR_PROFILE_LIFECYCLE_BUSY,
                "CV lifecycle is busy; retry the action",
            ) from exc
        except IntegrityError as exc:
            if final_relative is not None:
                storage.delete(final_relative)
                final_relative = None
            try:
                async with factory() as probe:
                    await assert_upload_lifecycle_clear(
                        probe, code=ERROR_PROFILE_SETUP_IN_PROGRESS
                    )
            except ActivityBlockedError as blocked:
                raise CvUploadError(
                    blocked.code,
                    blocked.summary,
                    profile_id=blocked.profile_id,
                    review_source=blocked.review_source,
                    operation_id=blocked.operation_id,
                    review_revision=blocked.review_revision,
                ) from exc
            raise
        except Exception:
            # Row failure: best-effort delete the new UUID file only.
            if final_relative is not None:
                storage.delete(final_relative)
            raise
    except CvUploadError:
        if temp_path is not None:
            storage.discard_temp(temp_path)
        raise
    except Exception:
        if temp_path is not None:
            storage.discard_temp(temp_path)
        raise


async def upload_cv_from_upload_file(
    *,
    content_type: str | None,
    filename: str | None,
    file_read: Callable[[int], Awaitable[bytes]],
    storage: AttachmentStorage,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> CvUploadResponse:
    """Adapter for Starlette/FastAPI ``UploadFile.read`` chunking."""

    async def _read_chunk() -> bytes:
        return await file_read(_READ_CHUNK)

    return await upload_cv(
        content_type=content_type,
        filename=filename,
        read_chunk=_read_chunk,
        storage=storage,
        settings=settings,
        session_factory=session_factory,
    )


__all__ = [
    "ERROR_APPROVAL_ACTION_REQUIRED",
    "ERROR_EMPTY_UPLOAD",
    "ERROR_INVALID_MIME",
    "ERROR_INVALID_PDF_MAGIC",
    "ERROR_MALFORMED_PDF",
    "ERROR_PDF_TOO_LARGE",
    "ERROR_PDF_TOO_MANY_PAGES",
    "ERROR_PROFILE_SETUP_IN_PROGRESS",
    "ERROR_PROFILE_LIFECYCLE_BUSY",
    "ERROR_STORAGE_FAILURE",
    "PDF_MAGIC",
    "CvUploadError",
    "sanitize_original_name",
    "upload_cv",
    "upload_cv_from_upload_file",
]
