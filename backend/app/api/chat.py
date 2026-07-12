"""Public chat boundary: history, turn, and same-run resume (Plan 3 §7.4/7.5).

API layer owns validation, dependency lookup, and SSE orchestration only.
Durable writes and graph execution stay in repositories / ``ChatService``.
Both POST routes return a validated ordered SSE stream. Completed/failed
paths emit one terminal outcome; interrupt streams end at ``approval_required``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Final, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.agent.approval import profile_display_summary
from app.db.enums import AgentRunState, ToolExecutionStatus
from app.db.models.conversation import ToolExecution
from app.db.session import DatabaseSessionManager
from app.repositories.conversations import (
    ConversationRepository,
    ConversationRepositoryError,
)
from app.repositories.tool_executions import ToolExecutionRepository
from app.schemas.chat import (
    HISTORY_LIMIT_MAX,
    HistoryMessage,
    HistoryResponse,
    ResumeRequest,
    TurnRequest,
)
from app.schemas.sse import (
    ApprovalRequiredEvent,
    ApprovalRequiredPayload,
    AssistantDisplayStatus,
    AssistantStatusEvent,
    AssistantStatusPayload,
    RunCompletedEvent,
    RunCompletedPayload,
    RunFailedEvent,
    RunFailedPayload,
    RunStartedEvent,
    RunStartedPayload,
    SSEEvent,
    SSEEventOrderValidator,
    SSESchemaError,
    TextDeltaEvent,
    TextDeltaPayload,
    ToolCompletedEvent,
    ToolCompletedPayload,
    ToolDisplayStatus,
    ToolStartedEvent,
    ToolStartedPayload,
    serialize_sse_event_json,
)
from app.services.chat_service import (
    ChatService,
    ChatServiceError,
    ChatServiceStateError,
    ChatServiceValidationError,
    ChatTurnResult,
)

router = APIRouter(tags=["chat"])

logger = logging.getLogger(__name__)

_MAX_TEXT_DELTA: Final[int] = 4096
_FRIENDLY_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9 _./-]{0,127}$"
)
_ERROR_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Public tool outcome is fail-closed to short status tokens only.
_ALLOWED_PUBLIC_TOOL_OUTCOMES: Final[frozenset[str]] = frozenset(
    {
        "completed",
        "tool_completed",
        "ok",
        "success",
        "done",
    }
)


def _chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is None or not isinstance(service, ChatService):
        raise HTTPException(status_code=503, detail="chat_unavailable")
    return cast(ChatService, service)


def _db(request: Request) -> DatabaseSessionManager:
    db = getattr(request.app.state, "db", None)
    if db is None or not isinstance(db, DatabaseSessionManager):
        raise HTTPException(status_code=503, detail="database_unavailable")
    return cast(DatabaseSessionManager, db)


def _safe_error_code(raw: str | None) -> str:
    if not raw:
        return "RUN_FAILED"
    cleaned = raw.strip().upper().replace("-", "_").replace(" ", "_")
    cleaned = re.sub(r"[^A-Z0-9_]", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return "RUN_FAILED"
    if not cleaned[0].isalpha():
        cleaned = f"E_{cleaned}"
    cleaned = cleaned[:64]
    if not _ERROR_CODE_RE.fullmatch(cleaned):
        return "RUN_FAILED"
    return cleaned


def _friendly_tool_label(tool_name: str) -> str:
    raw = (tool_name or "tool").replace("_", " ").strip()
    if not raw:
        raw = "Tool"
    if not raw[0].isalpha():
        raw = f"Tool {raw}"
    label = raw[0].upper() + raw[1:] if len(raw) > 1 else raw.upper()
    label = " ".join(label.split())[:128]
    if not _FRIENDLY_LABEL_RE.fullmatch(label):
        return "Tool"
    return label


def _safe_outcome(summary: str | None) -> str | None:
    """Map durable tool summary to a public SSE outcome.

    Fail closed: free-form tool results, arguments, and document text never
    reach the wire. Only short allowlisted status tokens are accepted.
    """
    if summary is None:
        return None
    cleaned = " ".join(str(summary).split())
    if not cleaned:
        return None
    token = cleaned.lower()
    if token in _ALLOWED_PUBLIC_TOOL_OUTCOMES:
        # Normalize synonyms to a single public status token.
        return "completed"
    # Unknown free text (including raw tool bodies) is never emitted.
    return "completed"


def _chunk_text(text: str) -> list[str]:
    if not text:
        return []
    if len(text) <= _MAX_TEXT_DELTA:
        return [text]
    return [
        text[i : i + _MAX_TEXT_DELTA] for i in range(0, len(text), _MAX_TEXT_DELTA)
    ]


def _now() -> datetime:
    return datetime.now(UTC)


async def _load_tool_rows(
    db: DatabaseSessionManager,
    run_id: UUID,
) -> list[ToolExecution]:
    try:
        async with db.session_scope() as session:
            return await ToolExecutionRepository(session).list_for_run(run_id)
    except Exception:
        logger.info("tool_rows_unavailable")
        return []


def _tool_events(
    *,
    run_id: str,
    ts: datetime,
    seq: list[int],
    tools: Sequence[ToolExecution],
) -> list[SSEEvent]:
    events: list[SSEEvent] = []

    def _eid() -> str:
        seq[0] += 1
        return f"e{seq[0]}"

    for index, row in enumerate(tools, start=1):
        # Opaque per-stream correlation id only — never the DB primary key.
        tool_call_id = f"t{index}"
        label = _friendly_tool_label(row.tool_name)
        events.append(
            ToolStartedEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=ToolStartedPayload(
                    tool_call_id=tool_call_id,
                    label=label,
                    status=ToolDisplayStatus.RUNNING,
                ),
            )
        )
        outcome: str | None
        if row.status == ToolExecutionStatus.FAILED.value:
            display = ToolDisplayStatus.ERROR
            outcome = row.error_code or "tool_failed"
        elif row.status == ToolExecutionStatus.SUCCEEDED.value:
            display = ToolDisplayStatus.COMPLETE
            outcome = _safe_outcome(row.arguments_summary)
        else:
            display = ToolDisplayStatus.ERROR
            outcome = "incomplete"
        events.append(
            ToolCompletedEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=ToolCompletedPayload(
                    tool_call_id=tool_call_id,
                    label=label,
                    status=display,
                    duration_ms=row.duration_ms,
                    outcome=outcome,
                ),
            )
        )
    return events


async def build_sse_events_for_result(
    db: DatabaseSessionManager,
    result: ChatTurnResult,
) -> list[SSEEvent]:
    """Map a durable chat outcome to a legal ordered public SSE sequence."""
    run_id = str(result.run_id)
    ts = _now()
    seq = [0]
    tools = await _load_tool_rows(db, result.run_id)

    raw: list[SSEEvent] = [
        RunStartedEvent(
            event_id="e1",
            run_id=run_id,
            timestamp=ts,
            payload=RunStartedPayload(),
        )
    ]
    seq[0] = 1

    def _eid() -> str:
        seq[0] += 1
        return f"e{seq[0]}"

    raw.append(
        AssistantStatusEvent(
            event_id=_eid(),
            run_id=run_id,
            timestamp=ts,
            payload=AssistantStatusPayload(
                status=AssistantDisplayStatus.WORKING,
                message=None,
            ),
        )
    )
    raw.extend(_tool_events(run_id=run_id, ts=ts, seq=seq, tools=tools))

    state = result.state
    outcome = result.outcome

    if state == AgentRunState.INTERRUPTED.value or outcome == "interrupted":
        # Display-safe fields only — never draft_id / resume keys / auth tokens.
        display = profile_display_summary(
            result.pending_approval
            if isinstance(result.pending_approval, dict)
            else None
        )
        raw.append(
            ApprovalRequiredEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=ApprovalRequiredPayload(
                    summary=str(display["summary"]),
                    approval_kind=display.get("approval_kind"),
                    current_title=display.get("current_title"),
                    skill_names=display.get("skill_names"),
                    experience_count=display.get("experience_count"),
                    education_count=display.get("education_count"),
                    has_preference_changes=display.get("has_preference_changes"),
                    target_roles_preview=display.get("target_roles_preview"),
                ),
            )
        )
    elif state == AgentRunState.FAILED.value or outcome in {"failed", "disconnected"}:
        code = _safe_error_code(result.error)
        if outcome == "disconnected":
            code = "CLIENT_DISCONNECTED"
        raw.append(
            RunFailedEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=RunFailedPayload(error_code=code, message=None),
            )
        )
    elif state == AgentRunState.COMPLETED.value or outcome == "completed":
        text = result.final_text or ""
        for chunk in _chunk_text(text):
            raw.append(
                TextDeltaEvent(
                    event_id=_eid(),
                    run_id=run_id,
                    timestamp=ts,
                    payload=TextDeltaPayload(delta=chunk),
                )
            )
        raw.append(
            RunCompletedEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=RunCompletedPayload(),
            )
        )
    else:
        raw.append(
            RunFailedEvent(
                event_id=_eid(),
                run_id=run_id,
                timestamp=ts,
                payload=RunFailedPayload(
                    error_code="INCOMPLETE_RUN",
                    message=None,
                ),
            )
        )

    validator = SSEEventOrderValidator()
    try:
        return list(validator.validate_sequence(list(raw)))
    except SSESchemaError:
        fallback: list[SSEEvent] = [
            RunStartedEvent(
                event_id="e1",
                run_id=run_id,
                timestamp=ts,
                payload=RunStartedPayload(),
            ),
            RunFailedEvent(
                event_id="e2",
                run_id=run_id,
                timestamp=ts,
                payload=RunFailedPayload(
                    error_code="STREAM_VALIDATION_FAILED",
                    message=None,
                ),
            ),
        ]
        return list(SSEEventOrderValidator().validate_sequence(list(fallback)))


def _sse_wire_chunk(event: SSEEvent) -> str:
    """Encode one validated event as an SSE frame (text/event-stream)."""
    data = serialize_sse_event_json(event)
    event_name = str(event.event)
    event_id = event.event_id
    return f"event: {event_name}\nid: {event_id}\ndata: {data}\n\n"


async def _watch_disconnect(
    request: Request,
    cancel_event: asyncio.Event,
) -> None:
    try:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        return


async def _execute_turn(
    request: Request,
    service: ChatService,
    body: TurnRequest,
) -> ChatTurnResult:
    cancel_event = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
    try:
        try:
            return await service.start_turn(
                user_text=body.text,
                turn_idempotency_key=body.idempotency_key,
                attachment_ids=body.attachment_ids,
                cancel_event=cancel_event,
            )
        except ChatServiceValidationError:
            raise HTTPException(status_code=400, detail="invalid_turn") from None
        except ChatServiceStateError:
            raise HTTPException(status_code=409, detail="turn_conflict") from None
        except ChatServiceError:
            logger.info("turn_failed sanitized")
            raise HTTPException(status_code=500, detail="turn_failed") from None
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


async def _execute_resume(
    request: Request,
    service: ChatService,
    run_id: UUID,
    body: ResumeRequest,
) -> ChatTurnResult:
    cancel_event = asyncio.Event()
    watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
    try:
        try:
            return await service.resume_run(
                run_id=run_id,
                resume_idempotency_key=body.idempotency_key,
                resume_value=body.resume_value(),
                cancel_event=cancel_event,
            )
        except ChatServiceValidationError:
            raise HTTPException(status_code=400, detail="invalid_resume") from None
        except ChatServiceStateError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail="run_not_found") from None
            raise HTTPException(status_code=409, detail="cannot_resume") from None
        except ChatServiceError:
            logger.info("resume_failed sanitized")
            raise HTTPException(status_code=500, detail="resume_failed") from None
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


async def _event_stream(
    db: DatabaseSessionManager,
    result: ChatTurnResult,
) -> AsyncIterator[str]:
    events = await build_sse_events_for_result(db, result)
    for event in events:
        yield _sse_wire_chunk(event)


def _sse_response(
    db: DatabaseSessionManager,
    result: ChatTurnResult,
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(db, result),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/chat/history", response_model=HistoryResponse)
async def get_chat_history(
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=HISTORY_LIMIT_MAX),
) -> HistoryResponse:
    """Hydrate durable singleton conversation history (bounded optional limit)."""
    db = _db(request)
    try:
        async with db.session_scope() as session:
            conv = ConversationRepository(session)
            await conv.ensure_singleton()
            rows = await conv.list_history(limit=limit)
            messages = [
                HistoryMessage(
                    role=row.role,
                    content=row.content,
                    created_at=row.created_at,
                    structured_payload=row.structured_payload,
                )
                for row in rows
            ]
            return HistoryResponse(messages=messages)
    except ConversationRepositoryError:
        raise HTTPException(status_code=400, detail="invalid_history_query") from None
    except Exception:
        logger.info("history_failed sanitized")
        raise HTTPException(status_code=500, detail="history_failed") from None


@router.post("/api/chat/turns")
async def post_chat_turn(
    request: Request,
    body: TurnRequest,
) -> StreamingResponse:
    """Start one user turn; stream validated ordered SSE events."""
    service = _chat_service(request)
    db = _db(request)
    result = await _execute_turn(request, service, body)
    return _sse_response(db, result)


@router.post("/api/chat/runs/{run_id}/resume")
async def post_chat_resume(
    request: Request,
    run_id: UUID,
    body: ResumeRequest,
) -> StreamingResponse:
    """Resume an interrupted run on the same identity; stream validated SSE."""
    service = _chat_service(request)
    db = _db(request)
    result = await _execute_resume(request, service, run_id, body)
    return _sse_response(db, result)


__all__ = [
    "build_sse_events_for_result",
    "router",
]
