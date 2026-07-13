"""History cursor pagination and durable run/tool hydration.

Owns the single history page contract: newest-first ``limit + 1`` fetch,
``next_cursor`` from the oldest returned ``(created_at, id)`` when older rows
exist, chronological page order, and attach of runs/tool executions only to
initiating user messages via ``agent_runs.user_message_id``. Never emits
``role='tool'`` items. Callers own the session and commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    AgentRun,
    ChatMessage,
    ToolExecution,
)
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.chat import (
    AgentRunView,
    ChatMessageView,
    HistoryPage,
    ToolExecutionView,
    decode_history_cursor,
    encode_history_cursor,
)
from app.schemas.tools import ToolResult, parse_tool_result


class ChatHistoryServiceError(Exception):
    """Base error for history service invariant violations."""


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite-returned datetimes to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware_utc(value: datetime) -> datetime:
    aware = _as_aware_utc(value)
    assert aware is not None
    return aware


def _tool_view(row: ToolExecution) -> ToolExecutionView:
    result: ToolResult | None = None
    if row.result_json is not None:
        result = parse_tool_result(row.result_json)
    return ToolExecutionView(
        id=row.id,
        tool_call_id=row.tool_call_id,
        tool_name=row.tool_name,
        status=row.status,  # type: ignore[arg-type]
        duration_ms=row.duration_ms,
        error_code=row.error_code,
        result=result,
        arguments_summary=row.arguments_summary_json,
        created_at=_require_aware_utc(row.created_at),
        updated_at=_require_aware_utc(row.updated_at),
    )


def _run_view(
    run: AgentRun,
    tools: list[ToolExecution],
) -> AgentRunView:
    return AgentRunView(
        id=run.id,
        user_message_id=run.user_message_id,
        state=run.state,  # type: ignore[arg-type]
        pending_approval=run.pending_approval_json,
        error_code=run.error_code,
        completed_at=_as_aware_utc(run.completed_at),
        created_at=_require_aware_utc(run.created_at),
        updated_at=_require_aware_utc(run.updated_at),
        tool_executions=[_tool_view(t) for t in tools],
    )


def _message_view(
    message: ChatMessage,
    run: AgentRun | None,
    tools_by_run: dict[str, list[ToolExecution]],
) -> ChatMessageView:
    run_view: AgentRunView | None = None
    if run is not None and message.role == CHAT_MESSAGE_ROLE_USER:
        run_view = _run_view(run, tools_by_run.get(run.id, []))
    return ChatMessageView(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        structured_payload=message.structured_payload,
        created_at=_require_aware_utc(message.created_at),
        updated_at=_require_aware_utc(message.updated_at),
        run=run_view,
    )


async def get_history_page(
    session: AsyncSession,
    *,
    limit: int = 50,
    before: str | None = None,
) -> HistoryPage:
    """Load one chronological history page with opaque cursor pagination.

    *limit* must be in ``1..100``. *before* is a validated opaque cursor or
    ``None`` for the newest page. Response shape is exactly
    ``{items, next_cursor}``. Does not finalize the caller's unit of work.
    """
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ChatHistoryServiceError("limit must be an integer in 1..100")

    cursor_pair: tuple[datetime, str] | None = None
    if before is not None:
        # Re-validate encoding/shape/time/UUID (same contract as HistoryQuery).
        cursor_pair = decode_history_cursor(before)

    # Newest-first with one extra row to detect older pages.
    newest_first = await messages_repo.list_messages_before(
        session,
        limit=limit + 1,
        before=cursor_pair,
    )
    has_older = len(newest_first) > limit
    page_newest_first = newest_first[:limit]
    # Chronological order for the response page.
    page = list(reversed(page_newest_first))

    next_cursor: str | None = None
    if has_older and page:
        oldest = page[0]
        next_cursor = encode_history_cursor(
            _require_aware_utc(oldest.created_at),
            oldest.id,
        )

    items = await _hydrate_items(session, page)
    return HistoryPage(items=items, next_cursor=next_cursor)


async def _hydrate_items(
    session: AsyncSession,
    messages: list[ChatMessage],
) -> list[ChatMessageView]:
    """Attach runs and durable tool activity to initiating user messages only."""
    user_ids = [m.id for m in messages if m.role == CHAT_MESSAGE_ROLE_USER]
    runs = await runs_repo.list_runs_for_user_message_ids(session, user_ids)
    run_by_user: dict[str, AgentRun] = {r.user_message_id: r for r in runs}
    run_ids = [r.id for r in runs]
    tools = await tool_repo.list_for_run_ids(session, run_ids)
    tools_by_run: dict[str, list[ToolExecution]] = {}
    for tool in tools:
        tools_by_run.setdefault(tool.run_id, []).append(tool)

    items: list[ChatMessageView] = []
    for message in messages:
        # Durable roles only; repository already forbids role='tool'.
        run = (
            run_by_user.get(message.id)
            if message.role == CHAT_MESSAGE_ROLE_USER
            else None
        )
        items.append(_message_view(message, run, tools_by_run))
    return items


def history_page_as_dict(page: HistoryPage) -> dict[str, Any]:
    """Serialize a history page to exactly ``items`` and ``next_cursor`` keys."""
    return page.model_dump(mode="json")
