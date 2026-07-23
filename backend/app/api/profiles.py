"""Profile list/detail/rename/selection API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.sse import EventSourceResponse

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.api.sse import open_sse_response
from app.core.settings import get_settings
from app.db.models.profiles import PROFILE_DISPLAY_NAME_MAX
from app.db.session import get_session_factory
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.common import UuidStr
from app.schemas.profile import (
    ProfileDeleteResponse,
    ProfileDetail,
    ProfileListResponse,
    ProfileUpdateRequest,
    ReextractRequest,
    SelectionResponse,
)
from app.services.activity_gate import ActivityBlockedError, assert_workspace_idle
from app.services.chat_turns import ChatTurnError, stream_cv_reprocess
from app.services.profile_activation import (
    ProfileActivationError,
    activate_profile_by_id,
)
from app.services.profile_deletion import ProfileDeletionError
from app.services.profile_deletion import delete_profile as delete_profile_service
from app.services.profile_projection import (
    ProfileProjectionError,
    build_profile_detail,
    build_profile_list_response,
)
from app.storage.attachments import AttachmentStorage


def _http_for_reextract_error(exc: ChatTurnError) -> HTTPException:
    status = {
        "PROFILE_NOT_READY": 409,
        "CONVERSATION_NOT_FOUND": 404,
        "CONVERSATION_SWITCH_BLOCKED": 409,
        "APPROVAL_ACTION_REQUIRED": 409,
    }.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )

router = APIRouter(tags=["profiles"])


def _http(code: str, summary: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "summary": summary})


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
                exc.code, exc.summary, 404 if exc.code == "PROFILE_NOT_FOUND" else 500
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
            raise _http(exc.code, exc.summary, 500) from exc


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
            "PROFILE_SWITCH_BLOCKED": 409,
            "PROFILE_INCONSISTENT": 500,
        }.get(exc.code, 500)
        raise _http(exc.code, exc.summary, status) from exc


@router.post("/profiles/{profile_id}/reextract")
async def reextract_profile(
    request: Request,
    profile_id: Annotated[UuidStr, Path(description="Profile id")],
    _body: ReextractRequest,
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    """Re-extract the active profile's retained CV through the normal SSE flow."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            await assert_workspace_idle(session)
        except ActivityBlockedError as exc:
            raise _http(exc.code, exc.summary, 409) from exc
        profile = await profiles_repo.get_profile(session, profile_id)
        active_id = await workspace_repo.get_active_profile_id(session)
        if profile is None:
            raise _http("PROFILE_NOT_FOUND", "profile not found", 404)
        if profile.state != "ready" or active_id != profile_id:
            raise _http(
                "PROFILE_NOT_READY",
                "profile is not the active ready profile",
                409,
            )
        attachment_id = profile.attachment_id
    storage = request.app.state.storage
    events = stream_cv_reprocess(
        attachment_id=attachment_id,
        storage=storage,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(events, error_mapper=_http_for_reextract_error)


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
