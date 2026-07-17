"""Typed read-only observability request/response contracts (Plan 8).

Collection queries use ``limit`` in ``1..50`` and opaque cursors. CV and run
cursors reuse chat history ``(created_at, id)`` encoding. Chunk cursors encode
``(created_at, ordinal)``. Models forbid extra fields and never carry PDF
bytes, storage paths, prompts, checkpoints, tool arguments, or secrets.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Literal

from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
)
from app.schemas.chat import decode_history_cursor, encode_history_cursor
from app.schemas.common import (
    AwareUtcDatetime,
    RunState,
    StrictModelConfig,
    ToolStatus,
    UuidStr,
)
from pydantic import BaseModel, Field, ValidationError, field_validator

# Abbreviated SHA-256 display width (hex prefix; never full hash in UI).
FILE_HASH_ABBREV_CHARS: int = 12

# Exact chunk-cursor JSON keys.
_CHUNK_CURSOR_KEYS: frozenset[str] = frozenset({"created_at", "ordinal"})

ObservabilityAttachmentState = Literal[
    "staged",
    "active",
    "archived",
    "failed",
]

assert frozenset(
    (
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
    )
) == frozenset(("staged", "active", "archived", "failed"))


class ObservabilityQuery(BaseModel):
    """Shared ``limit`` / ``before`` query for CV history and run history."""

    model_config = StrictModelConfig

    limit: int = Field(default=50, ge=1, le=50)
    before: str | None = None

    @field_validator("before")
    @classmethod
    def before_cursor_validated(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() == "":
            raise ValueError("before cursor must be non-empty when provided")
        decode_history_cursor(value)
        return value


class ChunkListQuery(BaseModel):
    """Chunk-list query: same limit bound; ordinal-based opaque cursor."""

    model_config = StrictModelConfig

    limit: int = Field(default=50, ge=1, le=50)
    before: str | None = None

    @field_validator("before")
    @classmethod
    def before_chunk_cursor_validated(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() == "":
            raise ValueError("before cursor must be non-empty when provided")
        decode_chunk_cursor(value)
        return value


class ChunkCursorPoint(BaseModel):
    """Validated ``(created_at, ordinal)`` key inside an opaque chunk cursor."""

    model_config = StrictModelConfig

    created_at: AwareUtcDatetime
    ordinal: int = Field(ge=0)


def encode_chunk_cursor(created_at: datetime, ordinal: int) -> str:
    """Encode ``(created_at, ordinal)`` as a URL-safe opaque cursor string."""
    point = ChunkCursorPoint(created_at=created_at, ordinal=ordinal)
    payload = point.model_dump(mode="json")
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_chunk_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode and validate an opaque chunk cursor.

    Raises ``ValueError`` for malformed encoding, shape, time, or ordinal so
    Pydantic/FastAPI surfaces a ``422`` at the query boundary.
    """
    if not isinstance(cursor, str) or cursor.strip() == "":
        raise ValueError("cursor encoding is malformed")
    text = cursor.strip()
    if any(ch in text for ch in ("+", "/", " ", "\n", "\r", "\t")):
        raise ValueError("cursor encoding is malformed")
    pad = "=" * (-len(text) % 4)
    try:
        raw = base64.b64decode(text + pad, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor encoding is malformed") from exc
    if not isinstance(data, dict):
        raise ValueError("cursor shape is invalid")
    if set(data.keys()) != _CHUNK_CURSOR_KEYS:
        raise ValueError("cursor shape is invalid")
    try:
        point = ChunkCursorPoint.model_validate(data)
    except ValidationError as exc:
        msg = str(exc).lower()
        if "ordinal" in msg:
            raise ValueError("cursor ordinal must be a non-negative integer") from exc
        if "timestamp" in msg or "datetime" in msg or "timezone" in msg:
            raise ValueError("cursor created_at must be timezone-aware UTC") from exc
        raise ValueError("cursor shape is invalid") from exc
    return point.created_at, point.ordinal


def abbreviate_file_hash(file_hash: str) -> str:
    """Return a fixed-width hex prefix of a SHA-256 digest (never the full hash)."""
    if not isinstance(file_hash, str) or file_hash.strip() == "":
        raise ValueError("file_hash must be a non-empty string")
    text = file_hash.strip().lower()
    if len(text) < FILE_HASH_ABBREV_CHARS:
        return text
    return text[:FILE_HASH_ABBREV_CHARS]


class CvHistoryItem(BaseModel):
    """One attachment summary for CV history (no PDF bytes or storage path)."""

    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1)
    mime_type: Literal["application/pdf"] = ATTACHMENT_MIME_TYPE_PDF  # type: ignore[assignment]
    size_bytes: int = Field(gt=0)
    page_count: int | None = Field(default=None, gt=0)
    state: ObservabilityAttachmentState
    failure_code: str | None = None
    file_hash_abbreviated: str = Field(min_length=1)
    file_available: bool
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class CvHistoryPage(BaseModel):
    """Chronological CV history page with opaque ``next_cursor``."""

    model_config = StrictModelConfig

    items: list[CvHistoryItem]
    next_cursor: str | None = None


class ChunkListItem(BaseModel):
    """One chunk summary for list views (preview only; no full text)."""

    model_config = StrictModelConfig

    attachment_id: UuidStr
    ordinal: int = Field(ge=0)
    preview: str
    char_count: int = Field(gt=0)
    token_estimate: int = Field(ge=0)
    created_at: AwareUtcDatetime


