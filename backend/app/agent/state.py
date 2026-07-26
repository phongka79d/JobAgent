"""Exact Agent runtime state (Plan 3 §7.4 / Master §12.3).

``AgentState`` exposes exactly eleven fields. Large documents stay out of state
and are referenced by attachment IDs only. ``active_cv_context`` is a compact
outline projection (never section bodies or chunks). No classifier, long-term
memory, or second-agent fields are permitted.
"""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import TypeAdapter, ValidationError

from app.schemas.common import UuidStr

_uuid_adapter = TypeAdapter(UuidStr)

# Exact runtime field set — single owner for Agent input/graph state shape.
AGENT_STATE_FIELDS: frozenset[str] = frozenset(
    {
        "conversation_id",
        "profile_id",
        "run_id",
        "messages_for_this_turn",
        "recent_context",
        "candidate_context",
        "active_cv_context",
        "attachment_ids",
        "selected_job_id",
        "pending_approval",
        "tool_iteration_count",
        "error",
    }
)

class ContextMessage(TypedDict):
    """Compact chat row projection for the model: role + text only.

    No raw document bodies, CV/JD payloads, or structured long-form blobs.
    ``id`` is the durable message UUID when loaded from persistence.
    """

    id: str
    role: str
    content: str


class AgentState(TypedDict):
    """LangGraph / runner state with exactly the eleven named fields.

    - ``conversation_id`` is the explicit durable conversation owner.
    - ``profile_id`` is that conversation's explicit durable profile owner.
    - ``run_id`` is the durable agent-run id and future LangGraph ``thread_id``.
    - ``messages_for_this_turn`` is the current turn only (not prior history).
    - ``recent_context`` is a budget-bounded prior window (see ``context``).
    - ``candidate_context`` is a compact approved profile/preferences projection
      (empty when no active profile; never raw CV text or drafts).
    - ``active_cv_context`` is a compact active-CV outline (ids/headings/kinds/
      counts/ranges only) or null; never section bodies or chunks.
    - ``attachment_ids`` are UUID references only — never raw file contents.
    - ``pending_approval`` is the compact interruption projection or null.
    - ``tool_iteration_count`` tracks ToolNode passes (limit owned by settings).
    - ``error`` is a stable controlled failure code or null.
    """

    conversation_id: str
    profile_id: str
    run_id: str
    messages_for_this_turn: list[ContextMessage]
    recent_context: list[ContextMessage]
    candidate_context: list[dict[str, Any]]
    active_cv_context: dict[str, Any] | None
    attachment_ids: list[str]
    selected_job_id: str | None
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: str | None


def agent_state_field_names() -> frozenset[str]:
    """Return the exact AgentState key set (for tests and callers)."""
    return AGENT_STATE_FIELDS


def build_initial_agent_state(
    *,
    run_id: str,
    conversation_id: str,
    profile_id: str,
    messages_for_this_turn: list[ContextMessage] | None = None,
    recent_context: list[ContextMessage] | None = None,
    candidate_context: list[dict[str, Any]] | None = None,
    active_cv_context: dict[str, Any] | None = None,
    attachment_ids: list[str] | None = None,
    selected_job_id: str | None = None,
    pending_approval: dict[str, Any] | None = None,
    tool_iteration_count: int = 0,
    error: str | None = None,
) -> AgentState:
    """Construct a valid state for one durable conversation/profile owner."""
    if not isinstance(run_id, str) or run_id.strip() == "":
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(conversation_id, str) or conversation_id.strip() == "":
        raise ValueError("conversation_id must be a non-empty string")
    if not isinstance(profile_id, str) or profile_id.strip() == "":
        raise ValueError("profile_id must be a non-empty string")
    if tool_iteration_count < 0:
        raise ValueError("tool_iteration_count must be >= 0")
    if selected_job_id is not None:
        try:
            selected_job_id = str(_uuid_adapter.validate_python(selected_job_id))
        except ValidationError as exc:
            raise ValueError("selected_job_id must be a UUID v4 or null") from exc

    state: AgentState = {
        "conversation_id": conversation_id.strip(),
        "profile_id": profile_id.strip(),
        "run_id": run_id,
        "messages_for_this_turn": list(messages_for_this_turn or ()),
        "recent_context": list(recent_context or ()),
        "candidate_context": list(candidate_context or ()),
        "active_cv_context": active_cv_context,
        "attachment_ids": list(attachment_ids or ()),
        "selected_job_id": selected_job_id,
        "pending_approval": pending_approval,
        "tool_iteration_count": tool_iteration_count,
        "error": error,
    }
    if set(state) != AGENT_STATE_FIELDS:
        raise RuntimeError("AgentState field set drift")
    return state
