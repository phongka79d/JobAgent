"""Shared JSON, UUID, UTC, and status vocabulary for Plan 3 contracts.

Status Literals reuse the exact values owned by ``app.db.models.chat`` so
validation boundaries and database CHECKs share one vocabulary. Frontend
aliases such as ``complete`` / ``error`` are not valid application statuses.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias, get_args

from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    AGENT_RUN_STATE_FAILED,
    AGENT_RUN_STATE_INTERRUPTED,
    AGENT_RUN_STATE_RUNNING,
    AGENT_RUN_STATES,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_SYSTEM,
    CHAT_MESSAGE_ROLE_USER,
    CHAT_MESSAGE_ROLES,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
    TOOL_EXECUTION_STATUS_PENDING,
    TOOL_EXECUTION_STATUS_RUNNING,
    TOOL_EXECUTION_STATUSES,
)
from pydantic import AfterValidator, BeforeValidator, ConfigDict, PlainSerializer

# Recursive JSON value: scalar, list, or object. No special "raw document"
# escape type — compact IDs/counts/cards use ordinary objects only.
JSONScalar: TypeAlias = str | int | float | bool | None


def _validate_json_value(value: Any) -> Any:
    """Accept only JSON scalars, lists, and string-keyed objects."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [_validate_json_value(item) for item in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            out[key] = _validate_json_value(item)
        return out
    raise ValueError("value must be a JSON scalar, list, or object")


def _validate_json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("must be a JSON object")
    validated = _validate_json_value(value)
    assert isinstance(validated, dict)
    return validated


# Annotated aliases so Pydantic validates nested JSON without forward-ref rebuild.
JSONValue = Annotated[Any, AfterValidator(_validate_json_value)]
JSONObject = Annotated[dict[str, Any], AfterValidator(_validate_json_object)]

# Exact status / role vocabularies (literals mirror database constants).
RunState = Literal[
    "running",
    "interrupted",
    "completed",
    "failed",
]
ToolStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
]
MessageRole = Literal["user", "assistant", "system"]

assert frozenset(get_args(RunState)) == AGENT_RUN_STATES
assert frozenset(get_args(ToolStatus)) == TOOL_EXECUTION_STATUSES
assert frozenset(get_args(MessageRole)) == CHAT_MESSAGE_ROLES

# Named constant re-exports so schema callers do not invent a second vocabulary.
RUN_STATE_RUNNING = AGENT_RUN_STATE_RUNNING
RUN_STATE_INTERRUPTED = AGENT_RUN_STATE_INTERRUPTED
RUN_STATE_COMPLETED = AGENT_RUN_STATE_COMPLETED
RUN_STATE_FAILED = AGENT_RUN_STATE_FAILED

TOOL_STATUS_PENDING = TOOL_EXECUTION_STATUS_PENDING
TOOL_STATUS_RUNNING = TOOL_EXECUTION_STATUS_RUNNING
TOOL_STATUS_COMPLETED = TOOL_EXECUTION_STATUS_COMPLETED
TOOL_STATUS_FAILED = TOOL_EXECUTION_STATUS_FAILED

MESSAGE_ROLE_USER = CHAT_MESSAGE_ROLE_USER
MESSAGE_ROLE_ASSISTANT = CHAT_MESSAGE_ROLE_ASSISTANT
MESSAGE_ROLE_SYSTEM = CHAT_MESSAGE_ROLE_SYSTEM

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

FORBIDDEN_STATUS_ALIASES: frozenset[str] = frozenset({"complete", "error"})

StrictModelConfig = ConfigDict(extra="forbid", str_strip_whitespace=False)


def _normalize_uuid_str(value: Any) -> str:
    """Accept UUID objects or strings; require lowercase UUID v4 text."""
    if isinstance(value, uuid.UUID):
        if value.version != 4:
            raise ValueError("must be a UUID version 4")
        text = str(value).lower()
    elif isinstance(value, str):
        text = value.strip().lower()
        try:
            parsed = uuid.UUID(text)
        except ValueError as exc:
            raise ValueError("must be a UUID v4 string") from exc
        if parsed.version != 4:
            raise ValueError("must be a UUID version 4")
        text = str(parsed).lower()
    else:
        raise ValueError("must be a UUID v4 string")
    if not _UUID_V4_RE.fullmatch(text):
        raise ValueError("must be a lowercase UUID v4 string")
    return text


def _require_aware_utc(value: datetime) -> datetime:
    """Require a timezone-aware datetime with UTC offset zero."""
    if not isinstance(value, datetime):
        raise ValueError("must be a datetime")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if offset.total_seconds() != 0:
        raise ValueError("timestamp must be UTC (offset zero)")
    return value


def _serialize_datetime_utc(value: datetime) -> str:
    return value.isoformat()


UuidStr = Annotated[str, BeforeValidator(_normalize_uuid_str)]
AwareUtcDatetime = Annotated[
    datetime,
    AfterValidator(_require_aware_utc),
    PlainSerializer(_serialize_datetime_utc, return_type=str),
]


def reject_status_alias(value: str) -> str:
    """Reject known frontend/backend status aliases at validation boundaries."""
    if value in FORBIDDEN_STATUS_ALIASES:
        raise ValueError(
            f"status alias {value!r} is not a valid application status; "
            "use completed|failed (not complete|error)"
        )
    return value
