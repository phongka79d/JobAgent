from __future__ import annotations

import re
from typing import Any, Literal

from app.schemas.common import AwareUtcDatetime, StrictModelConfig, ToolStatus, UuidStr
from pydantic import BaseModel, Field, field_validator, model_validator

ActivityKind = Literal["assistant", "tool"]


def humanize_activity_name(value: str) -> str:
    words = re.sub(r"[_-]+", " ", value).strip()
    return words.title() if words else "Agent activity"


class AgentActivityPayload(BaseModel):
    model_config = StrictModelConfig

    activity_id: UuidStr
    run_id: UuidStr
    sequence: int = Field(ge=0)
    kind: ActivityKind
    label: str = Field(min_length=1, max_length=160)
    technical_name: str | None = Field(default=None, max_length=120)
    state: ToolStatus
    started_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    completed_at: AwareUtcDatetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=120)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("activity label must be non-empty")
        return cleaned

    @field_validator("technical_name")
    @classmethod
    def clean_technical_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("technical_name must be non-empty when provided")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            forbidden = {
                "arguments",
                "result",
                "prompt",
                "stack",
                "traceback",
                "cv_text",
                "raw_content",
                "provider_payload",
            }
            if forbidden.intersection(str(key).lower() for key in data):
                raise ValueError("activity payload contains forbidden fields")
        return data

    @model_validator(mode="after")
    def terminal_coupling(self) -> AgentActivityPayload:
        terminal = self.state in ("completed", "failed")
        if terminal != (self.completed_at is not None):
            raise ValueError("terminal activity requires completed_at")
        if not terminal and self.duration_ms is not None:
            raise ValueError("non-terminal activity must not include duration_ms")
        if self.state == "failed":
            if self.error_code is None or not self.error_code.strip():
                raise ValueError("failed activity requires error_code")
        elif self.error_code is not None:
            raise ValueError("non-failed activity must not include error_code")
        return self
