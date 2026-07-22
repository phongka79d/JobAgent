from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

from fastapi import HTTPException
from fastapi.sse import EventSourceResponse, format_sse_event

from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_turns import ChatTurnError

ChatErrorMapper = Callable[[ChatTurnError], HTTPException]


def format_validated_sse(event: SseEvent) -> bytes:
    """Revalidate and frame one typed event as SSE wire bytes."""
    validated = parse_sse_event(sse_event_to_dict(event))
    payload = sse_event_to_dict(validated)
    return format_sse_event(
        data_str=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        event=validated.event,
        id=str(validated.event_id),
    )


async def open_sse_response(
    events: AsyncIterator[SseEvent],
    *,
    error_mapper: ChatErrorMapper,
) -> EventSourceResponse:
    """Prime before headers, then stream validated SSE frames."""
    iterator = events.__aiter__()
    try:
        first = await iterator.__anext__()
    except StopAsyncIteration:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_STREAM",
                "summary": "Agent stream produced no events",
            },
        ) from None
    except ChatTurnError as exc:
        raise error_mapper(exc) from exc

    first_bytes = format_validated_sse(first)

    async def produce() -> AsyncIterator[bytes]:
        yield first_bytes
        async for event in iterator:
            yield format_validated_sse(event)

    return EventSourceResponse(produce())
