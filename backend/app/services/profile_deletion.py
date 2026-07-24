"""Retryable, profile-scoped deletion coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import delete_run_checkpoints, open_checkpointer
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
from app.db.session import session_scope
from app.graph.delete_profile import delete_profile_branch
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.profile import ProfileDeleteResponse
from app.services.activity_gate import ActivityBlockedError, assert_profile_idle
from app.services.conversations import project_conversation
from app.services.profile_activation import (
    ActivationError,
    activate_selected_attachment,
)
from app.services.profile_projection import build_profile_list_response
from app.storage.attachments import AttachmentStorage


class ProfileDeletionError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


@dataclass(frozen=True, slots=True)
class _DeleteInputs:
    attachment_id: str
    storage_path: str
    run_ids: list[str]
    approved_shape: bool


def _approved_shape(profile: Profile) -> bool:
    return (
        profile.profile_json is not None
        and profile.extraction_version is not None
        and profile.source_hash is not None
    )


def _incomplete_shape(profile: Profile) -> bool:
    return (
        profile.profile_json is None
        and profile.location is None
        and profile.extraction_version is None
        and profile.source_hash is None
    )


def _inconsistent() -> ProfileDeletionError:
    return ProfileDeletionError(
        "PROFILE_INCONSISTENT", "profile deletion data is inconsistent"
    )


async def _mark_for_deletion(
    session: AsyncSession, profile_id: str
) -> _DeleteInputs:
    profile = await profiles_repo.get_profile(session, profile_id)
    if profile is None:
        raise ProfileDeletionError("PROFILE_NOT_FOUND", "profile not found")
    try:
        await assert_profile_idle(
            session, profile_id=profile_id, code="PROFILE_DELETE_BLOCKED"
        )
    except ActivityBlockedError as exc:
        raise ProfileDeletionError(exc.code, exc.summary) from exc

    approved = _approved_shape(profile)
    incomplete = _incomplete_shape(profile)
    if approved == incomplete:
        raise _inconsistent()
    attachment = await att_repo.get_by_id(session, profile.attachment_id)
    if attachment is None:
        raise _inconsistent()

    if profile.state == PROFILE_STATE_DELETING:
        if attachment.state != ATTACHMENT_STATE_DELETING:
            raise _inconsistent()
    else:
        expected_profile_state = (
            PROFILE_STATE_READY if approved else PROFILE_STATE_PENDING
        )
        allowed_attachment_states = (
            {ATTACHMENT_STATE_ACTIVE, ATTACHMENT_STATE_ARCHIVED}
            if approved
            else {ATTACHMENT_STATE_STAGED, ATTACHMENT_STATE_FAILED}
        )
        if (
            profile.state != expected_profile_state
            or attachment.state not in allowed_attachment_states
        ):
            raise _inconsistent()
        profile.state = PROFILE_STATE_DELETING
        attachment.state = ATTACHMENT_STATE_DELETING
        attachment.failure_code = None
        await session.flush()

    return _DeleteInputs(
        attachment_id=attachment.id,
        storage_path=attachment.storage_path,
        run_ids=await runs_repo.list_run_ids_for_profile(session, profile_id),
        approved_shape=approved,
    )


async def _external_cleanup(
    *,
    profile_id: str,
    inputs: _DeleteInputs,
    sqlite_path: str | Path,
    storage: AttachmentStorage,
    graph_driver: Any | None,
) -> None:
    try:
        async with open_checkpointer(sqlite_path) as saver:
            await delete_run_checkpoints(saver, inputs.run_ids)
        if not storage.delete(inputs.storage_path):
            raise OSError("retained file remains")
        if inputs.approved_shape:
            if graph_driver is None:
                raise RuntimeError("profile graph driver unavailable")
            await delete_profile_branch(graph_driver, profile_id)
    except Exception as exc:
        raise ProfileDeletionError(
            "PROFILE_DELETE_RETRYABLE",
            "profile cleanup is incomplete; restore dependencies and retry",
        ) from exc


async def _normalize_fallback(
    session: AsyncSession, *, deleted_profile_id: str
) -> Profile | None:
    remaining = list(
        (
            await session.execute(
                select(Profile)
                .where(
                    Profile.state == PROFILE_STATE_READY,
                    Profile.id != deleted_profile_id,
                )
                .order_by(
                    Profile.last_opened_at.desc(),
                    Profile.updated_at.desc(),
                    Profile.id.desc(),
                )
            )
        ).scalars()
    )
    fallback = remaining[0] if remaining else None

    for profile in remaining[1:]:
        attachment = await att_repo.get_by_id(session, profile.attachment_id)
        if attachment is None:
            raise _inconsistent()
        if attachment.state == ATTACHMENT_STATE_ACTIVE:
            await att_repo.mark_archived(session, attachment.id)
        elif attachment.state != ATTACHMENT_STATE_ARCHIVED:
            raise _inconsistent()

    if fallback is not None:
        try:
            await activate_selected_attachment(
                session,
                attachment_id=fallback.attachment_id,
                old_attachment_id=None,
            )
        except ActivationError as exc:
            raise _inconsistent() from exc
    await workspace_repo.set_active_profile_id(
        session, fallback.id if fallback is not None else None
    )
    return fallback


async def _finalize(
    *,
    profile_id: str,
    attachment_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> ProfileDeleteResponse:
    try:
        async with session_scope(session_factory) as session:
            profile = await profiles_repo.get_profile(session, profile_id)
            attachment = await att_repo.get_by_id(session, attachment_id)
            if profile is None or attachment is None:
                raise _inconsistent()
            if (
                profile.state != PROFILE_STATE_DELETING
                or attachment.state != ATTACHMENT_STATE_DELETING
            ):
                raise _inconsistent()

            fallback = await _normalize_fallback(
                session, deleted_profile_id=profile_id
            )
            await session.delete(profile)
            await session.flush()
            await att_repo.delete(session, attachment_id)

            listing = await build_profile_list_response(session)
            active_item = next(
                (
                    item
                    for item in listing.items
                    if item.id == listing.active_profile_id
                ),
                None,
            )
            selected = None
            if fallback is not None:
                conversation = await conversations_repo.most_recent_for_profile(
                    session, profile_id=fallback.id
                )
                if conversation is not None:
                    selected = project_conversation(conversation, selected=True)
            return ProfileDeleteResponse(
                deleted_profile_id=profile_id,
                active_profile=active_item,
                selected_conversation=selected,
            )
    except ProfileDeletionError:
        raise
    except Exception as exc:
        raise ProfileDeletionError(
            "PROFILE_DELETE_RETRYABLE",
            "profile cleanup is incomplete; restore dependencies and retry",
        ) from exc


async def delete_profile(
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    graph_driver: Any | None,
    sqlite_path: str | Path,
) -> ProfileDeleteResponse:
    async with session_scope(session_factory) as session:
        inputs = await _mark_for_deletion(session, profile_id)

    await _external_cleanup(
        profile_id=profile_id,
        inputs=inputs,
        sqlite_path=sqlite_path,
        storage=storage,
        graph_driver=graph_driver,
    )
    return await _finalize(
        profile_id=profile_id,
        attachment_id=inputs.attachment_id,
        session_factory=session_factory,
    )


__all__ = ["ProfileDeletionError", "delete_profile"]
