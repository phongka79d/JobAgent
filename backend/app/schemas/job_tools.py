"""Bounded Agent-facing Job tool result contracts (Plan 5 §7.7).

``SaveJobResult`` is the sole return shape of ``JDIngestionService`` (and the
future thin ``save_job`` tool wrapper). It deliberately omits raw JD content,
content hashes, embedding vectors, provider payloads, and secret material.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final
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
MAX_SOURCE_URL_LEN: Final[int] = 2048
MAX_ERROR_CODE_LEN: Final[int] = 64


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


__all__ = [
    "MAX_ERROR_CODE_LEN",
    "MAX_QUALITY_REASON_LEN",
    "MAX_QUALITY_REASONS",
    "MAX_SOURCE_URL_LEN",
    "DuplicateOutcome",
    "JobDisplaySummary",
    "JobToolSchemaBase",
    "ProcessingResult",
    "SaveJobResult",
]
