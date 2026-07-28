"""Flush-only tailoring session/version persistence with atomic version CAS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.cv_tailoring import CVTailoringSession, CVTailoringVersion
from app.schemas.cv_tailoring import (
    TAILORING_CREATED_BY_VALUES,
    TAILORING_SESSION_STATE_DELETING,
    TAILORING_SESSION_STATE_FAILED,
    TAILORING_SESSION_STATE_GENERATING,
    TAILORING_SESSION_STATE_READY,
)


class CVTailoringRepositoryError(Exception):
    """Base tailoring persistence invariant error."""


class TailoringParentConflict(CVTailoringRepositoryError):
    """Raised when the expected latest parent no longer owns the session head."""


@dataclass(frozen=True, slots=True)
class CVTailoringVersionWrite:
    id: str
    parent_version_id: str | None
    created_by: str
    content_json: dict[str, Any]
    provenance_json: dict[str, Any]
    source_revision_json: dict[str, Any]
    tex_relative_path: str
    pdf_relative_path: str
    tex_sha256: str
    pdf_sha256: str
    page_count: int
    page_warning: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.page_count, int)
            or isinstance(self.page_count, bool)
            or self.page_count <= 0
        ):
            raise ValueError("page_count must be a positive integer")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.created_by not in TAILORING_CREATED_BY_VALUES:
            raise ValueError("created_by is not an approved tailoring owner")


async def create_session(
    session: AsyncSession,
    *,
    profile_id: str,
    source_attachment_id: str,
    source_hash: str,
    profile_updated_at: datetime,
    job_id: str | None,
    job_updated_at: datetime | None,
    job_label_json: dict[str, Any] | None,
    instruction: str,
    template_version: str,
) -> CVTailoringSession:
    row = CVTailoringSession(
        profile_id=profile_id,
        source_attachment_id=source_attachment_id,
        source_hash=source_hash,
        profile_updated_at=profile_updated_at,
        job_id=job_id,
        job_updated_at=job_updated_at,
        job_label_json=job_label_json,
        instruction=instruction,
        template_version=template_version,
        state=TAILORING_SESSION_STATE_GENERATING,
        latest_version_number=0,
        error_code=None,
    )
    session.add(row)
    await session.flush()
    return row


async def get_session(
    session: AsyncSession, session_id: str
) -> CVTailoringSession | None:
    return await session.get(CVTailoringSession, session_id)


async def list_sessions_for_profile(
    session: AsyncSession, profile_id: str
) -> list[CVTailoringSession]:
    result = await session.execute(
        select(CVTailoringSession)
        .where(CVTailoringSession.profile_id == profile_id)
        .order_by(CVTailoringSession.updated_at.desc(), CVTailoringSession.id.desc())
    )
    return list(result.scalars().all())


async def list_versions(
    session: AsyncSession, session_id: str
) -> list[CVTailoringVersion]:
    result = await session.execute(
        select(CVTailoringVersion)
        .where(CVTailoringVersion.session_id == session_id)
        .order_by(CVTailoringVersion.version_number)
    )
    return list(result.scalars().all())


async def get_version(
    session: AsyncSession, version_id: str
) -> CVTailoringVersion | None:
    return await session.get(CVTailoringVersion, version_id)


async def get_latest_version(
    session: AsyncSession, session_id: str
) -> CVTailoringVersion | None:
    result = await session.execute(
        select(CVTailoringVersion)
        .where(CVTailoringVersion.session_id == session_id)
        .order_by(CVTailoringVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_version_cas(
    session: AsyncSession,
    *,
    session_id: str,
    expected_latest_version_number: int,
    expected_parent_version_id: str | None,
    version: CVTailoringVersionWrite,
) -> CVTailoringVersion:
    owner = await session.get(CVTailoringSession, session_id)
    if (
        owner is None
        or owner.latest_version_number != expected_latest_version_number
    ):
        raise TailoringParentConflict("tailoring session head changed")
    if version.parent_version_id != expected_parent_version_id:
        raise TailoringParentConflict("version parent does not match expected parent")
    if expected_latest_version_number == 0:
        if expected_parent_version_id is not None:
            raise TailoringParentConflict("first version cannot have a parent")
    else:
        parent = await session.get(CVTailoringVersion, expected_parent_version_id)
        if (
            parent is None
            or parent.session_id != session_id
            or parent.version_number != expected_latest_version_number
        ):
            raise TailoringParentConflict("expected parent is not the session head")

    new_version_number = expected_latest_version_number + 1
    row = CVTailoringVersion(
        id=version.id,
        session_id=session_id,
        version_number=new_version_number,
        parent_version_id=version.parent_version_id,
        created_by=version.created_by,
        content_json=version.content_json,
        provenance_json=version.provenance_json,
        source_revision_json=version.source_revision_json,
        tex_relative_path=version.tex_relative_path,
        pdf_relative_path=version.pdf_relative_path,
        tex_sha256=version.tex_sha256,
        pdf_sha256=version.pdf_sha256,
        page_count=version.page_count,
        page_warning=version.page_warning,
        created_at=version.created_at,
    )
    session.add(row)
    await session.flush()
    result = await session.execute(
        update(CVTailoringSession)
        .where(
            CVTailoringSession.id == session_id,
            CVTailoringSession.latest_version_number
            == expected_latest_version_number,
        )
        .values(
            latest_version_number=new_version_number,
            state=TAILORING_SESSION_STATE_READY,
            error_code=None,
            updated_at=utc_now(),
        )
    )
    if not isinstance(result, CursorResult) or result.rowcount != 1:
        raise TailoringParentConflict("tailoring session head changed")
    await session.flush()
    return row


async def mark_session_failed(
    session: AsyncSession, session_id: str, *, error_code: str
) -> CVTailoringSession:
    row = await session.get(CVTailoringSession, session_id)
    if row is None:
        raise CVTailoringRepositoryError("tailoring session not found")
    row.state = TAILORING_SESSION_STATE_FAILED
    row.error_code = error_code
    row.updated_at = utc_now()
    await session.flush()
    return row


async def mark_session_generating(
    session: AsyncSession, session_id: str, *, touch_updated_at: bool = True
) -> CVTailoringSession:
    row = await session.get(CVTailoringSession, session_id)
    if row is None:
        raise CVTailoringRepositoryError("tailoring session not found")
    if row.state not in {
        TAILORING_SESSION_STATE_READY,
        TAILORING_SESSION_STATE_FAILED,
    }:
        raise CVTailoringRepositoryError("tailoring session cannot start generation")
    row.state = TAILORING_SESSION_STATE_GENERATING
    row.error_code = None
    if touch_updated_at:
        row.updated_at = utc_now()
    await session.flush()
    return row


async def complete_no_change(
    session: AsyncSession,
    session_id: str,
    expected_latest_version_number: int,
) -> CVTailoringSession:
    row = await session.get(CVTailoringSession, session_id)
    if row is None:
        raise CVTailoringRepositoryError("tailoring session not found")
    if row.latest_version_number != expected_latest_version_number:
        raise TailoringParentConflict("tailoring session head changed")
    row.state = TAILORING_SESSION_STATE_READY
    row.error_code = None
    await session.flush()
    return row


async def restore_session_ready(
    session: AsyncSession, session_id: str
) -> CVTailoringSession:
    row = await session.get(CVTailoringSession, session_id)
    if row is None:
        raise CVTailoringRepositoryError("tailoring session not found")
    if row.latest_version_number <= 0:
        raise CVTailoringRepositoryError("zero-version session cannot be ready")
    row.state = TAILORING_SESSION_STATE_READY
    row.error_code = None
    row.updated_at = utc_now()
    await session.flush()
    return row


async def mark_session_deleting(
    session: AsyncSession, session_id: str
) -> CVTailoringSession:
    row = await session.get(CVTailoringSession, session_id)
    if row is None:
        raise CVTailoringRepositoryError("tailoring session not found")
    row.state = TAILORING_SESSION_STATE_DELETING
    row.error_code = None
    row.updated_at = utc_now()
    await session.flush()
    return row


async def delete_session(session: AsyncSession, session_id: str) -> bool:
    result = await session.execute(
        delete(CVTailoringSession).where(CVTailoringSession.id == session_id)
    )
    await session.flush()
    return bool(isinstance(result, CursorResult) and result.rowcount == 1)


__all__ = [
    "CVTailoringRepositoryError",
    "CVTailoringVersionWrite",
    "TailoringParentConflict",
    "create_session",
    "create_version_cas",
    "complete_no_change",
    "delete_session",
    "get_session",
    "get_latest_version",
    "get_version",
    "list_sessions_for_profile",
    "list_versions",
    "mark_session_deleting",
    "mark_session_failed",
    "mark_session_generating",
    "restore_session_ready",
]
