"""Profile/conversation scoped HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.api.query_params import (
    conversation_history_query,
    conversation_query,
)
from app.api.sse import open_sse_response
from app.db.session import get_session_factory
from app.schemas.chat import (
    ChatTurnRequest,
    ConversationListResponse,
    ConversationMutationResponse,
    ConversationQuery,
    HistoryPage,
    HistoryQuery,
)
from app.schemas.common import UuidStr
from app.services.chat_history import (
    ChatHistoryServiceError,
    get_history_page,
    history_page_as_dict,
)
from app.services.chat_turns import ChatTurnError, stream_chat_turn
from app.services.conversations import (
    ConversationServiceError,
    create_conversation,
    list_conversations,
    select_owned_conversation,
)

router = APIRouter(tags=["conversations"])


def _error(exc: ConversationServiceError) -> HTTPException:
    status = {
        "PROFILE_NOT_FOUND": 404,
        "PROFILE_NOT_READY": 409,
        "CONVERSATION_NOT_FOUND": 404,
        "CONVERSATION_PROFILE_MISMATCH": 409,
        "CONVERSATION_SWITCH_BLOCKED": 409,
    }.get(exc.code, 400)
    return HTTPException(
        status_code=status, detail={"code": exc.code, "summary": exc.summary}
    )


def _chat_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ChatTurnError):
        status = 404 if exc.code == "CONVERSATION_NOT_FOUND" else 409
        return HTTPException(
            status_code=status,
            detail={"code": exc.code, "summary": exc.message},
        )
    return HTTPException(
        status_code=400,
        detail={"code": "CHAT_ERROR", "summary": "chat request failed"},
    )


@router.get(
    "/profiles/{profile_id}/conversations",
    response_model=ConversationListResponse,
)
async def list_profile_conversations(
    profile_id: UuidStr,
    query: Annotated[ConversationQuery, Depends(conversation_query)],
) -> ConversationListResponse:
    try:
        return await list_conversations(
            profile_id=profile_id,
            limit=query.limit,
            before=query.before,
            session_factory=get_session_factory(),
        )
    except ConversationServiceError as exc:
        raise _error(exc) from exc


@router.post(
    "/profiles/{profile_id}/conversations",
    response_model=ConversationMutationResponse,
)
async def create_profile_conversation(
    profile_id: UuidStr,
) -> ConversationMutationResponse:
    try:
        return await create_conversation(
            profile_id=profile_id, session_factory=get_session_factory()
        )
    except ConversationServiceError as exc:
        raise _error(exc) from exc


@router.post(
    "/conversations/{conversation_id}/select",
    response_model=ConversationMutationResponse,
)
async def select_conversation(
    conversation_id: UuidStr,
) -> ConversationMutationResponse:
    try:
        return await select_owned_conversation(
            conversation_id=conversation_id, session_factory=get_session_factory()
        )
    except ConversationServiceError as exc:
        raise _error(exc) from exc


@router.get("/conversations/{conversation_id}/history", response_model=HistoryPage)
async def get_conversation_history(
    conversation_id: UuidStr,
    query: Annotated[HistoryQuery, Depends(conversation_history_query)],
) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            page = await get_history_page(
                session,
                conversation_id=conversation_id,
                limit=query.limit,
                before=query.before,
            )
        except ChatHistoryServiceError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "CONVERSATION_NOT_FOUND",
                    "summary": "conversation not found",
                },
            ) from exc
        await session.commit()
    return history_page_as_dict(page)


@router.post("/conversations/{conversation_id}/turns")
async def post_conversation_turn(
    conversation_id: UuidStr,
    body: ChatTurnRequest,
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    if body.conversation_id is not None and body.conversation_id != conversation_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONVERSATION_PROFILE_MISMATCH",
                "summary": "conversation body does not match path",
            },
        )
    events = stream_chat_turn(
        conversation_id=conversation_id,
        message=body.message,
        attachment_ids=body.attachment_ids,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(events, error_mapper=_chat_error)


__all__ = ["router"]
