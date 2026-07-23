"""Thin chat history / turn / resume FastAPI routes (Plan 3 §7.8).

Validate inputs, delegate to services, and frame already-validated SSE events.
No Agent construction, business rules, SQLAlchemy writes, checkpoint logic, or
provider calls live here. No application transaction remains open while
yielding SSE.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.sse import EventSourceResponse

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.api.query_params import history_query as _history_query
from app.api.sse import open_sse_response
from app.db.session import get_session_factory
from app.schemas.chat import (
    ChatTurnRequest,
    HistoryPage,
    HistoryQuery,
    ResumeRequest,
)
from app.schemas.common import UuidStr
from app.services.chat_history import (
    ChatHistoryServiceError,
    get_history_page,
    history_page_as_dict,
)
from app.services.chat_turns import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    ERROR_INVALID_APPROVAL_ACTION,
    ERROR_RUN_NOT_FOUND,
    ERROR_RUN_NOT_RESUMABLE,
    ERROR_RUN_PROFILE_MISMATCH,
    ChatTurnError,
    stream_chat_turn,
    stream_resume,
)

router = APIRouter(tags=["chat"])

# Stable HTTP mapping for pre-stream ChatTurnError (JSON body, no stack/secret).
_CHAT_ERROR_STATUS: dict[str, int] = {
    ERROR_APPROVAL_ACTION_REQUIRED: 409,
    ERROR_INVALID_APPROVAL_ACTION: 400,
    ERROR_RUN_NOT_FOUND: 404,
    ERROR_RUN_NOT_RESUMABLE: 409,
    ERROR_RUN_PROFILE_MISMATCH: 409,
    "CONVERSATION_NOT_FOUND": 404,
    "CONVERSATION_PROFILE_MISMATCH": 409,
    "EMPTY_MESSAGE": 422,
}


def _http_for_chat_error(exc: ChatTurnError) -> HTTPException:
    """Map a stable application code to a safe JSON HTTP error."""
    status = _CHAT_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


@router.get("/chat/history", response_model=HistoryPage)
async def get_chat_history(
    query: Annotated[HistoryQuery, Depends(_history_query)],
) -> dict[str, Any]:
    """Return one hydrated chronological history page ``{items, next_cursor}``."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            page = await get_history_page(
                session,
                limit=query.limit,
                before=query.before,
                conversation_id=query.conversation_id,
            )
        except ChatHistoryServiceError as exc:
            raise HTTPException(
                status_code=404 if "not found" in str(exc) else 422,
                detail={"code": "CONVERSATION_NOT_FOUND", "summary": str(exc)},
            ) from exc
        # Read-only unit of work; close before returning JSON (no open txn).
        await session.commit()
    return history_page_as_dict(page)


@router.post("/chat/turns")
async def post_chat_turn(
    body: ChatTurnRequest,
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    """Persist user+run then stream validated SSE for one Agent turn."""
    events = stream_chat_turn(
        message=body.message,
        attachment_ids=body.attachment_ids,
        conversation_id=body.conversation_id,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(events, error_mapper=_http_for_chat_error)


@router.post("/chat/runs/{run_id}/resume")
async def post_chat_resume(
    run_id: Annotated[UuidStr, Path(description="Agent run id")],
    body: ResumeRequest,
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    """Resume an interrupted run (or terminal no-op) as validated SSE."""
    events = stream_resume(
        run_id=run_id,
        action=body.action,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await open_sse_response(events, error_mapper=_http_for_chat_error)


__all__ = ["router"]