class ChunkListPage(BaseModel):
    """Chronological chunk list page (ascending ordinal) with ``next_cursor``."""

    model_config = StrictModelConfig

    items: list[ChunkListItem]
    next_cursor: str | None = None


class ChunkDetail(BaseModel):
    """Selected chunk full text and safe metadata (no provider fields)."""

    model_config = StrictModelConfig

    attachment_id: UuidStr
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    preview: str
    char_count: int = Field(gt=0)
    token_estimate: int = Field(ge=0)
    created_at: AwareUtcDatetime


class ObservabilityToolExecution(BaseModel):
    """Redacted durable tool activity for one observability run row."""

    model_config = StrictModelConfig

    id: UuidStr
    tool_name: str = Field(min_length=1)
    status: ToolStatus
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    summary: str | None = None


class RunHistoryItem(BaseModel):
    """One durable agent-run projection for observability (no checkpoint/args)."""

    model_config = StrictModelConfig

    id: UuidStr
    user_message_id: UuidStr
    state: RunState
    error_code: str | None = None
    completed_at: AwareUtcDatetime | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    related_attachment_ids: list[UuidStr] = Field(default_factory=list)
    related_job_ids: list[UuidStr] = Field(default_factory=list)
    tool_executions: list[ObservabilityToolExecution] = Field(default_factory=list)


class RunHistoryPage(BaseModel):
    """Chronological agent-run history page with opaque ``next_cursor``."""

    model_config = StrictModelConfig

    items: list[RunHistoryItem]
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# Bounded Neo4j graph snapshot (Plan 8/9 / Master §14)
# ---------------------------------------------------------------------------

GraphStatus = Literal["ready", "stale", "unavailable"]

GraphEdgeType = Literal[
    "HAS_SKILL",
    "REQUIRES",
    "PREFERS",
    "RELATED_TO",
    "PROJECTS_TO",
    "HAS_SECTION",
    "HAS_ENTRY",
]


class GraphCandidateNode(BaseModel):
    """Allowlisted Candidate node fields only."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class GraphCvNode(BaseModel):
    """Allowlisted active CV node fields only (no body/arbitrary attributes)."""

    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1)
    extraction_version: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class GraphCvSectionNode(BaseModel):
    """Allowlisted CVSection fields only."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    entry_count: int = Field(ge=0)


class GraphCvEntryNode(BaseModel):
    """Allowlisted CVEntry fields only (bounded preview; no body/bullets)."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    title: str | None = None
    subtitle: str | None = None
    date_text: str | None = None
    preview: str = ""


class GraphJobNode(BaseModel):
    """Allowlisted Job node fields only."""

    model_config = StrictModelConfig

    id: str = Field(min_length=1)
    title: str
    company: str
    revision: str = Field(min_length=1)


class GraphSkillNode(BaseModel):
    """Allowlisted Skill identity (canonical name only)."""

    model_config = StrictModelConfig

    canonical_name: str = Field(min_length=1)


class GraphEdge(BaseModel):
    """Allowlisted relationship among selected nodes."""

    model_config = StrictModelConfig

    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    type: GraphEdgeType


class GraphSnapshot(BaseModel):
    """Bounded graph projection with typed readiness/stale/unavailable state.

    Accepts no query/filter input at the transport layer. Empty projections for
    ``stale`` / ``unavailable`` / no-active-profile include safe guidance codes
    only — never embeddings, credentials, or arbitrary Cypher results.

    Existing Candidate/Job/Skill fields remain present for D3 compatibility;
    active CV branch fields default empty when absent.
    """

    model_config = StrictModelConfig

    status: GraphStatus
    code: str | None = None
    summary: str = Field(min_length=1)
    rebuild_instruction: str | None = None
    cv: GraphCvNode | None = None
    sections: list[GraphCvSectionNode] = Field(default_factory=list)
    entries: list[GraphCvEntryNode] = Field(default_factory=list)
    candidate: GraphCandidateNode | None = None
    jobs: list[GraphJobNode] = Field(default_factory=list)
    skills: list[GraphSkillNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    nodes_truncated: bool
    edges_truncated: bool
    omitted_node_count: int = Field(ge=0)
    omitted_edge_count: int = Field(ge=0)
    checked_at: AwareUtcDatetime


# Re-export history cursor helpers so observability callers share one owner.
encode_observability_cursor = encode_history_cursor
decode_observability_cursor = decode_history_cursor


__all__ = [
    "FILE_HASH_ABBREV_CHARS",
    "ChunkCursorPoint",
    "ChunkDetail",
    "ChunkListItem",
    "ChunkListPage",
    "ChunkListQuery",
    "CvHistoryItem",
    "CvHistoryPage",
    "GraphCandidateNode",
    "GraphCvEntryNode",
    "GraphCvNode",
    "GraphCvSectionNode",
    "GraphEdge",
    "GraphEdgeType",
    "GraphJobNode",
    "GraphSkillNode",
    "GraphSnapshot",
    "GraphStatus",
    "ObservabilityAttachmentState",
    "ObservabilityQuery",
    "ObservabilityToolExecution",
    "RunHistoryItem",
    "RunHistoryPage",
    "abbreviate_file_hash",
    "decode_chunk_cursor",
    "decode_observability_cursor",
    "encode_chunk_cursor",
    "encode_observability_cursor",
]
