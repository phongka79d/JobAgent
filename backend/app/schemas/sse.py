"""Validated public SSE event union and ordering boundary.

FastAPI owns the client-facing stream. This module is the single source of
truth for the exact eight-event contract, event-specific payloads, sanitized
display fields, deterministic serialization, and legal event ordering.

Prohibited in display payloads: raw tool arguments, document bodies, secrets,
headers, stack traces, and internal-only IDs (storage paths, Neo4j IDs, raw
DB keys). Public ``run_id`` and short opaque ``tool_call_id`` / ``event_id``
correlation keys are allowed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)

# ---------------------------------------------------------------------------
# Limits and prohibited content patterns
# ---------------------------------------------------------------------------

_MAX_EVENT_ID_LEN: Final[int] = 128
_MAX_LABEL_LEN: Final[int] = 128
_MAX_OUTCOME_LEN: Final[int] = 512
_MAX_STATUS_MESSAGE_LEN: Final[int] = 256
_MAX_TEXT_DELTA_LEN: Final[int] = 4096
_MAX_ERROR_CODE_LEN: Final[int] = 64
_MAX_APPROVAL_SUMMARY_LEN: Final[int] = 512
_MAX_TOOL_CALL_ID_LEN: Final[int] = 64
_MAX_APPROVAL_KIND_LEN: Final[int] = 64

_EVENT_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
)
_TOOL_CALL_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
)
_ERROR_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_APPROVAL_KIND_RE: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]{0,63}$"
)
_FRIENDLY_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9 _./-]{0,127}$"
)

_PATH_DRIVE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z]:[\\/]")
_AUTH_SCHEME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:Basic|Bearer|Digest|Token|Negotiate|NTLM)\s+\S+",
    re.IGNORECASE,
)
_URI_USERINFO_RE: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#\"']*:[^/\s?#\"']*@",
)
_CREDENTIAL_ASSIGNMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\s\"'=])(?:password|passwd|secret|token|api[_-]?key|x[_-]?api[_-]?key|"
    r"authorization|access[_-]?key|private[_-]?key|credential|credentials|"
    r"auth[_-]?token|session[_-]?token|auth)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_SECRET_VALUE_MARKERS: Final[tuple[str, ...]] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)
_STACK_TRACE_MARKERS: Final[tuple[str, ...]] = (
    "traceback (most recent call last)",
    'file "',
    "file '",
    '  file "',
)

_PROHIBITED_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "bearer",
        "private_key",
        "storage_path",
        "file_path",
        "raw_document",
        "raw_content",
        "document_bytes",
        "pdf_bytes",
        "cv_text",
        "jd_text",
        "stack_trace",
        "traceback",
        "neo4j_id",
        "element_id",
        "internal_id",
    }
)

# Field names that must never appear in serialized display payloads.
_PROHIBITED_SERIALIZED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "arguments",
        "raw_arguments",
        "tool_arguments",
        "document",
        "document_body",
        "cv_text",
        "jd_text",
        "secret",
        "secrets",
        "headers",
        "authorization",
        "stack_trace",
        "traceback",
        "exception",
        "storage_path",
        "file_path",
        "internal_id",
        "neo4j_id",
        "element_id",
        "api_key",
        "password",
    }
)


# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------


class SSEEventType(StrEnum):
    """Exact public SSE event names (source-locked set of eight)."""

    RUN_STARTED = "run_started"
    ASSISTANT_STATUS = "assistant_status"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    APPROVAL_REQUIRED = "approval_required"
    TEXT_DELTA = "text_delta"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


SUPPORTED_SSE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    member.value for member in SSEEventType
)

TERMINAL_SSE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        SSEEventType.RUN_COMPLETED.value,
        SSEEventType.RUN_FAILED.value,
    }
)


class ToolDisplayStatus(StrEnum):
    """Approved tool activity display states for ChatToolCalls."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class AssistantDisplayStatus(StrEnum):
    """Approved assistant status labels for the public stream."""

    THINKING = "thinking"
    WORKING = "working"
    STREAMING = "streaming"
    WAITING = "waiting"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SSESchemaError(ValueError):
    """SSE event validation or ordering failed (safe message only)."""


class SSEOrderError(SSESchemaError):
    """Event rejected by the single ordering / run-state boundary."""


