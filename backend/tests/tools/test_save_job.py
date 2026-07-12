"""Unit tests for bounded save_job tool authorization and input validation."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from app.schemas.job_tools import (
    DuplicateOutcome,
    JobDisplaySummary,
    ProcessingResult,
    SaveJobResult,
)
from app.services.chat_service import (
    _FORCE_NEW_AUDIT_JSON_FRAGMENT,
    PUBLIC_TOOL_OUTCOME_COMPLETED,
    PUBLIC_TOOL_OUTCOME_FORCE_NEW_AUTHORIZED,
)
from app.services.jd_ingestion import JdIngestionError
from app.tools.save_job import (
    FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN,
    SaveJobInput,
    SaveJobToolService,
    create_save_job_tool,
    is_force_new_declared_in_user_turn,
)
from langchain_core.messages import HumanMessage
from pydantic import ValidationError


class _RecordingIngestion:
    """Fake JD ingestion that records calls and returns a fixed result."""

    def __init__(self, *, result: SaveJobResult | Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result

    async def save_job(
        self,
        *,
        url: str | None = None,
        raw_text: str | None = None,
        force_new_authorized: bool = False,
    ) -> SaveJobResult:
        self.calls.append(
            {
                "url": url,
                "raw_text": raw_text,
                "force_new_authorized": force_new_authorized,
            }
        )
        if isinstance(self._result, Exception):
            raise self._result
        if self._result is not None:
            return self._result
        return SaveJobResult(
            job_id=uuid4(),
            source_type="text",
            source_url=None,
            processing_result=ProcessingResult.PROCESSED,
            processing_status="processed",
            jd_quality="full",
            quality_reasons=None,
            record_status="active",
            duplicate_outcome=DuplicateOutcome.NONE,
            duplicate_of_job_id=None,
            graph_sync_status="pending",
            error_code=None,
            display=JobDisplaySummary(title="Engineer", company="Acme"),
        )


def _state_with_user(text: str) -> dict[str, Any]:
    return {
        "messages_for_this_turn": [HumanMessage(content=text)],
        "run_id": "run-1",
    }


def test_save_job_input_rejects_neither_and_both() -> None:
    with pytest.raises(ValidationError):
        SaveJobInput()
    with pytest.raises(ValidationError):
        SaveJobInput(url=None, raw_text=None)
    with pytest.raises(ValidationError):
        SaveJobInput(url="https://example.com/j", raw_text="body text here")
    with pytest.raises(ValidationError):
        SaveJobInput(url="", raw_text="")
    ok_url = SaveJobInput(url="https://example.com/j")
    assert ok_url.url == "https://example.com/j"
    assert ok_url.raw_text is None
    assert ok_url.force_new is False
    ok_raw = SaveJobInput(raw_text="  pasted JD body content  ")
    assert ok_raw.raw_text == "pasted JD body content"
    assert ok_raw.url is None


def test_declaration_requires_text_outside_payload() -> None:
    jd = "We need a senior engineer. This is a separate position at Acme."
    assert not is_force_new_declared_in_user_turn(
        jd,
        url=None,
        raw_text=jd,
    )
    assert is_force_new_declared_in_user_turn(
        f"Please save this; it is a distinct position.\n\n{jd}",
        url=None,
        raw_text=jd,
    )
    assert is_force_new_declared_in_user_turn(
        "Save https://jobs.example.com/1 — separate position",
        url="https://jobs.example.com/1",
        raw_text=None,
    )
    assert not is_force_new_declared_in_user_turn(
        "https://jobs.example.com/1",
        url="https://jobs.example.com/1",
        raw_text=None,
    )
    # Phrase only in tool args / not in remainder after exclusion.
    assert not is_force_new_declared_in_user_turn(
        "save this JD",
        url=None,
        raw_text="separate position inside the JD body only",
    )


@pytest.mark.asyncio
async def test_unauthorized_force_new_zero_mutation() -> None:
    ingestion = _RecordingIngestion()
    service = SaveJobToolService(ingestion)
    # force_new with no user-turn declaration
    result = await service.execute(
        url=None,
        raw_text="JD body without declaration text.",
        force_new=True,
        state=_state_with_user("Please save this JD body without declaration text."),
    )
    assert "FORCE_NEW_UNAUTHORIZED" in result
    assert ingestion.calls == []

    # force_new when declaration only lives inside the JD payload
    jd = "Role at Acme. This is a separate position in the JD only."
    result2 = await service.execute(
        url=None,
        raw_text=jd,
        force_new=True,
        state=_state_with_user(jd),
    )
    assert "FORCE_NEW_UNAUTHORIZED" in result2
    assert ingestion.calls == []

    # No InjectedState / empty messages
    result3 = await service.execute(
        url=None,
        raw_text="some text",
        force_new=True,
        state=None,
    )
    assert "FORCE_NEW_UNAUTHORIZED" in result3
    assert ingestion.calls == []


@pytest.mark.asyncio
async def test_authorized_force_new_calls_service_and_emits_audit_token() -> None:
    ingestion = _RecordingIngestion()
    service = SaveJobToolService(ingestion)
    jd = "Backend Engineer at Acme. Build APIs. Location: Remote."
    user = f"This is a separate position. Please save:\n{jd}"
    result = await service.execute(
        url=None,
        raw_text=jd,
        force_new=True,
        state=_state_with_user(user),
    )
    assert ingestion.calls == [
        {"url": None, "raw_text": jd, "force_new_authorized": True}
    ]
    data = json.loads(result)
    assert data["ok"] is True
    assert data["authorization_audit"] == FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN
    assert data["authorization_audit"] == PUBLIC_TOOL_OUTCOME_FORCE_NEW_AUTHORIZED
    assert _FORCE_NEW_AUDIT_JSON_FRAGMENT in result
    # Result must not embed the raw JD body.
    assert jd not in result
    assert "raw_content" not in result
    assert "raw_text" not in data


@pytest.mark.asyncio
async def test_force_new_false_never_authorizes_even_with_declaration() -> None:
    ingestion = _RecordingIngestion()
    service = SaveJobToolService(ingestion)
    jd = "Some JD text content for saving."
    user = f"This is a distinct position. Save it.\n{jd}"
    result = await service.execute(
        url=None,
        raw_text=jd,
        force_new=False,
        state=_state_with_user(user),
    )
    assert len(ingestion.calls) == 1
    assert ingestion.calls[0]["force_new_authorized"] is False
    data = json.loads(result)
    assert data["ok"] is True
    assert "authorization_audit" not in data


@pytest.mark.asyncio
async def test_ingestion_errors_surface_stable_code() -> None:
    ingestion = _RecordingIngestion(result=JdIngestionError("INVALID_INPUT"))
    service = SaveJobToolService(ingestion)
    result = await service.execute(
        url=None,
        raw_text="body",
        force_new=False,
        state=_state_with_user("save body"),
    )
    assert result.startswith("ERROR:")
    assert "INVALID_INPUT" in result


@pytest.mark.asyncio
async def test_tool_wrapper_rejects_invalid_input_before_service() -> None:
    ingestion = _RecordingIngestion()
    tool = create_save_job_tool(SaveJobToolService(ingestion))
    # Neither url nor raw_text
    out = await tool.ainvoke({"state": _state_with_user("hello"), "force_new": False})
    assert "SAVE_JOB_INVALID_INPUT" in out
    assert ingestion.calls == []

    # Both provided
    out2 = await tool.ainvoke(
        {
            "state": _state_with_user("hello"),
            "url": "https://example.com/a",
            "raw_text": "also text",
        }
    )
    assert "SAVE_JOB_INVALID_INPUT" in out2
    assert ingestion.calls == []


@pytest.mark.asyncio
async def test_tool_wrapper_authorized_path_and_default_completed_token() -> None:
    ingestion = _RecordingIngestion()
    tool = create_save_job_tool(SaveJobToolService(ingestion))
    jd = "Compact JD for tool path."
    user = f"Treat as a separate position.\n{jd}"
    out = await tool.ainvoke(
        {
            "raw_text": jd,
            "force_new": True,
            "state": _state_with_user(user),
        }
    )
    data = json.loads(out)
    assert data["authorization_audit"] == PUBLIC_TOOL_OUTCOME_FORCE_NEW_AUTHORIZED
    assert PUBLIC_TOOL_OUTCOME_COMPLETED != data["authorization_audit"]
    assert tool.name == "save_job"
