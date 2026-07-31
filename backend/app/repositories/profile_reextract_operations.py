"""Durable profile re-extraction operation persistence and CAS helpers."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import delete, exists, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.profiles import ProfileDraft, ProfileReextractOperation

_TERMINAL_STATES = ("interrupted", "failed", "stale")
_ACTIONABLE_STATES = ("running", "review_ready")
_TRANSITION_STATES = frozenset(_TERMINAL_STATES + ("review_ready",))
_ACTIONABLE_UNIQUE_MESSAGE = (
    "UNIQUE constraint failed: profile_reextract_operations.profile_id"
)
ProfileReextractOperationState = Literal[
    "running", "review_ready", "interrupted", "failed", "stale"
]
ProfileReextractTransitionState = Literal[
    "review_ready", "interrupted", "failed", "stale"
]


class ProfileReextractOperationRepositoryError(ValueError):
    """Raised when repository inputs violate the operation contract."""


class ProfileReextractOperationConflict(Exception):
    """A durable profile operation or review already owns the profile."""

    def __init__(self, code: str, operation_id: str | None = None) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ProfileReextractOperationRepositoryError(
                "conflict code must be a non-empty string"
            )
        if operation_id is not None:
            operation_id = _required_id("operation_id", operation_id)
        self.code = code.strip()
        self.operation_id = operation_id
        detail = self.code
        if operation_id is not None:
            detail = f"{detail}: {operation_id}"
        super().__init__(detail)


def _required_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileReextractOperationRepositoryError(
            f"{name} must be a non-empty string"
        )
    return value.strip()


def _validate_claim_inputs(
    *,
    profile_id: str,
    source_attachment_id: str,
    base_profile_updated_at: datetime,
    base_workspace_updated_at: datetime,
) -> tuple[str, str]:
    profile_id = _required_id("profile_id", profile_id)
    source_attachment_id = _required_id(
        "source_attachment_id", source_attachment_id
    )
    if not isinstance(base_profile_updated_at, datetime):
        raise ProfileReextractOperationRepositoryError(
            "base_profile_updated_at must be a datetime"
        )
    if not isinstance(base_workspace_updated_at, datetime):
        raise ProfileReextractOperationRepositoryError(
            "base_workspace_updated_at must be a datetime"
        )
    return profile_id, source_attachment_id


def _validate_expected_state(
    expected_state: ProfileReextractOperationState | None,
) -> ProfileReextractOperationState | None:
    if expected_state is not None and expected_state not in {
        "running",
        "review_ready",
        "interrupted",
        "failed",
        "stale",
    }:
        raise ProfileReextractOperationRepositoryError(
            "expected_state is not a valid profile re-extraction state"
        )
    return expected_state


async def get_operation(
    session: AsyncSession, *, profile_id: str, operation_id: str
) -> ProfileReextractOperation | None:
    profile_id = _required_id("profile_id", profile_id)
    operation_id = _required_id("operation_id", operation_id)
    result = await session.execute(
        select(ProfileReextractOperation).where(
            ProfileReextractOperation.profile_id == profile_id,
            ProfileReextractOperation.id == operation_id,
        )
    )
    return result.scalar_one_or_none()


async def get_latest_operation_for_profile(
    session: AsyncSession, profile_id: str
) -> ProfileReextractOperation | None:
    profile_id = _required_id("profile_id", profile_id)
    result = await session.execute(
        select(ProfileReextractOperation)
        .where(ProfileReextractOperation.profile_id == profile_id)
        .order_by(
            ProfileReextractOperation.updated_at.desc(),
            ProfileReextractOperation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_running_operations(
    session: AsyncSession, profile_id: str | None = None
) -> list[ProfileReextractOperation]:
    if profile_id is not None:
        profile_id = _required_id("profile_id", profile_id)
    statement = select(ProfileReextractOperation).where(
        ProfileReextractOperation.state == "running"
    )
    if profile_id is not None:
        statement = statement.where(ProfileReextractOperation.profile_id == profile_id)
    result = await session.execute(
        statement.order_by(
            ProfileReextractOperation.updated_at.desc(),
            ProfileReextractOperation.id.desc(),
        )
    )
    return list(result.scalars().all())


async def _get_owned_review_operation_id(
    session: AsyncSession, profile_id: str
) -> str | None:
    result = await session.execute(
        select(ProfileReextractOperation.id)
        .join(
            ProfileDraft,
            ProfileDraft.reextract_operation_id == ProfileReextractOperation.id,
        )
        .where(
            ProfileDraft.target_profile_id == profile_id,
            ProfileDraft.reextract_operation_id.is_not(None),
        )
        .order_by(
            ProfileReextractOperation.updated_at.desc(),
            ProfileReextractOperation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_actionable_operation_id(
    session: AsyncSession, profile_id: str
) -> str | None:
    result = await session.execute(
        select(ProfileReextractOperation.id)
        .where(
            ProfileReextractOperation.profile_id == profile_id,
            ProfileReextractOperation.state.in_(_ACTIONABLE_STATES),
        )
        .order_by(
            ProfileReextractOperation.updated_at.desc(),
            ProfileReextractOperation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def claim_operation(
    session: AsyncSession,
    *,
    profile_id: str,
    source_attachment_id: str,
    base_profile_updated_at: datetime,
    base_workspace_updated_at: datetime,
) -> ProfileReextractOperation:
    profile_id, source_attachment_id = _validate_claim_inputs(
        profile_id=profile_id,
        source_attachment_id=source_attachment_id,
        base_profile_updated_at=base_profile_updated_at,
        base_workspace_updated_at=base_workspace_updated_at,
    )

    owned_review_id = await _get_owned_review_operation_id(session, profile_id)
    if owned_review_id is not None:
        raise ProfileReextractOperationConflict(
            "PROFILE_REVIEW_PENDING", owned_review_id
        )
    actionable_id = await _get_actionable_operation_id(session, profile_id)
    if actionable_id is not None:
        raise ProfileReextractOperationConflict(
            "PROFILE_REEXTRACT_IN_PROGRESS", actionable_id
        )

    owned_draft = exists().where(
        ProfileDraft.reextract_operation_id == ProfileReextractOperation.id
    )
    await session.execute(
        delete(ProfileReextractOperation).where(
            ProfileReextractOperation.profile_id == profile_id,
            ProfileReextractOperation.state.in_(_TERMINAL_STATES),
            ~owned_draft,
        )
    )
    now = utc_now()
    operation = ProfileReextractOperation(
        id=new_uuid(),
        profile_id=profile_id,
        source_attachment_id=source_attachment_id,
        base_profile_updated_at=base_profile_updated_at,
        base_workspace_updated_at=base_workspace_updated_at,
        state="running",
        error_code=None,
        created_at=now,
        updated_at=now,
    )
    session.add(operation)
    try:
        await session.flush()
    except IntegrityError as exc:
        if is_actionable_operation_unique_conflict(exc):
            raise ProfileReextractOperationConflict(
                "PROFILE_REEXTRACT_IN_PROGRESS"
            ) from exc
        raise
    return operation


def is_actionable_operation_unique_conflict(exc: IntegrityError) -> bool:
    """Recognize only the SQLite partial profile actionable uniqueness error."""
    original = exc.orig
    if not isinstance(original, sqlite3.IntegrityError):
        return False
    if str(original).strip() != _ACTIONABLE_UNIQUE_MESSAGE:
        return False
    error_code = getattr(original, "sqlite_errorcode", None)
    return error_code in (None, sqlite3.SQLITE_CONSTRAINT_UNIQUE)


def _validate_transition(
    to_state: ProfileReextractTransitionState, error_code: str | None
) -> str | None:
    if to_state not in _TRANSITION_STATES:
        raise ProfileReextractOperationRepositoryError(
            "to_state is not a valid running-operation transition target"
        )
    if to_state == "review_ready":
        if error_code is not None:
            raise ProfileReextractOperationRepositoryError(
                "review_ready operations cannot have an error_code"
            )
        return None
    if not isinstance(error_code, str) or not error_code.strip():
        raise ProfileReextractOperationRepositoryError(
            "terminal operations require a non-empty error_code"
        )
    return error_code.strip()


async def transition_running_operation(
    session: AsyncSession,
    *,
    profile_id: str,
    operation_id: str,
    to_state: ProfileReextractTransitionState,
    error_code: str | None,
) -> bool:
    profile_id = _required_id("profile_id", profile_id)
    operation_id = _required_id("operation_id", operation_id)
    error_code = _validate_transition(to_state, error_code)
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(ProfileReextractOperation)
            .where(
                ProfileReextractOperation.profile_id == profile_id,
                ProfileReextractOperation.id == operation_id,
                ProfileReextractOperation.state == "running",
            )
            .values(state=to_state, error_code=error_code, updated_at=utc_now())
        ),
    )
    return int(result.rowcount or 0) == 1


async def delete_operation(
    session: AsyncSession,
    *,
    profile_id: str,
    operation_id: str,
    expected_state: ProfileReextractOperationState | None = None,
) -> bool:
    profile_id = _required_id("profile_id", profile_id)
    operation_id = _required_id("operation_id", operation_id)
    expected_state = _validate_expected_state(expected_state)
    predicates = [
        ProfileReextractOperation.profile_id == profile_id,
        ProfileReextractOperation.id == operation_id,
    ]
    if expected_state is not None:
        predicates.append(ProfileReextractOperation.state == expected_state)
    result = cast(
        CursorResult[Any],
        await session.execute(delete(ProfileReextractOperation).where(*predicates)),
    )
    return int(result.rowcount or 0) == 1
