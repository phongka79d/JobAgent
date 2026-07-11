"""Single controlled LangGraph Agent: one decision node, one ToolNode, loop guard.

Topology (Plan 3 §7.3 / Master §12.1 + interrupt support):

    START -> load_context -> agent_decision
    agent_decision -> tools (ToolNode) -> increment_iteration -> await_approval
        -> agent_decision
    agent_decision -> await_approval -> persist_response -> cleanup_checkpoint
        -> END

Rules:
- At most six tool-loop iterations per turn (default ``TOOL_LOOP_LIMIT``).
- Stop **before** a seventh tool execution with ``TOOL_LOOP_LIMIT_EXCEEDED``.
- The LLM never owns retries; application routing owns the guard.
- Structured tool failures are not converted into a successful run outcome.
- Approval uses the production ``await_approval`` / ``request_human_approval``
  interrupt seam (same run/thread identity across resume).
- Production tools come only from the injected registry / tool list (empty by
  default). Synthetic tools belong in tests only.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, Final, Literal, NotRequired, Protocol, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from typing_extensions import TypedDict

from app.agent.prompt import (
    DOMAIN_REDIRECT_MESSAGE,
    build_system_prompt,
    evaluate_domain_policy,
)
from app.agent.state import AgentState
from app.services.shopaikey_chat import (
    DecisionResult,
    ObservedToolCall,
    ShopAIKeyChatError,
)
from app.tools.registry import ToolRegistry, create_empty_production_registry

# Exact controlled failure codes (stable; never embed secrets or raw payloads).
TOOL_LOOP_LIMIT_EXCEEDED: Final[str] = "TOOL_LOOP_LIMIT_EXCEEDED"
TOOL_EXECUTION_FAILED: Final[str] = "TOOL_EXECUTION_FAILED"
AGENT_DECISION_FAILED: Final[str] = "AGENT_DECISION_FAILED"
DEFAULT_TOOL_LOOP_LIMIT: Final[int] = 6

# Graph node names (single StateGraph; no multi-agent / handoff paths).
NODE_LOAD_CONTEXT: Final[str] = "load_context"
NODE_AGENT_DECISION: Final[str] = "agent_decision"
NODE_TOOLS: Final[str] = "tools"
NODE_INCREMENT_ITERATION: Final[str] = "increment_iteration"
NODE_AWAIT_APPROVAL: Final[str] = "await_approval"
NODE_PERSIST_RESPONSE: Final[str] = "persist_response"
NODE_CLEANUP_CHECKPOINT: Final[str] = "cleanup_checkpoint"

RouteAfterDecision = Literal["tools", "await_approval"]
RouteAfterApproval = Literal["agent_decision", "persist_response"]


def _append_messages(
    left: list[Any] | None,
    right: list[Any] | None,
) -> list[Any]:
    """Append-only reducer for turn messages (ToolNode returns only new tools)."""
    return list(left or ()) + list(right or ())


class AgentGraphState(TypedDict):
    """Graph state aligned with Plan 3 AgentState field names.

    ``messages_for_this_turn`` uses an append reducer so ``ToolNode`` can emit
    only new ``ToolMessage`` values without dropping prior AI/human messages.
    """

    conversation_id: str
    run_id: str
    messages_for_this_turn: Annotated[list[Any], _append_messages]
    recent_context: list[Any]
    candidate_context: dict[str, Any] | None
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: dict[str, Any] | None
    # Internal/runtime flags (not part of durable AgentState contract).
    final_assistant_text: NotRequired[str | None]
    run_outcome: NotRequired[str | None]
    domain_redirect: NotRequired[bool]
    context_loaded: NotRequired[bool]
    response_persisted: NotRequired[bool]
    checkpoint_cleaned: NotRequired[bool]
    # Resume value returned by request_human_approval / await_approval (internal).
    approval_resume_value: NotRequired[Any]


class DecisionPort(Protocol):
    """Minimal decision surface (production adapter or test fake)."""

    def invoke_decision(
        self,
        messages: Sequence[object],
        *,
        tools: Sequence[object] | None = None,
    ) -> DecisionResult: ...


DecisionFn = Callable[
    [Sequence[object], Sequence[object] | None],
    DecisionResult,
]


def _error_payload(code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code}
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            payload[key] = value
        else:
            payload[key] = str(type(value).__name__)
    return payload


def sanitize_approval_payload(
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a small JSON-safe approval payload for interrupt surfaces."""
    out: dict[str, Any] = {"kind": "approval_required"}
    if not isinstance(payload, Mapping):
        return out
    for key, item in payload.items():
        if not isinstance(key, str) or not key:
            continue
        safe_key = key[:64]
        if safe_key == "kind" and isinstance(item, str) and item.strip():
            out["kind"] = item.strip()[:64]
            continue
        if isinstance(item, bool) or item is None:
            out[safe_key] = item
        elif isinstance(item, int) and not isinstance(item, bool):
            out[safe_key] = item
        elif isinstance(item, float):
            out[safe_key] = item
        elif isinstance(item, str):
            if len(item) <= 512:
                out[safe_key] = item
        else:
            out[safe_key] = type(item).__name__
    return out


