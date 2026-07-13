"""Validated SSE event contracts for client-facing chat streams.

Every event has ``event_id`` (UUID v4), ``run_id``, timezone-aware UTC
``timestamp``, and an event-specific payload. Event names are exactly the seven
Plan 3 names. Application run/tool statuses stay ``pending|running|completed|
failed`` / ``running|interrupted|completed|failed`` — aliases ``complete`` and
``error`` fail validation.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, get_args

from app.schemas.common import (
    TOOL_STATUS_COMPLETED,
    TOOL_STATUS_FAILED,
    AwareUtcDatetime,
    JSONObject,
    StrictModelConfig,
    ToolStatus,
    UuidStr,
    reject_status_alias,
)
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

SseEventName = Literal[
    "run_started",
    "assistant_status",
    "tool_status",
    "approval_required",
    "text_delta",
    "run_completed",
    "run_failed",
]

SSE_EVENT_NAMES: frozenset[str] = frozenset(get_args(SseEventName))


class _SseEnvelopeBase(BaseModel):
    """Common envelope fields shared by every SSE event."""

    model_config = StrictModelConfig

    event_id: UuidStr
    run_id: UuidStr
    timestamp: AwareUtcDatetime


class RunStartedPayload(BaseModel):
    """``run_started`` payload: run enters ``running`` (optionally resumed)."""

    model_config = StrictModelConfig

    state: Literal["running"] = "running"
    resumed: bool


class AssistantStatusPayload(BaseModel):
    """Optional mid-stream assistant activity signal (not tool/run status)."""

    model_config = StrictModelConfig

    message: str = Field(min_length=1)


class ToolStatusPayload(BaseModel):
    """Durable tool transition: id/name, exact status, optional duration/summary."""

    model_config = StrictModelConfig

    tool_execution_id: UuidStr
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolStatus
    duration_ms: int | None = Field(default=None, ge=0)
    summary: str | None = None
    error_code: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def no_status_aliases(cls, value: Any) -> Any:
        if isinstance(value, str):
            reject_status_alias(value)
        return value

    @model_validator(mode="after")
    def terminal_fields(self) -> ToolStatusPayload:
        if self.status == TOOL_STATUS_FAILED:
            if self.error_code is None or self.error_code.strip() == "":
                raise ValueError(
                    "tool_status failed requires a stable non-null error_code"
                )
        if self.status in (TOOL_STATUS_COMPLETED, TOOL_STATUS_FAILED):
            if self.duration_ms is None:
                raise ValueError(
                    "tool_status completed|failed requires duration_ms"
                )
        if self.status not in (TOOL_STATUS_COMPLETED, TOOL_STATUS_FAILED):
            if self.duration_ms is not None:
                raise ValueError(
                    "tool_status pending|running must not include duration_ms"
                )
            if self.error_code is not None:
                raise ValueError(
                    "tool_status pending|running must not include error_code"
                )
        if self.status == TOOL_STATUS_COMPLETED and self.error_code is not None:
            raise ValueError("tool_status completed must not include error_code")
        return self


class ApprovalRequiredPayload(BaseModel):
    """Interrupt projection: interrupted state, kind, actions, compact card."""

    model_config = StrictModelConfig

    state: Literal["interrupted"] = "interrupted"
    kind: str = Field(min_length=1)
    allowed_actions: list[str] = Field(min_length=1)
    card: JSONObject = Field(default_factory=dict)

    @field_validator("allowed_actions")
    @classmethod
    def actions_non_empty_strings(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_actions must contain at least one action")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str) or item.strip() == "":
                raise ValueError("allowed_actions entries must be non-empty strings")
            cleaned.append(item)
        return cleaned


class TextDeltaPayload(BaseModel):
    """Ordered non-empty assistant text fragment."""

    model_config = StrictModelConfig

    delta: str = Field(min_length=1)

    @field_validator("delta")
    @classmethod
    def delta_must_be_non_empty(cls, value: str) -> str:
        if value == "":
            raise ValueError("text_delta must be a non-empty string")
        return value


class RunCompletedPayload(BaseModel):
    """Terminal success event."""

    model_config = StrictModelConfig

    state: Literal["completed"] = "completed"


class RunFailedPayload(BaseModel):
    """Terminal failure event with stable code and safe summary."""

    model_config = StrictModelConfig

    state: Literal["failed"] = "failed"
    error_code: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @field_validator("error_code")
    @classmethod
    def error_code_non_empty(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("error_code must be a stable non-empty string")
        return value


class RunStartedEvent(_SseEnvelopeBase):
    event: Literal["run_started"] = "run_started"
    payload: RunStartedPayload


class AssistantStatusEvent(_SseEnvelopeBase):
    event: Literal["assistant_status"] = "assistant_status"
    payload: AssistantStatusPayload


class ToolStatusEvent(_SseEnvelopeBase):
    event: Literal["tool_status"] = "tool_status"
    payload: ToolStatusPayload


class ApprovalRequiredEvent(_SseEnvelopeBase):
    event: Literal["approval_required"] = "approval_required"
    payload: ApprovalRequiredPayload


class TextDeltaEvent(_SseEnvelopeBase):
    event: Literal["text_delta"] = "text_delta"
    payload: TextDeltaPayload


class RunCompletedEvent(_SseEnvelopeBase):
    event: Literal["run_completed"] = "run_completed"
    payload: RunCompletedPayload


class RunFailedEvent(_SseEnvelopeBase):
    event: Literal["run_failed"] = "run_failed"
    payload: RunFailedPayload


SseEvent = Annotated[
    RunStartedEvent
    | AssistantStatusEvent
    | ToolStatusEvent
    | ApprovalRequiredEvent
    | TextDeltaEvent
    | RunCompletedEvent
    | RunFailedEvent,
    Field(discriminator="event"),
]

_sse_adapter: TypeAdapter[SseEvent] = TypeAdapter(SseEvent)


def parse_sse_event(data: Any) -> SseEvent:
    """Validate and return a typed SSE event envelope."""
    return _sse_adapter.validate_python(data)


def sse_event_to_dict(event: SseEvent) -> dict[str, Any]:
    """Serialize an SSE event for framing (JSON-compatible dict)."""
    return event.model_dump(mode="json")
