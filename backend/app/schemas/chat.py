"""Validated chat turn, history, and resume request/response contracts.

Public inputs enforce non-empty user messages, history ``limit`` in 1..100,
and exactly one resume action. Models forbid extra fields and never accept
secrets (API keys, passwords, or provider credentials).

Opaque history cursors encode only the oldest returned ``(created_at, id)``
pair as URL-safe base64 JSON; malformed encoding/shape/time/UUID raises
``ValueError`` suitable for FastAPI ``422`` via Pydantic validation.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any

from app.schemas.common import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_SYSTEM,
    MESSAGE_ROLE_USER,
    AwareUtcDatetime,
    JSONObject,
    MessageRole,
    RunState,
    StrictModelConfig,
    ToolStatus,
    UuidStr,
)
from app.schemas.tools import ToolResult
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

# Exact cursor JSON keys (no extras). Shape is validated on decode.
_CURSOR_KEYS: frozenset[str] = frozenset({"created_at", "id"})


class HistoryCursorPoint(BaseModel):
    """Validated oldest-item key encoded inside an opaque history cursor."""

    model_config = StrictModelConfig

    created_at: AwareUtcDatetime
    id: UuidStr


def encode_history_cursor(created_at: datetime, message_id: str) -> str:
    """Encode ``(created_at, id)`` as a URL-safe opaque cursor string."""
    point = HistoryCursorPoint(created_at=created_at, id=message_id)
    payload = point.model_dump(mode="json")
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_history_cursor(cursor: str) -> tuple[datetime, str]:
    """Decode and validate an opaque history cursor.

    Raises ``ValueError`` for malformed encoding, shape, time, or UUID so
    Pydantic/FastAPI surfaces a ``422`` at the query boundary.
    """
    if not isinstance(cursor, str) or cursor.strip() == "":
        raise ValueError("cursor encoding is malformed")
    text = cursor.strip()
    # Reject non-urlsafe alphabet characters early.
    if any(ch in text for ch in ("+", "/", " ", "\n", "\r", "\t")):
        raise ValueError("cursor encoding is malformed")
    pad = "=" * (-len(text) % 4)
    try:
        # urlsafe alphabet via altchars; validate rejects non-alphabet input.
        raw = base64.b64decode(text + pad, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    if not isinstance(data, dict):
        raise ValueError("cursor shape is invalid")
    if set(data.keys()) != _CURSOR_KEYS:
        raise ValueError("cursor shape is invalid")
    try:
        point = HistoryCursorPoint.model_validate(data)
    except ValidationError as exc:
        # Map nested time/UUID failures to clear cursor validation errors.
        msg = str(exc).lower()
        if "uuid" in msg:
            raise ValueError("cursor id must be a UUID v4") from exc
        if "timestamp" in msg or "datetime" in msg or "timezone" in msg:
            raise ValueError("cursor created_at must be timezone-aware UTC") from exc
        raise ValueError("cursor shape is invalid") from exc
    return point.created_at, point.id


class ChatTurnRequest(BaseModel):
    """``POST /api/chat/turns`` body: one non-empty message and staged attachments."""

    model_config = StrictModelConfig

    message: str
    attachment_ids: list[UuidStr] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def message_must_be_non_empty(cls, value: str) -> str:
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError("message must be a non-empty string")
        return value


class HistoryQuery(BaseModel):
    """``GET /api/chat/history`` query parameters."""

    model_config = StrictModelConfig

    limit: int = Field(default=50, ge=1, le=100)
    before: str | None = None

    @field_validator("before")
    @classmethod
    def before_cursor_validated(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() == "":
            raise ValueError("before cursor must be non-empty when provided")
        # Full encode/shape/time/UUID validation (422-suitable).
        decode_history_cursor(value)
        return value

class ResumeRequest(BaseModel):
    """``POST /api/chat/runs/{run_id}/resume`` body: exactly one approval action."""

    model_config = StrictModelConfig

    action: str

    @field_validator("action")
    @classmethod
    def action_must_be_non_empty(cls, value: str) -> str:
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError("action must be a non-empty string")
        return value

    @model_validator(mode="before")
    @classmethod
    def exactly_one_action_field(cls, data: Any) -> Any:
        """Require one ``action``; reject multi-action or secret-bearing bodies."""
        if not isinstance(data, dict):
            return data
        forbidden = {
            "api_key",
            "password",
            "secret",
            "token",
            "shopaikey_api_key",
            "SHOPAIKEY_API_KEY",
            "actions",
        }
        forbidden_lower = {name.lower() for name in forbidden}
        for key in data:
            key_text = str(key)
            if key_text.lower() in forbidden_lower or key_text.lower().endswith(
                "_password"
            ):
                raise ValueError("resume request must not include secrets")
        if "action" not in data:
            raise ValueError("resume requires exactly one action")
        if "actions" in data or "choice" in data:
            raise ValueError("resume accepts exactly one action field")
        return data


class ToolExecutionView(BaseModel):
    """Hydrated durable tool execution attached to a history run."""

    model_config = StrictModelConfig

    id: UuidStr
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    status: ToolStatus
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    result: ToolResult | None = None
    arguments_summary: JSONObject | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class AgentRunView(BaseModel):
    """Hydrated run metadata for a user message in history."""

    model_config = StrictModelConfig

    id: UuidStr
    user_message_id: UuidStr
    state: RunState
    pending_approval: JSONObject | None = None
    error_code: str | None = None
    completed_at: AwareUtcDatetime | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    tool_executions: list[ToolExecutionView] = Field(default_factory=list)


class ChatMessageView(BaseModel):
    """One history message item (never role ``tool``)."""

    model_config = StrictModelConfig

    id: UuidStr
    role: MessageRole
    content: str
    structured_payload: JSONObject | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    run: AgentRunView | None = None

    @model_validator(mode="after")
    def content_or_payload(self) -> ChatMessageView:
        if self.content == "" and self.structured_payload is None:
            raise ValueError(
                "message requires non-empty content or structured_payload"
            )
        return self


class HistoryPage(BaseModel):
    """Exact history response shape: ``{items, next_cursor}``."""

    model_config = StrictModelConfig

    items: list[ChatMessageView]
    next_cursor: str | None = None


# Re-export role constants for callers that import chat contracts only.
__all__ = [
    "AgentRunView",
    "ChatMessageView",
    "ChatTurnRequest",
    "HistoryCursorPoint",
    "HistoryPage",
    "HistoryQuery",
    "MESSAGE_ROLE_ASSISTANT",
    "MESSAGE_ROLE_SYSTEM",
    "MESSAGE_ROLE_USER",
    "ResumeRequest",
    "ToolExecutionView",
    "decode_history_cursor",
    "encode_history_cursor",
]