def request_human_approval(
    payload: Mapping[str, Any] | None = None,
) -> Any:
    """Production approval interrupt seam for guarded write/commit paths.

    Calls LangGraph ``interrupt()`` with a sanitized payload so the run pauses
    on the current thread until the application resumes with
    ``Command(resume=...)``. Domain write tools (Plan 4+) must use this helper
    rather than inventing a second graph or interrupt path.

    On the first entry into a task, raises a graph interrupt. On resume of the
    same task, returns the client-provided resume value.
    """
    return interrupt(sanitize_approval_payload(payload))


def _latest_user_text(messages: Sequence[Any]) -> str:
    for item in reversed(list(messages)):
        if isinstance(item, HumanMessage):
            content = item.content
            return content if isinstance(content, str) else str(content)
        if isinstance(item, Mapping):
            role = str(item.get("role", "")).lower()
            if role == "user":
                content = item.get("content", "")
                return content if isinstance(content, str) else str(content)
    return ""


def _as_base_messages(messages: Sequence[Any]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for item in messages:
        if isinstance(item, BaseMessage):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            role = str(item.get("role", "user")).lower()
            content = item.get("content", "")
            text = content if isinstance(content, str) else str(content)
            if role in {"assistant", "ai"}:
                out.append(AIMessage(content=text))
            elif role == "tool":
                tool_call_id = str(item.get("tool_call_id") or item.get("id") or "unknown")
                out.append(
                    ToolMessage(
                        content=text,
                        tool_call_id=tool_call_id,
                        name=str(item.get("name") or "tool"),
                    )
                )
            else:
                out.append(HumanMessage(content=text))
            continue
        out.append(HumanMessage(content=str(item)))
    return out


def _ai_message_from_decision(result: DecisionResult) -> AIMessage:
    tool_calls: list[dict[str, Any]] = []
    for index, call in enumerate(result.tool_calls):
        call_id = call.tool_call_id or f"call_{index}"
        args = call.arguments if isinstance(call.arguments, Mapping) else {}
        if not isinstance(args, Mapping):
            args = {"value": args}
        tool_calls.append(
            {
                "name": call.name,
                "args": dict(args),
                "id": call_id,
                "type": "tool_call",
            }
        )
    return AIMessage(content=result.content or "", tool_calls=tool_calls)


def _count_pending_tool_calls(messages: Sequence[Any]) -> int:
    for item in reversed(list(messages)):
        if isinstance(item, AIMessage):
            return len(item.tool_calls or ())
        if isinstance(item, Mapping) and str(item.get("role", "")).lower() in {
            "assistant",
            "ai",
        }:
            raw = item.get("tool_calls") or ()
            return len(raw) if isinstance(raw, Sequence) else 0
    return 0


def _last_ai_has_tool_calls(messages: Sequence[Any]) -> bool:
    return _count_pending_tool_calls(messages) > 0


def _recent_tool_messages(messages: Sequence[Any]) -> list[ToolMessage]:
    """Tool messages after the latest AIMessage that requested tools."""
    collected: list[ToolMessage] = []
    for item in reversed(list(messages)):
        if isinstance(item, ToolMessage):
            collected.append(item)
            continue
        if isinstance(item, AIMessage):
            break
    collected.reverse()
    return collected


def _tool_batch_has_failure(messages: Sequence[Any]) -> ToolMessage | None:
    for msg in _recent_tool_messages(messages):
        status = getattr(msg, "status", None)
        if status == "error":
            return msg
        content = msg.content
        text = content if isinstance(content, str) else str(content)
        # Structured failure payloads from tools (application convention).
        if text.startswith("ERROR:") or '"ok": false' in text.lower() or '"ok":false' in text.lower():
            return msg
    return None


# Marker convention for tool results that stage graph-level approval interrupt
# without calling interrupt() inside the tool body.
_APPROVAL_REQUIRED_PREFIX: Final[str] = "APPROVAL_REQUIRED:"


def _approval_request_from_tool_messages(
    messages: Sequence[Any],
) -> dict[str, Any] | None:
    """Extract a pending-approval payload from recent tool messages, if any."""
    for msg in _recent_tool_messages(messages):
        content = msg.content
        text = content if isinstance(content, str) else str(content)
        if not text.startswith(_APPROVAL_REQUIRED_PREFIX):
            continue
        raw = text[len(_APPROVAL_REQUIRED_PREFIX) :].strip()
        tool_name = getattr(msg, "name", None)
        base: dict[str, Any] = {"kind": "approval_required"}
        if isinstance(tool_name, str) and tool_name:
            base["tool"] = tool_name[:128]
        if not raw:
            return sanitize_approval_payload(base)
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                base["detail"] = raw[:512]
                return sanitize_approval_payload(base)
            if isinstance(parsed, Mapping):
                merged = {**base, **dict(parsed)}
                return sanitize_approval_payload(merged)
        base["detail"] = raw[:512]
        return sanitize_approval_payload(base)
    return None


def has_successful_run_outcome(state: Mapping[str, Any]) -> bool:
    """True only when the graph recorded a successful completion without error."""
    if state.get("error") is not None:
        return False
    outcome = state.get("run_outcome")
    return outcome == "completed"


def build_agent_graph(
    *,
    tools: Sequence[Any] | None = None,
    registry: ToolRegistry | None = None,
    decision: DecisionPort | DecisionFn | None = None,
    tool_loop_limit: int = DEFAULT_TOOL_LOOP_LIMIT,
    system_prompt: str | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Build the single controlled Agent ``StateGraph``.

    Parameters
    ----------
    tools:
        Explicit tool list for ``ToolNode`` / decision binding. When omitted,
        tools are taken from ``registry`` (empty production registry by default).
    registry:
        Optional registration seam. Ignored for tool selection when ``tools`` is
        provided. Never auto-loads later-phase domain tools.
    decision:
        Injectable decision port (``ShopAIKeyChatAdapter`` or test fake).
        Required for a runnable graph that calls the model.
    tool_loop_limit:
        Maximum ToolNode visits per turn (default 6). The seventh attempt is
        blocked with ``TOOL_LOOP_LIMIT_EXCEEDED`` before tool execution.
    system_prompt:
        Optional override; otherwise built from domain policy + candidate context.
    checkpointer:
        Optional LangGraph checkpointer (e.g. ``AsyncSqliteSaver``). Owned by
        the per-run lifecycle (02D); ``None`` keeps in-memory-only invocation.

    Returns
    -------
    Compiled LangGraph runnable (``invoke`` / ``ainvoke``).
    """
    if tool_loop_limit < 1:
        raise ValueError("tool_loop_limit must be positive")

    active_registry = registry if registry is not None else create_empty_production_registry()
    if tools is None:
        bound_tools: list[Any] = list(active_registry.list_tools())
    else:
        bound_tools = list(tools)

    decision_port = decision

    def load_context(state: AgentGraphState) -> dict[str, Any]:
        """Prepare bounded prompt context; apply domain redirect with zero tools."""
        if state.get("error") is not None:
            return {"context_loaded": True}

        user_text = _latest_user_text(state.get("messages_for_this_turn") or ())
        attachment_ids = list(state.get("attachment_ids") or ())
        policy = evaluate_domain_policy(user_text, attachment_ids=attachment_ids)
        updates: dict[str, Any] = {
            "context_loaded": True,
            "domain_redirect": policy.redirect,
        }

        if policy.redirect:
            updates["final_assistant_text"] = DOMAIN_REDIRECT_MESSAGE
            updates["messages_for_this_turn"] = [
                AIMessage(content=DOMAIN_REDIRECT_MESSAGE, tool_calls=[])
            ]
            updates["run_outcome"] = "completed"
            return updates

        # Turn messages should already be BaseMessage instances (see
        # initial_graph_state). No append conversion here — append reducer
        # would duplicate entries.
        return updates

    def agent_decision(state: AgentGraphState) -> dict[str, Any]:
        """LLM decision node — may emit tool calls or final text."""
        # Controlled failures and domain redirects never re-enter the model.
        if state.get("error") is not None:
            return {}
        if state.get("domain_redirect"):
            return {}
        if state.get("run_outcome") == "completed" and not _last_ai_has_tool_calls(
            state.get("messages_for_this_turn") or ()
        ):
            return {}

        # Structured tool failure: do not let a later model turn invent success.
        failed_tool = _tool_batch_has_failure(state.get("messages_for_this_turn") or ())
        if failed_tool is not None:
            return {
                "error": _error_payload(
                    TOOL_EXECUTION_FAILED,
                    tool_name=getattr(failed_tool, "name", None),
                ),
                "run_outcome": "failed",
                "final_assistant_text": None,
            }

        iteration = int(state.get("tool_iteration_count") or 0)
        if decision_port is None:
            return {
                "error": _error_payload(
                    AGENT_DECISION_FAILED, reason="no_decision_port"
                ),
                "run_outcome": "failed",
            }

        prompt = system_prompt or build_system_prompt(
            candidate_context=state.get("candidate_context"),
        )
        turn_msgs = _as_base_messages(state.get("messages_for_this_turn") or ())
        recent = state.get("recent_context") or []
        provider_messages: list[object] = [{"role": "system", "content": prompt}]
        for item in recent:
            if isinstance(item, Mapping):
                provider_messages.append(
                    {
                        "role": str(item.get("role", "user")),
                        "content": str(item.get("content", "")),
                    }
                )
        for msg in turn_msgs:
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                provider_messages.append({"role": "user", "content": content})
            elif isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                entry: dict[str, Any] = {"role": "assistant", "content": content}
                if msg.tool_calls:
                    entry["tool_calls"] = list(msg.tool_calls)
                provider_messages.append(entry)
            elif isinstance(msg, ToolMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                provider_messages.append(
                    {
                        "role": "tool",
                        "content": content,
                        "tool_call_id": msg.tool_call_id,
                        "name": msg.name,
                    }
                )

        try:
            invoke_decision = getattr(decision_port, "invoke_decision", None)
            if callable(invoke_decision):
                result = invoke_decision(
                    provider_messages,
                    tools=bound_tools or None,
                )
            else:
                result = cast(DecisionFn, decision_port)(
                    provider_messages, bound_tools or None
                )
        except ShopAIKeyChatError as err:
            return {
                "error": _error_payload(
                    AGENT_DECISION_FAILED, provider_code=err.code.value
                ),
                "run_outcome": "failed",
            }
        except Exception:
            return {
                "error": _error_payload(AGENT_DECISION_FAILED),
                "run_outcome": "failed",
            }

        if not isinstance(result, DecisionResult):
            return {
                "error": _error_payload(
                    AGENT_DECISION_FAILED, reason="invalid_result"
                ),
                "run_outcome": "failed",
            }

        # Enforce loop ceiling before any seventh tool execution.
        if result.tool_calls and iteration >= tool_loop_limit:
            return {
                "error": _error_payload(
                    TOOL_LOOP_LIMIT_EXCEEDED, limit=tool_loop_limit
                ),
                "run_outcome": "failed",
                "final_assistant_text": None,
                "messages_for_this_turn": [
                    AIMessage(content=result.content or "", tool_calls=[])
                ],
            }

        ai_message = _ai_message_from_decision(result)
        updates: dict[str, Any] = {"messages_for_this_turn": [ai_message]}
        if not result.tool_calls:
            updates["final_assistant_text"] = result.content or ""
            updates["run_outcome"] = "completed"
        return updates

    def route_after_decision(state: AgentGraphState) -> RouteAfterDecision:
        if state.get("error") is not None:
            return "await_approval"
        if state.get("domain_redirect"):
            return "await_approval"
        if state.get("run_outcome") == "failed":
            return "await_approval"
        messages = state.get("messages_for_this_turn") or ()
        if _last_ai_has_tool_calls(messages):
            iteration = int(state.get("tool_iteration_count") or 0)
            if iteration >= tool_loop_limit:
                return "await_approval"
            return "tools"
        return "await_approval"

    def increment_iteration(state: AgentGraphState) -> dict[str, Any]:
        """Count one ToolNode visit; surface structured tool failures."""
        new_count = int(state.get("tool_iteration_count") or 0) + 1
        updates: dict[str, Any] = {"tool_iteration_count": new_count}
        failed = _tool_batch_has_failure(state.get("messages_for_this_turn") or ())
        if failed is not None:
            updates["error"] = _error_payload(
                TOOL_EXECUTION_FAILED,
                tool_name=getattr(failed, "name", None),
            )
            updates["run_outcome"] = "failed"
            updates["final_assistant_text"] = None
            return updates
        # Tool outcomes may stage a pending approval for the await_approval node
        # without calling interrupt() themselves (marker-based seam).
        if not state.get("pending_approval"):
            staged = _approval_request_from_tool_messages(
                state.get("messages_for_this_turn") or ()
            )
            if staged is not None:
                updates["pending_approval"] = staged
                updates["run_outcome"] = None
                updates["final_assistant_text"] = None
        return updates

    def await_approval(state: AgentGraphState) -> dict[str, Any]:
        """Production graph approval interrupt seam.

        When ``pending_approval`` is set, pause via ``request_human_approval``
        (LangGraph ``interrupt``) on this thread. Resume clears pending approval
        and records the resume value for subsequent commit/decision steps.
        No-ops when no approval is pending so the normal complete path is unchanged.
        """
        if state.get("error") is not None:
            return {}
        pending = state.get("pending_approval")
        if not pending:
            return {}
        payload = pending if isinstance(pending, Mapping) else None
        resume_value = request_human_approval(
            dict(payload) if payload is not None else None
        )
        return {
            "pending_approval": None,
            "approval_resume_value": resume_value,
        }

    def route_after_approval(state: AgentGraphState) -> RouteAfterApproval:
        if state.get("error") is not None:
            return "persist_response"
        if state.get("domain_redirect"):
            return "persist_response"
        if state.get("run_outcome") == "failed":
            return "persist_response"
        messages = state.get("messages_for_this_turn") or ()
        # After tools (+ optional approval), continue the decision loop when the
        # latest AI message requested tools and tool results are present.
        if _last_ai_has_tool_calls(messages) and _recent_tool_messages(messages):
            return "agent_decision"
        return "persist_response"

    def persist_response(state: AgentGraphState) -> dict[str, Any]:
        """Persistence seam: normalize terminal outcome (02D owns durable writes).

        Failed or loop-limited runs never report ``run_outcome=completed``.
        """
        error = state.get("error")
        if error is not None:
            return {
                "response_persisted": True,
                "run_outcome": "failed",
                "final_assistant_text": None,
            }
        # Domain redirect already set completed.
        if state.get("run_outcome") == "completed":
            return {"response_persisted": True}
        # Final assistant text from last AI message without tool calls.
        text = state.get("final_assistant_text")
        if text is None:
            for item in reversed(list(state.get("messages_for_this_turn") or ())):
                if isinstance(item, AIMessage) and not (item.tool_calls or ()):
                    content = item.content
                    text = content if isinstance(content, str) else str(content)
                    break
        return {
            "response_persisted": True,
            "final_assistant_text": text,
            "run_outcome": "completed" if text is not None else state.get("run_outcome"),
        }

    def cleanup_checkpoint(state: AgentGraphState) -> dict[str, Any]:
        """Checkpoint cleanup seam — real deletion lands in lifecycle (02D)."""
        del state  # seam only; no checkpoint handle in this task
        return {"checkpoint_cleaned": True}

    graph = StateGraph(AgentGraphState)
    graph.add_node(NODE_LOAD_CONTEXT, load_context)
    graph.add_node(NODE_AGENT_DECISION, agent_decision)
    # Single ToolNode path; empty tool list is valid (no production domain tools).
    graph.add_node(
        NODE_TOOLS,
        ToolNode(
            bound_tools,
            messages_key="messages_for_this_turn",
            handle_tool_errors=True,
        ),
    )
    graph.add_node(NODE_INCREMENT_ITERATION, increment_iteration)
    graph.add_node(NODE_AWAIT_APPROVAL, await_approval)
    graph.add_node(NODE_PERSIST_RESPONSE, persist_response)
    graph.add_node(NODE_CLEANUP_CHECKPOINT, cleanup_checkpoint)

    graph.add_edge(START, NODE_LOAD_CONTEXT)
    graph.add_edge(NODE_LOAD_CONTEXT, NODE_AGENT_DECISION)
    graph.add_conditional_edges(
        NODE_AGENT_DECISION,
        route_after_decision,
        {
            "tools": NODE_TOOLS,
            "await_approval": NODE_AWAIT_APPROVAL,
        },
    )
    graph.add_edge(NODE_TOOLS, NODE_INCREMENT_ITERATION)
    graph.add_edge(NODE_INCREMENT_ITERATION, NODE_AWAIT_APPROVAL)
    graph.add_conditional_edges(
        NODE_AWAIT_APPROVAL,
        route_after_approval,
        {
            "agent_decision": NODE_AGENT_DECISION,
            "persist_response": NODE_PERSIST_RESPONSE,
        },
    )
    graph.add_edge(NODE_PERSIST_RESPONSE, NODE_CLEANUP_CHECKPOINT)
    graph.add_edge(NODE_CLEANUP_CHECKPOINT, END)

    return graph.compile(checkpointer=checkpointer)


def initial_graph_state(
    *,
    conversation_id: str,
    run_id: str,
    user_text: str,
    recent_context: Sequence[Any] | None = None,
    candidate_context: Mapping[str, Any] | None = None,
    attachment_ids: Sequence[str] | None = None,
    tool_iteration_count: int = 0,
) -> AgentGraphState:
    """Build a minimal invoke payload for the compiled graph."""
    return AgentGraphState(
        conversation_id=conversation_id,
        run_id=run_id,
        messages_for_this_turn=[HumanMessage(content=user_text)],
        recent_context=list(recent_context or ()),
        candidate_context=dict(candidate_context) if candidate_context is not None else None,
        attachment_ids=list(attachment_ids or ()),
        pending_approval=None,
        tool_iteration_count=tool_iteration_count,
        error=None,
        final_assistant_text=None,
        run_outcome=None,
        domain_redirect=False,
        context_loaded=False,
        response_persisted=False,
        checkpoint_cleaned=False,
    )


def graph_state_to_agent_state(state: Mapping[str, Any]) -> AgentState:
    """Project graph state onto the durable AgentState field set."""
    from app.agent.state import validate_agent_state

    # Serialize messages to plain mappings for durable validation.
    raw_messages = state.get("messages_for_this_turn") or []
    serializable: list[Any] = []
    for item in raw_messages:
        if isinstance(item, HumanMessage):
            serializable.append(
                {
                    "role": "user",
                    "content": item.content
                    if isinstance(item.content, str)
                    else str(item.content),
                }
            )
        elif isinstance(item, AIMessage):
            serializable.append(
                {
                    "role": "assistant",
                    "content": item.content
                    if isinstance(item.content, str)
                    else str(item.content),
                    "tool_calls": list(item.tool_calls or ()),
                }
            )
        elif isinstance(item, ToolMessage):
            serializable.append(
                {
                    "role": "tool",
                    "content": item.content
                    if isinstance(item.content, str)
                    else str(item.content),
                    "name": item.name,
                    "tool_call_id": item.tool_call_id,
                }
            )
        else:
            serializable.append(item)

    payload = {
        "conversation_id": state["conversation_id"],
        "run_id": state["run_id"],
        "messages_for_this_turn": serializable,
        "recent_context": list(state.get("recent_context") or ()),
        "candidate_context": state.get("candidate_context"),
        "attachment_ids": list(state.get("attachment_ids") or ()),
        "pending_approval": state.get("pending_approval"),
        "tool_iteration_count": int(state.get("tool_iteration_count") or 0),
        "error": state.get("error"),
    }
    return validate_agent_state(payload)


__all__ = [
    "AGENT_DECISION_FAILED",
    "DEFAULT_TOOL_LOOP_LIMIT",
    "NODE_AGENT_DECISION",
    "NODE_AWAIT_APPROVAL",
    "NODE_CLEANUP_CHECKPOINT",
    "NODE_INCREMENT_ITERATION",
    "NODE_LOAD_CONTEXT",
    "NODE_PERSIST_RESPONSE",
    "NODE_TOOLS",
    "TOOL_EXECUTION_FAILED",
    "TOOL_LOOP_LIMIT_EXCEEDED",
    "AgentGraphState",
    "DecisionPort",
    "build_agent_graph",
    "graph_state_to_agent_state",
    "has_successful_run_outcome",
    "initial_graph_state",
    "request_human_approval",
    "sanitize_approval_payload",
]

# Re-export ObservedToolCall for type checkers that bind decision fakes.
_ = ObservedToolCall
