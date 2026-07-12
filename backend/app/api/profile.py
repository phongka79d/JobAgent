"""Public read-only approved profile and active-CV endpoints (Plan 4 §7.1).

Resolves the active PDF only through ``candidate_profile.active_attachment_id``.
Stale unreferenced attachment rows are never downloadable. Routes never expose
drafts, raw PDF text, storage paths, hashes, or a mutation surface.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from pathlib import PurePath
from typing import Final, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.db.enums import AttachmentState
from app.db.session import DatabaseSessionManager
from app.repositories.attachments import AttachmentRepository
from app.repositories.preferences import (
    PreferencesRepository,
    PreferencesRepositoryError,
    PreferencesValidationError,
)
from app.repositories.profiles import (
    ProfileRepository,
    ProfileRepositoryError,
    ProfileValidationError,
)
from app.schemas.profile import (
    ProfilePresenceState,
    ProfileResponse,
    SafeActiveAttachment,
)
from app.services.attachment_storage import AttachmentStorage
from app.services.attachment_storage_errors import (
    AttachmentStorageError,
    AttachmentStorageNotFoundError,
    InvalidStoragePathError,
)
from app.services.attachment_storage_paths import require_canonical_service_path

router = APIRouter(tags=["profile"])

logger = logging.getLogger(__name__)

# Stable public failure codes (never paths, hashes, or raw payloads).
NO_ACTIVE_CV: Final[str] = "NO_ACTIVE_CV"
PROFILE_INVALID: Final[str] = "PROFILE_INVALID"
PREFERENCES_INVALID: Final[str] = "PREFERENCES_INVALID"
BLOCKED_BY_DATA_INTEGRITY: Final[str] = "BLOCKED_BY_DATA_INTEGRITY"
PROFILE_LOAD_FAILED: Final[str] = "PROFILE_LOAD_FAILED"

_CONTROL_CHARS: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f]")
_DEFAULT_CV_NAME: Final[str] = "cv.pdf"
_MAX_FILENAME_LEN: Final[int] = 180


def _detail(code: str) -> dict[str, str]:
    return {"code": code}


def _http_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=_detail(code))


def _db(request: Request) -> DatabaseSessionManager:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
        )
    return cast(DatabaseSessionManager, db)


def _storage(request: Request) -> AttachmentStorage:
    store = getattr(request.app.state, "storage", None)
    if store is None:
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
        )
    return cast(AttachmentStorage, store)



def sanitize_download_filename(original_name: str) -> str:
    """Return a basename-only PDF filename safe for Content-Disposition."""
    raw = original_name if isinstance(original_name, str) else ""
    leaf = PurePath(raw.replace("\\", "/")).name.strip()
    leaf = _CONTROL_CHARS.sub("", leaf)
    leaf = leaf.replace('"', "").replace("'", "").strip(" .")
    if not leaf:
        leaf = _DEFAULT_CV_NAME
    if not leaf.lower().endswith(".pdf"):
        leaf = f"{leaf}.pdf"
    if len(leaf) > _MAX_FILENAME_LEN:
        # Keep extension; trim the stem.
        stem = leaf[:-4][: _MAX_FILENAME_LEN - 4] or "cv"
        leaf = f"{stem}.pdf"
    return leaf


def content_disposition_for(filename: str) -> str:
    """Build a dual ASCII / RFC 5987 Content-Disposition header value."""
    safe = sanitize_download_filename(filename)
    # ASCII fallback: strip non-latin1 for the quoted-string form.
    ascii_name = safe.encode("ascii", errors="ignore").decode("ascii") or _DEFAULT_CV_NAME
    ascii_name = ascii_name.replace("\\", "").replace('"', "")
    if not ascii_name.lower().endswith(".pdf"):
        ascii_name = f"{ascii_name}.pdf" if ascii_name else _DEFAULT_CV_NAME
    encoded = quote(safe, safe="")
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


async def _safe_attachment_meta(
    session: object,
    attachment_id: UUID,
) -> SafeActiveAttachment:
    """Load safe metadata for the exact singleton-referenced active attachment.

    Requires the referenced row to exist, be ACTIVE, and use canonical
    ``active/<same-id>`` path authority. Raises sanitized HTTP 409
    ``BLOCKED_BY_DATA_INTEGRITY`` on any mismatch; never falls back to another
    row and never soft-nulls a broken reference.
    """
    row = await AttachmentRepository(session).get_by_id(attachment_id)  # type: ignore[arg-type]
    if row is None:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)
    if str(row.state) != AttachmentState.ACTIVE.value:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)
    if row.id != attachment_id:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)
    try:
        require_canonical_service_path(
            str(row.storage_path),
            row.id,
            expected_area=AttachmentState.ACTIVE.value,
        )
    except Exception as exc:
        raise _http_error(
            status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY
        ) from exc
    return SafeActiveAttachment(
        id=row.id,
        original_name=str(row.original_name),
        mime_type=str(row.mime_type),
        size_bytes=int(row.size_bytes),
        page_count=row.page_count if row.page_count is None else int(row.page_count),
        state=str(row.state),
    )


@router.get("/api/profile", response_model=ProfileResponse)
async def get_profile(request: Request) -> ProfileResponse:
    """Return approved profile/preferences and safe active attachment metadata."""
    db = _db(request)
    try:
        async with db.session_scope() as session:
            try:
                approved = await ProfileRepository(session).get()
            except ProfileValidationError as exc:
                raise _http_error(status.HTTP_400_BAD_REQUEST, PROFILE_INVALID) from exc
            except ProfileRepositoryError as exc:
                raise _http_error(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
                ) from exc

            if approved is None:
                return ProfileResponse(
                    state=ProfilePresenceState.NONE,
                    profile=None,
                    preferences=None,
                    active_attachment=None,
                )

            try:
                preferences = await PreferencesRepository(session).get()
            except PreferencesValidationError as exc:
                raise _http_error(
                    status.HTTP_400_BAD_REQUEST, PREFERENCES_INVALID
                ) from exc
            except PreferencesRepositoryError as exc:
                raise _http_error(
                    status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
                ) from exc

            active_meta: SafeActiveAttachment | None = None
            if approved.active_attachment_id is not None:
                active_meta = await _safe_attachment_meta(
                    session, approved.active_attachment_id
                )

            return ProfileResponse(
                state=ProfilePresenceState.ACTIVE,
                profile=approved.profile,
                preferences=preferences,
                active_attachment=active_meta,
            )
    except HTTPException:
        raise
    except Exception:
        logger.info("profile_read_failed sanitized")
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
        ) from None


async def _resolve_active_cv(
    db: DatabaseSessionManager,
) -> tuple[str, str]:
    """Return ``(service_relative_path, original_name)`` for the singleton CV.

    Raises HTTPException with sanitized codes; never falls back to another row.
    """
    async with db.session_scope() as session:
        try:
            approved = await ProfileRepository(session).get()
        except ProfileValidationError as exc:
            raise _http_error(status.HTTP_400_BAD_REQUEST, PROFILE_INVALID) from exc
        except ProfileRepositoryError as exc:
            raise _http_error(
                status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
            ) from exc

        if approved is None or approved.active_attachment_id is None:
            raise _http_error(status.HTTP_404_NOT_FOUND, NO_ACTIVE_CV)

        attachment_id = approved.active_attachment_id
        row = await AttachmentRepository(session).get_by_id(attachment_id)
        if row is None:
            raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)
        if str(row.state) != AttachmentState.ACTIVE.value:
            raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)
        if row.id != attachment_id:
            raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY)

        try:
            path = require_canonical_service_path(
                str(row.storage_path),
                row.id,
                expected_area=AttachmentState.ACTIVE.value,
            )
        except Exception as exc:
            raise _http_error(
                status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY
            ) from exc

        return path, str(row.original_name)


@router.get("/api/profile/cv")
async def get_profile_cv(request: Request) -> StreamingResponse:
    """Stream only the singleton-referenced active PDF with safe headers."""
    db = _db(request)
    storage = _storage(request)

    try:
        storage_path, original_name = await _resolve_active_cv(db)
    except HTTPException:
        raise
    except Exception:
        logger.info("profile_cv_resolve_failed sanitized")
        raise _http_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, PROFILE_LOAD_FAILED
        ) from None

    try:
        stream = await storage.open(storage_path)
    except AttachmentStorageNotFoundError as exc:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY) from exc
    except InvalidStoragePathError as exc:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY) from exc
    except AttachmentStorageError as exc:
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY) from exc
    except Exception:
        logger.info("profile_cv_open_failed sanitized")
        raise _http_error(status.HTTP_409_CONFLICT, BLOCKED_BY_DATA_INTEGRITY) from None

    filename = sanitize_download_filename(original_name)

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in stream:
                yield chunk
        except AttachmentStorageError:
            logger.info("profile_cv_stream_failed sanitized")
            return
        except Exception:
            logger.info("profile_cv_stream_failed sanitized")
            return

    return StreamingResponse(
        body(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition_for(filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
