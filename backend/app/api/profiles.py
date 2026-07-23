"""Profile list/detail/rename/selection API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request

from app.db.session import get_session_factory
from app.repositories import profiles as profiles_repo
from app.schemas.common import UuidStr
from app.schemas.profile import (
    ProfileDetail,
    ProfileListResponse,
    ProfileUpdateRequest,
    SelectionResponse,
)
from app.services.profile_activation import (
    ProfileActivationError,
    activate_profile_by_id,
)
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
    if not body.display_name.strip():
        raise _http("INVALID_DISPLAY_NAME", "display name must not be blank", 422)
    factory = get_session_factory()
    async with factory() as session:
        try:
            await profiles_repo.update_display_name(
                session, profile_id=profile_id, display_name=body.display_name.strip()
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


__all__ = ["router"]
