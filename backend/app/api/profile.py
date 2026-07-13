"""Thin profile read routes (Plan 4 §7.8 / Master §14).

``GET /api/profile`` — validated active profile/preferences + attachment
metadata, or explicit empty state. Never returns PDF bytes.

``GET /api/profile/cv`` — streams only the active stored PDF with a safe
content-disposition filename. Never exposes ``storage_path``.

No public profile write CRUD (PUT/PATCH/DELETE). Routes are transport-only:
repository reads, storage open, and response mapping. No provider, graph,
checkpoint, or approval side effects.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.attachments import ATTACHMENT_MIME_TYPE_PDF, ATTACHMENT_STATE_ACTIVE
from app.db.session import get_session_factory
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo
from app.schemas.attachments import AttachmentPublic
from app.schemas.profile import (
    ProfileReadResponse,
    empty_profile_read_response,
    parse_candidate_profile,
    parse_job_preferences,
)
from app.services.cv_upload import sanitize_original_name
from app.storage.attachments import AttachmentStorage, PathEscapeError

router = APIRouter(tags=["profile"])

ERROR_PROFILE_NOT_FOUND: str = "PROFILE_NOT_FOUND"
ERROR_ACTIVE_CV_NOT_FOUND: str = "ACTIVE_CV_NOT_FOUND"
ERROR_ACTIVE_CV_FILE_MISSING: str = "ACTIVE_CV_FILE_MISSING"
ERROR_PROFILE_INCONSISTENT: str = "PROFILE_INCONSISTENT"


def _http(code: str, summary: str, status: int = 404) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "summary": summary},
    )


def _attachment_public(row: Any) -> AttachmentPublic:
    return AttachmentPublic(
        id=row.id,
        original_name=row.original_name,
        mime_type="application/pdf",
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        state=row.state,
        failure_code=row.failure_code,
    )


async def build_profile_read_response(
    session: AsyncSession,
) -> ProfileReadResponse:
    """Assemble the public profile read body from approved SQLite truth.

    Returns the explicit empty state when no active profile exists. Never
    reads draft rows or file bytes.
    """
    profile_row = await profile_repo.get_active_profile(session)
    if profile_row is None:
        return empty_profile_read_response()

    try:
        profile = parse_candidate_profile(profile_row.profile_json)
    except Exception as exc:
        raise _http(
            ERROR_PROFILE_INCONSISTENT,
            "active profile JSON failed validation",
            status=500,
        ) from exc

    prefs_row = await profile_repo.get_job_preferences(session)
    if prefs_row is None:
        raise _http(
            ERROR_PROFILE_INCONSISTENT,
            "job preferences row missing for approved profile",
            status=500,
        )
    try:
        preferences = parse_job_preferences(prefs_row.preferences_json)
    except Exception as exc:
        raise _http(
            ERROR_PROFILE_INCONSISTENT,
            "job preferences JSON failed validation",
            status=500,
        ) from exc

    attachment = await att_repo.get_by_id(session, profile_row.active_attachment_id)
    if attachment is None or attachment.state != ATTACHMENT_STATE_ACTIVE:
        raise _http(
            ERROR_PROFILE_INCONSISTENT,
            "active profile has no matching active attachment",
            status=500,
        )

    return ProfileReadResponse(
        present=True,
        profile=profile,
        preferences=preferences,
        active_attachment=_attachment_public(attachment),
    )


def content_disposition_for(original_name: str) -> str:
    """Build a header-safe Content-Disposition for the active CV download.

    Display name is sanitized (no path segments, CR/LF). Uses both
    ``filename`` (ASCII fallback) and ``filename*`` (RFC 5987) forms.
    """
    safe = sanitize_original_name(original_name)
    # ASCII-only fallback for legacy clients.
    ascii_chars: list[str] = []
    for ch in safe:
        if 32 <= ord(ch) < 127 and ch not in {'"', "\\"}:
            ascii_chars.append(ch)
        else:
            ascii_chars.append("_")
    ascii_name = "".join(ascii_chars)
    if not ascii_name.strip("._") or ascii_name in {".", ".."}:
        ascii_name = "cv.pdf"
    encoded = quote(safe, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


@router.get(
    "/profile",
    response_model=ProfileReadResponse,
)
async def get_profile() -> ProfileReadResponse:
    """``GET /api/profile`` — active profile/preferences/attachment or empty."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        return await build_profile_read_response(session)


@router.get("/profile/cv")
async def get_profile_cv(request: Request) -> StreamingResponse:
    """``GET /api/profile/cv`` — stream only the active stored PDF."""
    storage: AttachmentStorage = request.app.state.storage
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as session:
        profile_row = await profile_repo.get_active_profile(session)
        if profile_row is None:
            raise _http(
                ERROR_PROFILE_NOT_FOUND,
                "no approved candidate profile",
            )
        attachment = await att_repo.get_by_id(
            session, profile_row.active_attachment_id
        )
        if attachment is None or attachment.state != ATTACHMENT_STATE_ACTIVE:
            raise _http(
                ERROR_ACTIVE_CV_NOT_FOUND,
                "no active CV attachment for approved profile",
            )
        # Capture metadata before leaving the short session.
        storage_path = attachment.storage_path
        original_name = attachment.original_name
        size_bytes = attachment.size_bytes

    try:
        if not storage.exists(storage_path):
            raise _http(
                ERROR_ACTIVE_CV_FILE_MISSING,
                "active CV file is missing from storage",
            )
        handle = storage.open(storage_path)
    except PathEscapeError as exc:
        raise _http(
            ERROR_PROFILE_INCONSISTENT,
            "active CV storage path is invalid",
            status=500,
        ) from exc
    except FileNotFoundError as exc:
        raise _http(
            ERROR_ACTIVE_CV_FILE_MISSING,
            "active CV file is missing from storage",
        ) from exc

    def _iter_file() -> Any:
        try:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    headers = {
        "Content-Disposition": content_disposition_for(original_name),
        "Content-Length": str(size_bytes),
        # Never echo storage_path or internal paths.
    }
    return StreamingResponse(
        _iter_file(),
        media_type=ATTACHMENT_MIME_TYPE_PDF,
        headers=headers,
    )


__all__ = [
    "ERROR_ACTIVE_CV_FILE_MISSING",
    "ERROR_ACTIVE_CV_NOT_FOUND",
    "ERROR_PROFILE_INCONSISTENT",
    "ERROR_PROFILE_NOT_FOUND",
    "build_profile_read_response",
    "content_disposition_for",
    "router",
]
