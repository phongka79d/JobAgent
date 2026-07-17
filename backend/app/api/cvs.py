"""Thin CV Manager mutation routes (Plan 9 / Master §14.1).

Transport only: validate path params, delegate reprocess to chat-turn
services, frame already-validated SSE events. No second runner, no extraction
or approval business rules, and no open DB transaction across yields.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.sse import EventSourceResponse, format_sse_event

from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.schemas.common import UuidStr
from app.schemas.cv_manager import (
    ERROR_APPROVAL_ACTION_REQUIRED,
    ERROR_CHUNKS_UNAVAILABLE,
    ERROR_CV_ATTACHMENT_NOT_FOUND,
    ERROR_CV_FILE_UNAVAILABLE,
    ERROR_CV_NOT_REPROCESSABLE,
)
from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_turns import (
    ChatTurnError,
    stream_cv_reprocess,
)
from app.storage.attachments import AttachmentStorage

router = APIRouter(tags=["cvs"])

_REPROCESS_ERROR_STATUS: dict[str, int] = {
    ERROR_APPROVAL_ACTION_REQUIRED: 409,
    ERROR_CV_ATTACHMENT_NOT_FOUND: 404,
    ERROR_CV_NOT_REPROCESSABLE: 409,
    ERROR_CV_FILE_UNAVAILABLE: 404,
    ERROR_CHUNKS_UNAVAILABLE: 404,
}


def _http_for_reprocess_error(exc: ChatTurnError) -> HTTPException:
    status = _REPROCESS_ERROR_STATUS.get(exc.code, 400)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "summary": exc.message},
    )


def _format_validated_sse(event: SseEvent) -> bytes:
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
    """Prime the stream so pre-yield ChatTurnError becomes JSON HTTP errors."""
    agen = events.__aiter__()
    try:
        first = await agen.__anext__()
    except StopAsyncIteration:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_STREAM",
                "summary": "Agent stream produced no events",
            },
        ) from None
    except ChatTurnError as exc:
        raise _http_for_reprocess_error(exc) from exc

    first_bytes = _format_validated_sse(first)

    async def produce() -> AsyncIterator[bytes]:
        yield first_bytes
        async for event in agen:
            yield _format_validated_sse(event)

    return EventSourceResponse(produce())


@router.post("/cvs/{attachment_id}/reprocess")
async def post_cv_reprocess(
    request: Request,
    attachment_id: Annotated[UuidStr, Path(description="Attachment id")],
    deps: Annotated[ChatAgentDeps, Depends(get_chat_agent_deps)],
) -> EventSourceResponse:
    """``POST /api/cvs/{attachment_id}/reprocess`` — active/archived re-extract.

    Returns the normal validated SSE stream through proposal and approval
    interrupt. Does not change active selection before Save Profile.
    """
    storage: AttachmentStorage = request.app.state.storage
    events = stream_cv_reprocess(
        attachment_id=attachment_id,
        storage=storage,
        model=deps.model,
        registry=deps.registry,
        sqlite_path=deps.sqlite_path,
        include_assistant_status=deps.include_assistant_status,
    )
    return await _open_sse_response(events)


__all__ = ["router"]
