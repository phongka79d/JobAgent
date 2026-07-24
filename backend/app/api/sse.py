from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from anyio import CancelScope
from fastapi import HTTPException
from fastapi.sse import EventSourceResponse, format_sse_event
from starlette.types import Send

from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_turns import ChatTurnError

ChatErrorMapper = Callable[[ChatTurnError], HTTPException]


async def _close_async_iterator(iterator: Any) -> None:
    aclose = getattr(iterator, "aclose", None)
    if aclose is None:
        return
    with CancelScope(shield=True):
        await aclose()


class ClosingEventSourceResponse(EventSourceResponse):
    """Close the body even when an ASGI disconnect cancels streaming."""

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            await _close_async_iterator(self.body_iterator)


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
        try:
            yield first_bytes
            async for event in iterator:
                yield format_validated_sse(event)
        finally:
            await _close_async_iterator(iterator)

    return ClosingEventSourceResponse(produce())
