from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core.ids import new_uuid
from app.schemas.agent_activity import AgentActivityPayload, humanize_activity_name
from pydantic import ValidationError

NOW = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


def _running_payload() -> dict[str, object]:
    return {
        "activity_id": new_uuid(),
        "run_id": new_uuid(),
        "sequence": 0,
        "kind": "assistant",
        "label": "Generating reply",
        "technical_name": "response_generation",
        "state": "running",
        "started_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
        "duration_ms": None,
        "error_code": None,
    }


def test_activity_payload_accepts_safe_running_projection() -> None:
    activity = AgentActivityPayload.model_validate(_running_payload())
    assert activity.label == "Generating reply"
    assert activity.state == "running"


def test_activity_payload_rejects_failed_without_safe_code() -> None:
    payload = _running_payload() | {"state": "failed", "completed_at": NOW}
    with pytest.raises(ValidationError, match="error_code"):
        AgentActivityPayload.model_validate(payload)


def test_activity_payload_forbids_unknown_or_raw_fields() -> None:
    with pytest.raises(ValidationError):
        AgentActivityPayload.model_validate(
            _running_payload() | {"arguments": {"cv_text": "forbidden"}}
        )


def test_humanize_activity_name_is_generic() -> None:
    assert humanize_activity_name("future_tool-name") == "Future Tool Name"
    assert humanize_activity_name("   ") == "Agent activity"
