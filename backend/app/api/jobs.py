"""Thin saved-JD public routes (Plan 10 / Master §14).

List/detail GETs and save/evaluate/delete mutations: validate inputs, delegate
to the saved-JD service and accepted owners, map stable codes to safe JSON
errors. No business logic, SQL, Cypher, or provider work inlined here.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import ShopAIKeyEmbeddingAdapter
from app.db.session import get_session_factory
from app.schemas.common import UuidStr
from app.schemas.job_evaluations import (
    EvaluateJobResponse,
    ReextractJobRequest,
    ReextractJobResponse,
    SaveAndEvaluateRequest,
    SaveAndEvaluateResponse,
    SavedJobDetail,
    SavedJobListPage,
    SavedJobsQuery,
)
from app.services.jd_extraction import ShopAIKeyStructuredJdInvoker
from app.services.saved_jobs import (
    ERROR_ACTIVE_PROFILE_REQUIRED,
    ERROR_JD_SOURCE_NOT_RECOVERABLE,
    ERROR_JOB_DELETE_GRAPH_FAILED,
    ERROR_JOB_NOT_FOUND,
    ERROR_JOB_NOT_SCORABLE,
    ERROR_JOB_REEXTRACT_CONFLICT,
    SavedJobsServiceError,
    delete_saved_job,
    evaluate_saved_job,
    get_saved_job_detail,
    get_saved_jobs_page,
    reextract_saved_job,
    save_and_evaluate_from_source,
)

router = APIRouter(tags=["jobs"])

_ERROR_STATUS: dict[str, int] = {
    ERROR_JOB_NOT_FOUND: 404,
    ERROR_JD_SOURCE_NOT_RECOVERABLE: 400,
    ERROR_JOB_NOT_SCORABLE: 409,
    ERROR_ACTIVE_PROFILE_REQUIRED: 409,
    ERROR_JOB_DELETE_GRAPH_FAILED: 409,
    ERROR_JOB_REEXTRACT_CONFLICT: 409,
    "EVALUATION_CONTEXT_CHANGED": 409,
    "INVALID_MATCH_RESULT": 422,
    "INVALID_LIMIT": 422,
    "INVALID_STRUCTURED_OUTPUT": 422,
    "NEO4J_UNAVAILABLE": 409,
    "NEO4J_REBUILD_REQUIRED": 409,
    "NEO4J_SYNC_FAILED": 409,
    "EMBEDDING_TIMEOUT": 502,
    "EMBEDDING_UNAVAILABLE": 502,
    "EMBEDDING_INVALID_RESPONSE": 502,
    "EMBEDDING_RATE_LIMIT": 502,
    "PROVIDER_ERROR": 502,
    "PROVIDER_TIMEOUT": 502,
    "PROVIDER_RATE_LIMIT": 502,
}


def _http_for_service_error(exc: SavedJobsServiceError) -> HTTPException:
    status = _ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


def _jobs_query(
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> SavedJobsQuery:
    """Validate list query params (malformed cursor → 422)."""
    try:
        return SavedJobsQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _graph_driver(request: Request) -> Any:
    return getattr(request.app.state, "neo4j_driver", None)


@router.get(
    "/jobs",
    response_model=SavedJobListPage,
)
async def list_saved_jobs(
    query: Annotated[SavedJobsQuery, Depends(_jobs_query)],
) -> SavedJobListPage:
    """``GET /api/jobs`` — cursor-paginated compact saved-JD list."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            page = await get_saved_jobs_page(
                session,
                limit=query.limit,
                before=query.before,
            )
        except SavedJobsServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return page


@router.get(
    "/jobs/{job_id}",
    response_model=SavedJobDetail,
)
async def get_saved_job(
    job_id: Annotated[UuidStr, Path()],
) -> SavedJobDetail:
    """``GET /api/jobs/{job_id}`` — selected detail + latest evaluation."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    async with factory() as session:
        try:
            detail = await get_saved_job_detail(session, job_id)
        except SavedJobsServiceError as exc:
            raise _http_for_service_error(exc) from exc
        await session.commit()
    return detail


@router.post(
    "/jobs/save-and-evaluate",
    response_model=SaveAndEvaluateResponse,
)
async def post_save_and_evaluate(
    request: Request,
    body: SaveAndEvaluateRequest,
) -> SaveAndEvaluateResponse:
    """``POST /api/jobs/save-and-evaluate`` — durable zero-result source only."""
    factory = get_session_factory()
    try:
        return await save_and_evaluate_from_source(
            body.source_message_id,
            session_factory=factory,
            graph_driver=_graph_driver(request),
            invoker=ShopAIKeyStructuredJdInvoker(),
            embedding_client=ShopAIKeyEmbeddingAdapter(),
        )
    except SavedJobsServiceError as exc:
        raise _http_for_service_error(exc) from exc


@router.post(
    "/jobs/{job_id}/evaluate",
    response_model=EvaluateJobResponse,
)
async def post_evaluate_job(
    request: Request,
    job_id: Annotated[UuidStr, Path()],
) -> EvaluateJobResponse:
    """``POST /api/jobs/{job_id}/evaluate`` — current-context create or reuse."""
    factory = get_session_factory()
    try:
        return await evaluate_saved_job(
            job_id,
            session_factory=factory,
            graph_driver=_graph_driver(request),
            embedding_client=ShopAIKeyEmbeddingAdapter(),
        )
    except SavedJobsServiceError as exc:
        raise _http_for_service_error(exc) from exc


@router.delete(
    "/jobs/{job_id}",
    status_code=204,
    response_class=Response,
)
async def delete_saved_job_route(
    request: Request,
    job_id: Annotated[UuidStr, Path()],
) -> Response:
    """``DELETE /api/jobs/{job_id}`` — complete deletion coordinator only."""
    factory = get_session_factory()
    try:
        await delete_saved_job(
            job_id,
            session_factory=factory,
            graph_driver=_graph_driver(request),
        )
    except SavedJobsServiceError as exc:
        raise _http_for_service_error(exc) from exc
    return Response(status_code=204)


@router.post(
    "/jobs/{job_id}/reextract",
    response_model=ReextractJobResponse,
)
async def post_reextract_job(
    request: Request,
    job_id: Annotated[UuidStr, Path()],
    body: ReextractJobRequest | None = None,
) -> ReextractJobResponse:
    """``POST /api/jobs/{job_id}/reextract`` — same-ID retained-JD replacement.

    Absent or empty JSON is allowed. Replacement/arbitrary fields are rejected
    by the zero-field ``extra='forbid'`` request model (422) before service work.
    """
    del body  # Boundary-only; server reloads retained Job by ID.
    factory = get_session_factory()
    try:
        return await reextract_saved_job(
            job_id,
            session_factory=factory,
            graph_driver=_graph_driver(request),
            invoker=ShopAIKeyStructuredJdInvoker(),
            embedding_client=ShopAIKeyEmbeddingAdapter(),
        )
    except SavedJobsServiceError as exc:
        raise _http_for_service_error(exc) from exc


__all__ = ["router"]
