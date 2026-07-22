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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_uuid
from app.core.settings import Settings, get_settings
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.session import get_session_factory
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo
from app.schemas.attachments import (
    AttachmentPublic,
    CvUploadOutcome,
    CvUploadResponse,
    DraftUploadSummary,
    ProfileUploadSummary,
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

PDF_MAGIC: bytes = b"%PDF-"
_READ_CHUNK: int = 64 * 1024
_CONTROL_OR_SEP = re.compile(r"[\x00-\x1f\x7f/\\]+")


class CvUploadError(Exception):
    """Application error with a stable code for HTTP mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@asynccontextmanager
async def _short_transaction(
    factory: async_sessionmaker[AsyncSession],
) -> Any:
    """Yield a session; commit on success, roll back on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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


def _profile_summary(profile_json: dict[str, Any] | None) -> ProfileUploadSummary:
    if not isinstance(profile_json, dict):
        return ProfileUploadSummary(present=False, current_title=None)
    title = profile_json.get("current_title")
    current_title = title if isinstance(title, str) and title.strip() else None
    return ProfileUploadSummary(present=True, current_title=current_title)


async def _assert_no_interrupted(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Raise APPROVAL_ACTION_REQUIRED before any upload read/persist work."""
    async with factory() as session:
        interrupted = await get_interrupted_run(session)
        if interrupted is not None:
            raise CvUploadError(
                ERROR_APPROVAL_ACTION_REQUIRED,
                "an interrupted run requires an approval action before a new upload",
            )


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
    profile = await profile_repo.get_active_profile(session)
    summary: ProfileUploadSummary | None = None
    if profile is not None:
        summary = _profile_summary(
            profile.profile_json if isinstance(profile.profile_json, dict) else None
        )
    else:
        summary = ProfileUploadSummary(present=False, current_title=None)
    return CvUploadResponse(
        attachment=_attachment_public(row),
        outcome="existing_active",
        profile=summary,
        draft=None,
    )


async def _build_staged_response(
    session: AsyncSession,
    row: Attachment,
    *,
    outcome: CvUploadOutcome,
) -> CvUploadResponse:
    draft = await profile_repo.get_current_draft(session)
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
    return CvUploadResponse(
        attachment=_attachment_public(row),
        outcome=outcome,
        profile=None,
        draft=draft_summary,
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
    await _assert_no_interrupted(factory)

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

            if existing is not None:
                state = existing.state
                if state == ATTACHMENT_STATE_ACTIVE:
                    response = await _build_active_response(session, existing)
                    storage.discard_temp(temp_path)
                    temp_path = None
                    return response

                if state == ATTACHMENT_STATE_STAGED:
                    response = await _build_staged_response(
                        session, existing, outcome="existing_staged"
                    )
                    storage.discard_temp(temp_path)
                    temp_path = None
                    return response

                if state == ATTACHMENT_STATE_FAILED:
                    try:
                        retried = await att_repo.retry_as_staged(
                            session, existing.id
                        )
                        if (
                            original_name
                            and original_name != retried.original_name
                        ):
                            retried.original_name = original_name
                            await session.flush()
                        response = await _build_staged_response(
                            session, retried, outcome="retry"
                        )
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise
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
            async with _short_transaction(factory) as session:
                row = await att_repo.create_staged(
                    session,
                    file_hash=file_hash,
                    original_name=original_name,
                    size_bytes=size_bytes,
                    storage_path=final_relative,
                    page_count=page_count,
                    attachment_id=attachment_id,
                )
                return await _build_staged_response(
                    session, row, outcome="new"
                )
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
    "ERROR_STORAGE_FAILURE",
    "PDF_MAGIC",
    "CvUploadError",
    "sanitize_original_name",
    "upload_cv",
    "upload_cv_from_upload_file",
]
