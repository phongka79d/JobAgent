'''Server-owned CV Manager list projection and action policy.'''

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypeGuard

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DELETING,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
)
from app.db.models.profiles import (
    PROFILE_STATE_DELETING,
    PROFILE_STATE_PENDING,
    PROFILE_STATE_READY,
    Profile,
)
from app.repositories import attachments as attachment_repo
from app.repositories import profiles as profile_repo
from app.schemas.cv_manager import (
    CvManagerAction,
    CvManagerItem,
    CvManagerListResponse,
)
from app.storage.attachments import AttachmentStorage, PathEscapeError

AttachmentState = Literal['staged', 'active', 'archived', 'failed', 'deleting']
ProfileState = Literal['pending', 'ready', 'deleting']


def _is_attachment_state(value: str) -> TypeGuard[AttachmentState]:
    return value in {
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
        ATTACHMENT_STATE_DELETING,
    }


def _attachment_state(value: str) -> AttachmentState:
    if not _is_attachment_state(value):
        raise ValueError(f'unknown attachment state: {value!r}')
    return value


def _is_profile_state(value: str) -> TypeGuard[ProfileState]:
    return value in {
        PROFILE_STATE_PENDING,
        PROFILE_STATE_READY,
        PROFILE_STATE_DELETING,
    }


def _profile_state(value: str) -> ProfileState:
    if not _is_profile_state(value):
        raise ValueError(f'unknown profile state: {value!r}')
    return value


def allowed_actions(
    *,
    state: str,
    owner: Profile | None,
    is_active: bool,
    file_available: bool,
) -> list[CvManagerAction]:
    '''Return the exact server-owned action ordering for one attachment.'''
    if owner is None:
        return ['delete_cv'] if state in {'staged', 'failed', 'deleting'} else []
    if owner.state == 'pending':
        return ['retry_upload'] if state in {'staged', 'failed'} else []
    if owner.state != 'ready':
        return []
    if state not in {'active', 'archived'}:
        return []
    actions: list[CvManagerAction] = []
    if file_available:
        actions.extend(['preview', 'download'])
    if state == 'archived' and not is_active:
        actions.append('activate_profile')
    actions.append('reextract')
    return actions


def _file_available(storage: AttachmentStorage, storage_path: str) -> bool:
    try:
        return storage.exists(storage_path)
    except (OSError, PathEscapeError, ValueError):
        return False


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def build_cv_manager_list(
    session: AsyncSession,
    *,
    storage: AttachmentStorage,
) -> CvManagerListResponse:
    '''Project every attachment without exposing internal storage metadata.'''
    rows = await attachment_repo.list_all(session)
    active_profile = await profile_repo.get_active_profile(session)
    items: list[CvManagerItem] = []
    for row in rows:
        owner = await profile_repo.get_profile_by_attachment_id(session, row.id)
        attachment_state = _attachment_state(row.state)
        profile_state = _profile_state(owner.state) if owner is not None else None
        file_available = _file_available(storage, row.storage_path)
        is_active = owner is not None and (
            active_profile is not None and owner.id == active_profile.id
        )
        items.append(
            CvManagerItem(
                id=row.id,
                original_name=row.original_name,
                state=attachment_state,
                failure_code=row.failure_code,
                page_count=row.page_count,
                file_available=file_available,
                profile_id=owner.id if owner is not None else None,
                profile_display_name=(
                    owner.display_name if owner is not None else None
                ),
                profile_state=profile_state,
                is_active_profile=is_active,
                allowed_actions=allowed_actions(
                    state=attachment_state,
                    owner=owner,
                    is_active=is_active,
                    file_available=file_available,
                ),
                created_at=_aware_utc(row.created_at),
                updated_at=_aware_utc(row.updated_at),
            )
        )
    return CvManagerListResponse(items=items)


__all__ = ['allowed_actions', 'build_cv_manager_list']
