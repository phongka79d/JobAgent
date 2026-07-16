"""One decision / one ToolNode LangGraph Agent (Plan 3 §7.5 / Master §12.1).

Topology:

* ``agent`` — single LLM decision node (direct answer or tool calls)
* ``tools`` — single ``ToolNode`` (injected registry tools only)

Tool calls loop back to ``agent``. Direct answers (no tool calls) terminate.
``tool_iteration_count`` increments before each ToolNode pass; a seventh pass
beyond ``TOOL_LOOP_LIMIT`` (default six) ends with a stable controlled failure.

Graph nodes perform no SQLAlchemy writes, HTTP transport, hidden transactions, or
provider construction. The factory may bind an injected model/tools; production
defaults to the six production tools via :func:`production_registry`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from app.adapters.shopaikey_chat import bind_chat_tools, build_shopaikey_chat
from app.agent.prompt import build_system_prompt
from app.agent.state import AGENT_CONVERSATION_ID, AGENT_STATE_FIELDS
from app.core.settings import Settings, get_settings
from app.db.models.profiles import PROFILE_DRAFT_ID
from app.tools.profile import (
    COMMIT_PROFILE_DRAFT_NAME,
    PROPOSE_PROFILE_FROM_CV_NAME,
    PROPOSE_PROFILE_UPDATE_NAME,
)
from app.tools.registry import ToolRegistry, production_registry

# Stable controlled-failure code when the tool loop would exceed the limit.
ERROR_TOOL_LOOP_LIMIT_EXCEEDED: str = "TOOL_LOOP_LIMIT_EXCEEDED"

# Graph node names — exactly one decision node and one ToolNode.
DECISION_NODE_NAME: str = "agent"
TOOLS_NODE_NAME: str = "tools"

# State channel ToolNode reads/writes (matches AgentState field name).
MESSAGES_KEY: str = "messages_for_this_turn"

RouteTarget = Literal["tools", "__end__"]


class AgentGraphState(TypedDict):
    """Runtime graph state: exact AgentState keys with message reducer.

    ``messages_for_this_turn`` holds LangChain messages for the current turn
    (Human / AI / Tool). Other fields mirror ``app.agent.state.AgentState``.
    """

    conversation_id: str
    run_id: str
    messages_for_this_turn: Annotated[list[AnyMessage], add_messages]
    recent_context: list[dict[str, Any]]
    candidate_context: list[dict[str, Any]]
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: str | None


class AgentGraphBundle:
    """Compiled graph plus inspection handles for the single ToolNode topology."""

    __slots__ = (
        "compiled",
        "tool_node",
        "decision_node_name",
        "tools_node_name",
        "tool_loop_limit",
        "registry",
    )

    def __init__(
        self,
        *,
        compiled: CompiledStateGraph[Any, Any, Any, Any],
        tool_node: ToolNode,
        tool_loop_limit: int,
        registry: ToolRegistry,
    ) -> None:
        self.compiled = compiled
        self.tool_node = tool_node
        self.decision_node_name = DECISION_NODE_NAME
        self.tools_node_name = TOOLS_NODE_NAME
        self.tool_loop_limit = tool_loop_limit
        self.registry = registry


class _CountingToolNode(ToolNode):
    """ToolNode that increments ``tool_iteration_count`` before each pass.

    When the next count would exceed ``tool_loop_limit``, returns a controlled
    failure without invoking tools (defense in depth; the decision route also
    guards).
    """

    def __init__(
        self,
        tools: Sequence[Any],
        *,
        tool_loop_limit: int,
        messages_key: str = MESSAGES_KEY,
    ) -> None:
        super().__init__(tools, messages_key=messages_key)
        self.tool_loop_limit = tool_loop_limit

    def invoke(
        self,
        input: dict[str, Any] | Any,
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        state = cast("dict[str, Any]", input)
        next_count = int(state.get("tool_iteration_count", 0)) + 1
        if next_count > self.tool_loop_limit:
            return {
                "tool_iteration_count": next_count,
                "error": ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
            }
        raw = super().invoke(input, config, **kwargs)
        return _merge_tool_output(raw, next_count)

    async def ainvoke(
        self,
        input: dict[str, Any] | Any,
        config: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        state = cast("dict[str, Any]", input)
        next_count = int(state.get("tool_iteration_count", 0)) + 1
        if next_count > self.tool_loop_limit:
            return {
                "tool_iteration_count": next_count,
                "error": ERROR_TOOL_LOOP_LIMIT_EXCEEDED,
            }
        raw = await super().ainvoke(input, config, **kwargs)
        return _merge_tool_output(raw, next_count)


def _merge_tool_output(raw: Any, next_count: int) -> dict[str, Any]:
    """Attach the incremented iteration count to ToolNode output."""
    if isinstance(raw, dict):
        return {**raw, "tool_iteration_count": next_count}
    if isinstance(raw, list):
        return {MESSAGES_KEY: raw, "tool_iteration_count": next_count}
    return {"tool_iteration_count": next_count}


def _coerce_message(item: Any) -> BaseMessage:
    """Convert a state message item to a LangChain ``BaseMessage``."""
    if isinstance(item, BaseMessage):
        return item
    if isinstance(item, dict):
        role = str(item.get("role", "user"))
        content = item.get("content", "")
        text = content if isinstance(content, str) else str(content)
        if role == "assistant":
            return AIMessage(content=text)
        if role == "system":
            return SystemMessage(content=text)
        if role == "tool":
            tool_call_id = str(item.get("tool_call_id") or item.get("id") or "")
            return ToolMessage(content=text, tool_call_id=tool_call_id)
        return HumanMessage(content=text)
    raise TypeError(f"Unsupported message type for agent graph: {type(item)!r}")


def _format_candidate_context_block(
    candidate_context: Sequence[dict[str, Any]] | None,
) -> str | None:
    """Serialize compact approved candidate cards for the system prompt.

    Returns ``None`` when empty so the model is not fed a placeholder block.
    Never includes raw CV bytes or storage paths (caller responsibility).
    """
    cards = list(candidate_context or ())
    if not cards:
        return None
    # json is stdlib; keep import local to avoid module-level cost for graphs
    # that never carry candidate context in pure unit tests.
    import json

    try:
        payload = json.dumps(cards, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    return (
        "Approved candidate memory (structured profile and preferences only; "
        "never invent a different approved profile; unapproved drafts are not "
        "included):\n"
        f"{payload}"
    )


def _format_attachment_ids_block(
    attachment_ids: Sequence[str] | None,
) -> str | None:
    """Serialize this-turn staged attachment UUID refs for the model.

    Returns ``None`` when empty. Never includes filenames, paths, or file bytes.
    ``propose_profile_from_cv`` requires an exact ``attachment_id``; without this
    block the model only sees prose like "I uploaded my CV" and invents IDs.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for raw in attachment_ids or ():
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)
    if not ids:
        return None
    lines = "\n".join(f"- {attachment_id}" for attachment_id in ids)
    return (
        "Staged attachment IDs for this turn (UUID references only). "
        "When calling propose_profile_from_cv, pass one of these exact values "
        "as attachment_id. Never invent IDs, paths, or placeholders such as "
        "'current' or 'latest':\n"
        f"{lines}"
    )


