from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, TypeVar

from anyio import CancelScope
from fastapi import HTTPException
from fastapi.sse import EventSourceResponse, format_sse_event
from starlette.types import Send

from app.schemas.profile_reextraction import ProfileReextractEvent
from app.schemas.sse import SseEvent, parse_sse_event, sse_event_to_dict
from app.services.chat_turns import ChatTurnError

StreamErrorMapper = Callable[[Any], HTTPException]
T = TypeVar("T")


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


def format_profile_reextract_sse(event: ProfileReextractEvent) -> bytes:
    """Validate and frame a direct profile event without widening chat SSE."""
    validated = ProfileReextractEvent.model_validate(
        event.model_dump(mode="json")
    )
    return format_sse_event(
        data_str=validated.model_dump_json(),
        event=validated.event,
        id=str(validated.event_id),
    )


async def open_typed_sse_response(
    events: AsyncIterator[T],
    *,
    serializer: Callable[[T], bytes],
    error_mapper: StreamErrorMapper,
    error_types: Sequence[type[Exception]],
    headers: Mapping[str, str] | None = None,
) -> EventSourceResponse:
    """Prime a typed stream before headers and close its source reliably."""
    iterator = events.__aiter__()
    try:
        first = await iterator.__anext__()
    except StopAsyncIteration:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_STREAM",
                "summary": "Operation produced no events",
            },
        ) from None
    except Exception as exc:
        if isinstance(exc, tuple(error_types)):
            raise error_mapper(exc) from exc
        raise

    first_bytes = serializer(first)

    async def produce() -> AsyncIterator[bytes]:
        try:
            yield first_bytes
            async for event in iterator:
                yield serializer(event)
        finally:
            await _close_async_iterator(iterator)

    return ClosingEventSourceResponse(produce(), headers=dict(headers or {}))


async def open_sse_response(
    events: AsyncIterator[SseEvent],
    *,
    error_mapper: StreamErrorMapper,
    error_types: Sequence[type[Exception]] = (ChatTurnError,),
    headers: Mapping[str, str] | None = None,
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
    except Exception as exc:
        if isinstance(exc, tuple(error_types)):
            raise error_mapper(exc) from exc
        raise

    first_bytes = format_validated_sse(first)

    async def produce() -> AsyncIterator[bytes]:
        try:
            yield first_bytes
            async for event in iterator:
                yield format_validated_sse(event)
        finally:
            await _close_async_iterator(iterator)

    return ClosingEventSourceResponse(produce(), headers=dict(headers or {}))
