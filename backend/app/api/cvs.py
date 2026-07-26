"""Deletion-only CV Manager route ownership (Plan 9 / Master §14.1).

Deletion-only transport: validate the attachment path parameter and delegate
to the CV Manager coordinator. Profile-owned re-extraction routes live in
app.api.profiles; this module owns no extraction or approval routes.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.schemas.common import UuidStr
from app.schemas.cv_manager import (
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_DELETE_CHECKPOINT_FAILED,
    ERROR_CV_DELETE_FILE_FAILED,
    ERROR_CV_DELETE_FINALIZE_FAILED,
    ERROR_CV_DELETE_GRAPH_FAILED,
)
from app.services.cv_manager import (
    ERROR_CV_DELETE_BLOCKED,
    CvDeleteError,
    delete_cv,
)
from app.storage.attachments import AttachmentStorage

router = APIRouter(tags=["cvs"])

_DELETE_ERROR_STATUS: dict[str, int] = {
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN: 409,
    ERROR_CV_DELETE_BLOCKED: 409,
    ERROR_CV_DELETE_CHECKPOINT_FAILED: 409,
    ERROR_CV_DELETE_FILE_FAILED: 409,
    ERROR_CV_DELETE_GRAPH_FAILED: 409,
    ERROR_CV_DELETE_FINALIZE_FAILED: 409,
}


def _http_for_delete_error(exc: CvDeleteError) -> HTTPException:
    status = _DELETE_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
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
