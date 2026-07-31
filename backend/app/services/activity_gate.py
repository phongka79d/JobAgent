"""Authoritative chat, tailoring-Agent, and manual-generation activity gates."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.chat import (
    AGENT_RUN_KIND_CHAT,
    AGENT_RUN_STATE_RUNNING,
    AgentRun,
    ChatMessage,
    Conversation,
)
from app.db.models.cv_tailoring import CVTailoringSession
from app.db.models.profiles import (
    PROFILE_STATE_READY,
    ProfileDraft,
    ProfileReextractOperation,
)
from app.repositories import profiles as profile_repo
from app.schemas.cv_tailoring import TAILORING_SESSION_STATE_GENERATING


class ActivityBlockedError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        self.code = code
        self.summary = summary
        super().__init__(summary)


_ACTIVE_RUN_STATES = ("running", "interrupted")


async def _query_exists(
    session: AsyncSession, statement: Select[tuple[str]]
) -> bool:
    return (await session.execute(statement)).scalar_one_or_none() is not None


async def _has_chat_activity(
    session: AsyncSession, *owner_predicates: ColumnElement[bool]
) -> bool:
    statement = (
        select(AgentRun.id)
        .join(ChatMessage, AgentRun.user_message_id == ChatMessage.id)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            AgentRun.run_kind == AGENT_RUN_KIND_CHAT,
            AgentRun.state.in_(_ACTIVE_RUN_STATES),
            *owner_predicates,
        )
        .limit(1)
    )
    return await _query_exists(session, statement)


async def _has_tailoring_activity(
    session: AsyncSession, *, profile_id: str | None = None
) -> bool:
    run_statement = (
        select(AgentRun.id)
        .join(
            CVTailoringSession,
            AgentRun.tailoring_session_id == CVTailoringSession.id,
        )
        .where(AgentRun.state.in_(_ACTIVE_RUN_STATES))
    )
    session_statement = select(CVTailoringSession.id).where(
        CVTailoringSession.state == TAILORING_SESSION_STATE_GENERATING
    )
    if profile_id is not None:
        run_statement = run_statement.where(
            CVTailoringSession.profile_id == profile_id
        )
        session_statement = session_statement.where(
            CVTailoringSession.profile_id == profile_id
        )
    return await _query_exists(session, run_statement.limit(1)) or await _query_exists(
        session, session_statement.limit(1)
    )


async def assert_workspace_idle(
    session: AsyncSession, *, code: str = "PROFILE_SWITCH_BLOCKED"
) -> None:
    any_run = await _query_exists(
        session,
        select(AgentRun.id)
        .where(AgentRun.state.in_(_ACTIVE_RUN_STATES))
        .limit(1),
    )
    if any_run or await _has_tailoring_activity(session):
        raise ActivityBlockedError(code, "finish or resolve the active run first")


async def assert_conversation_idle(
    session: AsyncSession,
    *,
    conversation_id: str,
    code: str = "CONVERSATION_SWITCH_BLOCKED",
) -> None:
    profile_id = await session.scalar(
        select(Conversation.profile_id).where(Conversation.id == conversation_id)
    )
    if await _has_chat_activity(
        session, Conversation.id == conversation_id
    ) or (
        profile_id is not None
        and await _has_tailoring_activity(session, profile_id=profile_id)
    ):
        raise ActivityBlockedError(code, "conversation has an active run")


async def assert_profile_idle(
    session: AsyncSession,
    *,
    profile_id: str,
    code: str = "PROFILE_DELETE_BLOCKED",
) -> None:
    if await _has_chat_activity(
        session, Conversation.profile_id == profile_id
    ) or await _has_tailoring_activity(session, profile_id=profile_id):
        raise ActivityBlockedError(code, "profile has an active run")


async def assert_profile_review_clear(
    session: AsyncSession,
    *,
    profile_id: str,
    code: str = "PROFILE_REVIEW_PENDING",
) -> None:
    """Block lifecycle mutations while this profile owns a durable review."""
    draft = await profile_repo.get_draft_for_profile(session, profile_id)
    profile = await profile_repo.get_profile(session, profile_id)
    if (
        profile is not None
        and profile.state == PROFILE_STATE_READY
        and draft is not None
    ):
        raise ActivityBlockedError(
            code,
            "Approve or discard the pending profile review first",
        )


async def assert_profile_reextract_clear(
    session: AsyncSession, *, profile_id: str
) -> None:
    """Block lifecycle work while re-extraction owns a review or is running."""
    owned_draft = await session.scalar(
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
    if owned_draft is not None:
        raise ActivityBlockedError(
            "PROFILE_REVIEW_PENDING",
            "Approve or discard the pending profile re-extraction review first",
        )

    actionable = await session.scalar(
        select(ProfileReextractOperation.id)
        .where(
            ProfileReextractOperation.profile_id == profile_id,
            ProfileReextractOperation.state.in_(("running", "review_ready")),
        )
        .order_by(
            ProfileReextractOperation.updated_at.desc(),
            ProfileReextractOperation.id.desc(),
        )
        .limit(1)
    )
    if actionable is not None:
        raise ActivityBlockedError(
            "PROFILE_REEXTRACT_IN_PROGRESS",
            "Wait for the profile re-extraction to finish first",
        )


async def assert_tailoring_start_allowed(
    session: AsyncSession,
    *,
    profile_id: str,
    parent_run_id: str | None = None,
    code: str = "TAILORING_START_BLOCKED",
) -> None:
    if parent_run_id is None:
        await assert_profile_idle(session, profile_id=profile_id, code=code)
        return
    parent_statement = (
        select(AgentRun.id)
        .join(ChatMessage, AgentRun.user_message_id == ChatMessage.id)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            AgentRun.id == parent_run_id,
            AgentRun.run_kind == AGENT_RUN_KIND_CHAT,
            AgentRun.state == AGENT_RUN_STATE_RUNNING,
            Conversation.profile_id == profile_id,
        )
        .limit(1)
    )
    if not await _query_exists(session, parent_statement):
        raise ActivityBlockedError(code, "tailoring parent run is not allowed")
    other_run = await _query_exists(
        session,
        select(AgentRun.id)
        .where(
            AgentRun.state.in_(_ACTIVE_RUN_STATES),
            AgentRun.id != parent_run_id,
        )
        .limit(1),
    )
    if other_run or await _has_tailoring_activity(session):
        raise ActivityBlockedError(code, "workspace has other active work")
