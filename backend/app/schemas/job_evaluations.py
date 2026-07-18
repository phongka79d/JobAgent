"""Validated job evaluation persistence and read projections.

Owns Pydantic boundaries for persisted ``result_json`` (compact MatchResult)
and derived none|current|stale state. Never accepts client-supplied revision
fields or context hashes as authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from app.schemas.matching import MatchResult, parse_match_result
from pydantic import BaseModel, Field

EvaluationCurrentnessLiteral = Literal["none", "current", "stale"]


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


__all__ = [
    "EvaluationCurrentnessLiteral",
    "JobEvaluationLookup",
    "JobEvaluationRecord",
    "match_result_to_json",
    "record_from_row",
    "validate_match_result_payload",
]
