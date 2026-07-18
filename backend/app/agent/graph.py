"""One decision / one ToolNode LangGraph Agent (Plan 3 §7.5 / Master §12.1).

Topology:

* ``agent`` — single LLM decision node (direct answer or tool calls)
* ``tools`` — single ``ToolNode`` (injected registry tools only)

Tool calls loop back to ``agent``. Direct answers (no tool calls) terminate.
``tool_iteration_count`` increments before each ToolNode pass; a seventh pass
beyond ``TOOL_LOOP_LIMIT`` (default six) ends with a stable controlled failure.

Graph nodes perform no SQLAlchemy writes, HTTP transport, hidden transactions, or
provider construction. The factory may bind an injected model/tools; production
defaults to the seven production tools via :func:`production_registry`.
"""

from __future__ import annotations

import json
import re
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
from app.services.job_save_confirmation import (
    CANCEL_SUMMARY,
    message_has_clear_opt_out,
    message_is_obvious_jd,
    message_is_sole_http_url,
)
from app.tools.jobs import SAVE_JOB_NAME
from app.tools.profile import (
    COMMIT_PROFILE_DRAFT_NAME,
    ERROR_INVALID_PROFILE_UPDATE,
    PROPOSE_PROFILE_FROM_CV_NAME,
    PROPOSE_PROFILE_UPDATE_NAME,
)
from app.tools.registry import ToolRegistry, production_registry

# Stable controlled-failure code when the tool loop would exceed the limit.
ERROR_TOOL_LOOP_LIMIT_EXCEEDED: str = "TOOL_LOOP_LIMIT_EXCEEDED"
ERROR_PROFILE_UPDATE_FAILED: str = "PROFILE_UPDATE_FAILED"

# Fixed truthful fallback when an explicitly named save_job turn never executes.
NAMED_SAVE_JOB_NO_ACTION_TEXT: str = (
    "No action occurred: save_job was not executed, so no Job was created "
    "or reused."
)

# Fixed truthful fallback when passive obvious-JD repair never issues confirmation.
PASSIVE_JD_NO_CONFIRMATION_TEXT: str = (
    "No confirmation was created and the JD was not saved."
)

SAVE_JOB_SOURCE_CURRENT_MESSAGE: str = "current_message"
SAVE_JOB_CANCEL_OUTCOME: str = "cancelled"

# Exact registered token only (word boundary). Not NL paraphrase detection.
_SAVE_JOB_NAME_IN_REQUEST = re.compile(rf"\b{re.escape(SAVE_JOB_NAME)}\b")

_NAMED_SAVE_JOB_REPAIR_INSTRUCTION: str = (
    "Required repair: the user explicitly named the registered save_job tool. "
    "Call exactly one valid save_job with the user's url or text argument. "
    "Do not call any other tool. Do not answer with plain text. Do not claim "
    "that a Job was created, returned, or reused until a ToolResult exists."
)

_PASSIVE_JD_REPAIR_INSTRUCTION: str = (
    "Required repair: the current message is an obvious pasted job description. "
    "Call exactly one valid save_job with source='current_message' (optional "
    "bounded preview only). Do not call any other tool. Do not answer with "
    "plain text. Do not claim the JD was saved until a ToolResult exists."
)

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
    active_cv_context: dict[str, Any] | None
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


