"""SSE event union, serialization, ordering, and leakage tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from app.schemas.sse import (
    SUPPORTED_SSE_EVENT_TYPES,
    SSEEventOrderValidator,
    SSEEventType,
    SSEOrderError,
    SSESchemaError,
    ToolDisplayStatus,
    parse_sse_event,
    serialize_sse_event,
    serialize_sse_event_json,
    validate_sse_event_order,
)
from pydantic import ValidationError

RUN_ID = str(uuid4())
TS = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)

LEAK_SENTINELS = (
    "sk-secret-api-key-value",
    "Bearer abc.def.ghi",
    "Authorization: Bearer xyz",
    "password=hunter2",
    "C:\\Users\\secret\\cv.pdf",
    "/var/lib/jobagent/files/active/cv.pdf",
    "Traceback (most recent call last):",
    '  File "/app/backend/app/agent/graph.py", line 42',
    "BEGIN PRIVATE KEY",
    '{"raw_arguments": {"cv_text": "full body"}}',
)


def _base(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "event_id": f"evt-{uuid4().hex[:12]}",
        "run_id": RUN_ID,
        "timestamp": TS.isoformat().replace("+00:00", "Z"),
    }
    data.update(overrides)
    return data


def _run_started(**overrides: Any) -> dict[str, Any]:
    return _base(event="run_started", payload={}, **overrides)


def _assistant_status(
    status: str = "thinking", message: str | None = None, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status}
    if message is not None:
        payload["message"] = message
    return _base(event="assistant_status", payload=payload, **overrides)


def _tool_started(
    tool_call_id: str = "tc-1",
    label: str = "Lookup memory",
    status: str = "running",
    **overrides: Any,
) -> dict[str, Any]:
    return _base(
        event="tool_started",
        payload={"tool_call_id": tool_call_id, "label": label, "status": status},
        **overrides,
    )


def _tool_completed(
    tool_call_id: str = "tc-1",
    label: str = "Lookup memory",
    status: str = "complete",
    duration_ms: int | None = 12,
    outcome: str | None = "Found city preference",
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "label": label,
        "status": status,
        "duration_ms": duration_ms,
        "outcome": outcome,
    }
    return _base(event="tool_completed", payload=payload, **overrides)


def _approval_required(
    summary: str = "Review proposed profile updates",
    approval_kind: str | None = "profile_draft",
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"summary": summary}
    if approval_kind is not None:
        payload["approval_kind"] = approval_kind
    return _base(event="approval_required", payload=payload, **overrides)


def _text_delta(delta: str = "Hello", **overrides: Any) -> dict[str, Any]:
    return _base(event="text_delta", payload={"delta": delta}, **overrides)


def _run_completed(**overrides: Any) -> dict[str, Any]:
    return _base(event="run_completed", payload={}, **overrides)


def _run_failed(
    error_code: str = "PROVIDER_TIMEOUT",
    message: str | None = "Upstream timed out",
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"error_code": error_code}
    if message is not None:
        payload["message"] = message
    return _base(event="run_failed", payload=payload, **overrides)


# ---------------------------------------------------------------------------
# Union accepts all and only eight event types
# ---------------------------------------------------------------------------


def test_supported_event_types_are_exactly_eight() -> None:
    expected = {
        "run_started",
        "assistant_status",
        "tool_started",
        "tool_completed",
        "approval_required",
        "text_delta",
        "run_completed",
        "run_failed",
    }
    assert SUPPORTED_SSE_EVENT_TYPES == expected
    assert {m.value for m in SSEEventType} == expected


def test_run_completed_saved_job_payload_is_display_safe() -> None:
    import json
    from uuid import uuid4 as _uuid4

    job_id = str(_uuid4())
    event = parse_sse_event(
        {
            "event": "run_completed",
            "event_id": f"evt-{uuid4().hex[:12]}",
            "run_id": RUN_ID,
            "timestamp": TS.isoformat().replace("+00:00", "Z"),
            "payload": {
                "saved_job": {
                    "kind": "saved_job",
                    "job_id": job_id,
                    "title": "Engineer",
                    "company": "Acme",
                    "location": "Remote",
                    "work_mode": "remote",
                    "employment_type": "full_time",
                    "jd_quality": "full",
                    "quality_reasons_preview": ["optional note"],
                    "processing_result": "processed",
                    "duplicate_outcome": "none",
                    "graph_sync_status": "pending",
                    "source_url": "https://example.com/jobs/1",
                }
            },
        }
    )
    serialized = serialize_sse_event(event)
    assert serialized["event"] == "run_completed"
    assert serialized["payload"]["saved_job"]["job_id"] == job_id
    assert serialized["payload"]["saved_job"]["title"] == "Engineer"
    blob = json.dumps(serialized)
    assert "raw_content" not in blob
    assert "cv_text" not in blob
    assert "jd_text" not in blob
    assert "stack_trace" not in blob
    assert "api_key" not in blob


def test_run_completed_rejects_saved_job_with_unsafe_url() -> None:
    from uuid import uuid4 as _uuid4

    job_id = str(_uuid4())
    with pytest.raises(SSESchemaError):
        parse_sse_event(
            {
                "event": "run_completed",
                "event_id": f"evt-{uuid4().hex[:12]}",
                "run_id": RUN_ID,
                "timestamp": TS.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "saved_job": {
                        "kind": "saved_job",
                        "job_id": job_id,
                        "processing_result": "processed",
                        "duplicate_outcome": "none",
                        "graph_sync_status": "pending",
                        "source_url": "http://user:pass@example.com/j",
                    }
                },
            }
        )


def _match_result_item(job_id: str | None = None) -> dict[str, Any]:
    from uuid import uuid4 as _uuid4

    jid = job_id or str(_uuid4())
    weights = {
        "semantic_similarity": (0.9, 0.3),
        "skill_score": (0.8, 0.4),
        "seniority_score": (1.0, 0.1),
        "experience_score": (1.0, 0.1),
        "location_score": (1.0, 0.05),
        "work_mode_score": (1.0, 0.05),
    }
    components = [
        {
            "name": name,
            "available": True,
            "value": value,
            "effective_weight": weight,
        }
        for name, (value, weight) in weights.items()
    ]
    return {
        "job_id": jid,
        "title": "Engineer",
        "company": "Acme",
        "location": "Remote",
        "work_mode": "remote",
        "final_score": 0.85,
        "quality": "full",
        "components": components,
        "matched_required_skills": [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "match_kind": "direct",
                "strength": 1.0,
                "related_path": [],
            }
        ],
        "related_skills": [],
        "missing_required_skills": [],
        "explanation_lines": ["Semantic similarity: 0.9"],
        "source_url": "https://example.com/jobs/1",
        "seed_config_version": "hybrid_seed_v1",
        "contract_version": "match_result_v1",
    }


def test_run_completed_match_results_payload_is_display_safe() -> None:
    import json
    from uuid import uuid4 as _uuid4

    job_id = str(_uuid4())
    item = _match_result_item(job_id)
    event = parse_sse_event(
        {
            "event": "run_completed",
            "event_id": f"evt-{uuid4().hex[:12]}",
            "run_id": RUN_ID,
            "timestamp": TS.isoformat().replace("+00:00", "Z"),
            "payload": {
                "match_results": {
                    "kind": "match_results",
                    "contract_version": "match_result_v1",
                    "seed_config_version": "hybrid_seed_v1",
                    "count": 1,
                    "results": [item],
                }
            },
        }
    )
    serialized = serialize_sse_event(event)
    assert serialized["event"] == "run_completed"
    card = serialized["payload"]["match_results"]
    assert card["kind"] == "match_results"
    assert card["count"] == 1
    assert card["results"][0]["job_id"] == job_id
    assert card["results"][0]["title"] == "Engineer"
    blob = json.dumps(serialized)
    assert "raw_content" not in blob
    assert "cv_text" not in blob
    assert "vector" not in blob
    assert "api_key" not in blob
    assert "stack_trace" not in blob


def test_run_completed_rejects_malformed_match_results() -> None:
    with pytest.raises(SSESchemaError):
        parse_sse_event(
            {
                "event": "run_completed",
                "event_id": f"evt-{uuid4().hex[:12]}",
                "run_id": RUN_ID,
                "timestamp": TS.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "match_results": {
                        "kind": "match_results",
                        "contract_version": "match_result_v1",
                        "seed_config_version": "hybrid_seed_v1",
                        "count": 1,
                        "results": [{"job_id": "not-a-uuid", "final_score": 0.5}],
                    }
                },
            }
        )


def test_run_completed_rejects_oversized_match_results() -> None:
    items = [_match_result_item() for _ in range(11)]
    with pytest.raises(SSESchemaError):
        parse_sse_event(
            {
                "event": "run_completed",
                "event_id": f"evt-{uuid4().hex[:12]}",
                "run_id": RUN_ID,
                "timestamp": TS.isoformat().replace("+00:00", "Z"),
                "payload": {
                    "match_results": {
                        "kind": "match_results",
                        "contract_version": "match_result_v1",
                        "seed_config_version": "hybrid_seed_v1",
                        "count": 11,
                        "results": items,
                    }
                },
            }
        )


def test_profile_approval_payload_extension_is_display_safe() -> None:
    import json

    event = parse_sse_event(
        {
            "event": "approval_required",
            "event_id": f"evt-{uuid4().hex[:12]}",
            "run_id": RUN_ID,
            "timestamp": TS.isoformat().replace("+00:00", "Z"),
            "payload": {
                "summary": "Review proposed Engineer",
                "approval_kind": "profile_draft",
                "current_title": "Engineer",
                "skill_names": ["Python", "SQL"],
                "experience_count": 2,
                "education_count": 1,
                "has_preference_changes": True,
                "target_roles_preview": ["Backend"],
            },
        }
    )
    serialized = serialize_sse_event(event)
    assert serialized["event"] == "approval_required"
    assert serialized["payload"]["skill_names"] == ["Python", "SQL"]
    blob = json.dumps(serialized)
    assert "draft_id" not in blob
    assert "resume_idempotency" not in blob
    assert "storage_path" not in blob
    assert "cv_text" not in blob


@pytest.mark.parametrize(
    "builder",
    [
        _run_started,
        _assistant_status,
        lambda: _tool_started(),
        lambda: _tool_completed(),
        _approval_required,
        _text_delta,
        _run_completed,
        _run_failed,
    ],
)
def test_every_valid_event_type_parses(builder: Any) -> None:
    event = parse_sse_event(builder())
    assert event.event in SUPPORTED_SSE_EVENT_TYPES
    assert event.event_id
    assert event.run_id == RUN_ID
    assert event.timestamp.tzinfo is not None
    assert event.payload is not None


def test_unknown_event_type_rejected() -> None:
    data = _base(event="run_paused", payload={})
    with pytest.raises(SSESchemaError, match="unknown event type"):
        parse_sse_event(data)


def test_mismatched_payload_rejected() -> None:
    # tool_started requires tool_call_id/label; empty payload must fail.
    data = _base(event="tool_started", payload={})
    with pytest.raises(SSESchemaError):
        parse_sse_event(data)

    # run_failed requires error_code
    data = _base(event="run_failed", payload={})
    with pytest.raises(SSESchemaError):
        parse_sse_event(data)

    # wrong shape for text_delta
    data = _base(event="text_delta", payload={"chunk": "x"})
    with pytest.raises(SSESchemaError):
        parse_sse_event(data)


def test_required_common_fields() -> None:
    for missing in ("event_id", "run_id", "timestamp"):
        data = _run_started()
        del data[missing]
        with pytest.raises(SSESchemaError):
            parse_sse_event(data)

    with pytest.raises(SSESchemaError):
        parse_sse_event(_run_started(event_id=""))

    with pytest.raises(SSESchemaError):
        parse_sse_event(_run_started(run_id="not-a-uuid"))

    with pytest.raises(SSESchemaError):
        parse_sse_event(_run_started(event_id="bad id with spaces"))


@pytest.mark.parametrize(
    "event_name",
    [
        "run_started",
        "assistant_status",
        "tool_started",
        "tool_completed",
        "approval_required",
        "text_delta",
        "run_completed",
        "run_failed",
    ],
)
def test_missing_payload_rejected_for_all_event_types(event_name: str) -> None:
    """Every event requires an explicit payload field (no default fill-in)."""
    data = _base(event=event_name)
    assert "payload" not in data
    with pytest.raises(SSESchemaError):
        parse_sse_event(data)


def test_explicit_empty_payload_accepted_only_for_empty_payload_models() -> None:
    """Explicit {} is valid only for run_started and run_completed."""
    started = parse_sse_event(_base(event="run_started", payload={}))
    assert started.event == SSEEventType.RUN_STARTED
    assert started.payload is not None
    assert started.payload.model_dump(exclude_none=True) == {}

    completed = parse_sse_event(_base(event="run_completed", payload={}))
    assert completed.event == SSEEventType.RUN_COMPLETED
    assert completed.payload is not None
    # Optional saved_job may exist as None on the model; wire omits nulls.
    assert completed.payload.model_dump(exclude_none=True) == {}
    assert getattr(completed.payload, "saved_job", None) is None

    # Non-empty payload models reject bare {}.
    for event_name in (
        "assistant_status",
        "tool_started",
        "tool_completed",
        "approval_required",
        "text_delta",
        "run_failed",
    ):
        with pytest.raises(SSESchemaError):
            parse_sse_event(_base(event=event_name, payload={}))


def test_text_delta_rejects_raw_document_like_multiline() -> None:
    """CV/JD-shaped multi-line bodies are not valid public text deltas."""
    cv_like = (
        "Curriculum Vitae\n"
        "Name: Jane Doe\n"
        "Email: jane@example.com\n"
        "Experience:\n"
        "- Software Engineer at Acme\n"
        "- Built APIs and data pipelines\n"
        "Skills: Python, FastAPI, SQL\n"
    )
    with pytest.raises((SSESchemaError, ValidationError, ValueError)):
        parse_sse_event(_text_delta(delta=cv_like))

    jd_like = (
        "Job Description\n"
        "Title: Backend Engineer\n"
        "Requirements:\n"
        "- 5 years of experience with Python\n"
        "- Strong communication skills\n"
        "Responsibilities: own chat APIs\n"
    )
    with pytest.raises((SSESchemaError, ValidationError, ValueError)):
        parse_sse_event(_text_delta(delta=jd_like))


def test_text_delta_accepts_normal_partial_response() -> None:
    """Ordinary streamed assistant chunks remain valid."""
    event = parse_sse_event(_text_delta(delta="Based on your preferences, "))
    assert event.payload.delta == "Based on your preferences, "
    event2 = parse_sse_event(_text_delta(delta="I'd suggest focusing on Python."))
    assert "Python" in event2.payload.delta
    # Short multi-sentence partial without document shape still ok.
    short = parse_sse_event(
        _text_delta(delta="Done. Next we can refine your profile.")
    )
    assert short.payload.delta.startswith("Done.")


def test_tool_display_status_constraints() -> None:
    parse_sse_event(_tool_started(status="pending"))
    parse_sse_event(_tool_started(status="running"))
    with pytest.raises(SSESchemaError):
        parse_sse_event(_tool_started(status="complete"))
    with pytest.raises(SSESchemaError):
        parse_sse_event(_tool_completed(status="running"))
    assert ToolDisplayStatus.COMPLETE.value == "complete"
    assert ToolDisplayStatus.ERROR.value == "error"


def test_extra_payload_fields_forbidden() -> None:
    data = _tool_started()
    data["payload"]["arguments"] = {"q": "secret"}
    with pytest.raises(SSESchemaError):
        parse_sse_event(data)


# ---------------------------------------------------------------------------
# Serialization and leakage
# ---------------------------------------------------------------------------


def test_serialize_is_deterministic_and_ordered() -> None:
    event = parse_sse_event(
        _tool_completed(outcome="ok", duration_ms=5, tool_call_id="tc-a")
    )
    first = serialize_sse_event(event)
    second = serialize_sse_event(event)
    assert first == second
    assert list(first.keys()) == [
        "event",
        "event_id",
        "run_id",
        "timestamp",
        "payload",
    ]
    json_a = serialize_sse_event_json(event)
    json_b = serialize_sse_event_json(event)
    assert json_a == json_b
    assert '"event":"tool_completed"' in json_a.replace(" ", "")


def test_serialized_events_exclude_prohibited_categories() -> None:
    legal_sequence = [
        _run_started(event_id="e1"),
        _tool_started(event_id="e2", tool_call_id="tc-1"),
        _tool_completed(
            event_id="e3",
            tool_call_id="tc-1",
            outcome="Short result",
            duration_ms=9,
        ),
        _text_delta(event_id="e4", delta="Hello world"),
        _run_completed(event_id="e5"),
    ]
    for raw in legal_sequence:
        dumped = serialize_sse_event(raw)
        wire = str(dumped)
        for sentinel in LEAK_SENTINELS:
            assert sentinel not in wire
        # Display payloads only expose approved tool fields.
        if dumped["event"] in ("tool_started", "tool_completed"):
            keys = set(dumped["payload"].keys())
            assert "arguments" not in keys
            assert "raw_arguments" not in keys
            assert "headers" not in keys
            assert "stack_trace" not in keys
            assert "label" in keys
            assert "status" in keys


@pytest.mark.parametrize(
    "field_builder",
    [
        lambda: _tool_completed(outcome="password=hunter2"),
        lambda: _tool_completed(outcome="Bearer abc.def"),
        lambda: _tool_completed(outcome="C:\\Users\\x\\cv.pdf"),
        lambda: _tool_completed(outcome="Traceback (most recent call last):"),
        lambda: _tool_completed(outcome="cv_text dump here"),
        lambda: _tool_started(label="secret token tool"),
        lambda: _approval_required(summary="api_key exposed in summary"),
        lambda: _run_failed(message="Authorization: Bearer xyz"),
        lambda: _assistant_status(message="BEGIN PRIVATE KEY"),
        lambda: _text_delta(delta="Bearer sk-live-abcdef"),
    ],
)
def test_payload_sanitization_rejects_leaks(field_builder: Any) -> None:
    with pytest.raises((SSESchemaError, ValidationError, ValueError)):
        parse_sse_event(field_builder())


def test_tool_payload_exposes_only_friendly_display_fields() -> None:
    started = serialize_sse_event(_tool_started(label="Search jobs", status="running"))
    assert started["payload"]["label"] == "Search jobs"
    assert started["payload"]["status"] == "running"
    assert set(started["payload"].keys()) == {"tool_call_id", "label", "status"}

    completed = serialize_sse_event(
        _tool_completed(label="Search jobs", status="error", outcome="No matches", duration_ms=3)
    )
    assert completed["payload"]["status"] == "error"
    assert completed["payload"]["duration_ms"] == 3
    assert completed["payload"]["outcome"] == "No matches"
    assert set(completed["payload"].keys()) == {
        "tool_call_id",
        "label",
        "status",
        "duration_ms",
        "outcome",
    }


# ---------------------------------------------------------------------------
# Ordering boundary
# ---------------------------------------------------------------------------


def test_legal_ordering_happy_path() -> None:
    events = [
        _run_started(event_id="e1"),
        _assistant_status(event_id="e2"),
        _tool_started(event_id="e3", tool_call_id="tc-1"),
        _tool_completed(event_id="e4", tool_call_id="tc-1"),
        _text_delta(event_id="e5", delta="Done "),
        _text_delta(event_id="e6", delta="here."),
        _run_completed(event_id="e7"),
    ]
    validated = validate_sse_event_order(events)
    assert len(validated) == 7
    assert validated[0].event == SSEEventType.RUN_STARTED
    assert validated[-1].event == SSEEventType.RUN_COMPLETED


def test_rejects_events_before_run_started() -> None:
    with pytest.raises(SSEOrderError, match="before run_started"):
        validate_sse_event_order([_assistant_status(event_id="e1")])
    with pytest.raises(SSEOrderError, match="before run_started"):
        validate_sse_event_order([_text_delta(event_id="e1")])
    with pytest.raises(SSEOrderError, match="before run_started"):
        validate_sse_event_order([_tool_started(event_id="e1")])


def test_rejects_events_after_terminal() -> None:
    seq = [
        _run_started(event_id="e1"),
        _run_completed(event_id="e2"),
        _text_delta(event_id="e3"),
    ]
    with pytest.raises(SSEOrderError, match="after terminal"):
        validate_sse_event_order(seq)

    seq_fail = [
        _run_started(event_id="e1"),
        _run_failed(event_id="e2"),
        _assistant_status(event_id="e3"),
    ]
    with pytest.raises(SSEOrderError, match="after terminal"):
        validate_sse_event_order(seq_fail)


def test_rejects_duplicate_event_ids() -> None:
    seq = [
        _run_started(event_id="same"),
        _assistant_status(event_id="same"),
    ]
    with pytest.raises(SSEOrderError, match="duplicate event_id"):
        validate_sse_event_order(seq)


def test_tool_sequence_requires_started_before_completed() -> None:
    with pytest.raises(SSEOrderError, match="tool_completed without tool_started"):
        validate_sse_event_order(
            [
                _run_started(event_id="e1"),
                _tool_completed(event_id="e2", tool_call_id="tc-x"),
            ]
        )


def test_tool_sequence_rejects_double_start_same_id() -> None:
    with pytest.raises(SSEOrderError, match="tool sequence inconsistent"):
        validate_sse_event_order(
            [
                _run_started(event_id="e1"),
                _tool_started(event_id="e2", tool_call_id="tc-1"),
                _tool_started(event_id="e3", tool_call_id="tc-1"),
            ]
        )


def test_approval_then_tool_or_text_rejected() -> None:
    base = [
        _run_started(event_id="e1"),
        _approval_required(event_id="e2"),
    ]
    with pytest.raises(SSEOrderError, match="awaiting_approval"):
        validate_sse_event_order([*base, _tool_started(event_id="e3")])
    with pytest.raises(SSEOrderError, match="awaiting_approval"):
        validate_sse_event_order([*base, _text_delta(event_id="e3")])
    with pytest.raises(SSEOrderError, match="awaiting_approval"):
        validate_sse_event_order([*base, _assistant_status(event_id="e3")])


def test_approval_required_with_open_tools_rejected() -> None:
    with pytest.raises(SSEOrderError, match="open tools"):
        validate_sse_event_order(
            [
                _run_started(event_id="e1"),
                _tool_started(event_id="e2", tool_call_id="tc-1"),
                _approval_required(event_id="e3"),
            ]
        )


def test_approval_then_terminal_allowed() -> None:
    validated = validate_sse_event_order(
        [
            _run_started(event_id="e1"),
            _approval_required(event_id="e2"),
            _run_completed(event_id="e3"),
        ]
    )
    assert validated[-1].event == SSEEventType.RUN_COMPLETED


def test_run_id_mismatch_rejected() -> None:
    other = str(uuid4())
    with pytest.raises(SSEOrderError, match="run_id mismatch"):
        validate_sse_event_order(
            [
                _run_started(event_id="e1", run_id=RUN_ID),
                _assistant_status(event_id="e2", run_id=other),
            ]
        )


def test_order_validator_state_progression() -> None:
    v = SSEEventOrderValidator()
    assert v.state.value == "idle"
    v.validate(_run_started(event_id="e1"))
    assert v.state.value == "active"
    assert v.run_id == RUN_ID
    v.validate(_approval_required(event_id="e2"))
    assert v.state.value == "awaiting_approval"
    v.validate(_run_failed(event_id="e3", error_code="USER_REJECTED"))
    assert v.state.value == "terminal"


def test_terminal_with_open_tools_rejected() -> None:
    with pytest.raises(SSEOrderError, match="open tools"):
        validate_sse_event_order(
            [
                _run_started(event_id="e1"),
                _tool_started(event_id="e2", tool_call_id="tc-1"),
                _run_completed(event_id="e3"),
            ]
        )
