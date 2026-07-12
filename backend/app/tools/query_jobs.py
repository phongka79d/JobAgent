"""Bounded read-only ``query_jobs`` Agent tool (Plan 5 §7.7 / Master §13.6).

Supports one Job ID or bounded status filters. Defaults to 10 results and caps
at 50. Returns compact validated repository views and existing ``score_cache``
details when present. Never returns raw JD content, content hashes, error
internals, embedding vectors, provider payloads, or an unbounded corpus.
Never computes or refreshes scores.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.db.enums import ProcessingStatus, RecordStatus
from app.db.session import DatabaseSessionManager
from app.repositories.job_posts import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    JobPostRecord,
    JobPostRepository,
    JobPostRepositoryError,
    JobPostValidationError,
)
from app.schemas.job_tools import JobDisplaySummary
from app.schemas.matching import MATCH_RESULT_CONTRACT_VERSION, MatchResult


class QueryJobsInput(BaseModel):
    """Strict LLM-visible args for ID mode or bounded filter mode."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    job_id: UUID | None = None
    processing_status: str | None = Field(default=None, max_length=64)
    jd_quality: str | None = Field(default=None, max_length=64)
    record_status: str | None = Field(default=None, max_length=64)
    graph_sync_status: str | None = Field(default=None, max_length=64)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIST_LIMIT)

    @model_validator(mode="after")
    def _id_xor_filters_consistent(self) -> QueryJobsInput:
        # ID mode: job_id alone (filters/limit ignored when id present is ok
        # only if no conflicting dual-mode intent — reject when both id and
        # any filter are supplied).
        has_id = self.job_id is not None
        filter_set = any(
            v is not None
            for v in (
                self.processing_status,
                self.jd_quality,
                self.record_status,
                self.graph_sync_status,
            )
        )
        if has_id and filter_set:
            raise ValueError("provide job_id or filters, not both")
        if self.limit is not None and (
            not isinstance(self.limit, int) or isinstance(self.limit, bool)
        ):
            raise ValueError("invalid limit")
        return self


def _error(code: str) -> str:
    return f'ERROR:{{"code":"{code}","ok":false}}'


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _validated_score_details(record: JobPostRecord) -> dict[str, Any] | None:
    """Expose only validated versioned score details for eligible Jobs.

    Never computes scores. Omits cache for ignored/unscorable rows and for
    payloads that fail MatchResult re-validation or version checks.
    """
    if record.score_cache is None:
        return None
    if record.record_status != RecordStatus.ACTIVE.value:
        return None
    if record.processing_status != ProcessingStatus.PROCESSED.value:
        return None
    if record.jd_quality not in {"full", "partial"}:
        return None
    try:
        parsed = MatchResult.model_validate(record.score_cache)
    except (ValidationError, ValueError, TypeError):
        return None
    if parsed.contract_version != MATCH_RESULT_CONTRACT_VERSION:
        return None
    if parsed.job_id != record.id:
        return None
    return parsed.model_dump(mode="json")


def _compact_job(record: JobPostRecord) -> dict[str, Any]:
    """Map a repository compact view to a tool-safe payload.

    Excludes raw content, hashes, error fields, embedding identity, and
    provider/internal material. Includes ``score_cache`` only when already
    present, validated, and eligible (never computed here).
    """
    extraction = record.extraction
    display = JobDisplaySummary(
        title=extraction.title if extraction is not None else None,
        company=extraction.company if extraction is not None else None,
        location=extraction.location if extraction is not None else None,
        work_mode=(
            extraction.work_mode.value
            if extraction is not None and extraction.work_mode is not None
            else None
        ),
        employment_type=(
            extraction.employment_type.value
            if extraction is not None and extraction.employment_type is not None
            else None
        ),
        source_url=record.source_url,
    )
    payload: dict[str, Any] = {
        "job_id": str(record.id),
        "source_type": record.source_type,
        "source_url": record.source_url,
        "processing_status": record.processing_status,
        "jd_quality": record.jd_quality,
        "quality_reasons": record.quality_reasons,
        "record_status": record.record_status,
        "graph_sync_status": record.graph_sync_status,
        "duplicate_of_job_id": (
            str(record.duplicate_of_job_id)
            if record.duplicate_of_job_id is not None
            else None
        ),
        "display": display.model_dump(mode="json"),
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }
    # Score details only when already stored and validated — never compute here.
    score = _validated_score_details(record)
    if score is not None:
        payload["score_cache"] = score
    return payload


class QueryJobsToolService:
    """Read-only compact Job queries through one database boundary."""

    def __init__(self, database: DatabaseSessionManager) -> None:
        self._database = database

    async def execute(
        self,
        *,
        job_id: UUID | None = None,
        processing_status: str | None = None,
        jd_quality: str | None = None,
        record_status: str | None = None,
        graph_sync_status: str | None = None,
        limit: int | None = None,
    ) -> str:
        try:
            async with self._database.session_scope() as session:
                jobs = JobPostRepository(session)
                if job_id is not None:
                    record = await jobs.get_by_id(job_id)
                    if record is None:
                        return _error("JOB_NOT_FOUND")
                    items = [_compact_job(record)]
                else:
                    records = await jobs.list_filtered(
                        processing_status=processing_status,
                        jd_quality=jd_quality,
                        record_status=record_status,
                        graph_sync_status=graph_sync_status,
                        limit=limit,
                    )
                    items = [_compact_job(r) for r in records]
        except JobPostValidationError:
            return _error("QUERY_JOBS_INVALID_INPUT")
        except JobPostRepositoryError:
            return _error("QUERY_JOBS_FAILED")
        except Exception:
            return _error("QUERY_JOBS_FAILED")

        effective_limit = DEFAULT_LIST_LIMIT if limit is None else limit
        if job_id is not None:
            effective_limit = 1
        payload = {
            "ok": True,
            "count": len(items),
            "limit": effective_limit,
            "jobs": items,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def create_query_jobs_tool(service: QueryJobsToolService) -> StructuredTool:
    """Create the strict read-only LangChain tool wrapper."""

    async def _query(
        job_id: UUID | None = None,
        processing_status: str | None = None,
        jd_quality: str | None = None,
        record_status: str | None = None,
        graph_sync_status: str | None = None,
        limit: int | None = None,
    ) -> str:
        try:
            parsed = QueryJobsInput(
                job_id=job_id,
                processing_status=processing_status,
                jd_quality=jd_quality,
                record_status=record_status,
                graph_sync_status=graph_sync_status,
                limit=limit,
            )
        except ValidationError:
            return _error("QUERY_JOBS_INVALID_INPUT")
        return await service.execute(
            job_id=parsed.job_id,
            processing_status=parsed.processing_status,
            jd_quality=parsed.jd_quality,
            record_status=parsed.record_status,
            graph_sync_status=parsed.graph_sync_status,
            limit=parsed.limit,
        )

    return StructuredTool.from_function(
        coroutine=_query,
        name="query_jobs",
        description=(
            "Read one saved job by ID or list jobs with bounded filters "
            f"(default {DEFAULT_LIST_LIMIT}, max {MAX_LIST_LIMIT}). "
            "Returns compact fields and existing score details only."
        ),
        args_schema=QueryJobsInput,
    )


__all__ = [
    "QueryJobsInput",
    "QueryJobsToolService",
    "create_query_jobs_tool",
]