def _format_active_cv_context_block(
    active_cv_context: dict[str, Any] | None,
) -> str | None:
    """Serialize compact active-CV outline for the system prompt.

    Outline only: attachment identity, revision/hash, and section
    ids/headings/kinds/counts/ranges. Never bodies, entries, or chunks.
    Returns ``None`` when empty so the model is not fed a placeholder block.
    """
    if not isinstance(active_cv_context, dict) or not active_cv_context:
        return None
    try:
        payload = json.dumps(
            active_cv_context, ensure_ascii=False, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return None
    return (
        "Active CV outline only (identity, revision, section ids/headings/"
        "kinds/entry counts; never section bodies or chunks). When document "
        "evidence is needed beyond this outline, call read_active_cv with the "
        "narrowest mode; do not assume full CV text is already in context:\n"
        f"{payload}"
    )


def _build_model_messages(
    state: AgentGraphState,
    system_prompt: str,
) -> list[BaseMessage]:
    """Assemble system + candidate + active-CV outline + attachment refs + turn."""
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    candidate_block = _format_candidate_context_block(
        state.get("candidate_context")
    )
    if candidate_block is not None:
        messages.append(SystemMessage(content=candidate_block))
    active_cv_block = _format_active_cv_context_block(
        state.get("active_cv_context")
    )
    if active_cv_block is not None:
        messages.append(SystemMessage(content=active_cv_block))
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


def _tool_call_args(call: Any) -> dict[str, Any]:
    if isinstance(call, dict):
        args = call.get("args")
    else:
        args = getattr(call, "args", None)
    return args if isinstance(args, dict) else {}


def _is_current_message_source_args(args: dict[str, Any]) -> bool:
    return args.get("source") == SAVE_JOB_SOURCE_CURRENT_MESSAGE


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
    raw_messages = state.get(MESSAGES_KEY)
    messages: list[Any] = (
        list(raw_messages) if isinstance(raw_messages, list) else []
    )
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


def _has_invalid_profile_update_result(state: AgentGraphState) -> bool:
    """Return true when the latest profile update failed full-draft validation."""
    raw_messages = state.get(MESSAGES_KEY)
    messages: list[Any] = (
        list(raw_messages) if isinstance(raw_messages, list) else []
    )
    for item in reversed(messages):
        if isinstance(item, AIMessage) and _has_tool_calls(item):
            break
        if not isinstance(item, ToolMessage):
            continue
        if getattr(item, "name", None) != PROPOSE_PROFILE_UPDATE_NAME:
            continue
        payload = _parse_tool_result_payload(item.content)
        return (
            payload is not None
            and payload.get("ok") is False
            and payload.get("code") == ERROR_INVALID_PROFILE_UPDATE
        )
    return False


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content) if content is not None else ""


def _initiating_user_text(state: AgentGraphState) -> str:
    """Return the first HumanMessage text for this turn (initiating request)."""
    raw_messages = state.get(MESSAGES_KEY)
    messages: list[Any] = (
        list(raw_messages) if isinstance(raw_messages, list) else []
    )
    for item in messages:
        if isinstance(item, HumanMessage):
            return _message_text(item.content)
    return ""


def _request_names_save_job(
    user_text: str,
    *,
    save_job_registered: bool,
) -> bool:
    """True when the initiating text names the registered save_job tool."""
    # ponytail: exact-name gate is intentionally narrow — only the literal
    # registered save_job token in the initiating user text (word boundary), not
    # natural-language paraphrase detection. Acceptable while the verified F-04
    # failure surface is explicit named requests. If natural-language mutation
    # reliability later remains insufficient, replace this gate with a typed
    # mutation-intent contract rather than expanding keyword heuristics.
    if not save_job_registered or not user_text:
        return False
    return _SAVE_JOB_NAME_IN_REQUEST.search(user_text) is not None


def _turn_already_called_save_job(messages: Sequence[Any]) -> bool:
    for item in messages:
        if isinstance(item, AIMessage):
            for call in item.tool_calls or []:
                if _tool_call_name(call) == SAVE_JOB_NAME:
                    return True
        if (
            isinstance(item, ToolMessage)
            and getattr(item, "name", None) == SAVE_JOB_NAME
        ):
            return True
    return False


def _is_sole_save_job_call(message: AIMessage | None) -> bool:
    if message is None:
        return False
    calls = list(message.tool_calls or [])
    if len(calls) != 1:
        return False
    return _tool_call_name(calls[0]) == SAVE_JOB_NAME


