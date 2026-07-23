"""Authoritative running/interrupted run gates for workspace mutations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.chat import AgentRun, ChatMessage, Conversation


class ActivityBlockedError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        self.code = code
        self.summary = summary
        super().__init__(summary)


async def _has_activity(
    session: AsyncSession, *owner_predicates: ColumnElement[bool]
) -> bool:
    statement = (
        select(AgentRun.id)
        .join(ChatMessage, AgentRun.user_message_id == ChatMessage.id)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            AgentRun.state.in_(("running", "interrupted")),
            *owner_predicates,
        )
        .limit(1)
    )
    return (await session.execute(statement)).scalar_one_or_none() is not None


async def assert_workspace_idle(
    session: AsyncSession, *, code: str = "PROFILE_SWITCH_BLOCKED"
) -> None:
    if await _has_activity(session):
        raise ActivityBlockedError(code, "finish or resolve the active run first")


async def assert_conversation_idle(
    session: AsyncSession,
    *,
    conversation_id: str,
    code: str = "CONVERSATION_SWITCH_BLOCKED",
) -> None:
    if await _has_activity(session, Conversation.id == conversation_id):
        raise ActivityBlockedError(code, "conversation has an active run")


async def assert_profile_idle(
    session: AsyncSession,
    *,
    profile_id: str,
    code: str = "PROFILE_DELETE_BLOCKED",
) -> None:
    if await _has_activity(session, Conversation.profile_id == profile_id):
        raise ActivityBlockedError(code, "profile has an active run")
