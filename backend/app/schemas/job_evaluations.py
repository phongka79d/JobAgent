"""Validated job evaluation persistence and public saved-JD read projections.

Owns Pydantic boundaries for persisted ``result_json`` (compact MatchResult),
derived none|current|stale state, and Master §7.7 SavedJob list/detail views.
Never accepts client-supplied revision fields or context hashes as authority.
Opaque list cursors reuse the chat ``(created_at, id)`` codec.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.schemas.chat import decode_history_cursor, encode_history_cursor
from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from app.schemas.jobs import (
    JobJdQuality,
    JobPostExtraction,
    JobProcessingStatus,
)
from app.schemas.matching import MatchResult, parse_match_result
from pydantic import BaseModel, Field, field_validator

EvaluationCurrentnessLiteral = Literal["none", "current", "stale"]
EvaluationRowStateLiteral = Literal["current", "stale"]
JobSourceTypeLiteral = Literal["url", "text"]

# Public saved-JD list uses the same opaque (created_at, id) cursor owner as chat.
encode_saved_jobs_cursor = encode_history_cursor
decode_saved_jobs_cursor = decode_history_cursor

SAVED_JOBS_LIMIT_MIN: int = 1
SAVED_JOBS_LIMIT_MAX: int = 50
SAVED_JOBS_DEFAULT_LIMIT: int = 50


def _as_aware_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive datetimes to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class JobEvaluationRecord(BaseModel):
    """Durable evaluation row projection (no raw CV/JD/embeddings)."""

    model_config = StrictModelConfig

    id: UuidStr
    job_id: UuidStr
    active_attachment_id: UuidStr
    evaluation_context_hash: str = Field(min_length=1)
    job_revision: AwareUtcDatetime
    profile_revision: AwareUtcDatetime
    preferences_revision: AwareUtcDatetime
    cv_source_hash: str = Field(min_length=1)
    matching_contract_version: str = Field(min_length=1)
    result: MatchResult
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class JobEvaluationLookup(BaseModel):
    """Read-side currentness plus optional latest/current evaluation row."""

    model_config = StrictModelConfig

    job_id: str = Field(min_length=1)
    currentness: EvaluationCurrentnessLiteral
    evaluation: JobEvaluationRecord | None = None


class JobEvaluationView(BaseModel):
    """Public evaluation projection for saved-JD detail (Master §7.7)."""

    model_config = StrictModelConfig

    id: UuidStr
    job_id: UuidStr
    evaluation_state: EvaluationRowStateLiteral
    evaluation_context_hash: str = Field(min_length=1)
    result: MatchResult
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class SavedJobListItem(BaseModel):
    """Compact saved-JD list row: no raw JD, evidence, embeddings, or history."""

    model_config = StrictModelConfig

    id: UuidStr
    title: str | None = None
    company: str | None = None
    processing_status: JobProcessingStatus
    jd_quality: JobJdQuality | None = None
    source_type: JobSourceTypeLiteral
    source_url: str | None = None
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime
    evaluation_state: EvaluationCurrentnessLiteral
    latest_score: float | None = None


class SavedJobDetail(BaseModel):
    """Selected saved-JD detail with validated extraction and one evaluation."""

    model_config = StrictModelConfig

    compact: SavedJobListItem
    extraction: JobPostExtraction | None = None
    raw_content: str | None = None
    latest_evaluation: JobEvaluationView | None = None


class SavedJobListPage(BaseModel):
    """Newest-first saved-JD page with opaque ``next_cursor``."""

    model_config = StrictModelConfig

    items: list[SavedJobListItem]
    next_cursor: str | None = None


class SavedJobsQuery(BaseModel):
    """``GET /api/jobs`` query: ``limit`` 1..50 and opaque ``before`` cursor."""

    model_config = StrictModelConfig

    limit: int = Field(
        default=SAVED_JOBS_DEFAULT_LIMIT,
        ge=SAVED_JOBS_LIMIT_MIN,
        le=SAVED_JOBS_LIMIT_MAX,
    )
    before: str | None = None

    @field_validator("before")
    @classmethod
    def before_cursor_validated(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.strip() == "":
            raise ValueError("before cursor must be non-empty when provided")
        decode_saved_jobs_cursor(value)
        return value


# Public mutation outcome vocabularies (Master §7.7 / Plan 10).
# Ingest maps internal ``returned`` → public ``existing``.
SaveIngestOutcomeLiteral = Literal["created", "existing", "retried"]
SaveEvaluationOutcomeLiteral = Literal["created", "reused", "unavailable"]
EvaluateOutcomeLiteral = Literal["created", "reused"]


class SaveAndEvaluateRequest(BaseModel):
    """``POST /api/jobs/save-and-evaluate`` body: durable source message only."""

    model_config = StrictModelConfig

    source_message_id: UuidStr


class SaveAndEvaluateResponse(BaseModel):
    """Combined save + evaluate result without false evaluation success."""

    model_config = StrictModelConfig

    ingest_outcome: SaveIngestOutcomeLiteral
    job: SavedJobListItem
    evaluation_outcome: SaveEvaluationOutcomeLiteral
    evaluation: JobEvaluationView | None = None
    code: str | None = None


class EvaluateJobResponse(BaseModel):
    """``POST /api/jobs/{job_id}/evaluate`` current-context create/reuse."""

    model_config = StrictModelConfig

    outcome: EvaluateOutcomeLiteral
    job: SavedJobListItem
    evaluation: JobEvaluationView


def validate_match_result_payload(payload: Any) -> MatchResult:
    """Validate a compact MatchResult for persistence."""
    return parse_match_result(payload)


def match_result_to_json(result: MatchResult) -> dict[str, Any]:
    """Serialize a validated MatchResult for ``result_json`` storage."""
    return result.model_dump(mode="json")


def record_from_row(
    *,
    id: str,
    job_id: str,
    active_attachment_id: str,
    evaluation_context_hash: str,
    job_revision: datetime,
    profile_revision: datetime,
    preferences_revision: datetime,
    cv_source_hash: str,
    matching_contract_version: str,
    result_json: Any,
    created_at: datetime,
    updated_at: datetime,
) -> JobEvaluationRecord:
    """Build a validated record from ORM/row fields."""
    return JobEvaluationRecord(
        id=id,
        job_id=job_id,
        active_attachment_id=active_attachment_id,
        evaluation_context_hash=evaluation_context_hash,
        job_revision=_as_aware_utc(job_revision),
        profile_revision=_as_aware_utc(profile_revision),
        preferences_revision=_as_aware_utc(preferences_revision),
        cv_source_hash=cv_source_hash,
        matching_contract_version=matching_contract_version,
        result=validate_match_result_payload(result_json),
        created_at=_as_aware_utc(created_at),
        updated_at=_as_aware_utc(updated_at),
    )


def evaluation_view_from_record(
    record: JobEvaluationRecord,
    *,
    evaluation_state: EvaluationRowStateLiteral,
) -> JobEvaluationView:
    """Project a durable record into the public evaluation view."""
    return JobEvaluationView(
        id=record.id,
        job_id=record.job_id,
        evaluation_state=evaluation_state,
        evaluation_context_hash=record.evaluation_context_hash,
        result=record.result,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


__all__ = [
    "EvaluateJobResponse",
    "EvaluateOutcomeLiteral",
    "EvaluationCurrentnessLiteral",
    "EvaluationRowStateLiteral",
    "JobEvaluationLookup",
    "JobEvaluationRecord",
    "JobEvaluationView",
    "JobSourceTypeLiteral",
    "SAVED_JOBS_DEFAULT_LIMIT",
    "SAVED_JOBS_LIMIT_MAX",
    "SAVED_JOBS_LIMIT_MIN",
    "SaveAndEvaluateRequest",
    "SaveAndEvaluateResponse",
    "SaveEvaluationOutcomeLiteral",
    "SaveIngestOutcomeLiteral",
    "SavedJobDetail",
    "SavedJobListItem",
    "SavedJobListPage",
    "SavedJobsQuery",
    "decode_saved_jobs_cursor",
    "encode_saved_jobs_cursor",
    "evaluation_view_from_record",
    "match_result_to_json",
    "record_from_row",
    "validate_match_result_payload",
]