def _is_sole_current_message_save_job_call(message: AIMessage | None) -> bool:
    """True when the AIMessage is exactly one save_job(source=current_message)."""
    if not _is_sole_save_job_call(message):
        return False
    assert message is not None
    calls = list(message.tool_calls or [])
    return _is_current_message_source_args(_tool_call_args(calls[0]))


def _turn_called_current_message_save_job(messages: Sequence[Any]) -> bool:
    for item in messages:
        if not isinstance(item, AIMessage):
            continue
        for call in item.tool_calls or []:
            if _tool_call_name(call) != SAVE_JOB_NAME:
                continue
            if _is_current_message_source_args(_tool_call_args(call)):
                return True
    return False


def _is_cancellation_payload(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    return (
        data.get("outcome") == SAVE_JOB_CANCEL_OUTCOME
        and data.get("committed") is False
    )


def _should_project_save_job_narration(
    *,
    named_save: bool,
    messages: Sequence[Any],
    payload: dict[str, Any],
) -> bool:
    """Project only for named, current-message, or cancellation ToolResults."""
    if named_save:
        return True
    if _turn_called_current_message_save_job(messages):
        return True
    return _is_cancellation_payload(payload)


def _latest_save_job_tool_result(
    messages: Sequence[Any],
) -> dict[str, Any] | None:
    """Return the newest validated save_job ToolResult payload, if any."""
    save_call_ids: set[str] = set()
    for item in messages:
        if not isinstance(item, AIMessage):
            continue
        for call in item.tool_calls or []:
            if _tool_call_name(call) != SAVE_JOB_NAME:
                continue
            call_id: Any
            if isinstance(call, dict):
                call_id = call.get("id")
            else:
                call_id = getattr(call, "id", None)
            if isinstance(call_id, str) and call_id.strip():
                save_call_ids.add(call_id)

    for item in reversed(list(messages)):
        if not isinstance(item, ToolMessage):
            continue
        name = getattr(item, "name", None)
        call_id = getattr(item, "tool_call_id", None)
        if name != SAVE_JOB_NAME and call_id not in save_call_ids:
            continue
        payload = _parse_tool_result_payload(item.content)
        if payload is None:
            continue
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            continue
        if "ok" not in payload:
            continue
        return payload
    return None


def _project_save_job_narration(payload: dict[str, Any]) -> str:
    """Project final assistant text from validated save_job ToolResult only."""
    summary = str(payload.get("summary") or "").strip()
    data = payload.get("data")
    data_dict = data if isinstance(data, dict) else {}
    outcome = data_dict.get("outcome")
    job_id = data_dict.get("job_id")
    ok = payload.get("ok") is True

    if not ok:
        code = payload.get("code")
        if summary:
            return summary
        if isinstance(code, str) and code.strip():
            return f"save_job failed ({code.strip()})."
        return "save_job failed."

    # Cancellation is never narrated as saved/created/reused.
    if outcome == SAVE_JOB_CANCEL_OUTCOME or _is_cancellation_payload(payload):
        return summary or CANCEL_SUMMARY

    if outcome == "returned":
        # Compact outcome wins over any model-like "created" language.
        base = summary or "Returned existing job for exact content match"
        if "created" in base.lower() and "return" not in base.lower():
            base = "Returned existing job for exact content match"
        if isinstance(job_id, str) and job_id.strip():
            return (
                f"{base} Existing job_id={job_id.strip()} was reused; "
                "no new Job was created."
            )
        return f"{base} No new Job was created."

    if outcome == "created":
        base = summary or "Saved job description"
        if isinstance(job_id, str) and job_id.strip():
            return f"{base} job_id={job_id.strip()}."
        return base

    if outcome == "retried":
        base = summary or "Retried failed job in place after exact content match"
        if isinstance(job_id, str) and job_id.strip():
            return f"{base} job_id={job_id.strip()}."
        return base

    if summary:
        return summary
    return "save_job completed."


def _normalize_ai_response(response_raw: Any) -> AIMessage:
    if isinstance(response_raw, AIMessage):
        return response_raw
    content = getattr(response_raw, "content", response_raw)
    text = content if isinstance(content, str) else str(content)
    return AIMessage(content=text)


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
        Tool registry. Defaults to :func:`production_registry` (seven tools).
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
    save_job_available = SAVE_JOB_NAME in set(tool_names)

    def decision_node(state: AgentGraphState) -> dict[str, Any]:
        """LLM decision: append AIMessage; set controlled error if loop exhausted."""
        if state.get("error"):
            return {}

        if _has_invalid_profile_update_result(state):
            return {"error": ERROR_PROFILE_UPDATE_FAILED}

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

        raw_messages = state.get(MESSAGES_KEY)
        turn_messages: list[Any] = (
            list(raw_messages) if isinstance(raw_messages, list) else []
        )
        user_text = _initiating_user_text(state)
        # Deterministic order: clear opt-out → positive exact-name → sole URL /
        # obvious passive JD. Opt-out suppresses both save repairs.
        clear_opt_out = message_has_clear_opt_out(user_text)
        named_save = (not clear_opt_out) and _request_names_save_job(
            user_text,
            save_job_registered=save_job_available,
        )
        save_job_already = _turn_already_called_save_job(turn_messages)

        # After a durable save_job ToolResult on named / current-message /
        # cancellation paths, narrate only from validated summary/outcome.
        if save_job_already:
            payload = _latest_save_job_tool_result(turn_messages)
            if payload is not None and _should_project_save_job_narration(
                named_save=named_save,
                messages=turn_messages,
                payload=payload,
            ):
                return {
                    MESSAGES_KEY: [
                        AIMessage(content=_project_save_job_narration(payload))
                    ]
                }

        prompt_messages = _build_model_messages(state, system_prompt)
        response_raw = chat.invoke(prompt_messages)
        response = _normalize_ai_response(response_raw)

        # Explicitly named save_job: plain-text first answer is discarded once;
        # repair must be exactly one valid sole save_job call or fixed no-action.
        if named_save and not save_job_already:
            if not _has_tool_calls(response):
                # Discard unsupported mutation prose; one bounded repair only.
                repair_messages = list(prompt_messages) + [
                    SystemMessage(content=_NAMED_SAVE_JOB_REPAIR_INSTRUCTION)
                ]
                response = _normalize_ai_response(chat.invoke(repair_messages))
            if not _is_sole_save_job_call(response):
                return {
                    MESSAGES_KEY: [
                        AIMessage(content=NAMED_SAVE_JOB_NO_ACTION_TEXT)
                    ]
                }
        # Passive obvious-JD: only after opt-out and positive exact-name lose;
        # sole URL is excluded; one repair after plain-text miss only.
        elif (
            save_job_available
            and not clear_opt_out
            and not save_job_already
            and not message_is_sole_http_url(user_text)
            and message_is_obvious_jd(user_text)
        ):
            if not _has_tool_calls(response):
                repair_messages = list(prompt_messages) + [
                    SystemMessage(content=_PASSIVE_JD_REPAIR_INSTRUCTION)
                ]
                response = _normalize_ai_response(chat.invoke(repair_messages))
                if not _is_sole_current_message_save_job_call(response):
                    return {
                        MESSAGES_KEY: [
                            AIMessage(content=PASSIVE_JD_NO_CONFIRMATION_TEXT)
                        ]
                    }
            # First decision already has tool calls: leave normal validation.

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
    active_cv_context: dict[str, Any] | None = None,
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
        "active_cv_context": active_cv_context,
        "attachment_ids": list(attachment_ids or ()),
        "pending_approval": None,
        "tool_iteration_count": tool_iteration_count,
        "error": error,
    }
    if set(state) != AGENT_STATE_FIELDS:
        raise RuntimeError("AgentGraphState field set drift vs AgentState")
    return state
