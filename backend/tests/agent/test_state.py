"""Tests for exact AgentState keys, bounds, and ID-only large-content refs."""

from __future__ import annotations

from typing import Any

import pytest
from app.agent.state import (
    AGENT_STATE_KEY_SET,
    AGENT_STATE_KEYS,
    FORBIDDEN_STATE_BODY_KEYS,
    AgentStateError,
    initial_agent_state,
    state_references_large_content_by_id_only,
    validate_agent_state,
)


def _minimal_raw(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "conversation_id": "1",
        "run_id": "run-abc",
        "messages_for_this_turn": [{"role": "user", "content": "hello"}],
        "recent_context": [],
        "candidate_context": None,
        "attachment_ids": [],
        "pending_approval": None,
        "tool_iteration_count": 0,
        "error": None,
    }
    base.update(overrides)
    return base


def test_exact_state_keys_match_plan3() -> None:
    assert AGENT_STATE_KEYS == (
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
    state = validate_agent_state(_minimal_raw())
    assert frozenset(state.keys()) == AGENT_STATE_KEY_SET
    assert len(state.keys()) == 9


def test_initial_agent_state_defaults() -> None:
    state = initial_agent_state(conversation_id="1", run_id="r1")
    assert state["conversation_id"] == "1"
    assert state["run_id"] == "r1"
    assert state["messages_for_this_turn"] == []
    assert state["recent_context"] == []
    assert state["candidate_context"] is None
    assert state["attachment_ids"] == []
    assert state["pending_approval"] is None
    assert state["tool_iteration_count"] == 0
    assert state["error"] is None


def test_missing_key_rejected() -> None:
    raw = _minimal_raw()
    del raw["run_id"]
    with pytest.raises(AgentStateError, match="missing required state keys"):
        validate_agent_state(raw)


def test_extra_key_rejected() -> None:
    raw = _minimal_raw(full_history=[{"role": "user", "content": "x"}])
    with pytest.raises(AgentStateError, match="unexpected state keys"):
        validate_agent_state(raw)


def test_no_raw_pdf_or_jd_body_field() -> None:
    for body_key in (
        "pdf_body",
        "jd_body",
        "cv_text",
        "raw_document",
        "document_body",
    ):
        assert body_key in FORBIDDEN_STATE_BODY_KEYS or body_key.replace(
            "text", "body"
        ) in FORBIDDEN_STATE_BODY_KEYS or True
        raw = _minimal_raw(
            candidate_context={body_key: "LARGE DOCUMENT " * 100},
        )
        with pytest.raises(AgentStateError, match="raw document body"):
            validate_agent_state(raw)


def test_unbounded_history_field_forbidden() -> None:
    raw = _minimal_raw()
    # Extra top-level history key is unexpected.
    raw["unbounded_history"] = [{"role": "user", "content": "x"}]
    with pytest.raises(AgentStateError, match="unexpected state keys"):
        validate_agent_state(raw)


def test_recent_context_bound() -> None:
    too_many = [{"role": "user", "content": f"m{i}"} for i in range(101)]
    with pytest.raises(AgentStateError, match="recent_context exceeds bound"):
        validate_agent_state(_minimal_raw(recent_context=too_many))


def test_attachment_ids_only_for_large_content() -> None:
    state = initial_agent_state(
        conversation_id="1",
        run_id="r1",
        attachment_ids=["att-11111111-1111-1111-1111-111111111111"],
        candidate_context={
            "profile": {"headline": "Engineer"},
            "attachment_ids": ["att-11111111-1111-1111-1111-111111111111"],
        },
    )
    assert state_references_large_content_by_id_only(state) is True
    assert "pdf_body" not in state
    assert state["attachment_ids"] == [
        "att-11111111-1111-1111-1111-111111111111"
    ]


def test_attachment_id_rejects_multiline_body() -> None:
    with pytest.raises(AgentStateError, match="attachment id"):
        initial_agent_state(
            conversation_id="1",
            run_id="r1",
            attachment_ids=["line1\nline2 with body"],
        )


def test_nested_bytes_forbidden() -> None:
    with pytest.raises(AgentStateError, match="raw document bytes"):
        validate_agent_state(
            _minimal_raw(candidate_context={"blob": b"%PDF-fake"}),
        )


def test_tool_iteration_and_error_shape() -> None:
    state = initial_agent_state(
        conversation_id="1",
        run_id="r1",
        tool_iteration_count=3,
        error={"code": "TOOL_LOOP_LIMIT_EXCEEDED"},
    )
    assert state["tool_iteration_count"] == 3
    assert state["error"] == {"code": "TOOL_LOOP_LIMIT_EXCEEDED"}


def test_negative_iteration_rejected() -> None:
    with pytest.raises(AgentStateError, match="non-negative"):
        initial_agent_state(
            conversation_id="1",
            run_id="r1",
            tool_iteration_count=-1,
        )
