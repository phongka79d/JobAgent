"""Profile list/detail/rename/selection API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.sse import EventSourceResponse

from app.api.dependencies import (
    ProfileReextractDeps,
    get_profile_reextract_deps,
)
from app.api.sse import format_profile_reextract_sse, open_typed_sse_response
from app.core.settings import get_settings
from app.db.models.profiles import PROFILE_DISPLAY_NAME_MAX
from app.db.session import get_session_factory
from app.repositories import profiles as profiles_repo
from app.schemas.common import AwareUtcDatetime, UuidStr
from app.schemas.profile import (
    ProfileDeleteResponse,
    ProfileDetail,
    ProfileListResponse,
    ProfileUpdateRequest,
    ReextractRequest,
    SelectionResponse,
)
from app.schemas.profile_reextraction import (
    ProfileReextractApprovalResponse,
    ProfileReextractApproveRequest,
    ProfileReextractReview,
)
from app.services.profile_activation import (
    ProfileActivationError,
    activate_profile_by_id,
)
from app.services.profile_deletion import ProfileDeletionError
from app.services.profile_deletion import delete_profile as delete_profile_service
from app.services.profile_reextraction import (
    ProfileReextractError,
    ProfileReextractionCoordinator,
)
from app.services.profile_projection import (
    ProfileProjectionError,
    build_profile_detail,
    build_profile_list_response,
)
from app.storage.attachments import AttachmentStorage


def _http_for_reextract_error(exc: Exception) -> HTTPException:
    if not isinstance(exc, ProfileReextractError):
        return HTTPException(
            status_code=500,
            detail={
                "code": "PROFILE_REEXTRACT_FAILED",
                "summary": "CV re-extraction could not be started",
            },
        )
    status = {
        "PROFILE_NOT_FOUND": 404,
        "PROFILE_NOT_READY": 409,
        "CV_ATTACHMENT_NOT_FOUND": 404,
        "CV_FILE_UNAVAILABLE": 404,
        "CV_NOT_REPROCESSABLE": 409,
        "PROFILE_REVIEW_PENDING": 409,
        "PROFILE_REEXTRACT_CONFLICT": 409,
        "PROFILE_REEXTRACT_DRAFT_NOT_FOUND": 404,
        "PROFILE_REEXTRACT_DRAFT_INVALID": 422,
        "DRAFT_NOT_FOUND": 404,
        "DRAFT_INVALID": 422,
        "DOCUMENT_DRAFT_NOT_FOUND": 404,
        "DOCUMENT_DRAFT_INVALID": 422,
        "ATTACHMENT_NOT_FOUND": 404,
        "ATTACHMENT_FILE_MISSING": 404,
        "PROFILE_INCONSISTENT": 409,
        "PROFILE_SWITCH_BLOCKED": 409,
    }.get(exc.code, 500)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.summary},
    )

router = APIRouter(tags=["profiles"])


def _http(code: str, summary: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "summary": summary})


def _profile_reextract_coordinator(
    deps: ProfileReextractDeps,
) -> ProfileReextractionCoordinator:
    return ProfileReextractionCoordinator(
        session_factory=deps.session_factory,
        storage=deps.storage,
        normalizer=deps.normalizer,
        invoker=deps.document_invoker,
        graph_driver=deps.graph_driver,
    )


@router.get("/profiles", response_model=ProfileListResponse)
async def list_profiles() -> ProfileListResponse:
    factory = get_session_factory()
    async with factory() as session:
        try:
            return await build_profile_list_response(session)
        except ProfileProjectionError as exc:
            await session.rollback()
            raise _http(exc.code, exc.summary, 500) from exc


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
async def get_profile(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
) -> ProfileDetail:
    factory = get_session_factory()
    async with factory() as session:
        try:
            return await build_profile_detail(session, profile_id=profile_id)
        except ProfileProjectionError as exc:
            raise _http(
                exc.code,
                exc.summary,
                404
                if exc.code == "PROFILE_NOT_FOUND"
                else 409
                if exc.code == "PROFILE_NOT_READY"
                else 500,
            ) from exc


@router.patch("/profiles/{profile_id}", response_model=ProfileDetail)
async def patch_profile(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    body: ProfileUpdateRequest,
) -> ProfileDetail:
    display_name = body.display_name.strip()
    if not display_name:
        raise _http("INVALID_DISPLAY_NAME", "display name must not be blank", 422)
    if len(display_name) > PROFILE_DISPLAY_NAME_MAX:
        raise _http(
            "INVALID_DISPLAY_NAME",
            (
                "display name must be between 1 and "
                f"{PROFILE_DISPLAY_NAME_MAX} characters"
            ),
            422,
        )
    factory = get_session_factory()
    async with factory() as session:
        try:
            await profiles_repo.update_display_name(
                session, profile_id=profile_id, display_name=display_name
            )
            detail = await build_profile_detail(session, profile_id=profile_id)
            await session.commit()
            return detail
        except profiles_repo.ProfileRepositoryError as exc:
            await session.rollback()
            raise _http("PROFILE_NOT_FOUND", "profile not found", 404) from exc
        except ProfileProjectionError as exc:
            await session.rollback()
            raise _http(
                exc.code,
                exc.summary,
                409 if exc.code == "PROFILE_NOT_READY" else 500,
            ) from exc


@router.post("/profiles/{profile_id}/activate", response_model=SelectionResponse)
async def activate_profile(
    request: Request,
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
) -> SelectionResponse:
    factory = get_session_factory()
    graph_driver: Any | None = getattr(request.app.state, "neo4j_driver", None)
    try:
        return await activate_profile_by_id(
            profile_id=profile_id,
            session_factory=factory,
            graph_driver=graph_driver,
        )
    except ProfileActivationError as exc:
        status = {
            "PROFILE_NOT_FOUND": 404,
            "PROFILE_NOT_READY": 409,
            "PROFILE_SETUP_IN_PROGRESS": 409,
            "PROFILE_SWITCH_BLOCKED": 409,
            "PROFILE_REVIEW_PENDING": 409,
            "PROFILE_INCONSISTENT": 500,
        }.get(exc.code, 500)
        raise _http(exc.code, exc.summary, status) from exc


@router.post("/profiles/{profile_id}/reextract")
async def reextract_profile(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    _body: ReextractRequest,
    deps: Annotated[ProfileReextractDeps, Depends(get_profile_reextract_deps)],
) -> EventSourceResponse:
    coordinator = _profile_reextract_coordinator(deps)
    return await open_typed_sse_response(
        coordinator.stream(profile_id),
        serializer=format_profile_reextract_sse,
        error_mapper=_http_for_reextract_error,
        error_types=(ProfileReextractError,),
    )


@router.get(
    "/profiles/{profile_id}/reextract-draft",
    response_model=ProfileReextractReview,
)
async def get_profile_reextract_review(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    deps: Annotated[ProfileReextractDeps, Depends(get_profile_reextract_deps)],
) -> ProfileReextractReview:
    coordinator = _profile_reextract_coordinator(deps)
    try:
        return await coordinator.get_review(profile_id)
    except ProfileReextractError as exc:
        raise _http_for_reextract_error(exc) from exc


@router.post(
    "/profiles/{profile_id}/reextract-draft/approve",
    response_model=ProfileReextractApprovalResponse,
)
async def approve_profile_reextract_review(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    body: ProfileReextractApproveRequest,
    deps: Annotated[ProfileReextractDeps, Depends(get_profile_reextract_deps)],
) -> ProfileReextractApprovalResponse:
    coordinator = _profile_reextract_coordinator(deps)
    try:
        return await coordinator.approve(profile_id, revision=body.revision)
    except ProfileReextractError as exc:
        raise _http_for_reextract_error(exc) from exc


@router.delete(
    "/profiles/{profile_id}/reextract-draft",
    status_code=204,
    response_class=Response,
)
async def discard_profile_reextract_review(
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    revision: Annotated[
        AwareUtcDatetime, Query(description="Expected UTC draft revision")
    ],
    deps: Annotated[ProfileReextractDeps, Depends(get_profile_reextract_deps)],
) -> Response:
    coordinator = _profile_reextract_coordinator(deps)
    try:
        await coordinator.discard(profile_id, revision=revision)
    except ProfileReextractError as exc:
        raise _http_for_reextract_error(exc) from exc
    return Response(status_code=204)


@router.delete("/profiles/{profile_id}", response_model=ProfileDeleteResponse)
async def delete_profile(
    request: Request,
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
) -> ProfileDeleteResponse:
    settings = getattr(request.app.state, "settings", None)
    storage = getattr(request.app.state, "storage", None)
    if not isinstance(storage, AttachmentStorage):
        cfg = settings if settings is not None else get_settings()
        storage = AttachmentStorage(cfg.FILES_DIR)
    try:
        return await delete_profile_service(
            profile_id=profile_id,
            session_factory=get_session_factory(),
            storage=storage,
            graph_driver=getattr(request.app.state, "neo4j_driver", None),
            sqlite_path=getattr(settings, "SQLITE_PATH", get_settings().SQLITE_PATH),
        )
    except ProfileDeletionError as exc:
        status = 404 if exc.code == "PROFILE_NOT_FOUND" else 409
        raise _http(exc.code, exc.summary, status) from exc


__all__ = ["router"]
