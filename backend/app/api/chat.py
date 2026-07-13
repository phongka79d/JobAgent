"""Thin chat history / turn / resume FastAPI routes (Plan 3 §7.8).

Validate inputs, delegate to services, and frame already-validated SSE events.
No Agent construction, business rules, SQLAlchemy writes, checkpoint logic, or
provider calls live here. No application transaction remains open while
yielding SSE.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.sse import EventSourceResponse, format_sse_event
from pydantic import ValidationError

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.db.session import get_session_factory
from app.schemas.chat import (
    ChatTurnRequest,
    HistoryPage,
    HistoryQuery,
    ResumeRequest,
)
from app.schemas.common import UuidStr
from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_history import get_history_page, history_page_as_dict
from app.services.chat_turns import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    ERROR_INVALID_APPROVAL_ACTION,
    ERROR_RUN_NOT_FOUND,
    ERROR_RUN_NOT_RESUMABLE,
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
    "EMPTY_MESSAGE": 422,
}


def _http_for_chat_error(exc: ChatTurnError) -> HTTPException:
    """Map a stable application code to a safe JSON HTTP error."""
    status = _CHAT_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


def _format_validated_sse(event: SseEvent) -> bytes:
    """Re-validate and frame one typed event as SSE wire bytes."""
    validated = parse_sse_event(sse_event_to_dict(event))
    payload = sse_event_to_dict(validated)
    return format_sse_event(
        data_str=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        event=validated.event,
        id=str(validated.event_id),
    )


async def _open_sse_response(
    events: AsyncIterator[SseEvent],
) -> EventSourceResponse:
    """Prime the service stream so pre-yield errors become JSON HTTP errors.

    Creates the durable turn/resume claim inside the handler (before headers)
    so interruption guards and invalid actions are not lost as empty SSE 200.
    Subsequent events are framed only after the response starts; no DB
    transaction is held across yields.
    """
    agen = events.__aiter__()
    try:
        first = await agen.__anext__()
    except StopAsyncIteration:
        # Empty stream should not occur for valid turn/resume paths.
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_STREAM",
                "summary": "Agent stream produced no events",
            },
        ) from None
    except ChatTurnError as exc:
        raise _http_for_chat_error(exc) from exc

    first_bytes = _format_validated_sse(first)

    async def produce() -> AsyncIterator[bytes]:
        yield first_bytes
        async for event in agen:
            yield _format_validated_sse(event)

    return EventSourceResponse(produce())


def _history_query(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[str | None, Query()] = None,
) -> HistoryQuery:
    """Validate history query params (malformed cursor → 422)."""
    try:
        return HistoryQuery(limit=limit, before=before)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.get("/chat/history", response_model=HistoryPage)
async def get_chat_history(
    query: Annotated[HistoryQuery, Depends(_history_query)],
) -> dict[str, Any]:
    """Return one hydrated chronological history page ``{items, next_cursor}``."""
    factory = get_session_factory()
    async with factory() as session:
        page = await get_history_page(
            session,
            limit=query.limit,
            before=query.before,
        )
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
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await _open_sse_response(events)


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
    return await _open_sse_response(events)


__all__ = ["router"]
