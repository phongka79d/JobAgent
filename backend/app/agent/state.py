"""Bounded Agent state for Plan 3 LangGraph runs.

Exact fields follow Plan 3 §7.2 / Master §12.3. Large PDF/JD bodies are never
stored in state — only attachment/document IDs and structured slices. History
in state is the bounded recent window plus the current-turn messages, never
full conversation history.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, TypedDict, cast

# Exact Plan 3 / Master source keys (order matches Plan 3 listing).
AGENT_STATE_KEYS: Final[tuple[str, ...]] = (
    "conversation_id",
    "run_id",
    "messages_for_this_turn",
    "recent_context",
    "candidate_context",
    "attachment_ids",
    "pending_approval",
    "tool_iteration_count",
    "error",
)

AGENT_STATE_KEY_SET: Final[frozenset[str]] = frozenset(AGENT_STATE_KEYS)

# Keys that must never appear on state, candidate_context, or nested payloads
# as raw document bodies (ID references are allowed under attachment_ids).
FORBIDDEN_STATE_BODY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "pdf_body",
        "pdf_bytes",
        "pdf_text",
        "jd_body",
        "jd_text",
        "job_description_body",
        "job_description_text",
        "cv_body",
        "cv_text",
        "resume_body",
        "resume_text",
        "raw_document",
        "raw_content",
        "raw_text",
        "full_text",
        "document_body",
        "document_text",
        "document_bytes",
        "file_bytes",
        "content_bytes",
        "unbounded_history",
        "full_history",
        "all_messages",
    }
)

# Soft ceiling for serialized string values nested in state (not chat content
# itself — chat content is already repository-bounded). Used to reject accidental
# large document dumps into candidate_context / error / pending_approval.
_MAX_NESTED_STRING_LEN: Final[int] = 8_192
_MAX_RECENT_CONTEXT_LEN: Final[int] = 100
_MAX_TURN_MESSAGES: Final[int] = 32
_MAX_ATTACHMENT_IDS: Final[int] = 32
_MAX_WALK_NODES: Final[int] = 400


class AgentState(TypedDict):
    """Bounded per-run Agent state (Plan 3 exact fields)."""

    conversation_id: str
    run_id: str
    messages_for_this_turn: list[Any]
    recent_context: list[Any]
    candidate_context: dict[str, Any] | None
    attachment_ids: list[str]
    pending_approval: dict[str, Any] | None
    tool_iteration_count: int
    error: dict[str, Any] | None


class AgentStateError(ValueError):
    """Agent state failed closed validation (no payload values in message)."""


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _key_is_forbidden_body(key: str) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return True
    if normalized in FORBIDDEN_STATE_BODY_KEYS:
        return True
    # Partial token matches for smuggled body field names.
    body_tokens = (
        "pdf_body",
        "jd_body",
        "cv_body",
        "resume_body",
        "raw_document",
        "document_body",
        "full_history",
        "unbounded_history",
    )
    return any(token in normalized for token in body_tokens)


def _walk_reject_forbidden(
    value: Any,
    *,
    depth: int,
    nodes: list[int],
    path: str,
) -> None:
    nodes[0] += 1
    if nodes[0] > _MAX_WALK_NODES:
        raise AgentStateError("state payload too large")
    if depth > 8:
        raise AgentStateError("state payload too deep")

    if value is None or isinstance(value, bool | int | float):
        return
    if isinstance(value, str):
        if len(value) > _MAX_NESTED_STRING_LEN:
            raise AgentStateError("state string value exceeds bound")
        return
    if isinstance(value, Mapping):
        for raw_key, raw_val in value.items():
            if not isinstance(raw_key, str):
                raise AgentStateError("state keys must be strings")
            if _key_is_forbidden_body(raw_key):
                raise AgentStateError("raw document body field forbidden in state")
            _walk_reject_forbidden(
                raw_val,
                depth=depth + 1,
                nodes=nodes,
                path=f"{path}.{raw_key}",
            )
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _walk_reject_forbidden(
                item,
                depth=depth + 1,
                nodes=nodes,
                path=path,
            )
        return
    if isinstance(value, (bytes, bytearray)):
        raise AgentStateError("raw document bytes forbidden in state")
    # Allow simple non-mapping objects only at leaves that already passed
    # structured conversion; reject unknown complex types.
    raise AgentStateError("unsupported state value type")


def validate_agent_state(state: Mapping[str, Any]) -> AgentState:
    """Validate exact keys and reject raw document bodies / unbounded history.

    Returns a shallow-normalized ``AgentState``. Does not mutate the input
    mapping beyond reading validated values.
    """
    if not isinstance(state, Mapping):
        raise AgentStateError("state must be a mapping")

    keys = frozenset(state.keys())
    missing = AGENT_STATE_KEY_SET - keys
    extra = keys - AGENT_STATE_KEY_SET
    if missing:
        raise AgentStateError("missing required state keys")
    if extra:
        raise AgentStateError("unexpected state keys")

    conversation_id = state["conversation_id"]
    run_id = state["run_id"]
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise AgentStateError("invalid conversation_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise AgentStateError("invalid run_id")

    messages_for_this_turn = state["messages_for_this_turn"]
    recent_context = state["recent_context"]
    if not isinstance(messages_for_this_turn, list):
        raise AgentStateError("messages_for_this_turn must be a list")
    if not isinstance(recent_context, list):
        raise AgentStateError("recent_context must be a list")
    if len(messages_for_this_turn) > _MAX_TURN_MESSAGES:
        raise AgentStateError("messages_for_this_turn exceeds bound")
    if len(recent_context) > _MAX_RECENT_CONTEXT_LEN:
        raise AgentStateError("recent_context exceeds bound")

    candidate_context = state["candidate_context"]
    if candidate_context is not None and not isinstance(candidate_context, dict):
        raise AgentStateError("candidate_context must be a dict or None")

    attachment_ids = state["attachment_ids"]
    if not isinstance(attachment_ids, list):
        raise AgentStateError("attachment_ids must be a list")
    if len(attachment_ids) > _MAX_ATTACHMENT_IDS:
        raise AgentStateError("attachment_ids exceeds bound")
    safe_attachment_ids: list[str] = []
    for item in attachment_ids:
        if not isinstance(item, str) or not item.strip():
            raise AgentStateError("attachment_ids must be non-empty strings")
        # IDs only — reject values that look like embedded document bodies.
        if len(item) > 128:
            raise AgentStateError("attachment id too long")
        if "\n" in item or "\r" in item:
            raise AgentStateError("attachment id must be a single-line id")
        safe_attachment_ids.append(item.strip())

    pending_approval = state["pending_approval"]
    if pending_approval is not None and not isinstance(pending_approval, dict):
        raise AgentStateError("pending_approval must be a dict or None")

    tool_iteration_count = state["tool_iteration_count"]
    if not isinstance(tool_iteration_count, int) or isinstance(
        tool_iteration_count, bool
    ):
        raise AgentStateError("tool_iteration_count must be an int")
    if tool_iteration_count < 0:
        raise AgentStateError("tool_iteration_count must be non-negative")

    error = state["error"]
    if error is not None and not isinstance(error, dict):
        raise AgentStateError("error must be a dict or None")

    # Nested forbidden-body scan (excluding free-text chat content fields that
    # are already length-capped by the conversation repository).
    nodes = [0]
    for nested in (
        candidate_context,
        pending_approval,
        error,
        messages_for_this_turn,
        recent_context,
    ):
        if nested is not None:
            _walk_reject_forbidden(nested, depth=0, nodes=nodes, path="state")

    return AgentState(
        conversation_id=conversation_id.strip(),
        run_id=run_id.strip(),
        messages_for_this_turn=list(messages_for_this_turn),
        recent_context=list(recent_context),
        candidate_context=(
            dict(cast(dict[str, Any], candidate_context))
            if candidate_context is not None
            else None
        ),
        attachment_ids=safe_attachment_ids,
        pending_approval=(
            dict(cast(dict[str, Any], pending_approval))
            if pending_approval is not None
            else None
        ),
        tool_iteration_count=tool_iteration_count,
        error=dict(cast(dict[str, Any], error)) if error is not None else None,
    )


def initial_agent_state(
    *,
    conversation_id: str,
    run_id: str,
    messages_for_this_turn: Sequence[Any] | None = None,
    recent_context: Sequence[Any] | None = None,
    candidate_context: Mapping[str, Any] | None = None,
    attachment_ids: Sequence[str] | None = None,
    pending_approval: Mapping[str, Any] | None = None,
    tool_iteration_count: int = 0,
    error: Mapping[str, Any] | None = None,
) -> AgentState:
    """Build a validated initial ``AgentState`` with source-defined fields only."""
    raw: dict[str, Any] = {
        "conversation_id": conversation_id,
        "run_id": run_id,
        "messages_for_this_turn": list(messages_for_this_turn or ()),
        "recent_context": list(recent_context or ()),
        "candidate_context": (
            dict(candidate_context) if candidate_context is not None else None
        ),
        "attachment_ids": list(attachment_ids or ()),
        "pending_approval": (
            dict(pending_approval) if pending_approval is not None else None
        ),
        "tool_iteration_count": tool_iteration_count,
        "error": dict(error) if error is not None else None,
    }
    return validate_agent_state(raw)


def state_references_large_content_by_id_only(state: Mapping[str, Any]) -> bool:
    """Return True when large content is referenced only via attachment IDs.

    Used by tests and callers that must assert no raw PDF/JD body field is
    present. Requires a previously validated state shape.
    """
    validate_agent_state(state)
    # Attachment IDs are the only approved large-content reference surface.
    for key in state:
        if _key_is_forbidden_body(key):
            return False
    candidate = state.get("candidate_context")
    if isinstance(candidate, Mapping):
        for key in candidate:
            if _key_is_forbidden_body(str(key)):
                return False
            # Explicit document body ref patterns.
            if _normalize_key(str(key)) in {
                "pdf",
                "cv",
                "jd",
                "document",
                "resume",
            }:
                val = candidate[key]
                if isinstance(val, str) and len(val) > 256:
                    return False
    return True
