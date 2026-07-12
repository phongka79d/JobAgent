"""Public staged CV upload route."""
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, UploadFile, status

from app.schemas.attachments import StagedAttachmentResponse
from app.services.cv_ingestion import CvIngestionError, CvIngestionService

router = APIRouter()


@router.post("/api/attachments/cv", response_model=StagedAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_cv(request: Request, file: UploadFile) -> StagedAttachmentResponse:
    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await file.read(64 * 1024):
            yield chunk
    service = CvIngestionService(request.app.state.db, request.app.state.storage, max_size_bytes=request.app.state.settings.max_pdf_size_mb * 1024 * 1024, max_pages=request.app.state.settings.max_pdf_pages)
    try:
        result = await service.intake(file.filename or "cv.pdf", file.content_type or "", chunks())
    except CvIngestionError as exc:
        statuses = {"UNSUPPORTED_MEDIA_TYPE": 415, "PDF_TOO_LARGE": 413, "UPLOAD_CONFLICT": 409}
        raise HTTPException(status_code=statuses.get(exc.code, 400), detail={"code": exc.code}) from None
    return StagedAttachmentResponse.model_validate(result, from_attributes=True)
