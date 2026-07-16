"""Thin read-only observability routes (Plan 8 / Master §14).

CV history, retained-CV stream, chunk list/detail, durable run history, and
the bounded Neo4j graph snapshot. Transport-only: validate inputs, delegate
to the observability service, map stable codes to safe JSON errors. No
mutation, Agent, provider Cypher, or checkpoint work.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.profile import content_disposition_for
from app.db.models.attachments import ATTACHMENT_MIME_TYPE_PDF
from app.db.session import get_session_factory
from app.graph.consistency import AsyncGraphReadDriver
from app.schemas.common import UuidStr
from app.schemas.observability import (
    ChunkDetail,
    ChunkListPage,
    ChunkListQuery,
    CvHistoryPage,
    GraphSnapshot,
    ObservabilityQuery,
    RunHistoryPage,
)
from app.services.observability import (
    ERROR_CHUNK_NOT_FOUND,
    ERROR_CHUNKS_UNAVAILABLE,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_FILE_UNAVAILABLE,
    ObservabilityServiceError,
    get_chunk_detail,
    get_chunk_list_page,
    get_cv_history_page,
    get_graph_snapshot,
    get_run_history_page,
    resolve_retained_cv_file,
)
from app.storage.attachments import AttachmentStorage, PathEscapeError

router = APIRouter(tags=["observability"])

_ERROR_STATUS: dict[str, int] = {
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_FILE_UNAVAILABLE: 404,
    ERROR_CHUNKS_UNAVAILABLE: 404,
    ERROR_CHUNK_NOT_FOUND: 404,
    "INVALID_LIMIT": 422,
}


def _http_for_service_error(exc: ObservabilityServiceError) -> HTTPException:
    status = _ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


def _http(code: str, summary: str, status: int = 404) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "summary": summary},
    )


def _obs_query(
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> ObservabilityQuery:
    """Validate CV/run history query params (malformed cursor → 422)."""
    try:
        return ObservabilityQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _chunk_query(
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> ChunkListQuery:
    """Validate chunk-list query params (malformed cursor → 422)."""
    try:
        return ChunkListQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get(
    "/observability/cvs",
    response_model=CvHistoryPage,
)
async def get_observability_cvs(
    request: Request,
    query: Annotated[ObservabilityQuery, Depends(_obs_query)],
) -> CvHistoryPage:
    """``GET /api/observability/cvs`` — cursor-paginated CV attachment history."""
    storage: AttachmentStorage = request.app.state.storage
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            page = await get_cv_history_page(
                session,
                storage,
                limit=query.limit,
                before=query.before,
            )
        except ObservabilityServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return page


@router.get("/observability/cvs/{attachment_id}/file")
async def get_observability_cv_file(
    request: Request,
    attachment_id: Annotated[UuidStr, Path()],
) -> StreamingResponse:
    """``GET /api/observability/cvs/{id}/file`` — stream retained PDF."""
    storage: AttachmentStorage = request.app.state.storage
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as session:
        try:
            storage_path, original_name, size_bytes = await resolve_retained_cv_file(
                session,
                storage,
                attachment_id,
            )
        except ObservabilityServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()

    try:
        if not storage.exists(storage_path):
            raise _http(
                ERROR_CV_FILE_UNAVAILABLE,
                "retained CV file is unavailable",
            )
        handle = storage.open(storage_path)
    except PathEscapeError as exc:
        raise _http(
            ERROR_CV_FILE_UNAVAILABLE,
            "retained CV file is unavailable",
            status=404,
        ) from exc
    except FileNotFoundError as exc:
        raise _http(
            ERROR_CV_FILE_UNAVAILABLE,
            "retained CV file is unavailable",
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
    }
    return StreamingResponse(
        _iter_file(),
        media_type=ATTACHMENT_MIME_TYPE_PDF,
        headers=headers,
    )


@router.get(
    "/observability/cvs/{attachment_id}/chunks",
    response_model=ChunkListPage,
)
async def get_observability_chunks(
    attachment_id: Annotated[UuidStr, Path()],
    query: Annotated[ChunkListQuery, Depends(_chunk_query)],
) -> ChunkListPage:
    """``GET /api/observability/cvs/{id}/chunks`` — preview-only chunk page."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            page = await get_chunk_list_page(
                session,
                attachment_id,
                limit=query.limit,
                before=query.before,
            )
        except ObservabilityServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return page


@router.get(
    "/observability/cvs/{attachment_id}/chunks/{ordinal}",
    response_model=ChunkDetail,
)
async def get_observability_chunk_detail(
    attachment_id: Annotated[UuidStr, Path()],
    ordinal: Annotated[int, Path(ge=0)],
) -> ChunkDetail:
    """``GET /api/observability/cvs/{id}/chunks/{ordinal}`` — selected full text."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            detail = await get_chunk_detail(session, attachment_id, ordinal)
        except ObservabilityServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return detail


@router.get(
    "/observability/runs",
    response_model=RunHistoryPage,
)
async def get_observability_runs(
    query: Annotated[ObservabilityQuery, Depends(_obs_query)],
) -> RunHistoryPage:
    """``GET /api/observability/runs`` — cursor-paginated durable run history."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            page = await get_run_history_page(
                session,
                limit=query.limit,
                before=query.before,
            )
        except ObservabilityServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return page


@router.get(
    "/observability/graph",
    response_model=GraphSnapshot,
)
async def get_observability_graph(request: Request) -> GraphSnapshot:
    """``GET /api/observability/graph`` — bounded allowlisted Neo4j snapshot.

    Accepts no query/filter/expansion/mutation input. Typed ``ready``,
    ``stale``, and ``unavailable`` states are returned as ``200`` bodies.
    """
    driver: AsyncGraphReadDriver = request.app.state.neo4j_driver
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        snapshot = await get_graph_snapshot(session, driver)
        await session.commit()
    return snapshot


__all__ = [
    "router",
]
