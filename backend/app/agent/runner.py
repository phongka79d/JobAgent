"""Request-scoped Agent runner: stream validated SSE events + terminal cleanup.

Opens one ``AsyncSqliteSaver`` per invocation, compiles the injected graph with
that checkpointer, streams activity as (01A) typed events, and after an injected
durable-terminal callback confirms commit, deletes only this run's checkpoint
for completed/failed outcomes. Interrupted checkpoints are retained.

No application transaction is held open during graph execution or event yield.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.agent.checkpoint import (
    delete_run_checkpoint,
    open_checkpointer,
    thread_config,
)
from app.agent.graph import (
    DECISION_NODE_NAME,
    ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
    MESSAGES_KEY,
    AgentGraphBundle,
    AgentGraphState,
    build_agent_graph,
    initial_graph_state,
)
from app.core.ids import new_uuid
from app.core.settings import Settings
from app.core.time import utc_now
from app.schemas.sse import SseEvent, parse_sse_event
from app.tools.registry import ToolRegistry

# Stable runner-level failure when the graph raises unexpectedly.
ERROR_AGENT_EXECUTION: str = "AGENT_EXECUTION_FAILED"

_SAFE_ERROR_SUMMARIES: dict[str, str] = {
    ERROR_TOOL_LOOP_LIMIT_EXCEEDED: "Tool loop limit exceeded for this run",
    ERROR_AGENT_EXECUTION: "Agent execution failed",
}

TerminalKind = Literal["completed", "failed", "interrupted"]

DurableTerminalCallback = Callable[["TerminalOutcome"], Awaitable[bool]]
CheckpointerOpen = Callable[
    ...,
    AbstractAsyncContextManager[AsyncSqliteSaver],
]


@dataclass(frozen=True, slots=True)
class TerminalOutcome:
    """Outcome passed to the durable-terminal callback before cleanup."""

    kind: TerminalKind
    run_id: str
    assistant_text: str | None
    error_code: str | None
    error_summary: str | None
    pending_approval: dict[str, Any] | None


def _safe_summary(error_code: str) -> str:
    return _SAFE_ERROR_SUMMARIES.get(error_code, "Agent run failed")


def _envelope(event: str, run_id: str, payload: dict[str, Any]) -> SseEvent:
    """Build and validate a typed SSE event envelope."""
    return parse_sse_event(
        {
            "event": event,
            "event_id": new_uuid(),
            "run_id": run_id,
            "timestamp": utc_now(),
            "payload": payload,
        }
    )


def _message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _ai_has_tool_calls(message: AIMessage) -> bool:
    calls = getattr(message, "tool_calls", None) or []
    return len(calls) > 0


def _extract_text_deltas_from_update(update: dict[str, Any]) -> list[str]:
    """Pull non-empty assistant text fragments from a graph updates chunk."""
    deltas: list[str] = []
    node_payload = update.get(DECISION_NODE_NAME)
    if not isinstance(node_payload, dict):
        return deltas
    messages = node_payload.get(MESSAGES_KEY) or []
    if not isinstance(messages, list):
        return deltas
    for item in messages:
        if not isinstance(item, AIMessage):
            continue
        if _ai_has_tool_calls(item):
            continue
        text = _message_text(item).strip()
        if text:
            deltas.append(text)
    return deltas


def _error_from_update(update: dict[str, Any]) -> str | None:
    for key, payload in update.items():
        if key == "__interrupt__":
            continue
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, str) and err.strip():
                return err
    return None


def _pending_approval_from_interrupt_chunk(
    chunk: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract compact approval projection from a LangGraph ``__interrupt__`` chunk."""
    raw = chunk.get("__interrupt__")
    if raw is None:
        return None
    items = raw if isinstance(raw, (list, tuple)) else (raw,)
    for item in items:
        value = getattr(item, "value", item)
        if isinstance(value, dict) and value:
            return value
    return None


def _pending_approval_from_snapshot(snap: Any) -> dict[str, Any] | None:
    """Read interrupt value from checkpoint snapshot tasks when stream ended."""
    if snap is None:
        return None
    tasks = getattr(snap, "tasks", None) or ()
    for task in tasks:
        interrupts = getattr(task, "interrupts", None) or ()
        for item in interrupts:
            value = getattr(item, "value", None)
            if isinstance(value, dict) and value:
                return value
    values = getattr(snap, "values", None)
    if isinstance(values, dict):
        pa = values.get("pending_approval")
        if isinstance(pa, dict) and pa:
            return pa
    return None


