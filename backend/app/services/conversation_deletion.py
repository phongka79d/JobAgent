"""Checkpoint-safe permanent conversation deletion."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import delete_run_checkpoints, open_checkpointer
from app.db.models.profiles import PROFILE_STATE_READY
from app.repositories import agent_runs as runs_repo
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.schemas.chat import ConversationDeleteResponse
from app.services.activity_gate import ActivityBlockedError, assert_conversation_idle
from app.services.conversations import project_conversation


class ConversationDeletionError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


async def delete_conversation(
    *,
    conversation_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    sqlite_path: str | Path,
) -> ConversationDeleteResponse:
    async with session_factory() as session:
        owner = await conversations_repo.get_owned(
            session, conversation_id=conversation_id
        )
        if owner is None:
            raise ConversationDeletionError(
                "CONVERSATION_NOT_FOUND", "conversation not found"
            )
        profile = await profiles_repo.get_profile(session, owner.profile_id)
        if profile is None or profile.state != PROFILE_STATE_READY:
            raise ConversationDeletionError(
                "PROFILE_NOT_READY", "profile is not ready"
            )
        try:
            await assert_conversation_idle(
                session,
                conversation_id=conversation_id,
                code="CONVERSATION_DELETE_BLOCKED",
            )
        except ActivityBlockedError as exc:
            raise ConversationDeletionError(exc.code, exc.summary) from exc
        run_ids = await runs_repo.list_run_ids_for_conversation(
            session, conversation_id
        )
        profile_id = owner.profile_id

    try:
        async with open_checkpointer(sqlite_path) as saver:
            await delete_run_checkpoints(saver, run_ids)
    except Exception as exc:
        raise ConversationDeletionError(
            "CONVERSATION_DELETE_CHECKPOINT_FAILED",
            "conversation checkpoints could not be removed; retry the deletion",
        ) from exc

    async with session_factory() as session:
        selected, was_last = await conversations_repo.delete_and_select(
            session,
            profile_id=profile_id,
            conversation_id=conversation_id,
        )
        await session.commit()
    return ConversationDeleteResponse(
        deleted_conversation_id=conversation_id,
        selected_conversation=project_conversation(selected, selected=True),
        replacement_conversation_id=selected.id if was_last else None,
    )


__all__ = ["ConversationDeletionError", "delete_conversation"]
