"""Public chat request and history response schemas (Plan 3 §7.4).

API-layer validation only. Persistence and run execution live in repositories
and ``ChatService``. Invalid payloads fail closed before any durable write.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services.chat_context import MAX_ATTACHMENT_IDS

_MAX_USER_TEXT_LEN: Final[int] = 32_768
_MAX_CORRECTION_TEXT_LEN: Final[int] = 32_768
_MAX_IDEMPOTENCY_KEY_LEN: Final[int] = 128
_MAX_ATTACHMENT_ID_LEN: Final[int] = 128
_MAX_HISTORY_LIMIT: Final[int] = 500

_IDEMPOTENCY_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)
_ATTACHMENT_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)


class ChatSchemaBase(BaseModel):
    """Shared config: forbid extras; strip accidental whitespace on strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid idempotency_key")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_IDEMPOTENCY_KEY_LEN:
        raise ValueError("invalid idempotency_key")
    if not _IDEMPOTENCY_KEY_RE.fullmatch(cleaned):
        raise ValueError("invalid idempotency_key")
    return cleaned


def _validate_attachment_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid attachment_id")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_ATTACHMENT_ID_LEN:
        raise ValueError("invalid attachment_id")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError("invalid attachment_id")
    if not _ATTACHMENT_ID_RE.fullmatch(cleaned):
        raise ValueError("invalid attachment_id")
    return cleaned


class TurnRequest(ChatSchemaBase):
    """POST /api/chat/turns body: user text, bounded attachments, turn key."""

    text: str = Field(..., min_length=1, max_length=_MAX_USER_TEXT_LEN)
    attachment_ids: list[str] = Field(default_factory=list, max_length=MAX_ATTACHMENT_IDS)
    idempotency_key: str = Field(..., min_length=1, max_length=_MAX_IDEMPOTENCY_KEY_LEN)

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("invalid text")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("invalid text")
        if len(cleaned) > _MAX_USER_TEXT_LEN:
            raise ValueError("text too large")
        return cleaned

    @field_validator("idempotency_key")
    @classmethod
    def _check_key(cls, value: str) -> str:
        return _validate_idempotency_key(value)

    @field_validator("attachment_ids")
    @classmethod
    def _check_attachments(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("invalid attachment_ids")
        if len(value) > MAX_ATTACHMENT_IDS:
            raise ValueError("too many attachment_ids")
        return [_validate_attachment_id(item) for item in value]


class ResumeRequest(ChatSchemaBase):
    """POST /api/chat/runs/{run_id}/resume body: approval/correction + key."""

    action: Literal["approve", "correct"]
    idempotency_key: str = Field(..., min_length=1, max_length=_MAX_IDEMPOTENCY_KEY_LEN)
    correction_text: str | None = Field(
        default=None,
        max_length=_MAX_CORRECTION_TEXT_LEN,
    )

    @field_validator("idempotency_key")
    @classmethod
    def _check_key(cls, value: str) -> str:
        return _validate_idempotency_key(value)

    @field_validator("correction_text")
    @classmethod
    def _check_correction_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("invalid correction_text")
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > _MAX_CORRECTION_TEXT_LEN:
            raise ValueError("correction_text too large")
        return cleaned

    @model_validator(mode="after")
    def _require_correction_when_correct(self) -> ResumeRequest:
        if self.action == "correct" and not self.correction_text:
            raise ValueError("correction_text required for correct action")
        return self

    def resume_value(self) -> bool | str | dict[str, str]:
        """Map validated command to the LangGraph ``Command(resume=...)`` value."""
        if self.action == "approve":
            return True
        assert self.correction_text is not None
        return {"action": "correct", "text": self.correction_text}


class HistoryMessage(ChatSchemaBase):
    """One durable application history message for hydration.

    Public contract only: role, content, timestamp, optional structured payload.
    Database message primary keys and conversation IDs are never serialized.
    """

    role: str
    content: str
    created_at: datetime
    structured_payload: dict[str, Any] | None = None


class HistoryResponse(ChatSchemaBase):
    """GET /api/chat/history response (bounded optional limit applied server-side).

    Does not expose the singleton conversation primary key or message row IDs.
    """

    messages: list[HistoryMessage]


# Re-export ceiling for route Query constraints.
HISTORY_LIMIT_MAX: Final[int] = _MAX_HISTORY_LIMIT

__all__ = [
    "HISTORY_LIMIT_MAX",
    "HistoryMessage",
    "HistoryResponse",
    "ResumeRequest",
    "TurnRequest",
]
