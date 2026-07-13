"""Exact Agent runtime state (Plan 3 §7.4 / Master §12.3).

``AgentState`` exposes exactly nine fields. Large documents stay out of state
and are referenced by attachment IDs only. No classifier, long-term memory, or
second-agent fields are permitted.
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.db.models.chat import CONVERSATION_ID

# Exact runtime field set — single owner for Agent input/graph state shape.
AGENT_STATE_FIELDS: frozenset[str] = frozenset(
    {
        "conversation_id",
        "run_id",
        "messages_for_this_turn",
        "recent_context",
        "candidate_context",
        "attachment_ids",
        "pending_approval",
        "tool_iteration_count",
        "error",
    }
)

# Singleton conversation identity for every Agent turn (Master §6.1 / §12.3).
AGENT_CONVERSATION_ID: str = CONVERSATION_ID


class ContextMessage(TypedDict):
    """Compact chat row projection for the model: role + text only.

    No raw document bodies, CV/JD payloads, or structured long-form blobs.
    ``id`` is the durable message UUID when loaded from persistence.
    """

    id: str
    role: str
    content: str


class AgentState(TypedDict):
    """LangGraph / runner state with exactly the nine named fields.

    - ``conversation_id`` is always the singleton ``main``.
    - ``run_id`` is the durable agent-run id and future LangGraph ``thread_id``.
    - ``messages_for_this_turn`` is the current turn only (not prior history).
    - ``recent_context`` is a budget-bounded prior window (see ``context``).
    - ``candidate_context`` is empty in Phase 2 (Plan 4 fills a compact projection).
    - ``attachment_ids`` are UUID references only — never raw file contents.
    - ``pending_approval`` is the compact interruption projection or null.
    - ``tool_iteration_count`` tracks ToolNode passes (limit owned by settings).
    - ``error`` is a stable controlled failure code or null.
    """

    conversation_id: str
    run_id: str
    messages_for_this_turn: list[ContextMessage]
    recent_context: list[ContextMessage]
    candidate_context: list[dict[str, Any]]
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: str | None


def agent_state_field_names() -> frozenset[str]:
    """Return the exact AgentState key set (for tests and callers)."""
    return AGENT_STATE_FIELDS


def build_initial_agent_state(
    *,
    run_id: str,
    messages_for_this_turn: list[ContextMessage] | None = None,
    recent_context: list[ContextMessage] | None = None,
    attachment_ids: list[str] | None = None,
    pending_approval: dict[str, Any] | None = None,
    tool_iteration_count: int = 0,
    error: str | None = None,
) -> AgentState:
    """Construct a valid initial ``AgentState`` with singleton conversation.

    Always sets ``conversation_id`` to ``main`` and ``candidate_context`` to an
    empty list. Does not accept raw document bodies or extra state keys.
    """
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")
    if tool_iteration_count < 0:
        raise ValueError("tool_iteration_count must be >= 0")

    state: AgentState = {
        "conversation_id": AGENT_CONVERSATION_ID,
        "run_id": run_id,
        "messages_for_this_turn": list(messages_for_this_turn or ()),
        "recent_context": list(recent_context or ()),
        "candidate_context": [],
        "attachment_ids": list(attachment_ids or ()),
        "pending_approval": pending_approval,
        "tool_iteration_count": tool_iteration_count,
        "error": error,
    }
    if set(state) != AGENT_STATE_FIELDS:
        raise RuntimeError("AgentState field set drift")
    return state
