"""Unit tests for SSE event contracts and status vocabulary (Plan 3 §7.7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.schemas.common import (
    RUN_STATE_COMPLETED,
    RUN_STATE_FAILED,
    RUN_STATE_INTERRUPTED,
    RUN_STATE_RUNNING,
    TOOL_STATUS_COMPLETED,
    TOOL_STATUS_FAILED,
    TOOL_STATUS_PENDING,
    TOOL_STATUS_RUNNING,
    reject_status_alias,
)
from app.schemas.sse import (
    SSE_EVENT_NAMES,
    ApprovalRequiredEvent,
    AssistantStatusEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    TextDeltaEvent,
    ToolStatusEvent,
    parse_sse_event,
    sse_event_to_dict,
)
from pydantic import ValidationError


def _envelope(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id": new_uuid(),
        "run_id": new_uuid(),
        "timestamp": utc_now(),
    }
    base.update(overrides)
    return base


def test_all_seven_event_names_defined() -> None:
    assert SSE_EVENT_NAMES == frozenset(
        {
            "run_started",
            "assistant_status",
            "tool_status",
            "approval_required",
            "text_delta",
            "run_completed",
            "run_failed",
        }
    )


def test_run_started_requires_running_and_resumed() -> None:
    event = parse_sse_event(
        {
            **_envelope(),
            "event": "run_started",
            "payload": {"state": RUN_STATE_RUNNING, "resumed": False},
        }
    )
    assert isinstance(event, RunStartedEvent)
    assert event.payload.state == "running"
    assert event.payload.resumed is False
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "run_started",
                "payload": {"state": "completed", "resumed": False},
            }
        )
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "run_started",
                "payload": {"state": "running"},
            }
        )


def test_assistant_status_requires_message() -> None:
    event = parse_sse_event(
        {
            **_envelope(),
            "event": "assistant_status",
            "payload": {"message": "generating"},
        }
    )
    assert isinstance(event, AssistantStatusEvent)
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "assistant_status",
                "payload": {"message": ""},
            }
        )


def test_tool_status_exact_statuses_and_terminal_fields() -> None:
    pending = parse_sse_event(
        {
            **_envelope(),
            "event": "tool_status",
            "payload": {
                "tool_execution_id": new_uuid(),
                "tool_call_id": "call_1",
                "tool_name": "synthetic_tool",
                "status": TOOL_STATUS_PENDING,
            },
        }
    )
    assert isinstance(pending, ToolStatusEvent)
    assert pending.payload.status == "pending"

    running = parse_sse_event(
        {
            **_envelope(),
            "event": "tool_status",
            "payload": {
                "tool_execution_id": new_uuid(),
                "tool_call_id": "call_1",
                "tool_name": "synthetic_tool",
                "status": TOOL_STATUS_RUNNING,
            },
        }
    )
    assert running.payload.status == "running"

    completed = parse_sse_event(
        {
            **_envelope(),
            "event": "tool_status",
            "payload": {
                "tool_execution_id": new_uuid(),
                "tool_call_id": "call_1",
                "tool_name": "synthetic_tool",
                "status": TOOL_STATUS_COMPLETED,
                "duration_ms": 12,
                "summary": "ok",
            },
        }
    )
    assert completed.payload.duration_ms == 12

    failed = parse_sse_event(
        {
            **_envelope(),
            "event": "tool_status",
            "payload": {
                "tool_execution_id": new_uuid(),
                "tool_call_id": "call_1",
                "tool_name": "synthetic_tool",
                "status": TOOL_STATUS_FAILED,
                "duration_ms": 5,
                "error_code": "TOOL_ERROR",
                "summary": "failed",
            },
        }
    )
    assert failed.payload.error_code == "TOOL_ERROR"


def test_tool_status_rejects_complete_and_error_aliases() -> None:
    for alias in ("complete", "error"):
        with pytest.raises(ValidationError):
            parse_sse_event(
                {
                    **_envelope(),
                    "event": "tool_status",
                    "payload": {
                        "tool_execution_id": new_uuid(),
                        "tool_call_id": "c",
                        "tool_name": "t",
                        "status": alias,
                        "duration_ms": 1,
                    },
                }
            )
    with pytest.raises(ValueError):
        reject_status_alias("complete")
    with pytest.raises(ValueError):
        reject_status_alias("error")


def test_tool_status_rejects_invalid_terminal_coupling() -> None:
    # completed without duration
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "tool_status",
                "payload": {
                    "tool_execution_id": new_uuid(),
                    "tool_call_id": "c",
                    "tool_name": "t",
                    "status": "completed",
                },
            }
        )
    # failed without error_code
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "tool_status",
                "payload": {
                    "tool_execution_id": new_uuid(),
                    "tool_call_id": "c",
                    "tool_name": "t",
                    "status": "failed",
                    "duration_ms": 1,
                },
            }
        )
    # running with duration
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "tool_status",
                "payload": {
                    "tool_execution_id": new_uuid(),
                    "tool_call_id": "c",
                    "tool_name": "t",
                    "status": "running",
                    "duration_ms": 1,
                },
            }
        )


def test_approval_required_interrupted_kind_actions_card() -> None:
    event = parse_sse_event(
        {
            **_envelope(),
            "event": "approval_required",
            "payload": {
                "state": RUN_STATE_INTERRUPTED,
                "kind": "synthetic_approval",
                "allowed_actions": ["approve", "reject"],
                "card": {"title": "Confirm"},
            },
        }
    )
    assert isinstance(event, ApprovalRequiredEvent)
    assert event.payload.state == "interrupted"
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "approval_required",
                "payload": {
                    "state": "running",
                    "kind": "x",
                    "allowed_actions": ["a"],
                    "card": {},
                },
            }
        )
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "approval_required",
                "payload": {
                    "state": "interrupted",
                    "kind": "x",
                    "allowed_actions": [],
                    "card": {},
                },
            }
        )


def test_text_delta_non_empty() -> None:
    event = parse_sse_event(
        {
            **_envelope(),
            "event": "text_delta",
            "payload": {"delta": "Hello"},
        }
    )
    assert isinstance(event, TextDeltaEvent)
    assert event.payload.delta == "Hello"
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "text_delta",
                "payload": {"delta": ""},
            }
        )


def test_run_completed_and_failed_payloads() -> None:
    done = parse_sse_event(
        {
            **_envelope(),
            "event": "run_completed",
            "payload": {"state": RUN_STATE_COMPLETED},
        }
    )
    assert isinstance(done, RunCompletedEvent)
    assert done.payload.state == "completed"

    failed = parse_sse_event(
        {
            **_envelope(),
            "event": "run_failed",
            "payload": {
                "state": RUN_STATE_FAILED,
                "error_code": "AGENT_LOOP_LIMIT",
                "summary": "iteration limit exceeded",
            },
        }
    )
    assert isinstance(failed, RunFailedEvent)
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "run_failed",
                "payload": {
                    "state": "failed",
                    "error_code": "",
                    "summary": "x",
                },
            }
        )
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "run_completed",
                "payload": {"state": "failed"},
            }
        )


def test_event_requires_uuid_event_id_and_run_id() -> None:
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                "event_id": "not-uuid",
                "run_id": new_uuid(),
                "timestamp": utc_now(),
                "event": "run_completed",
                "payload": {"state": "completed"},
            }
        )
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                "event_id": new_uuid(),
                "run_id": "bad",
                "timestamp": utc_now(),
                "event": "run_completed",
                "payload": {"state": "completed"},
            }
        )


def test_timestamp_must_be_aware_utc() -> None:
    naive = datetime.now()
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                "event_id": new_uuid(),
                "run_id": new_uuid(),
                "timestamp": naive,
                "event": "run_completed",
                "payload": {"state": "completed"},
            }
        )
    non_utc = datetime.now(timezone(timedelta(hours=2)))
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                "event_id": new_uuid(),
                "run_id": new_uuid(),
                "timestamp": non_utc,
                "event": "run_completed",
                "payload": {"state": "completed"},
            }
        )
    # explicit UTC accepted
    event = parse_sse_event(
        {
            "event_id": new_uuid(),
            "run_id": new_uuid(),
            "timestamp": datetime.now(UTC),
            "event": "run_completed",
            "payload": {"state": "completed"},
        }
    )
    assert event.timestamp.utcoffset() == timedelta(0)


def test_unknown_event_name_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_sse_event(
            {
                **_envelope(),
                "event": "message_delta",
                "payload": {},
            }
        )


def test_complete_and_error_fail_as_application_run_states() -> None:
    """Aliases are not valid run payload states."""
    for alias in ("complete", "error"):
        with pytest.raises(ValidationError):
            parse_sse_event(
                {
                    **_envelope(),
                    "event": "run_completed",
                    "payload": {"state": alias},
                }
            )
        with pytest.raises(ValidationError):
            parse_sse_event(
                {
                    **_envelope(),
                    "event": "run_failed",
                    "payload": {
                        "state": alias,
                        "error_code": "X",
                        "summary": "y",
                    },
                }
            )


def test_sse_event_to_dict_json_mode() -> None:
    event = parse_sse_event(
        {
            **_envelope(),
            "event": "text_delta",
            "payload": {"delta": "Hi"},
        }
    )
    data = sse_event_to_dict(event)
    assert data["event"] == "text_delta"
    assert data["payload"]["delta"] == "Hi"
    assert isinstance(data["event_id"], str)
    assert isinstance(data["timestamp"], str)
