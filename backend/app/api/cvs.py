"""Deletion-only CV Manager route ownership (Plan 9 / Master §14.1).

Deletion-only transport: validate the attachment path parameter and delegate
to the CV Manager coordinator. Profile-owned re-extraction routes live in
app.api.profiles; this module owns no extraction or approval routes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import FileResponse

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
)
from app.db.models.profiles import PROFILE_STATE_READY
from app.db.session import get_session_factory
from app.repositories import attachments as attachment_repo
from app.repositories import profiles as profile_repo
from app.schemas.common import UuidStr
from app.schemas.cv_manager import (
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_DELETE_CHECKPOINT_FAILED,
    ERROR_CV_DELETE_FILE_FAILED,
    ERROR_CV_DELETE_FINALIZE_FAILED,
    ERROR_CV_DELETE_GRAPH_FAILED,
    ERROR_CV_FILE_UNAVAILABLE,
    ERROR_CV_PROFILE_OWNED_DELETE_FORBIDDEN,
    CvManagerListResponse,
)
from app.services.cv_manager import (
    ERROR_CV_DELETE_BLOCKED,
    CvDeleteError,
    delete_cv,
)
from app.services.cv_manager_projection import build_cv_manager_list
from app.services.cv_upload import sanitize_original_name
from app.storage.attachments import AttachmentStorage, PathEscapeError

router = APIRouter(tags=["cvs"])

_DELETE_ERROR_STATUS: dict[str, int] = {
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_ACTIVE_DELETE_FORBIDDEN: 409,
    ERROR_CV_PROFILE_OWNED_DELETE_FORBIDDEN: 409,
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


def content_disposition_for(
    original_name: str,
    disposition: Literal['inline', 'attachment'],
) -> str:
    '''Build a header-safe disposition with ASCII and RFC 5987 names.'''
    safe = sanitize_original_name(original_name)
    ascii_chars: list[str] = []
    for ch in safe:
        if 32 <= ord(ch) < 127 and ch not in {'"', '\\'}:
            ascii_chars.append(ch)
        else:
            ascii_chars.append('_')
    ascii_name = ''.join(ascii_chars)
    if not ascii_name.strip('._') or ascii_name in {'.', '..'}:
        ascii_name = 'cv.pdf'
    encoded = quote(safe, safe='')
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


@router.get('/cvs', response_model=CvManagerListResponse)
async def list_cv_manager(request: Request) -> CvManagerListResponse:
    '''Return the server-authoritative CV Manager projection.'''
    storage: AttachmentStorage = request.app.state.storage
    factory = get_session_factory()
    async with factory() as session:
        return await build_cv_manager_list(session, storage=storage)


@router.get('/cvs/{attachment_id}/file')
async def get_cv_file(
    request: Request,
    attachment_id: Annotated[UuidStr, Path(description='Attachment id')],
    disposition: Literal['inline', 'attachment'] = Query(default='inline'),
) -> FileResponse:
    '''Stream only an existing retained file belonging to a ready profile.'''
    storage: AttachmentStorage = request.app.state.storage
    factory = get_session_factory()
    async with factory() as session:
        attachment = await attachment_repo.get_by_id(session, attachment_id)
        owner = await profile_repo.get_profile_by_attachment_id(
            session, attachment_id
        )
        if (
            attachment is None
            or owner is None
            or owner.state != PROFILE_STATE_READY
            or attachment.state not in {
                ATTACHMENT_STATE_ACTIVE,
                ATTACHMENT_STATE_ARCHIVED,
            }
        ):
            raise HTTPException(
                status_code=404,
                detail={
                    'code': ERROR_CV_FILE_UNAVAILABLE,
                    'summary': 'CV file is unavailable',
                },
            )
        storage_path = attachment.storage_path
        original_name = attachment.original_name

    try:
        path = storage.resolve_path(storage_path)
        if not path.is_file():
            raise FileNotFoundError(storage_path)
    except (FileNotFoundError, OSError, PathEscapeError, ValueError) as exc:
        raise HTTPException(
            status_code=404,
            detail={
                'code': ERROR_CV_FILE_UNAVAILABLE,
                'summary': 'CV file is unavailable',
            },
        ) from exc

    headers = {
        'Content-Disposition': content_disposition_for(original_name, disposition),
        'X-Content-Type-Options': 'nosniff',
    }
    return FileResponse(path, media_type='application/pdf', headers=headers)


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
