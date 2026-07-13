"""Singleton candidate-profile, draft, and job-preferences repository primitives.

Owns focused reads/upserts/deletes for ``candidate_profile``,
``profile_drafts``, and ``job_preferences`` using the fixed singleton IDs
``active`` / ``current`` / ``active``. JSON document shape is not validated
here — services must validate Pydantic contracts before calling writers.
Callers own the async session and commit; this module never opens a session,
commits/rolls back, or touches providers, filesystem, or Neo4j.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.profiles import (
    CANDIDATE_PROFILE_ID,
    JOB_PREFERENCES_ID,
    PROFILE_DRAFT_ID,
    CandidateProfile,
    JobPreferences,
    ProfileDraft,
)


class ProfileRepositoryError(Exception):
    """Base error for profile-family repository invariant violations."""


class ProfileNotFoundError(ProfileRepositoryError):
    """Raised when a required singleton row is missing for a hard update."""


async def get_active_profile(
    session: AsyncSession,
) -> CandidateProfile | None:
    """Return ``candidate_profile('active')``, or ``None`` if not created yet."""
    return await session.get(CandidateProfile, CANDIDATE_PROFILE_ID)


async def upsert_active_profile(
    session: AsyncSession,
    *,
    active_attachment_id: str,
    profile_json: dict[str, Any],
) -> CandidateProfile:
    """Insert or update the singleton approved profile row.

    Always uses :data:`CANDIDATE_PROFILE_ID`. Does not validate *profile_json*
    shape or attachment state cross-row invariants. Does not finalize the
    caller's unit of work.
    """
    if not isinstance(active_attachment_id, str) or active_attachment_id.strip() == "":
        raise ProfileRepositoryError(
            "active_attachment_id must be a non-empty string"
        )
    if not isinstance(profile_json, dict):
        raise ProfileRepositoryError("profile_json must be a mapping")

    now = utc_now()
    row = await session.get(CandidateProfile, CANDIDATE_PROFILE_ID)
    if row is None:
        row = CandidateProfile(
            id=CANDIDATE_PROFILE_ID,
            active_attachment_id=active_attachment_id,
            profile_json=profile_json,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.active_attachment_id = active_attachment_id
        row.profile_json = profile_json
        row.updated_at = now
    await session.flush()
    return row


async def get_current_draft(session: AsyncSession) -> ProfileDraft | None:
    """Return ``profile_drafts('current')``, or ``None`` if no draft exists."""
    return await session.get(ProfileDraft, PROFILE_DRAFT_ID)


async def upsert_current_draft(
    session: AsyncSession,
    *,
    draft_json: dict[str, Any],
    source_attachment_id: str | None = None,
) -> ProfileDraft:
    """Insert or update the singleton draft row.

    Always uses :data:`PROFILE_DRAFT_ID`. *source_attachment_id* may be
    ``None`` for profile/preference-only updates. Does not validate
    *draft_json* shape. Does not finalize the caller's unit of work.
    """
    if not isinstance(draft_json, dict):
        raise ProfileRepositoryError("draft_json must be a mapping")
    if source_attachment_id is not None and (
        not isinstance(source_attachment_id, str)
        or source_attachment_id.strip() == ""
    ):
        raise ProfileRepositoryError(
            "source_attachment_id must be a non-empty string when set"
        )

    now = utc_now()
    row = await session.get(ProfileDraft, PROFILE_DRAFT_ID)
    if row is None:
        row = ProfileDraft(
            id=PROFILE_DRAFT_ID,
            source_attachment_id=source_attachment_id,
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
    """Delete ``profile_drafts('current')`` if present.

    Returns ``True`` when a row was deleted, ``False`` when already absent.
    Does not finalize the caller's unit of work.
    """
    row = await session.get(ProfileDraft, PROFILE_DRAFT_ID)
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_job_preferences(
    session: AsyncSession,
) -> JobPreferences | None:
    """Return ``job_preferences('active')``, or ``None`` if missing.

    After seed the row always exists; ``None`` is for incomplete environments.
    """
    return await session.get(JobPreferences, JOB_PREFERENCES_ID)


async def upsert_job_preferences(
    session: AsyncSession,
    *,
    preferences_json: dict[str, Any],
) -> JobPreferences:
    """Insert or update the singleton job-preferences row.

    Always uses :data:`JOB_PREFERENCES_ID`. Does not validate
    *preferences_json* shape. Does not finalize the caller's unit of work.
    """
    if not isinstance(preferences_json, dict):
        raise ProfileRepositoryError("preferences_json must be a mapping")

    now = utc_now()
    row = await session.get(JobPreferences, JOB_PREFERENCES_ID)
    if row is None:
        row = JobPreferences(
            id=JOB_PREFERENCES_ID,
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
