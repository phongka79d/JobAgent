"""Safe, profile-row keyed projection for profile APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
    Attachment,
)
from app.db.models.profiles import PROFILE_SKILL_TAG_LIMIT, Profile
from app.repositories import attachments as attachments_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_documents_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.cv_document import parse_cv_document
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    ProfileAttachmentMetadata,
    ProfileAttachmentState,
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


_PROFILE_ATTACHMENT_STATES = frozenset(
    {
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_DELETING,
    }
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def project_skill_tags(profile: CandidateProfile) -> tuple[list[ProfileSkillTag], int]:
    selected = [skill for skill in profile.skills if not skill.excluded]
    tags = [
        ProfileSkillTag(key=skill.skill.canonical_key, label=skill.skill.display_name)
        for skill in selected
    ]
    return tags[:PROFILE_SKILL_TAG_LIMIT], len(tags)


def project_display_name(profile: CandidateProfile, original_name: str) -> str:
    if profile.full_name and profile.full_name.strip():
        return profile.full_name.strip()
    return sanitize_original_name(original_name)


def _attachment(row: Attachment) -> ProfileAttachmentMetadata:
    return ProfileAttachmentMetadata(
        id=row.id,
        original_name=sanitize_original_name(row.original_name),
        mime_type=cast("Literal['application/pdf']", ATTACHMENT_MIME_TYPE_PDF),
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        state=cast(ProfileAttachmentState, row.state),
        failure_code=row.failure_code,
    )


async def _validated(
    session: AsyncSession, row: Profile
) -> tuple[CandidateProfile, JobPreferences, Attachment]:
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
    document = await cv_documents_repo.get_document(session, row.attachment_id)
    try:
        if document is None:
            raise ValueError("missing profile document")
        parsed_document = parse_cv_document(document.document_json)
        if (
            attachment.state not in _PROFILE_ATTACHMENT_STATES
            or parsed_document.attachment_id != row.attachment_id
            or document.extraction_version != row.extraction_version
            or document.source_hash != row.source_hash
        ):
            raise ValueError("profile document ownership or revision mismatch")
    except Exception as exc:
        raise ProfileProjectionError(
            "PROFILE_INCONSISTENT", "profile data is inconsistent"
        ) from exc
    if row.location != profile.location:
        raise ProfileProjectionError(
            "PROFILE_INCONSISTENT", "profile location projection is inconsistent"
        )
    return profile, preferences, attachment


def _project_list_item(
    row: Profile,
    *,
    profile: CandidateProfile,
    attachment: Attachment,
    active_id: str | None,
) -> ProfileListItem:
    tags, count = project_skill_tags(profile)
    safe_filename = sanitize_original_name(attachment.original_name)
    return ProfileListItem(
        id=row.id,
        display_name=(
            row.display_name.strip()
            if row.display_name.strip()
            else project_display_name(profile, safe_filename)
        ),
        cv_filename=safe_filename,
        attachment_state=cast(ProfileAttachmentState, attachment.state),
        location=profile.location,
        skill_tags=tags,
        skill_count=count,
        extraction_version=row.extraction_version,
        source_hash=row.source_hash,
        state=cast("Literal['ready', 'deleting']", row.state),
        is_active=row.id == active_id,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        last_opened_at=_utc(row.last_opened_at),
    )


async def project_profile_list_item(
    session: AsyncSession, row: Profile, active_id: str | None
) -> ProfileListItem:
    profile, _, attachment = await _validated(session, row)
    return _project_list_item(
        row, profile=profile, attachment=attachment, active_id=active_id
    )


async def project_profile_detail(
    session: AsyncSession, row: Profile, active_id: str | None = None
) -> ProfileDetail:
    profile, preferences, attachment = await _validated(session, row)
    selected = await conversations_repo.most_recent_for_profile(
        session, profile_id=row.id
    )
    item = _project_list_item(
        row, profile=profile, attachment=attachment, active_id=active_id
    )
    return ProfileDetail(
        **item.model_dump(),
        profile=profile,
        preferences=preferences,
        attachment=_attachment(attachment),
        selected_conversation_id=selected.id if selected is not None else None,
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
