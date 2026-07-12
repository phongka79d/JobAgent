"""Bounded Agent-facing Job tool result contracts (Plan 5 §7.7).

``SaveJobResult`` is the sole return shape of ``JDIngestionService`` (and the
future thin ``save_job`` tool wrapper). It deliberately omits raw JD content,
content hashes, embedding vectors, provider payloads, and secret material.

``SavedJobCardPayload`` is the single minimal display card shared by live
``run_completed`` SSE and durable chat ``structured_payload`` history.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.job_post import (
    MAX_LOCATION_LEN,
    MAX_ORG_LEN,
    MAX_TITLE_LEN,
)

# ---------------------------------------------------------------------------
# Bounds for display-only tool surfaces
# ---------------------------------------------------------------------------

MAX_QUALITY_REASONS: Final[int] = 50
MAX_QUALITY_REASON_LEN: Final[int] = 256
MAX_QUALITY_REASONS_PREVIEW: Final[int] = 5
MAX_SOURCE_URL_LEN: Final[int] = 2048
MAX_ERROR_CODE_LEN: Final[int] = 64
MAX_STATUS_TOKEN_LEN: Final[int] = 64

# Discriminator for assistant structured_payload / run_completed.saved_job.
KIND_SAVED_JOB: Final[str] = "saved_job"

# Allowlisted public tool-activity outcome tokens for save_job (never raw body).
SAVE_JOB_OUTCOME_JOB_SAVED: Final[str] = "job_saved"
SAVE_JOB_OUTCOME_EXACT_DUPLICATE: Final[str] = "exact_duplicate"
SAVE_JOB_OUTCOME_IGNORED_DUPLICATE: Final[str] = "ignored_duplicate"
SAVE_JOB_OUTCOME_UNSCORABLE: Final[str] = "unscorable"
SAVE_JOB_OUTCOME_FORCE_NEW: Final[str] = "force_new_authorized"
SAVE_JOB_OUTCOME_SAVE_FAILED: Final[str] = "save_failed"
SAVE_JOB_OUTCOME_GRAPH_PENDING: Final[str] = "graph_pending"
SAVE_JOB_OUTCOME_GRAPH_FAILED: Final[str] = "graph_sync_failed"

_PRIVATE_HOST_MARKERS: Final[tuple[str, ...]] = (
    "localhost",
    "metadata.google.internal",
    "metadata",
)


class DuplicateOutcome(StrEnum):
    """How this save interacted with existing Job identity."""

    NONE = "none"
    EXACT = "exact"
    IGNORED_NORMALIZED = "ignored_normalized"
    FORCE_NEW = "force_new"


class ProcessingResult(StrEnum):
    """High-level processing outcome for the save operation."""

    PROCESSED = "processed"
    FAILED = "failed"
    EXACT_DUPLICATE = "exact_duplicate"


class JobToolSchemaBase(BaseModel):
    """Strict extra-forbid base for Job tool documents."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobDisplaySummary(JobToolSchemaBase):
    """Safe, bounded fields for chat cards and tool summaries."""

    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    company: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    location: str | None = Field(default=None, max_length=MAX_LOCATION_LEN)
    work_mode: str | None = None
    employment_type: str | None = None
    source_url: str | None = Field(default=None, max_length=MAX_SOURCE_URL_LEN)

    @field_validator("title", "company", "location", "source_url")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SaveJobResult(JobToolSchemaBase):
    """Strict bounded ``save_job`` / ingestion result.

    Contains Job identity, source, processing result, quality/reasons,
    duplicate outcome, graph-sync state, and a sanitized display summary.
    Never carries raw content, hashes, vectors, or provider payloads.
    """

    job_id: UUID
    source_type: str
    source_url: str | None = Field(default=None, max_length=MAX_SOURCE_URL_LEN)
    processing_result: ProcessingResult
    processing_status: str
    jd_quality: str | None = None
    quality_reasons: list[str] | None = Field(
        default=None,
        max_length=MAX_QUALITY_REASONS,
    )
    record_status: str
    duplicate_outcome: DuplicateOutcome
    duplicate_of_job_id: UUID | None = None
    graph_sync_status: str
    error_code: str | None = Field(default=None, max_length=MAX_ERROR_CODE_LEN)
    display: JobDisplaySummary

    @field_validator("quality_reasons")
    @classmethod
    def _quality_reasons(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = " ".join(item.strip().split())
            if not text:
                continue
            if len(text) > MAX_QUALITY_REASON_LEN:
                text = text[:MAX_QUALITY_REASON_LEN]
            cleaned.append(text)
            if len(cleaned) >= MAX_QUALITY_REASONS:
                break
        return cleaned

    @field_validator("error_code")
    @classmethod
    def _error_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper().replace("-", "_").replace(" ", "_")
        if not cleaned:
            return None
        if len(cleaned) > MAX_ERROR_CODE_LEN:
            cleaned = cleaned[:MAX_ERROR_CODE_LEN]
        return cleaned


class SavedJobCardPayload(JobToolSchemaBase):
    """Minimal saved-Job chat card for live SSE and durable history.

    Persist/emit only these display fields — never the tool body, raw JD,
    hashes, vectors, secrets, stack traces, or unsafe URL details.
    """

    kind: Literal["saved_job"] = "saved_job"
    job_id: UUID
    title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    company: str | None = Field(default=None, max_length=MAX_ORG_LEN)
    location: str | None = Field(default=None, max_length=MAX_LOCATION_LEN)
    work_mode: str | None = Field(default=None, max_length=MAX_STATUS_TOKEN_LEN)
    employment_type: str | None = Field(
        default=None,
        max_length=MAX_STATUS_TOKEN_LEN,
    )
    jd_quality: str | None = Field(default=None, max_length=MAX_STATUS_TOKEN_LEN)
    quality_reasons_preview: list[str] | None = Field(
        default=None,
        max_length=MAX_QUALITY_REASONS_PREVIEW,
    )
    processing_result: str = Field(max_length=MAX_STATUS_TOKEN_LEN)
    duplicate_outcome: str = Field(max_length=MAX_STATUS_TOKEN_LEN)
    graph_sync_status: str = Field(max_length=MAX_STATUS_TOKEN_LEN)
    source_url: str | None = Field(default=None, max_length=MAX_SOURCE_URL_LEN)

    @field_validator(
        "title",
        "company",
        "location",
        "work_mode",
        "employment_type",
        "jd_quality",
        "source_url",
    )
    @classmethod
    def _optional_display_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        return cleaned or None

    @field_validator("quality_reasons_preview")
    @classmethod
    def _reasons_preview(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = " ".join(item.strip().split())
            if not text:
                continue
            if len(text) > MAX_QUALITY_REASON_LEN:
                text = text[:MAX_QUALITY_REASON_LEN]
            cleaned.append(text)
            if len(cleaned) >= MAX_QUALITY_REASONS_PREVIEW:
                break
        return cleaned or None

    @field_validator("processing_result", "duplicate_outcome", "graph_sync_status")
    @classmethod
    def _status_token(cls, value: str) -> str:
        cleaned = " ".join(str(value).strip().lower().replace("-", "_").split())
        cleaned = cleaned.replace(" ", "_")
        if not cleaned or len(cleaned) > MAX_STATUS_TOKEN_LEN:
            raise ValueError("invalid status token")
        return cleaned


def safe_public_source_url(value: str | None) -> str | None:
    """Return a credential-free public HTTP(S) URL for display, or None.

    Fail closed on credentials, non-http schemes, localhost/metadata hosts,
    and oversize values. Does not perform DNS (display-only structural check).
    """
    if value is None or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_SOURCE_URL_LEN:
        return None
    try:
        parsed = urlparse(cleaned)
    except Exception:
        return None
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host in _PRIVATE_HOST_MARKERS or host.endswith(".localhost"):
        return None
    if host.endswith(".local") or host.endswith(".internal"):
        return None
    # Literal private / link-local / metadata patterns without DNS.
    if host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."):
        return None
    if host.startswith("169.254.") or host == "0.0.0.0":
        return None
    if host.startswith("::1") or host.startswith("fc") or host.startswith("fd"):
        return None
    return cleaned


def build_saved_job_card(
    result: SaveJobResult,
) -> SavedJobCardPayload:
    """Map a bounded ``SaveJobResult`` to the shared chat card payload."""
    display = result.display
    source = safe_public_source_url(
        display.source_url if display.source_url else result.source_url
    )
    reasons = result.quality_reasons
    preview: list[str] | None = None
    if reasons:
        preview = list(reasons[:MAX_QUALITY_REASONS_PREVIEW])
    return SavedJobCardPayload(
        kind="saved_job",
        job_id=result.job_id,
        title=display.title,
        company=display.company,
        location=display.location,
        work_mode=display.work_mode,
        employment_type=display.employment_type,
        jd_quality=result.jd_quality,
        quality_reasons_preview=preview,
        processing_result=str(result.processing_result),
        duplicate_outcome=str(result.duplicate_outcome),
        graph_sync_status=str(result.graph_sync_status),
        source_url=source,
    )


def try_parse_saved_job_card(
    raw: Mapping[str, Any] | None,
) -> SavedJobCardPayload | None:
    """Fail-closed parse of a saved-job card mapping (history / SSE)."""
    if raw is None or not isinstance(raw, Mapping):
        return None
    if str(raw.get("kind", "")).strip().lower() != KIND_SAVED_JOB:
        return None
    try:
        card = SavedJobCardPayload.model_validate(dict(raw))
    except Exception:
        return None
    # Re-validate URL safety after model parse (fail closed → drop URL).
    safe_url = safe_public_source_url(card.source_url)
    if safe_url != card.source_url:
        card = card.model_copy(update={"source_url": safe_url})
    return card


def parse_save_job_tool_body(
    text: str | None,
) -> tuple[SaveJobResult | None, str | None]:
    """Parse a successful ``save_job`` tool JSON body for card/outcome only.

    Returns ``(result, force_new_audit_or_none)``. Malformed or ERROR bodies
    return ``(None, None)`` without raising. Never returns raw content fields.
    """
    import json

    if not text or not isinstance(text, str):
        return None, None
    stripped = text.strip()
    if not stripped or stripped.startswith("ERROR:"):
        return None, None
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    if data.get("ok") is False:
        return None, None
    audit: str | None = None
    raw_audit = data.get("authorization_audit")
    if isinstance(raw_audit, str) and raw_audit.strip() == SAVE_JOB_OUTCOME_FORCE_NEW:
        audit = SAVE_JOB_OUTCOME_FORCE_NEW
    # Strip non-schema keys before validation.
    payload = {
        key: data[key]
        for key in (
            "job_id",
            "source_type",
            "source_url",
            "processing_result",
            "processing_status",
            "jd_quality",
            "quality_reasons",
            "record_status",
            "duplicate_outcome",
            "duplicate_of_job_id",
            "graph_sync_status",
            "error_code",
            "display",
        )
        if key in data
    }
    try:
        result = SaveJobResult.model_validate(payload)
    except Exception:
        return None, None
    return result, audit


def save_job_public_outcome(
    result: SaveJobResult,
    *,
    force_new_authorized: bool = False,
) -> str:
    """Map a ``SaveJobResult`` to one allowlisted public tool outcome token."""
    if force_new_authorized:
        return SAVE_JOB_OUTCOME_FORCE_NEW
    processing = result.processing_result
    if processing is ProcessingResult.FAILED:
        return SAVE_JOB_OUTCOME_SAVE_FAILED
    if processing is ProcessingResult.EXACT_DUPLICATE:
        return SAVE_JOB_OUTCOME_EXACT_DUPLICATE
    if result.duplicate_outcome is DuplicateOutcome.IGNORED_NORMALIZED:
        return SAVE_JOB_OUTCOME_IGNORED_DUPLICATE
    quality = (result.jd_quality or "").strip().lower()
    if quality == "unscorable":
        return SAVE_JOB_OUTCOME_UNSCORABLE
    graph = (result.graph_sync_status or "").strip().lower()
    if graph in {"failed", "error", "sync_failed"}:
        return SAVE_JOB_OUTCOME_GRAPH_FAILED
    if graph in {"pending", "not_synced", "queued"}:
        return SAVE_JOB_OUTCOME_GRAPH_PENDING
    return SAVE_JOB_OUTCOME_JOB_SAVED


__all__ = [
    "KIND_SAVED_JOB",
    "MAX_ERROR_CODE_LEN",
    "MAX_QUALITY_REASON_LEN",
    "MAX_QUALITY_REASONS",
    "MAX_QUALITY_REASONS_PREVIEW",
    "MAX_SOURCE_URL_LEN",
    "MAX_STATUS_TOKEN_LEN",
    "SAVE_JOB_OUTCOME_EXACT_DUPLICATE",
    "SAVE_JOB_OUTCOME_FORCE_NEW",
    "SAVE_JOB_OUTCOME_GRAPH_FAILED",
    "SAVE_JOB_OUTCOME_GRAPH_PENDING",
    "SAVE_JOB_OUTCOME_IGNORED_DUPLICATE",
    "SAVE_JOB_OUTCOME_JOB_SAVED",
    "SAVE_JOB_OUTCOME_SAVE_FAILED",
    "SAVE_JOB_OUTCOME_UNSCORABLE",
    "DuplicateOutcome",
    "JobDisplaySummary",
    "JobToolSchemaBase",
    "ProcessingResult",
    "SaveJobResult",
    "SavedJobCardPayload",
    "build_saved_job_card",
    "parse_save_job_tool_body",
    "safe_public_source_url",
    "save_job_public_outcome",
    "try_parse_saved_job_card",
]
