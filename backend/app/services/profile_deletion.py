"""Retryable, profile-scoped deletion coordinator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import delete_run_checkpoints, open_checkpointer
from app.db.models.profiles import PROFILE_STATE_DELETING, PROFILE_STATE_READY, Profile
from app.graph.delete_profile import delete_profile_branch
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.profile import ProfileDeleteResponse
from app.services.activity_gate import ActivityBlockedError, assert_profile_idle
from app.services.profile_projection import (
    build_profile_list_response,
)
from app.storage.attachments import AttachmentStorage


class ProfileDeletionError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


async def delete_profile(
    *,
    profile_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    graph_driver: Any | None,
    sqlite_path: str | Path,
) -> ProfileDeleteResponse:
    async with session_factory() as session:
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise ProfileDeletionError("PROFILE_NOT_FOUND", "profile not found")
        try:
            await assert_profile_idle(
                session, profile_id=profile_id, code="PROFILE_DELETE_BLOCKED"
            )
        except ActivityBlockedError as exc:
            raise ProfileDeletionError(exc.code, exc.summary) from exc
        run_ids = await runs_repo.list_run_ids_for_profile(session, profile_id)
        attachment_id = profile.attachment_id
        attachment = await att_repo.get_by_id(session, attachment_id)
        if attachment is None:
            raise ProfileDeletionError(
                "PROFILE_INCONSISTENT", "profile attachment is missing"
            )
        profile.state = PROFILE_STATE_DELETING
        attachment.state = "deleting"
        attachment.failure_code = None
        attachment.page_count = None
        await session.flush()
        await session.commit()

    try:
        async with open_checkpointer(sqlite_path) as saver:
            await delete_run_checkpoints(saver, run_ids)
        # A retry may observe a file already removed by a prior attempt; the
        # retained-file phase is intentionally idempotent.
        if storage.exists(attachment.storage_path):
            storage.delete(attachment.storage_path)
        if graph_driver is not None:
            await delete_profile_branch(graph_driver, profile_id)
    except Exception as exc:
        raise ProfileDeletionError(
            "PROFILE_DELETE_RETRYABLE",
            "profile cleanup is incomplete; restore dependencies and retry",
        ) from exc

    async with session_factory() as session:
        row = await profiles_repo.get_profile(session, profile_id)
        if row is None:
            raise ProfileDeletionError("PROFILE_NOT_FOUND", "profile not found")
        active_id = await workspace_repo.get_active_profile_id(session)
        await session.delete(row)
        await session.flush()
        await att_repo.delete(session, attachment_id)
        if active_id == profile_id:
            fallback = (
                await session.execute(
                    select(Profile)
                    .where(Profile.state == PROFILE_STATE_READY)
                    .order_by(Profile.last_opened_at.desc(), Profile.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            await workspace_repo.set_active_profile_id(
                session, fallback.id if fallback is not None else None
            )
        await session.commit()

    async with session_factory() as session:
        listing = await build_profile_list_response(session)
        active_item = next(
            (item for item in listing.items if item.id == listing.active_profile_id),
            None,
        )
        selected = None
        if active_item is not None:
            selected_row = await profiles_repo.get_profile(session, active_item.id)
            if selected_row is not None:
                from app.repositories import conversations as conversations_repo
                from app.services.conversations import project_conversation

                conversation = await conversations_repo.most_recent_for_profile(
                    session, profile_id=selected_row.id
                )
                if conversation is not None:
                    selected = project_conversation(conversation, selected=True)
    return ProfileDeleteResponse(
        deleted_profile_id=profile_id,
        active_profile=active_item,
        selected_conversation=selected,
    )


__all__ = ["ProfileDeletionError", "delete_profile"]
