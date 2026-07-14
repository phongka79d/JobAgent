"""Job extraction and compact tool contracts (Plan 5 §7.1 / §7.6 / Master §7.4).

Validated-model boundary for ``job_posts.extraction_json``
---------------------------------------------------------
ORM rows store opaque JSON. Before every write of ``extraction_json``, services
must validate a full ``JobPostExtraction`` and only persist
``model_dump(mode="json")`` of the accepted model.

Extraction contains facts and short source evidence only. The LLM must not
assign aliases, relationships, or ``jd_quality``. Authoritative quality lives
in ``job_posts.jd_quality`` via ``app.services.jd_quality`` after validation.

Compact tool input/output models shape Agent ``save_job`` / ``query_jobs``
payloads. They never carry raw JD text or embeddings.

Status/quality Literals mirror ``app.db.models.jobs`` (asserted). Ingest
outcome is owned here for tool + ingestion callers. Compact query bounds reuse
the ORM owner; only the tool default limit is schema-local.

No ORM, provider, filesystem, graph, route, or Agent behavior lives here.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from app.db.models.jobs import (
    JOB_COMPACT_QUERY_LIMIT_MAX,
    JOB_COMPACT_QUERY_LIMIT_MIN,
    JOB_JD_QUALITIES,
    JOB_PROCESSING_STATUSES,
)
from app.schemas.common import StrictModelConfig
from app.schemas.skills import SkillRef
from pydantic import BaseModel, Field, model_validator

# Exact enum vocabularies from Master §7.4 (job extraction only).
JobSeniority = Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
JobWorkMode = Literal["remote", "hybrid", "onsite", "unknown"]

# Status / quality Literals mirror the ORM production owners (common.py pattern).
JobProcessingStatus = Literal[
    "received",
    "processing",
    "processed",
    "failed",
]
JobJdQuality = Literal["full", "partial", "unscorable"]

assert frozenset(get_args(JobProcessingStatus)) == JOB_PROCESSING_STATUSES
assert frozenset(get_args(JobJdQuality)) == JOB_JD_QUALITIES

# Single owner for ingestion/tool outcome vocabulary (created|returned|retried).
JobIngestOutcome = Literal["created", "returned", "retried"]
JOB_INGEST_OUTCOME_CREATED: JobIngestOutcome = "created"
JOB_INGEST_OUTCOME_RETURNED: JobIngestOutcome = "returned"
JOB_INGEST_OUTCOME_RETRIED: JobIngestOutcome = "retried"
JOB_INGEST_OUTCOMES: frozenset[str] = frozenset(get_args(JobIngestOutcome))

assert frozenset(
    {
        JOB_INGEST_OUTCOME_CREATED,
        JOB_INGEST_OUTCOME_RETURNED,
        JOB_INGEST_OUTCOME_RETRIED,
    }
) == JOB_INGEST_OUTCOMES

# Query limit bounds: one owner on the Job ORM model; tool default is local.
QUERY_JOBS_LIMIT_MIN: int = JOB_COMPACT_QUERY_LIMIT_MIN
QUERY_JOBS_LIMIT_MAX: int = JOB_COMPACT_QUERY_LIMIT_MAX
QUERY_JOBS_DEFAULT_LIMIT: int = 10

assert QUERY_JOBS_LIMIT_MIN == JOB_COMPACT_QUERY_LIMIT_MIN
assert QUERY_JOBS_LIMIT_MAX == JOB_COMPACT_QUERY_LIMIT_MAX
assert QUERY_JOBS_LIMIT_MIN <= QUERY_JOBS_DEFAULT_LIMIT <= QUERY_JOBS_LIMIT_MAX


class JobSkill(BaseModel):
    """One skill assertion on a job extraction (Master §7.4)."""

    model_config = StrictModelConfig

    skill: SkillRef
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]


class JobPostExtraction(BaseModel):
    """Structured JD facts stored in ``extraction_json``.

    Distinct from the SQLAlchemy ``app.db.models.jobs.JobPost`` row type, which
    owns the table and opaque JSON column. ``jd_quality`` is never a field here.
    """

    model_config = StrictModelConfig

    title: str | None
    company: str | None
    summary: str
    responsibilities: list[str]
    required_skills: list[JobSkill]
    preferred_skills: list[JobSkill]
    seniority: JobSeniority
    min_experience_years: float | None
    max_experience_years: float | None
    location: str | None
    work_mode: JobWorkMode
    extraction_confidence: float = Field(ge=0.0, le=1.0)


class SaveJobInput(BaseModel):
    """``save_job`` arguments: exactly one of non-empty ``url`` or ``text``."""

    model_config = StrictModelConfig

    url: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def exactly_one_of_url_or_text(self) -> SaveJobInput:
        has_url = isinstance(self.url, str) and self.url.strip() != ""
        has_text = isinstance(self.text, str) and self.text.strip() != ""
        if has_url == has_text:
            raise ValueError(
                "save_job requires exactly one of non-empty url or text"
            )
        return self


class QueryJobsInput(BaseModel):
    """``query_jobs`` arguments: optional filters and limit in ``1..50``.

    Omitted ``limit`` defaults to exactly ``10``.
    """

    model_config = StrictModelConfig

    job_id: str | None = None
    processing_status: JobProcessingStatus | None = None
    jd_quality: JobJdQuality | None = None
    limit: int = Field(
        default=QUERY_JOBS_DEFAULT_LIMIT,
        ge=QUERY_JOBS_LIMIT_MIN,
        le=QUERY_JOBS_LIMIT_MAX,
    )


class CompactJobToolRow(BaseModel):
    """One compact saved-job row for tool/history surfaces (no raw/embeddings)."""

    model_config = StrictModelConfig

    job_id: str
    title: str | None = None
    company: str | None = None
    source_url: str | None = None
    processing_status: JobProcessingStatus
    jd_quality: JobJdQuality | None = None
    failure_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SaveJobResultData(BaseModel):
    """Compact ``save_job`` ToolResult.data (no raw JD or embeddings)."""

    model_config = StrictModelConfig

    job_id: str
    title: str | None = None
    company: str | None = None
    source_url: str | None = None
    processing_status: JobProcessingStatus
    jd_quality: JobJdQuality | None = None
    outcome: JobIngestOutcome
    sqlite_committed: bool
    sync_ok: bool | None = None
    failure_code: str | None = None
    rebuild_instruction: str | None = None
    paste_instruction: str | None = None


class QueryJobsResultData(BaseModel):
    """Compact ``query_jobs`` ToolResult.data."""

    model_config = StrictModelConfig

    jobs: list[CompactJobToolRow]
    count: int
    limit: int


def parse_job_post_extraction(payload: Any) -> JobPostExtraction:
    """Parse and validate full ``JobPostExtraction`` before extraction_json write."""
    return JobPostExtraction.model_validate(payload)
