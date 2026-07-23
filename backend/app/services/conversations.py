"""Conversation ownership, selection, and safe response projection."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time import utc_now
from app.db.models.chat import Conversation
from app.db.models.profiles import NEW_CONVERSATION_TITLE, PROFILE_STATE_READY
from app.db.session import session_scope
from app.repositories import conversations as conversations_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.repositories.conversations import ConversationListPage
from app.schemas.chat import (
    ConversationListResponse,
    ConversationMutationResponse,
    ConversationSummary,
)
from app.services.activity_gate import ActivityBlockedError, assert_workspace_idle


class ConversationServiceError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


def project_conversation(row: Conversation, *, selected: bool) -> ConversationSummary:
    return ConversationSummary(
        id=row.id,
        profile_id=row.profile_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_opened_at=row.last_opened_at,
        is_selected=selected,
    )


def project_conversation_list(
    page: ConversationListPage, *, selected_id: str | None
) -> ConversationListResponse:
    return ConversationListResponse(
        items=[
            project_conversation(row, selected=row.id == selected_id)
            for row in page.rows
        ],
        next_cursor=page.next_cursor,
    )


async def list_conversations(
    *,
    profile_id: str,
    limit: int,
    before: str | None,
    session_factory: async_sessionmaker[AsyncSession],
) -> ConversationListResponse:
    async with session_scope(session_factory) as session:
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise ConversationServiceError("PROFILE_NOT_FOUND", "profile not found")
        if profile.state != PROFILE_STATE_READY:
            raise ConversationServiceError("PROFILE_NOT_READY", "profile is not ready")
        page = await conversations_repo.list_for_profile(
            session, profile_id=profile_id, limit=limit, before=before
        )
        selected = await conversations_repo.most_recent_for_profile(
            session, profile_id=profile_id
        )
        return project_conversation_list(
            page, selected_id=selected.id if selected else None
        )


async def create_conversation(
    *, profile_id: str, session_factory: async_sessionmaker[AsyncSession]
) -> ConversationMutationResponse:
    async with session_scope(session_factory) as session:
        profile = await profiles_repo.get_profile(session, profile_id)
        if profile is None:
            raise ConversationServiceError("PROFILE_NOT_FOUND", "profile not found")
        try:
            await assert_workspace_idle(session, code="CONVERSATION_SWITCH_BLOCKED")
        except ActivityBlockedError as exc:
            raise ConversationServiceError(exc.code, exc.summary) from exc
        row = await conversations_repo.create_for_profile(
            session, profile_id=profile_id, title=NEW_CONVERSATION_TITLE
        )
        return ConversationMutationResponse(
            conversation=project_conversation(row, selected=True)
        )


async def select_owned_conversation(
    *, conversation_id: str, session_factory: async_sessionmaker[AsyncSession]
) -> ConversationMutationResponse:
    async with session_scope(session_factory) as session:
        try:
            await assert_workspace_idle(session, code="CONVERSATION_SWITCH_BLOCKED")
        except ActivityBlockedError as exc:
            raise ConversationServiceError(exc.code, exc.summary) from exc
        owner = await conversations_repo.resolve_owner(session, conversation_id)
        if owner is None:
            raise ConversationServiceError(
                "CONVERSATION_NOT_FOUND", "conversation not found"
            )
        active_id = await workspace_repo.get_active_profile_id(session)
        if active_id != owner.profile_id:
            raise ConversationServiceError(
                "CONVERSATION_PROFILE_MISMATCH", "conversation is not active"
            )
        row = await conversations_repo.select_for_profile(
            session,
            profile_id=owner.profile_id,
            conversation_id=conversation_id,
            now=utc_now(),
        )
        return ConversationMutationResponse(
            conversation=project_conversation(row, selected=True)
        )


__all__ = [
    "ConversationServiceError",
    "create_conversation",
    "list_conversations",
    "project_conversation",
    "project_conversation_list",
    "select_owned_conversation",
]