# ---------------------------------------------------------------------------
# Sanitization helpers (schema-local; no repository import)
# ---------------------------------------------------------------------------


def _collapse_ws(value: str) -> str:
    return " ".join(value.strip().split())


def _looks_like_path(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    if "file:" in lower:
        return True
    if _PATH_DRIVE_RE.match(stripped):
        return True
    if stripped.startswith(("\\\\", "//", "/", "./", "../")):
        return True
    if "\\" in stripped:
        return True
    return False


def _looks_like_secret_or_header(value: str) -> bool:
    stripped = value.strip().strip("\"'")
    if _AUTH_SCHEME_RE.search(stripped):
        return True
    if _URI_USERINFO_RE.search(stripped):
        return True
    if _CREDENTIAL_ASSIGNMENT_RE.search(stripped):
        return True
    upper = value.upper()
    for marker in _SECRET_VALUE_MARKERS:
        if marker in upper:
            return True
    return False


def _looks_like_stack_trace(value: str) -> bool:
    lowered = value.lower()
    for marker in _STACK_TRACE_MARKERS:
        if marker in lowered:
            return True
    if "traceback" in lowered and "line " in lowered:
        return True
    return False


def _looks_like_document_body(value: str) -> bool:
    """Conservative detector for raw multi-line CV/JD-style document dumps.

    Streamed assistant deltas are short partial chunks; pasted multi-line
    document bodies are not permitted on the public SSE boundary. Intentionally
    narrow so ordinary single-line or short multi-sentence partial responses pass.
    """
    lines = [line for line in value.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    # Three or more non-empty lines with substantial length → document-shaped.
    if len(value) >= 80:
        return True
    lowered = value.lower()
    document_markers = (
        "curriculum vitae",
        "job description",
        "years of experience",
        "work experience",
        "education:",
        "skills:",
        "experience:",
        "responsibilities:",
        "qualifications:",
        "requirements:",
        "objective:",
    )
    return any(marker in lowered for marker in document_markers)


def _contains_prohibited_token(value: str) -> bool:
    lowered = value.lower().replace("-", "_")
    for token in _PROHIBITED_TOKENS:
        if token in lowered:
            return True
    return False


def _reject_unsafe_text(value: str, *, field: str) -> str:
    """Fail closed on path/secret/stack/document-category display text."""
    if _looks_like_path(value):
        raise ValueError(f"{field}: filesystem path not permitted")
    if _looks_like_secret_or_header(value):
        raise ValueError(f"{field}: prohibited content category")
    if _looks_like_stack_trace(value):
        raise ValueError(f"{field}: stack traces not permitted")
    if _contains_prohibited_token(value):
        raise ValueError(f"{field}: prohibited content category")
    return value


def _validate_event_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid event_id")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_EVENT_ID_LEN:
        raise ValueError("invalid event_id")
    if not _EVENT_ID_RE.fullmatch(cleaned):
        raise ValueError("invalid event_id")
    return cleaned


def _validate_run_id(value: str | UUID) -> str:
    """Public run identity as canonical UUID string (no internal-only IDs)."""
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise ValueError("invalid run_id")
    cleaned = value.strip()
    try:
        return str(UUID(cleaned))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("invalid run_id") from exc


def _validate_timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("invalid timestamp")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validate_friendly_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid label")
    cleaned = _collapse_ws(value)
    if not cleaned or len(cleaned) > _MAX_LABEL_LEN:
        raise ValueError("invalid label")
    if not _FRIENDLY_LABEL_RE.fullmatch(cleaned):
        raise ValueError("invalid label")
    return _reject_unsafe_text(cleaned, field="label")


def _validate_tool_call_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid tool_call_id")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_TOOL_CALL_ID_LEN:
        raise ValueError("invalid tool_call_id")
    if not _TOOL_CALL_ID_RE.fullmatch(cleaned):
        raise ValueError("invalid tool_call_id")
    return cleaned


def _validate_short_outcome(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid outcome")
    cleaned = _collapse_ws(value)
    if not cleaned:
        return None
    if len(cleaned) > _MAX_OUTCOME_LEN:
        raise ValueError("outcome too large")
    return _reject_unsafe_text(cleaned, field="outcome")


def _validate_error_code(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid error_code")
    cleaned = value.strip().upper().replace("-", "_").replace(" ", "_")
    if not cleaned or len(cleaned) > _MAX_ERROR_CODE_LEN:
        raise ValueError("invalid error_code")
    if not _ERROR_CODE_RE.fullmatch(cleaned):
        raise ValueError("invalid error_code")
    return cleaned


def _validate_approval_kind(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid approval_kind")
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not cleaned:
        return None
    if len(cleaned) > _MAX_APPROVAL_KIND_LEN:
        raise ValueError("invalid approval_kind")
    if not _APPROVAL_KIND_RE.fullmatch(cleaned):
        raise ValueError("invalid approval_kind")
    return cleaned


def _assert_no_prohibited_keys(data: dict[str, Any], *, path: str = "") -> None:
    for key, child in data.items():
        key_l = str(key).lower()
        if key_l in _PROHIBITED_SERIALIZED_KEYS:
            raise ValueError(f"prohibited key in payload: {path}{key}")
        if isinstance(child, dict):
            _assert_no_prohibited_keys(child, path=f"{path}{key}.")
        elif isinstance(child, list):
            for idx, item in enumerate(child):
                if isinstance(item, dict):
                    _assert_no_prohibited_keys(item, path=f"{path}{key}[{idx}].")


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------


class _PayloadBase(BaseModel):
    """Shared payload config: forbid extras and unknown fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RunStartedPayload(_PayloadBase):
    """Marks the start of a public run stream (no display secrets)."""

    # Empty payload is valid; field reserved for future non-sensitive metadata.
    pass


class AssistantStatusPayload(_PayloadBase):
    """Assistant activity label for the stream."""

    status: AssistantDisplayStatus
    message: str | None = Field(default=None, max_length=_MAX_STATUS_MESSAGE_LEN)

    @field_validator("message")
    @classmethod
    def _sanitize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _collapse_ws(value)
        if not cleaned:
            return None
        if len(cleaned) > _MAX_STATUS_MESSAGE_LEN:
            raise ValueError("message too large")
        return _reject_unsafe_text(cleaned, field="message")


class ToolStartedPayload(_PayloadBase):
    """Tool activity start: friendly label + approved display status only."""

    tool_call_id: str
    label: str
    status: ToolDisplayStatus = ToolDisplayStatus.RUNNING

    @field_validator("tool_call_id")
    @classmethod
    def _check_tool_call_id(cls, value: str) -> str:
        return _validate_tool_call_id(value)

    @field_validator("label")
    @classmethod
    def _check_label(cls, value: str) -> str:
        return _validate_friendly_label(value)

    @field_validator("status")
    @classmethod
    def _check_start_status(cls, value: ToolDisplayStatus) -> ToolDisplayStatus:
        if value not in (ToolDisplayStatus.PENDING, ToolDisplayStatus.RUNNING):
            raise ValueError("tool_started status must be pending or running")
        return value


class ToolCompletedPayload(_PayloadBase):
    """Tool activity finish: label, terminal display status, duration, outcome."""

    tool_call_id: str
    label: str
    status: ToolDisplayStatus
    duration_ms: int | None = Field(default=None, ge=0)
    outcome: str | None = Field(default=None, max_length=_MAX_OUTCOME_LEN)

    @field_validator("tool_call_id")
    @classmethod
    def _check_tool_call_id(cls, value: str) -> str:
        return _validate_tool_call_id(value)

    @field_validator("label")
    @classmethod
    def _check_label(cls, value: str) -> str:
        return _validate_friendly_label(value)

    @field_validator("status")
    @classmethod
    def _check_complete_status(cls, value: ToolDisplayStatus) -> ToolDisplayStatus:
        if value not in (ToolDisplayStatus.COMPLETE, ToolDisplayStatus.ERROR):
            raise ValueError("tool_completed status must be complete or error")
        return value

    @field_validator("outcome")
    @classmethod
    def _check_outcome(cls, value: str | None) -> str | None:
        return _validate_short_outcome(value)


class ApprovalRequiredPayload(_PayloadBase):
    """Interrupt: short sanitized approval summary only (no draft/document bodies)."""

    summary: str = Field(max_length=_MAX_APPROVAL_SUMMARY_LEN)
    approval_kind: str | None = None

    @field_validator("summary")
    @classmethod
    def _check_summary(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("invalid summary")
        cleaned = _collapse_ws(value)
        if not cleaned or len(cleaned) > _MAX_APPROVAL_SUMMARY_LEN:
            raise ValueError("invalid summary")
        return _reject_unsafe_text(cleaned, field="summary")

    @field_validator("approval_kind")
    @classmethod
    def _check_kind(cls, value: str | None) -> str | None:
        return _validate_approval_kind(value)


class TextDeltaPayload(_PayloadBase):
    """Partial assistant text chunk (never secrets/headers/stack/document dumps)."""

    # Keep intentional streaming spacing (do not strip trailing spaces).
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    delta: str = Field(min_length=1, max_length=_MAX_TEXT_DELTA_LEN)

    @field_validator("delta")
    @classmethod
    def _check_delta(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("invalid delta")
        if len(value) > _MAX_TEXT_DELTA_LEN:
            raise ValueError("delta too large")
        # Do not collapse whitespace: preserve intentional streaming spacing.
        # Reuse schema-local secret/stack detectors (same semantics as other
        # display fields) rather than full _reject_unsafe_text, which collapses
        # paths/token categories too aggressively for free-form assistant text.
        if _looks_like_secret_or_header(value):
            raise ValueError("delta: prohibited content category")
        if _looks_like_stack_trace(value):
            raise ValueError("delta: stack traces not permitted")
        if _AUTH_SCHEME_RE.search(value) or _URI_USERINFO_RE.search(value):
            raise ValueError("delta: prohibited content category")
        # Conservative document boundary: multi-line CV/JD-shaped bodies only.
        if _looks_like_document_body(value):
            raise ValueError("delta: raw document body not permitted")
        return value


class RunCompletedPayload(_PayloadBase):
    """Terminal success marker (no additional display secrets)."""

    pass


class RunFailedPayload(_PayloadBase):
    """Terminal failure: stable code + short sanitized message only."""

    error_code: str
    message: str | None = Field(default=None, max_length=_MAX_STATUS_MESSAGE_LEN)

    @field_validator("error_code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return _validate_error_code(value)

    @field_validator("message")
    @classmethod
    def _check_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _collapse_ws(value)
        if not cleaned:
            return None
        if len(cleaned) > _MAX_STATUS_MESSAGE_LEN:
            cleaned = cleaned[:_MAX_STATUS_MESSAGE_LEN]
        return _reject_unsafe_text(cleaned, field="message")


# ---------------------------------------------------------------------------
# Event envelope (discriminated union)
# ---------------------------------------------------------------------------


class _SSEEventBase(BaseModel):
    """Common envelope fields required on every public SSE event."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: str
    run_id: str
    timestamp: datetime

    @field_validator("event_id")
    @classmethod
    def _check_event_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("run_id", mode="before")
    @classmethod
    def _check_run_id(cls, value: str | UUID) -> str:
        return _validate_run_id(value)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _check_timestamp(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _validate_timestamp(parsed)
        return _validate_timestamp(value)


class RunStartedEvent(_SSEEventBase):
    event: Literal[SSEEventType.RUN_STARTED] = SSEEventType.RUN_STARTED
    # payload is required on the wire; empty object only when explicitly supplied.
    payload: RunStartedPayload


class AssistantStatusEvent(_SSEEventBase):
    event: Literal[SSEEventType.ASSISTANT_STATUS] = SSEEventType.ASSISTANT_STATUS
    payload: AssistantStatusPayload


class ToolStartedEvent(_SSEEventBase):
    event: Literal[SSEEventType.TOOL_STARTED] = SSEEventType.TOOL_STARTED
    payload: ToolStartedPayload


class ToolCompletedEvent(_SSEEventBase):
    event: Literal[SSEEventType.TOOL_COMPLETED] = SSEEventType.TOOL_COMPLETED
    payload: ToolCompletedPayload


class ApprovalRequiredEvent(_SSEEventBase):
    event: Literal[SSEEventType.APPROVAL_REQUIRED] = SSEEventType.APPROVAL_REQUIRED
    payload: ApprovalRequiredPayload


class TextDeltaEvent(_SSEEventBase):
    event: Literal[SSEEventType.TEXT_DELTA] = SSEEventType.TEXT_DELTA
    payload: TextDeltaPayload


class RunCompletedEvent(_SSEEventBase):
    event: Literal[SSEEventType.RUN_COMPLETED] = SSEEventType.RUN_COMPLETED
    # payload is required on the wire; empty object only when explicitly supplied.
    payload: RunCompletedPayload


class RunFailedEvent(_SSEEventBase):
    event: Literal[SSEEventType.RUN_FAILED] = SSEEventType.RUN_FAILED
    payload: RunFailedPayload


type SSEEvent = Annotated[
    RunStartedEvent
    | AssistantStatusEvent
    | ToolStartedEvent
    | ToolCompletedEvent
    | ApprovalRequiredEvent
    | TextDeltaEvent
    | RunCompletedEvent
    | RunFailedEvent,
    Field(discriminator="event"),
]

_SSE_EVENT_ADAPTER: Final[TypeAdapter[SSEEvent]] = TypeAdapter(SSEEvent)


def parse_sse_event(data: dict[str, Any] | SSEEvent) -> SSEEvent:
    """Parse and validate one event; rejects unknown types and payload mismatch."""
    if isinstance(
        data,
        (
            RunStartedEvent,
            AssistantStatusEvent,
            ToolStartedEvent,
            ToolCompletedEvent,
            ApprovalRequiredEvent,
            TextDeltaEvent,
            RunCompletedEvent,
            RunFailedEvent,
        ),
    ):
        return data
    if not isinstance(data, dict):
        raise SSESchemaError("event must be an object")
    event_name = data.get("event")
    if event_name is not None and event_name not in SUPPORTED_SSE_EVENT_TYPES:
        raise SSESchemaError("unknown event type")
    try:
        event = _SSE_EVENT_ADAPTER.validate_python(data)
    except Exception as exc:  # noqa: BLE001 — normalize to SSESchemaError
        raise SSESchemaError("invalid event") from exc
    return event


def serialize_sse_event(event: SSEEvent | dict[str, Any]) -> dict[str, Any]:
    """Deterministic JSON-ready dict (mode=json); rejects prohibited keys."""
    model = parse_sse_event(event) if isinstance(event, dict) else event
    if not isinstance(
        model,
        (
            RunStartedEvent,
            AssistantStatusEvent,
            ToolStartedEvent,
            ToolCompletedEvent,
            ApprovalRequiredEvent,
            TextDeltaEvent,
            RunCompletedEvent,
            RunFailedEvent,
        ),
    ):
        raise SSESchemaError("invalid event")
    dumped: dict[str, Any] = model.model_dump(mode="json")
    # Canonical field order for wire stability.
    ordered: dict[str, Any] = {
        "event": dumped["event"],
        "event_id": dumped["event_id"],
        "run_id": dumped["run_id"],
        "timestamp": dumped["timestamp"],
        "payload": dumped["payload"],
    }
    _assert_no_prohibited_keys(ordered)
    return ordered


def serialize_sse_event_json(event: SSEEvent | dict[str, Any]) -> str:
    """Deterministic JSON string for SSE ``data:`` lines."""
    model = parse_sse_event(event) if isinstance(event, dict) else event
    ordered = serialize_sse_event(model)
    # Re-validate through model for stable separators via pydantic JSON.
    return model.__class__.model_validate(ordered).model_dump_json()


# ---------------------------------------------------------------------------
# Ordering / run-state boundary
# ---------------------------------------------------------------------------


class RunStreamState(StrEnum):
    """Declared public run stream state used by the ordering boundary."""

    IDLE = "idle"
    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    TERMINAL = "terminal"


class SSEEventOrderValidator:
    """Single ordering and state-consistency boundary for one run stream.

    Rules:
    - No event is accepted before ``run_started``.
    - ``run_started`` only from idle; establishes ``run_id``.
    - No events after a terminal event (``run_completed`` / ``run_failed``).
    - ``tool_completed`` requires a matching open ``tool_started``.
    - ``tool_started`` / ``text_delta`` rejected while awaiting approval.
    - ``approval_required`` only from active (not while tools still open).
    - Duplicate ``event_id`` values are rejected (producer contract).
    - All events must share the stream ``run_id`` after start.
    """

    def __init__(self) -> None:
        self._state: RunStreamState = RunStreamState.IDLE
        self._run_id: str | None = None
        self._seen_event_ids: set[str] = set()
        self._open_tools: set[str] = set()
        self._finished_tools: set[str] = set()

    @property
    def state(self) -> RunStreamState:
        return self._state

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def validate(self, event: SSEEvent | dict[str, Any]) -> SSEEvent:
        """Validate one event against stream state; return the typed event."""
        model = parse_sse_event(event)
        event_name = str(model.event)
        event_id = model.event_id
        run_id = model.run_id

        if event_id in self._seen_event_ids:
            raise SSEOrderError("duplicate event_id")

        if self._state is RunStreamState.TERMINAL:
            raise SSEOrderError("event after terminal")

        if self._state is RunStreamState.IDLE:
            if event_name != SSEEventType.RUN_STARTED.value:
                raise SSEOrderError("event before run_started")
            self._run_id = run_id
            self._seen_event_ids.add(event_id)
            self._state = RunStreamState.ACTIVE
            return model

        # ACTIVE or AWAITING_APPROVAL
        if self._run_id is not None and run_id != self._run_id:
            raise SSEOrderError("run_id mismatch")

        if event_name == SSEEventType.RUN_STARTED.value:
            raise SSEOrderError("duplicate run_started")

        if self._state is RunStreamState.AWAITING_APPROVAL:
            if event_name in (
                SSEEventType.TOOL_STARTED.value,
                SSEEventType.TOOL_COMPLETED.value,
                SSEEventType.TEXT_DELTA.value,
                SSEEventType.ASSISTANT_STATUS.value,
                SSEEventType.APPROVAL_REQUIRED.value,
            ):
                raise SSEOrderError("event inconsistent with awaiting_approval")
            if event_name not in TERMINAL_SSE_EVENT_TYPES:
                raise SSEOrderError("event inconsistent with awaiting_approval")

        if event_name == SSEEventType.TOOL_STARTED.value:
            assert isinstance(model, ToolStartedEvent)
            tool_call_id = model.payload.tool_call_id
            if tool_call_id in self._open_tools or tool_call_id in self._finished_tools:
                raise SSEOrderError("tool sequence inconsistent")
            self._open_tools.add(tool_call_id)

        elif event_name == SSEEventType.TOOL_COMPLETED.value:
            assert isinstance(model, ToolCompletedEvent)
            tool_call_id = model.payload.tool_call_id
            if tool_call_id not in self._open_tools:
                raise SSEOrderError("tool_completed without tool_started")
            self._open_tools.discard(tool_call_id)
            self._finished_tools.add(tool_call_id)

        elif event_name == SSEEventType.APPROVAL_REQUIRED.value:
            if self._state is not RunStreamState.ACTIVE:
                raise SSEOrderError("approval_required inconsistent with run state")
            if self._open_tools:
                raise SSEOrderError("approval_required with open tools")
            self._seen_event_ids.add(event_id)
            self._state = RunStreamState.AWAITING_APPROVAL
            return model

        elif event_name in TERMINAL_SSE_EVENT_TYPES:
            if self._open_tools:
                raise SSEOrderError("terminal event with open tools")
            self._seen_event_ids.add(event_id)
            self._state = RunStreamState.TERMINAL
            return model

        elif event_name in (
            SSEEventType.ASSISTANT_STATUS.value,
            SSEEventType.TEXT_DELTA.value,
        ):
            if self._state is not RunStreamState.ACTIVE:
                raise SSEOrderError("event inconsistent with run state")

        else:
            raise SSEOrderError("unknown event in order boundary")

        self._seen_event_ids.add(event_id)
        return model

    def validate_sequence(
        self, events: list[SSEEvent | dict[str, Any]]
    ) -> list[SSEEvent]:
        """Validate a full sequence; fails on first illegal event."""
        return [self.validate(item) for item in events]


def validate_sse_event_order(
    events: list[SSEEvent | dict[str, Any]],
) -> list[SSEEvent]:
    """Convenience: validate a sequence with a fresh ordering boundary."""
    return SSEEventOrderValidator().validate_sequence(events)
