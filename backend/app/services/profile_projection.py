"""Safe, profile-row keyed projection for profile APIs."""

from __future__ import annotations

from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachments import ATTACHMENT_MIME_TYPE_PDF, Attachment
from app.db.models.profiles import Profile
from app.repositories import attachments as attachments_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.attachments import AttachmentPublic, AttachmentState
from app.schemas.profile import (
    CandidateProfile,
    ProfileDetail,
    ProfileListItem,
    ProfileListResponse,
    ProfileSkillTag,
    parse_candidate_profile,
    parse_job_preferences,
)
from app.services.cv_upload import sanitize_original_name


class ProfileProjectionError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


def project_skill_tags(profile: CandidateProfile) -> tuple[list[ProfileSkillTag], int]:
    selected = [skill for skill in profile.skills if not skill.excluded]
    tags = [
        ProfileSkillTag(key=skill.skill.canonical_key, label=skill.skill.display_name)
        for skill in selected
    ]
    return tags[:12], len(tags)


def project_display_name(profile: CandidateProfile, original_name: str) -> str:
    if profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    return sanitize_original_name(original_name)


def _attachment(row: Attachment) -> AttachmentPublic:
    return AttachmentPublic(
        id=row.id,
        original_name=row.original_name,
        mime_type=cast("Literal['application/pdf']", ATTACHMENT_MIME_TYPE_PDF),
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        state=cast(AttachmentState, row.state),
        failure_code=row.failure_code,
    )


async def _validated(
    session: AsyncSession, row: Profile
) -> tuple[CandidateProfile, Any, Attachment]:
    try:
        profile = parse_candidate_profile(row.profile_json)
        prefs_row = await profiles_repo.get_profile_preferences(session, row.id)
        if prefs_row is None:
            raise ValueError("missing profile preferences")
        preferences = parse_job_preferences(prefs_row.preferences_json)
    except Exception as exc:
        raise ProfileProjectionError(
            "PROFILE_INCONSISTENT", "profile data is inconsistent"
        ) from exc
    attachment = await attachments_repo.get_by_id(session, row.attachment_id)
    if attachment is None:
        raise ProfileProjectionError(
            "PROFILE_INCONSISTENT", "profile attachment is missing"
        )
    return profile, preferences, attachment


async def project_profile_list_item(
    session: AsyncSession, row: Profile, active_id: str | None
) -> ProfileListItem:
    profile, _, attachment = await _validated(session, row)
    tags, count = project_skill_tags(profile)
    return ProfileListItem(
        id=row.id,
        display_name=row.display_name
        or project_display_name(profile, attachment.original_name),
        location=row.location or profile.location,
        state=row.state,
        active=row.id == active_id,
        attachment=_attachment(attachment),
        skill_tags=tags,
        skill_count=count,
        last_opened_at=row.last_opened_at,
    )


async def project_profile_detail(
    session: AsyncSession, row: Profile, active_id: str | None = None
) -> ProfileDetail:
    profile, preferences, attachment = await _validated(session, row)
    return ProfileDetail(
        id=row.id,
        display_name=row.display_name
        or project_display_name(profile, attachment.original_name),
        location=row.location or profile.location,
        state=row.state,
        active=row.id == active_id,
        profile=profile,
        preferences=preferences,
        attachment=_attachment(attachment),
    )


async def build_profile_list_response(session: AsyncSession) -> ProfileListResponse:
    active_id = await workspace_repo.get_active_profile_id(session)
    rows = await profiles_repo.list_profiles(session)
    return ProfileListResponse(
        items=[
            await project_profile_list_item(session, row, active_id) for row in rows
        ],
        active_profile_id=active_id,
    )


async def build_profile_detail(
    session: AsyncSession, *, profile_id: str
) -> ProfileDetail:
    row = await profiles_repo.get_profile(session, profile_id)
    if row is None:
        raise ProfileProjectionError("PROFILE_NOT_FOUND", "profile not found")
    active_id = await workspace_repo.get_active_profile_id(session)
    return await project_profile_detail(session, row, active_id)


__all__ = [
    "ProfileProjectionError",
    "build_profile_detail",
    "build_profile_list_response",
    "project_display_name",
    "project_profile_detail",
    "project_profile_list_item",
    "project_skill_tags",
]
