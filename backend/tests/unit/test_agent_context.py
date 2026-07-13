"""Unit tests for AgentState shape and bounded recent-context selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, get_type_hints

import pytest
from app.agent.context import (
    RECENT_CONTEXT_CHAR_BUDGET,
    RECENT_CONTEXT_MAX_MESSAGES,
    apply_recent_context_budget,
    empty_candidate_context,
)
from app.agent.state import (
    AGENT_CONVERSATION_ID,
    AGENT_STATE_FIELDS,
    AgentState,
    ContextMessage,
    agent_state_field_names,
    build_initial_agent_state,
)
from app.db.models.chat import CONVERSATION_ID

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeMsg:
    id: str
    role: str
    content: str
    # Deliberately available but must never enter context projections.
    structured_payload: dict[str, Any] | None = None
    raw_content: str | None = None
    raw_cv: str | None = None
    raw_jd: str | None = None


def _msg(i: int, *, role: str = "user", content: str | None = None) -> _FakeMsg:
    return _FakeMsg(
        id=f"00000000-0000-4000-8000-{i:012d}",
        role=role,
        content=content if content is not None else f"message-{i}",
    )


# ---------------------------------------------------------------------------
# Exact AgentState shape
# ---------------------------------------------------------------------------


def test_agent_state_has_exactly_nine_named_fields() -> None:
    expected = {
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
    assert AGENT_STATE_FIELDS == expected
    assert agent_state_field_names() == expected
    assert len(AGENT_STATE_FIELDS) == 9
    # TypedDict annotations expose the same nine keys.
    hints = get_type_hints(AgentState)
    assert set(hints) == expected


def test_build_initial_state_singleton_conversation_and_run_identity() -> None:
    run_id = "11111111-1111-4111-8111-111111111111"
    state = build_initial_agent_state(run_id=run_id)
    assert state["conversation_id"] == "main"
    assert state["conversation_id"] == CONVERSATION_ID
    assert state["conversation_id"] == AGENT_CONVERSATION_ID
    assert state["run_id"] == run_id
    assert set(state) == AGENT_STATE_FIELDS


def test_build_initial_state_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="run_id"):
        build_initial_agent_state(run_id="")
    with pytest.raises(ValueError, match="run_id"):
        build_initial_agent_state(run_id="   ")


def test_build_initial_state_candidate_context_always_empty() -> None:
    state = build_initial_agent_state(
        run_id="22222222-2222-4222-8222-222222222222",
        recent_context=[
            ContextMessage(id="a", role="user", content="hi"),
        ],
        attachment_ids=["33333333-3333-4333-8333-333333333333"],
    )
    assert state["candidate_context"] == []
    assert empty_candidate_context() == []
    # Cannot inject candidate rows through the builder — field is forced empty.
    assert state["candidate_context"] is not None
    assert len(state["candidate_context"]) == 0


def test_build_initial_state_attachment_ids_only_no_document_bodies() -> None:
    att = "44444444-4444-4444-8444-444444444444"
    state = build_initial_agent_state(
        run_id="55555555-5555-4555-8555-555555555555",
        attachment_ids=[att],
    )
    assert state["attachment_ids"] == [att]
    # State keys do not include raw document fields.
    assert "raw_content" not in state
    assert "raw_cv" not in state
    assert "raw_jd" not in state
    assert "document" not in state
    assert "cv_text" not in state
    assert "jd_text" not in state


def test_build_initial_state_defaults() -> None:
    state = build_initial_agent_state(run_id="66666666-6666-4666-8666-666666666666")
    assert state["messages_for_this_turn"] == []
    assert state["recent_context"] == []
    assert state["attachment_ids"] == []
    assert state["pending_approval"] is None
    assert state["tool_iteration_count"] == 0
    assert state["error"] is None


def test_build_initial_state_rejects_negative_iteration() -> None:
    with pytest.raises(ValueError, match="tool_iteration_count"):
        build_initial_agent_state(
            run_id="77777777-7777-4777-8777-777777777777",
            tool_iteration_count=-1,
        )


def test_no_extra_memory_or_classifier_fields_on_agent_state() -> None:
    forbidden = {
        "memory",
        "long_term_memory",
        "classifier",
        "intent",
        "second_agent",
        "handoff",
        "full_history",
        "history",
        "profile_raw",
        "jd_raw",
        "cv_raw",
    }
    assert AGENT_STATE_FIELDS.isdisjoint(forbidden)
    state = build_initial_agent_state(run_id="88888888-8888-4888-8888-888888888888")
    assert forbidden.isdisjoint(state.keys())


# ---------------------------------------------------------------------------
# Prompt budget constants (documented ceilings)
# ---------------------------------------------------------------------------


def test_prompt_budget_ceilings_are_positive_and_bounded() -> None:
    assert RECENT_CONTEXT_MAX_MESSAGES == 20
    assert RECENT_CONTEXT_CHAR_BUDGET == 12_000
    assert RECENT_CONTEXT_MAX_MESSAGES > 0
    assert RECENT_CONTEXT_CHAR_BUDGET > 0
    # Far below a 64_000-token-style dump (character budget is smaller).
    assert RECENT_CONTEXT_CHAR_BUDGET < 64_000


# ---------------------------------------------------------------------------
# Bounded recent-context selection
# ---------------------------------------------------------------------------


def test_budget_selects_newest_within_message_cap_chronological_order() -> None:
    # Newest-first input (as repository returns).
    rows = [_msg(i) for i in range(10, 0, -1)]  # 10 .. 1
    selected = apply_recent_context_budget(rows, max_messages=3, char_budget=10_000)
    assert [m["id"] for m in selected] == [
        _msg(8).id,
        _msg(9).id,
        _msg(10).id,
    ]
    assert [m["content"] for m in selected] == [
        "message-8",
        "message-9",
        "message-10",
    ]


def test_budget_respects_character_ceiling_drops_older() -> None:
    # Three short messages newest-first: m3, m2, m1 with sizes 5, 5, 5.
    rows = [
        _msg(3, content="aaaaa"),
        _msg(2, content="bbbbb"),
        _msg(1, content="ccccc"),
    ]
    # Budget 12 fits newest two (10) but not all three (15).
    selected = apply_recent_context_budget(rows, max_messages=20, char_budget=12)
    assert len(selected) == 2
    assert [m["content"] for m in selected] == ["bbbbb", "aaaaa"]
    assert sum(len(m["content"]) for m in selected) <= 12


def test_budget_boundary_exact_char_fit() -> None:
    rows = [
        _msg(2, content="12345"),
        _msg(1, content="67890"),
    ]
    selected = apply_recent_context_budget(rows, max_messages=10, char_budget=10)
    assert len(selected) == 2
    assert sum(len(m["content"]) for m in selected) == 10


def test_budget_excludes_current_turn_ids() -> None:
    current = _msg(99, content="current-turn")
    older = [_msg(i) for i in range(5, 0, -1)]
    rows = [current, *older]
    selected = apply_recent_context_budget(
        rows,
        max_messages=10,
        char_budget=10_000,
        exclude_ids=frozenset({current.id}),
    )
    ids = {m["id"] for m in selected}
    assert current.id not in ids
    assert len(selected) == 5


def test_budget_excludes_irrelevant_old_messages_beyond_cap() -> None:
    # 30 messages newest-first; only 20 may enter (default max).
    rows = [_msg(i) for i in range(30, 0, -1)]
    selected = apply_recent_context_budget(rows)
    assert len(selected) == RECENT_CONTEXT_MAX_MESSAGES
    # Oldest of the full set must be dropped.
    selected_ids = {m["id"] for m in selected}
    assert _msg(1).id not in selected_ids
    assert _msg(10).id not in selected_ids
    # Newest retained.
    assert _msg(30).id in selected_ids
    assert _msg(11).id in selected_ids


def test_context_projection_never_includes_raw_document_fields() -> None:
    dirty = _FakeMsg(
        id="99999999-9999-4999-8999-999999999999",
        role="user",
        content="short",
        structured_payload={"raw_content": "HUGE_CV_BODY", "pages": 9},
        raw_content="HUGE_CV_BODY",
        raw_cv="CV_BYTES",
        raw_jd="JD_TEXT",
    )
    selected = apply_recent_context_budget([dirty], max_messages=5, char_budget=1000)
    assert len(selected) == 1
    proj = selected[0]
    assert set(proj) == {"id", "role", "content"}
    assert proj["content"] == "short"
    assert "raw_content" not in proj
    assert "raw_cv" not in proj
    assert "raw_jd" not in proj
    assert "structured_payload" not in proj
    assert "HUGE_CV_BODY" not in proj["content"]
    assert "CV_BYTES" not in proj["content"]


def test_single_oversized_message_truncated_to_char_budget() -> None:
    huge = _msg(1, content="x" * 50_000)
    selected = apply_recent_context_budget(
        [huge], max_messages=5, char_budget=100
    )
    assert len(selected) == 1
    assert len(selected[0]["content"]) == 100


def test_empty_input_yields_empty_context() -> None:
    assert apply_recent_context_budget([]) == []


def test_budget_rejects_negative_ceilings() -> None:
    with pytest.raises(ValueError, match="max_messages"):
        apply_recent_context_budget([], max_messages=-1)
    with pytest.raises(ValueError, match="char_budget"):
        apply_recent_context_budget([], char_budget=-1)


def test_recent_context_roles_preserved_without_tool_role_invention() -> None:
    rows = [
        _msg(3, role="assistant", content="answer"),
        _msg(2, role="user", content="ask"),
        _msg(1, role="system", content="note"),
    ]
    selected = apply_recent_context_budget(rows, max_messages=10, char_budget=1000)
    assert [m["role"] for m in selected] == ["system", "user", "assistant"]
    assert all(m["role"] != "tool" for m in selected)


def test_state_with_recent_context_keeps_candidate_empty() -> None:
    # Newest-first repository order: message-2 is newer than message-1.
    rows = [_msg(2, content="prev"), _msg(1, content="older")]
    recent = apply_recent_context_budget(rows, max_messages=10, char_budget=1000)
    assert [m["content"] for m in recent] == ["older", "prev"]

    turn = [ContextMessage(id=_msg(3).id, role="user", content="now")]
    state = build_initial_agent_state(
        run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        messages_for_this_turn=turn,
        recent_context=recent,
        attachment_ids=[],
    )
    assert state["candidate_context"] == []
    assert state["messages_for_this_turn"] == turn
    assert state["recent_context"] == recent
    # Current turn is separate from recent_context in this assembly.
    recent_ids = {m["id"] for m in state["recent_context"]}
    assert turn[0]["id"] not in recent_ids
