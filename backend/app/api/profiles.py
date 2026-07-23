"""Profile list/detail/rename/selection API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.time import utc_now
from app.db.models.profiles import PROFILE_STATE_READY
from app.db.session import get_session_factory
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.profile import (
    ProfileDetail,
    ProfileListResponse,
    ProfileUpdateRequest,
    SelectionResponse,
)
from app.services.activity_gate import ActivityBlockedError, assert_workspace_idle
from app.services.profile_activation import activate_selected_attachment
from app.services.profile_projection import (
    ProfileProjectionError,
    build_profile_detail,
    build_profile_list_response,
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
            raise _http(exc.code, exc.summary, 500) from exc


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
async def get_profile(profile_id: str) -> ProfileDetail:
    factory = get_session_factory()
    async with factory() as session:
        try:
            return await build_profile_detail(session, profile_id=profile_id)
        except ProfileProjectionError as exc:
            raise _http(
                exc.code, exc.summary, 404 if exc.code == "PROFILE_NOT_FOUND" else 500
            ) from exc


@router.patch("/profiles/{profile_id}", response_model=ProfileDetail)
async def patch_profile(profile_id: str, body: ProfileUpdateRequest) -> ProfileDetail:
    if not body.display_name.strip():
        raise _http("INVALID_DISPLAY_NAME", "display name must not be blank", 422)
    factory = get_session_factory()
    async with factory() as session:
        try:
            await profiles_repo.update_display_name(
                session, profile_id=profile_id, display_name=body.display_name.strip()
            )
            await session.commit()
            return await build_profile_detail(session, profile_id=profile_id)
        except profiles_repo.ProfileRepositoryError as exc:
            await session.rollback()
            raise _http("PROFILE_NOT_FOUND", "profile not found", 404) from exc
        except ProfileProjectionError as exc:
            raise _http(exc.code, exc.summary, 500) from exc


@router.post("/profiles/{profile_id}/activate", response_model=SelectionResponse)
async def activate_profile(profile_id: str) -> SelectionResponse:
    factory = get_session_factory()
    async with factory() as session:
        try:
            await assert_workspace_idle(session)
        except ActivityBlockedError as exc:
            raise _http(exc.code, exc.summary, 409) from exc
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise _http("PROFILE_NOT_FOUND", "profile not found", 404)
        if profile.state != PROFILE_STATE_READY:
            raise _http("PROFILE_NOT_READY", "profile is not ready", 409)
        current = await workspace_repo.get_active_profile_id(session)
        if current != profile_id:
            current_profile = (
                await profiles_repo.get_profile(session, current) if current else None
            )
            await activate_selected_attachment(
                session,
                attachment_id=profile.attachment_id,
                old_attachment_id=current_profile.attachment_id
                if current_profile
                else None,
            )
        await workspace_repo.set_active_profile_id(session, profile_id)
        profile.last_opened_at = utc_now()
        selected = await conversations_repo.most_recent_for_profile(
            session, profile_id=profile_id
        )
        await session.commit()
        detail = await build_profile_detail(session, profile_id=profile_id)
        return SelectionResponse(
            profile=detail, conversation_id=selected.id if selected else None
        )


__all__ = ["router"]
