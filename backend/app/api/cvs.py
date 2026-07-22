"""Thin CV Manager mutation routes (Plan 9 / Master §14.1).

Transport only: validate path params, delegate reprocess to chat-turn
services and delete to the CV Manager coordinator, frame already-validated
SSE events. No second runner, no extraction/approval/deletion business rules
inlined here, and no open DB transaction across yields.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.sse import EventSourceResponse

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.api.sse import open_sse_response
from app.schemas.common import UuidStr
from app.schemas.cv_manager import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    ERROR_CHUNKS_UNAVAILABLE,
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_DELETE_CHECKPOINT_FAILED,
    ERROR_CV_DELETE_FILE_FAILED,
    ERROR_CV_DELETE_FINALIZE_FAILED,
    ERROR_CV_DELETE_GRAPH_FAILED,
    ERROR_CV_FILE_UNAVAILABLE,
    ERROR_CV_NOT_REPROCESSABLE,
)
from app.services.chat_turns import (
    ChatTurnError,
    stream_cv_reprocess,
)
from app.services.cv_manager import CvDeleteError, delete_cv
from app.storage.attachments import AttachmentStorage

router = APIRouter(tags=["cvs"])

_REPROCESS_ERROR_STATUS: dict[str, int] = {
    ERROR_APPROVAL_ACTION_REQUIRED: 409,
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_NOT_REPROCESSABLE: 409,
    ERROR_CV_FILE_UNAVAILABLE: 404,
    ERROR_CHUNKS_UNAVAILABLE: 404,
}

_DELETE_ERROR_STATUS: dict[str, int] = {
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN: 409,
    ERROR_CV_DELETE_CHECKPOINT_FAILED: 409,
    ERROR_CV_DELETE_FILE_FAILED: 409,
    ERROR_CV_DELETE_GRAPH_FAILED: 409,
    ERROR_CV_DELETE_FINALIZE_FAILED: 409,
}


def _http_for_reprocess_error(exc: ChatTurnError) -> HTTPException:
    status = _REPROCESS_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


def _http_for_delete_error(exc: CvDeleteError) -> HTTPException:
    status = _DELETE_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


@router.post("/cvs/{attachment_id}/reprocess")
async def post_cv_reprocess(
    request: Request,
    attachment_id: Annotated[UuidStr, Path(description="Attachment id")],
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    """``POST /api/cvs/{attachment_id}/reprocess`` — active/archived re-extract.

    Returns the normal validated SSE stream through proposal and approval
    interrupt. Does not change active selection before Save Profile.
    """
    storage: AttachmentStorage = request.app.state.storage
    events = stream_cv_reprocess(
        attachment_id=attachment_id,
        storage=storage,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(
        events,
        error_mapper=_http_for_reprocess_error,
    )


@router.delete(
    "/cvs/{attachment_id}",
    status_code=204,
    response_class=Response,
)
async def delete_cv_attachment(
    request: Request,
    attachment_id: Annotated[UuidStr, Path(description="Attachment id")],
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> Response:
    """``DELETE /api/cvs/{attachment_id}`` — retryable complete non-active delete.

    Returns ``204`` only after SQLite ownership, retained file, and CV-owned
    Neo4j branch are gone. Active rows return ``409 CV_ACTIVE_DELETE_FORBIDDEN``
    without mutation. Partial cleanup keeps ``deleting`` and a stable retry code.
    """
    storage: AttachmentStorage = request.app.state.storage
    driver: Any = getattr(request.app.state, "neo4j_driver", None)
    try:
        await delete_cv(
            attachment_id,
            storage=storage,
            driver=driver,
            sqlite_path=deps.sqlite_path,
        )
    except CvDeleteError as exc:
        raise _http_for_delete_error(exc) from exc
    return Response(status_code=204)


__all__ = ["router"]
