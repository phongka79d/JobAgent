"""Unit tests for ToolResult and chat input contracts (Plan 3 §7.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.ids import new_uuid
from app.schemas.chat import ChatTurnRequest, HistoryQuery, ResumeRequest
from app.schemas.common import (
    FORBIDDEN_STATUS_ALIASES,
    TOOL_STATUS_COMPLETED,
    TOOL_STATUS_FAILED,
    TOOL_STATUS_PENDING,
    TOOL_STATUS_RUNNING,
)
from app.schemas.tools import (
    ToolResult,
    parse_tool_result,
    validate_tool_result_terminal_coupling,
)
from pydantic import ValidationError


def test_tool_result_fields_exactly_ok_code_summary_data() -> None:
    result = ToolResult(ok=True, code=None, summary="done", data={"count": 1})
    assert set(ToolResult.model_fields) == {"ok", "code", "summary", "data"}
    dumped = result.model_dump()
    assert set(dumped) == {"ok", "code", "summary", "data"}


def test_tool_result_success_requires_null_code() -> None:
    ok = ToolResult(ok=True, summary="saved", data=None)
    assert ok.code is None
    with pytest.raises(ValidationError):
        ToolResult(ok=True, code="SHOULD_NOT", summary="saved")


def test_tool_result_failure_requires_stable_code() -> None:
    bad = ToolResult(ok=False, code="TOOL_TIMEOUT", summary="timed out")
    assert bad.code == "TOOL_TIMEOUT"
    with pytest.raises(ValidationError):
        ToolResult(ok=False, code=None, summary="failed")
    with pytest.raises(ValidationError):
        ToolResult(ok=False, code="", summary="failed")
    with pytest.raises(ValidationError):
        ToolResult(ok=False, code="   ", summary="failed")


def test_tool_result_summary_required_non_empty() -> None:
    with pytest.raises(ValidationError):
        ToolResult(ok=True, summary="")
    with pytest.raises(ValidationError):
        ToolResult.model_validate({"ok": True, "summary": ""})


def test_tool_result_data_is_ordinary_json_object_not_escape_type() -> None:
    """Raw documents are not a special type — only compact JSON objects."""
    result = ToolResult(
        ok=True,
        summary="card",
        data={"draft_id": "current", "counts": {"skills": 3}, "nested": [1, "a", None]},
    )
    assert result.data is not None
    assert result.data["draft_id"] == "current"
    # No dedicated RawDocument / Blob escape field on the model
    assert "raw" not in ToolResult.model_fields
    assert "document" not in ToolResult.model_fields
    assert "blob" not in ToolResult.model_fields


def test_tool_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ToolResult.model_validate(
            {
                "ok": True,
                "code": None,
                "summary": "x",
                "data": None,
                "extra": True,
            }
        )


def test_terminal_coupling_success_completed() -> None:
    result = ToolResult(ok=True, summary="ok", data={"id": "a"})
    validate_tool_result_terminal_coupling(
        result, status=TOOL_STATUS_COMPLETED, error_code=None
    )


def test_terminal_coupling_failure_matches_error_code() -> None:
    result = ToolResult(ok=False, code="PARSE_ERROR", summary="bad input")
    validate_tool_result_terminal_coupling(
        result, status=TOOL_STATUS_FAILED, error_code="PARSE_ERROR"
    )


def test_terminal_coupling_rejects_mismatches() -> None:
    success = ToolResult(ok=True, summary="ok")
    failure = ToolResult(ok=False, code="X", summary="no")

    with pytest.raises(ValueError, match="completed"):
        validate_tool_result_terminal_coupling(
            failure, status=TOOL_STATUS_COMPLETED, error_code=None
        )
    with pytest.raises(ValueError, match="error_code"):
        validate_tool_result_terminal_coupling(
            success, status=TOOL_STATUS_COMPLETED, error_code="LEAK"
        )
    with pytest.raises(ValueError, match="failed"):
        validate_tool_result_terminal_coupling(
            success, status=TOOL_STATUS_FAILED, error_code="X"
        )
    with pytest.raises(ValueError, match="equal"):
        validate_tool_result_terminal_coupling(
            failure, status=TOOL_STATUS_FAILED, error_code="OTHER"
        )
    with pytest.raises(ValueError, match="error_code"):
        validate_tool_result_terminal_coupling(
            failure, status=TOOL_STATUS_FAILED, error_code=None
        )


@pytest.mark.parametrize(
    "status",
    [TOOL_STATUS_PENDING, TOOL_STATUS_RUNNING, "complete", "error"],
)
def test_terminal_coupling_rejects_non_terminal_and_aliases(status: str) -> None:
    result = ToolResult(ok=True, summary="ok")
    with pytest.raises(ValueError):
        validate_tool_result_terminal_coupling(
            result, status=status, error_code=None
        )


def test_parse_tool_result_round_trip() -> None:
    payload = {
        "ok": False,
        "code": "NETWORK",
        "summary": "unreachable",
        "data": {"retries": 0},
    }
    parsed = parse_tool_result(payload)
    assert parsed.ok is False
    assert parsed.code == "NETWORK"
    assert parse_tool_result(parsed.model_dump()) == parsed


def test_chat_turn_requires_non_empty_message() -> None:
    ok = ChatTurnRequest(message="hello", attachment_ids=[])
    assert ok.message == "hello"
    with pytest.raises(ValidationError):
        ChatTurnRequest(message="")
    with pytest.raises(ValidationError):
        ChatTurnRequest(message="   ")
    with pytest.raises(ValidationError):
        ChatTurnRequest.model_validate({"message": ""})


def test_chat_turn_attachment_ids_must_be_uuid_v4() -> None:
    aid = new_uuid()
    ok = ChatTurnRequest(message="with file", attachment_ids=[aid])
    assert ok.attachment_ids == [aid]
    with pytest.raises(ValidationError):
        ChatTurnRequest(message="x", attachment_ids=["not-a-uuid"])


def test_chat_turn_forbids_secrets_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ChatTurnRequest.model_validate(
            {
                "message": "hi",
                "attachment_ids": [],
                "SHOPAIKEY_API_KEY": "secret",
            }
        )


def test_history_query_limit_bounds() -> None:
    assert HistoryQuery().limit == 50
    assert HistoryQuery(limit=1).limit == 1
    assert HistoryQuery(limit=100).limit == 100
    with pytest.raises(ValidationError):
        HistoryQuery(limit=0)
    with pytest.raises(ValidationError):
        HistoryQuery(limit=101)
    with pytest.raises(ValidationError):
        HistoryQuery(before="")


def test_resume_requires_exactly_one_action() -> None:
    ok = ResumeRequest(action="save_profile")
    assert ok.action == "save_profile"
    with pytest.raises(ValidationError):
        ResumeRequest(action="")
    with pytest.raises(ValidationError):
        ResumeRequest(action="  ")
    with pytest.raises(ValidationError):
        ResumeRequest.model_validate({"actions": ["a", "b"]})
    with pytest.raises(ValidationError):
        ResumeRequest.model_validate(
            {"action": "save_profile", "choice": "other"}
        )


def test_resume_rejects_secrets() -> None:
    with pytest.raises(ValidationError):
        ResumeRequest.model_validate(
            {"action": "save_profile", "api_key": "x"}
        )
    with pytest.raises(ValidationError):
        ResumeRequest.model_validate(
            {"action": "save_profile", "password": "x"}
        )


def test_forbidden_status_aliases_documented() -> None:
    assert FORBIDDEN_STATUS_ALIASES == frozenset({"complete", "error"})


def test_aware_utc_used_in_tool_views_via_import() -> None:
    """Sanity: UTC now is acceptable for future view construction."""
    now = datetime.now(UTC)
    assert now.tzinfo is not None