def _build_model_messages(
    state: AgentGraphState,
    system_prompt: str,
) -> list[BaseMessage]:
    """Assemble system + candidate + attachment refs + context + turn messages."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    candidate_block = _format_candidate_context_block(
        state.get("candidate_context")
    )
    if candidate_block is not None:
        messages.append(SystemMessage(content=candidate_block))
    attachment_block = _format_attachment_ids_block(state.get("attachment_ids"))
    if attachment_block is not None:
        messages.append(SystemMessage(content=attachment_block))
    for ctx_item in state.get("recent_context") or []:
        messages.append(_coerce_message(ctx_item))
    for turn_item in state.get("messages_for_this_turn") or []:
        messages.append(_coerce_message(turn_item))
    return messages


def _last_ai_message(state: AgentGraphState) -> AIMessage | None:
    messages = state.get("messages_for_this_turn") or []
    for item in reversed(messages):
        if isinstance(item, AIMessage):
            return item
    return None


def _has_tool_calls(message: AIMessage | None) -> bool:
    if message is None:
        return False
    calls = getattr(message, "tool_calls", None) or []
    return len(calls) > 0


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        name = call.get("name")
        return name if isinstance(name, str) else ""
    name = getattr(call, "name", None)
    return name if isinstance(name, str) else ""


def _parse_tool_result_payload(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_result_indicates_profile_draft(payload: dict[str, Any]) -> bool:
    """True when a propose/update tool left an unapproved draft to commit."""
    if payload.get("ok") is not True:
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    kind = data.get("kind")
    if kind in {"new_draft", "existing_draft", "current_draft", "active_context"}:
        return True
    return data.get("draft_id") == PROFILE_DRAFT_ID


def _turn_already_requested_commit(messages: Sequence[Any]) -> bool:
    for item in messages:
        if not isinstance(item, AIMessage):
            continue
        for call in item.tool_calls or []:
            if _tool_call_name(call) == COMMIT_PROFILE_DRAFT_NAME:
                return True
    return False


def _auto_commit_after_draft_tool(
    state: AgentGraphState,
    *,
    commit_available: bool,
) -> AIMessage | None:
    """Force commit_profile_draft after a successful draft propose/update.

    Plan 4 flow is propose → commit interrupt. Live models often narrate the
    draft and skip commit, so the UI never gets Save Profile. Deterministically
    chain one commit tool call when a draft-producing tool just succeeded.
    """
    if not commit_available:
        return None
    messages = list(state.get(MESSAGES_KEY) or [])
    if not messages or _turn_already_requested_commit(messages):
        return None

    draft_ready = False
    for item in reversed(messages):
        if isinstance(item, AIMessage) and _has_tool_calls(item):
            # Stop at the previous model decision boundary.
            break
        if not isinstance(item, ToolMessage):
            continue
        tool_name = getattr(item, "name", None)
        if tool_name not in {
            PROPOSE_PROFILE_FROM_CV_NAME,
            PROPOSE_PROFILE_UPDATE_NAME,
        }:
            continue
        payload = _parse_tool_result_payload(item.content)
        if payload is not None and _tool_result_indicates_profile_draft(payload):
            draft_ready = True
            break

    if not draft_ready:
        return None

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": COMMIT_PROFILE_DRAFT_NAME,
                "args": {"draft_id": PROFILE_DRAFT_ID},
                "id": f"auto-commit-{uuid4()}",
                "type": "tool_call",
            }
        ],
    )


def _as_base_chat_model(
    model: BaseChatModel | Runnable[Any, Any],
) -> BaseChatModel:
    """Narrow injected model for ``bind_chat_tools`` (Runnable after re-bind)."""
    if isinstance(model, BaseChatModel):
        return model
    raise TypeError(
        "model must be a BaseChatModel before tool binding; "
        f"got {type(model)!r}"
    )


def build_agent_graph(
    *,
    model: BaseChatModel | Runnable[Any, Any] | None = None,
    registry: ToolRegistry | None = None,
    tool_loop_limit: int | None = None,
    settings: Settings | None = None,
) -> AgentGraphBundle:
    """Build the single-Agent StateGraph with injected model and registry.

    Parameters
    ----------
    model:
        Chat model used by the decision node. When omitted, constructed via the
        ShopAIKey adapter (not inside a graph node). Tests inject fakes.
    registry:
        Tool registry. Defaults to :func:`production_registry` (six tools).
    tool_loop_limit:
        Max ToolNode passes per turn (default ``Settings.TOOL_LOOP_LIMIT`` = 6).
    settings:
        Optional settings for default model/limit resolution only.
    """
    if tool_loop_limit is not None:
        limit = tool_loop_limit
    else:
        cfg_for_limit = settings if settings is not None else get_settings()
        limit = int(cfg_for_limit.TOOL_LOOP_LIMIT)
    if limit < 1:
        raise ValueError("tool_loop_limit must be >= 1")

    reg = registry if registry is not None else production_registry()
    tools = reg.list_tools()
    tool_names = reg.tool_names()
    system_prompt = build_system_prompt(tool_names)

    chat: BaseChatModel | Runnable[Any, Any]
    if model is None:
        cfg = settings if settings is not None else get_settings()
        chat = bind_chat_tools(build_shopaikey_chat(cfg), tools)
    elif tools:
        chat = bind_chat_tools(_as_base_chat_model(model), tools)
    else:
        chat = model

    tool_node = _CountingToolNode(
        tools,
        tool_loop_limit=limit,
        messages_key=MESSAGES_KEY,
    )

    commit_available = COMMIT_PROFILE_DRAFT_NAME in set(tool_names)

    def decision_node(state: AgentGraphState) -> dict[str, Any]:
        """LLM decision: append AIMessage; set controlled error if loop exhausted."""
        if state.get("error"):
            return {}

        # After a successful draft propose/update, always open Save Profile.
        auto_commit = _auto_commit_after_draft_tool(
            state,
            commit_available=commit_available,
        )
        if auto_commit is not None:
            updates: dict[str, Any] = {MESSAGES_KEY: [auto_commit]}
            count = int(state.get("tool_iteration_count") or 0)
            if count >= limit:
                updates["error"] = ERROR_TOOL_LOOP_LIMIT_EXCEEDED
            return updates

        prompt_messages = _build_model_messages(state, system_prompt)
        response_raw = chat.invoke(prompt_messages)
        if isinstance(response_raw, AIMessage):
            response: AIMessage = response_raw
        else:
            content = getattr(response_raw, "content", response_raw)
            text = content if isinstance(content, str) else str(content)
            response = AIMessage(content=text)

        updates = {MESSAGES_KEY: [response]}
        count = int(state.get("tool_iteration_count") or 0)
        if _has_tool_calls(response) and count >= limit:
            # Seventh (or further) pass would exceed the configured limit.
            updates["error"] = ERROR_TOOL_LOOP_LIMIT_EXCEEDED
        return updates

    def route_after_decision(state: AgentGraphState) -> RouteTarget:
        if state.get("error"):
            return "__end__"
        last = _last_ai_message(state)
        if _has_tool_calls(last):
            count = int(state.get("tool_iteration_count") or 0)
            if count >= limit:
                return "__end__"
            return "tools"
        return "__end__"

    builder: StateGraph[AgentGraphState, None, AgentGraphState, AgentGraphState] = (
        StateGraph(AgentGraphState)
    )
    builder.add_node(DECISION_NODE_NAME, decision_node)
    builder.add_node(TOOLS_NODE_NAME, tool_node)
    builder.add_edge(START, DECISION_NODE_NAME)
    builder.add_conditional_edges(
        DECISION_NODE_NAME,
        route_after_decision,
        {TOOLS_NODE_NAME: TOOLS_NODE_NAME, END: END},
    )
    builder.add_edge(TOOLS_NODE_NAME, DECISION_NODE_NAME)

    compiled = builder.compile()
    return AgentGraphBundle(
        compiled=compiled,
        tool_node=tool_node,
        tool_loop_limit=limit,
        registry=reg,
    )


def initial_graph_state(
    *,
    run_id: str,
    user_text: str,
    recent_context: Sequence[dict[str, Any]] | None = None,
    candidate_context: Sequence[dict[str, Any]] | None = None,
    attachment_ids: Sequence[str] | None = None,
    tool_iteration_count: int = 0,
    error: str | None = None,
) -> AgentGraphState:
    """Build a valid starting graph state for one user turn (no DB access)."""
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")
    state: AgentGraphState = {
        "conversation_id": AGENT_CONVERSATION_ID,
        "run_id": run_id,
        "messages_for_this_turn": [HumanMessage(content=user_text)],
        "recent_context": list(recent_context or ()),
        "candidate_context": list(candidate_context or ()),
        "attachment_ids": list(attachment_ids or ()),
        "pending_approval": None,
        "tool_iteration_count": tool_iteration_count,
        "error": error,
    }
    if set(state) != AGENT_STATE_FIELDS:
        raise RuntimeError("AgentGraphState field set drift vs AgentState")
    return state
