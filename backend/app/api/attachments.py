"""Thin multipart CV upload route (Plan 4 §7.3 / Master §14.1).

Transport only: validate multipart presence, delegate to ``cv_upload``, map
stable codes to JSON HTTP errors. No provider, graph, checkpoint, Neo4j, or
active-profile write logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.core.settings import Settings
from app.db.session import get_session_factory
from app.schemas.attachments import CvUploadResponse
from app.services.chat_turns import ERROR_APPROVAL_ACTION_REQUIRED
from app.services.cv_upload import (
    ERROR_EMPTY_UPLOAD,
    ERROR_INVALID_MIME,
    ERROR_INVALID_PDF_MAGIC,
    ERROR_MALFORMED_PDF,
    ERROR_PDF_TOO_LARGE,
    ERROR_PDF_TOO_MANY_PAGES,
    ERROR_STORAGE_FAILURE,
    CvUploadError,
    upload_cv_from_upload_file,
)
from app.storage.attachments import AttachmentStorage

router = APIRouter(tags=["attachments"])

_UPLOAD_ERROR_STATUS: dict[str, int] = {
    ERROR_APPROVAL_ACTION_REQUIRED: 409,
    ERROR_INVALID_MIME: 422,
    ERROR_INVALID_PDF_MAGIC: 422,
    ERROR_EMPTY_UPLOAD: 422,
    ERROR_PDF_TOO_LARGE: 422,
    ERROR_PDF_TOO_MANY_PAGES: 422,
    ERROR_MALFORMED_PDF: 422,
    ERROR_STORAGE_FAILURE: 500,
}


def _http_for_upload_error(exc: CvUploadError) -> HTTPException:
    status = _UPLOAD_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


@router.post(
    "/attachments/cv",
    response_model=CvUploadResponse,
)
async def post_cv_upload(
    request: Request,
    file: Annotated[UploadFile, File(description="PDF CV file")],
) -> CvUploadResponse:
    """``POST /api/attachments/cv`` — shared sidebar and chat CV upload."""
    storage: AttachmentStorage = request.app.state.storage
    settings: Settings = request.app.state.settings

    async def _read(size: int) -> bytes:
        return await file.read(size)

    try:
        return await upload_cv_from_upload_file(
            content_type=file.content_type,
            filename=file.filename,
            file_read=_read,
            storage=storage,
            settings=settings,
            session_factory=get_session_factory(),
        )
    except CvUploadError as exc:
        raise _http_for_upload_error(exc) from exc
