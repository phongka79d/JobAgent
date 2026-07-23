"""Flush-only profile, draft, and preference repository primitives."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.profiles import (
    PROFILE_STATE_READY,
    WORKSPACE_STATE_ID,
    Profile,
    ProfileDraft,
    ProfilePreference,
    WorkspaceState,
)
from app.repositories import workspace_state as workspace_repo


class ProfileRepositoryError(Exception):
    """Profile repository invariant violation."""


def _required(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileRepositoryError(f"{name} must be a non-empty string")
    return value.strip()


async def get_profile(session: AsyncSession, profile_id: str) -> Profile | None:
    return await session.get(Profile, _required("profile_id", profile_id))


async def list_profiles(session: AsyncSession) -> list[Profile]:
    result = await session.execute(
        select(Profile).order_by(
            Profile.last_opened_at.desc(),
            Profile.updated_at.desc(),
            Profile.id.desc(),
        )
    )
    return list(result.scalars().all())


async def create_profile(
    session: AsyncSession,
    *,
    attachment_id: str,
    display_name: str,
    profile_json: dict[str, Any],
    location: str | None,
    extraction_version: str,
    source_hash: str,
) -> Profile:
    attachment_id = _required("attachment_id", attachment_id)
    display_name = _required("display_name", display_name)
    extraction_version = _required("extraction_version", extraction_version)
    source_hash = _required("source_hash", source_hash)
    if not isinstance(profile_json, dict):
        raise ProfileRepositoryError("profile_json must be a mapping")
    now = utc_now()
    row = Profile(
        id=new_uuid(),
        attachment_id=attachment_id,
        display_name=display_name,
        profile_json=profile_json,
        location=location,
        extraction_version=extraction_version,
        source_hash=source_hash,
        state=PROFILE_STATE_READY,
        created_at=now,
        updated_at=now,
        last_opened_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def update_display_name(
    session: AsyncSession, *, profile_id: str, display_name: str
) -> Profile:
    row = await get_profile(session, profile_id)
    if row is None:
        raise ProfileRepositoryError("profile not found")
    row.display_name = _required("display_name", display_name)
    row.updated_at = utc_now()
    await session.flush()
    return row


async def get_profile_preferences(
    session: AsyncSession, profile_id: str
) -> ProfilePreference | None:
    return await session.get(
        ProfilePreference, _required("profile_id", profile_id)
    )


async def upsert_profile_preferences(
    session: AsyncSession,
    *,
    profile_id: str,
    preferences_json: dict[str, Any],
) -> ProfilePreference:
    profile_id = _required("profile_id", profile_id)
    if not isinstance(preferences_json, dict):
        raise ProfileRepositoryError("preferences_json must be a mapping")
    now = utc_now()
    row = await session.get(ProfilePreference, profile_id)
    if row is None:
        row = ProfilePreference(
            profile_id=profile_id,
            preferences_json=preferences_json,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.preferences_json = preferences_json
        row.updated_at = now
    await session.flush()
    return row


# Transitional read/write adapters for services migrated in Task 5. They use
# workspace ownership and never restore singleton table semantics.
async def get_active_profile(session: AsyncSession) -> Profile | None:
    state = await session.get(WorkspaceState, WORKSPACE_STATE_ID)
    if state is None or state.active_profile_id is None:
        return None
    return await session.get(Profile, state.active_profile_id)


async def get_current_draft(session: AsyncSession) -> ProfileDraft | None:
    result = await session.execute(
        select(ProfileDraft)
        .order_by(ProfileDraft.updated_at.desc(), ProfileDraft.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_current_draft(
    session: AsyncSession,
    *,
    draft_json: dict[str, Any],
    source_attachment_id: str | None = None,
) -> ProfileDraft:
    if not isinstance(draft_json, dict):
        raise ProfileRepositoryError("draft_json must be a mapping")
    row = await get_current_draft(session)
    now = utc_now()
    if row is None:
        row = ProfileDraft(
            id=new_uuid(),
            source_attachment_id=source_attachment_id,
            target_profile_id=None,
            draft_json=draft_json,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.source_attachment_id = source_attachment_id
        row.draft_json = draft_json
        row.updated_at = now
    await session.flush()
    return row


async def delete_current_draft(session: AsyncSession) -> bool:
    row = await get_current_draft(session)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_job_preferences(
    session: AsyncSession,
) -> ProfilePreference | None:
    profile = await get_active_profile(session)
    if profile is None:
        return None
    return await get_profile_preferences(session, profile.id)


async def upsert_job_preferences(
    session: AsyncSession, *, preferences_json: dict[str, Any]
) -> ProfilePreference:
    profile = await get_active_profile(session)
    if profile is None:
        raise ProfileRepositoryError("no active profile")
    return await upsert_profile_preferences(
        session,
        profile_id=profile.id,
        preferences_json=preferences_json,
    )


async def upsert_active_profile(
    session: AsyncSession,
    *,
    active_attachment_id: str,
    profile_json: dict[str, Any],
) -> Profile:
    profile = await get_active_profile(session)
    if profile is None:
        # ponytail: compatibility callers still model first approval through
        # the old upsert name; create the durable profile row instead.
        profile = await create_profile(
            session,
            attachment_id=active_attachment_id,
            display_name="Candidate profile",
            profile_json=profile_json,
            location=None,
            extraction_version="legacy-compat",
            source_hash=f"legacy:{active_attachment_id}",
        )
        await workspace_repo.set_active_profile_id(session, profile.id)
        return profile
    profile.attachment_id = _required("active_attachment_id", active_attachment_id)
    profile.profile_json = profile_json
    profile.updated_at = utc_now()
    await session.flush()
    return profile