def _compile_with_checkpointer(
    bundle: AgentGraphBundle,
    saver: AsyncSqliteSaver,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Recompile the graph builder with a request-scoped checkpointer."""
    return bundle.compiled.builder.compile(checkpointer=saver)


async def stream_agent_run(
    *,
    run_id: str,
    user_text: str | None = None,
    resumed: bool = False,
    resume_value: Any | None = None,
    recent_context: Sequence[dict[str, Any]] | None = None,
    candidate_context: Sequence[dict[str, Any]] | None = None,
    attachment_ids: Sequence[str] | None = None,
    input_state: AgentGraphState | None = None,
    model: BaseChatModel | Runnable[Any, Any] | None = None,
    registry: ToolRegistry | None = None,
    tool_loop_limit: int | None = None,
    settings: Settings | None = None,
    sqlite_path: str | Path | None = None,
    graph_bundle: AgentGraphBundle | None = None,
    on_durable_terminal: DurableTerminalCallback | None = None,
    include_assistant_status: bool = True,
    assistant_status_message: str = "Generating reply",
    checkpointer_open: CheckpointerOpen | None = None,
) -> AsyncIterator[SseEvent]:
    """Run one Agent turn/resume and yield validated SSE events.

    Parameters
    ----------
    run_id:
        Durable agent-run id; used as LangGraph ``thread_id``.
    user_text:
        Required for a new turn when ``input_state`` is omitted.
    resumed:
        When True, continues the existing checkpoint thread.
    resume_value:
        Value for LangGraph ``Command(resume=...)`` after ``interrupt()``.
        Required for true interrupt resume; ignored on a fresh turn.
    on_durable_terminal:
        Awaitable called with :class:`TerminalOutcome` after the graph finishes
        and before checkpoint cleanup. Return ``True`` only when durable
        terminal state is committed; cleanup runs only then for completed/failed.
    checkpointer_open:
        Optional override of :func:`open_checkpointer` (tests inject spies).
    """
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")

    open_cm: CheckpointerOpen = (
        checkpointer_open if checkpointer_open is not None else open_checkpointer
    )
    bundle = graph_bundle or build_agent_graph(
        model=model,
        registry=registry,
        tool_loop_limit=tool_loop_limit,
        settings=settings,
    )
    config = thread_config(run_id)

    async with open_cm(sqlite_path, settings=settings) as saver:
        compiled = _compile_with_checkpointer(bundle, saver)

        yield _envelope(
            "run_started",
            run_id,
            {"state": "running", "resumed": resumed},
        )

        if include_assistant_status and assistant_status_message.strip():
            yield _envelope(
                "assistant_status",
                run_id,
                {"message": assistant_status_message.strip()},
            )

        graph_error: str | None = None
        assistant_parts: list[str] = []
        pending_approval: dict[str, Any] | None = None

        stream_input: AgentGraphState | Command[Any] | None
        if input_state is not None:
            stream_input = input_state
        elif resumed:
            # Interrupt resume must pass Command(resume=...); bare None re-pauses.
            if resume_value is not None:
                stream_input = Command(resume=resume_value)
            else:
                stream_input = None
        else:
            if user_text is None or user_text.strip() == "":
                raise ValueError("user_text is required for a new turn")
            stream_input = initial_graph_state(
                run_id=run_id,
                user_text=user_text,
                recent_context=recent_context,
                candidate_context=candidate_context,
                attachment_ids=attachment_ids,
            )

        try:
            stream = compiled.astream(
                stream_input,
                config,
                stream_mode="updates",
                version="v1",
            )
            async for chunk in stream:
                if not isinstance(chunk, dict):
                    continue
                interrupt_pa = _pending_approval_from_interrupt_chunk(chunk)
                if interrupt_pa is not None:
                    pending_approval = interrupt_pa
                    continue
                err = _error_from_update(chunk)
                if err is not None:
                    graph_error = err
                for delta in _extract_text_deltas_from_update(chunk):
                    assistant_parts.append(delta)
                    yield _envelope(
                        "text_delta",
                        run_id,
                        {"delta": delta},
                    )
        except Exception:
            graph_error = ERROR_AGENT_EXECUTION

        if graph_error is None:
            try:
                snap = await compiled.aget_state(config)
                values = snap.values if snap is not None else None
                if isinstance(values, dict):
                    err_val = values.get("error")
                    if isinstance(err_val, str) and err_val.strip():
                        graph_error = err_val
                if pending_approval is None:
                    pending_approval = _pending_approval_from_snapshot(snap)
            except Exception:
                pass

        assistant_text = "".join(assistant_parts) if assistant_parts else None

        if pending_approval is not None and graph_error is None:
            kind: TerminalKind = "interrupted"
            error_code: str | None = None
            error_summary: str | None = None
        elif graph_error is not None:
            kind = "failed"
            error_code = graph_error
            error_summary = _safe_summary(graph_error)
        else:
            kind = "completed"
            error_code = None
            error_summary = None

        outcome = TerminalOutcome(
            kind=kind,
            run_id=run_id,
            assistant_text=assistant_text,
            error_code=error_code,
            error_summary=error_summary,
            pending_approval=pending_approval,
        )

        durable_ok = True
        if on_durable_terminal is not None:
            durable_ok = bool(await on_durable_terminal(outcome))

        # Terminal cleanup: only this thread, only after durable commit, only
        # for completed|failed (interrupted checkpoints remain).
        if durable_ok and kind in ("completed", "failed"):
            await delete_run_checkpoint(saver, run_id)

        if kind == "failed":
            assert error_code is not None and error_summary is not None
            yield _envelope(
                "run_failed",
                run_id,
                {
                    "state": "failed",
                    "error_code": error_code,
                    "summary": error_summary,
                },
            )
        elif kind == "interrupted":
            # Interrupt framing is owned by chat services (03B); retain checkpoint.
            return
        else:
            yield _envelope(
                "run_completed",
                run_id,
                {"state": "completed"},
            )


__all__ = [
    "ERROR_AGENT_EXECUTION",
    "DurableTerminalCallback",
    "TerminalKind",
    "TerminalOutcome",
    "stream_agent_run",
]
