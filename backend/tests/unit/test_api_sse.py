from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.api.sse import format_validated_sse, open_sse_response
from app.schemas.sse import SseEvent, build_sse_event
from app.services.chat_turns import ChatTurnError
from fastapi import HTTPException

RUN_ID = "11111111-1111-4111-8111-111111111111"


def _event() -> SseEvent:
    return build_sse_event(
        "assistant_status",
        RUN_ID,
        {"message": "Working"},
    )


def test_format_validated_sse_preserves_event_id_and_compact_json() -> None:
    event = _event()
    framed = format_validated_sse(event).decode("utf-8")
    assert "event: assistant_status" in framed
    assert f"id: {event.event_id}" in framed
    assert '"message":"Working"' in framed


@pytest.mark.asyncio
async def test_open_sse_response_maps_pre_yield_error() -> None:
    async def events() -> AsyncIterator[SseEvent]:
        raise ChatTurnError("RUN_NOT_FOUND", "run missing")
        yield _event()

    def mapper(exc: ChatTurnError) -> HTTPException:
        return HTTPException(
            status_code=404,
            detail={"code": exc.code, "summary": exc.message},
        )

    with pytest.raises(HTTPException) as exc_info:
        await open_sse_response(events(), error_mapper=mapper)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_open_sse_response_rejects_empty_stream() -> None:
    async def events() -> AsyncIterator[SseEvent]:
        if False:
            yield _event()

    with pytest.raises(HTTPException) as exc_info:
        await open_sse_response(
            events(),
            error_mapper=lambda exc: HTTPException(status_code=400),
        )
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {
        "code": "EMPTY_STREAM",
        "summary": "Agent stream produced no events",
    }


@pytest.mark.asyncio
async def test_open_sse_response_closes_underlying_iterator_when_body_closes() -> None:
    class TrackedEvents:
        def __init__(self) -> None:
            self.closed = 0
            self._sent_event = False

        def __aiter__(self) -> TrackedEvents:
            return self

        async def __anext__(self) -> SseEvent:
            if self._sent_event:
                raise StopAsyncIteration
            self._sent_event = True
            return _event()

        async def aclose(self) -> None:
            self.closed += 1

    events = TrackedEvents()
    response = await open_sse_response(
        events,
        error_mapper=lambda exc: HTTPException(status_code=400),
    )

    first = await response.body_iterator.__anext__()
    assert b"event: assistant_status" in first

    await response.body_iterator.aclose()
    await response.body_iterator.aclose()

    assert events.closed == 1
