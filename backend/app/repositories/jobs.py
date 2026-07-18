"""Focused job_posts repository: create, transition, hash/ID reads, compact lists.

Flush-only/read primitives over the existing schema. Callers own the session and
commit. No HTTP, providers, Neo4j, graph, or presentation logic. Full extraction
validation and embedding finiteness stay service-owned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from sqlalchemy import null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.time import utc_now
from app.db.models.jobs import (
    JOB_COMPACT_QUERY_LIMIT_MAX,
    JOB_COMPACT_QUERY_LIMIT_MIN,
    JOB_JD_QUALITIES,
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_PROCESSING_STATUS_PROCESSING,
    JOB_PROCESSING_STATUS_RECEIVED,
    JOB_PROCESSING_STATUSES,
    JOB_SOURCE_TYPE_TEXT,
    JOB_SOURCE_TYPE_URL,
    JobPost,
)

# received → processing|failed; processing → processed|failed;
# failed → processing (retry); processed terminal.
_ALLOWED: dict[str, frozenset[str]] = {
    JOB_PROCESSING_STATUS_RECEIVED: frozenset(
        {JOB_PROCESSING_STATUS_PROCESSING, JOB_PROCESSING_STATUS_FAILED}
    ),
    JOB_PROCESSING_STATUS_PROCESSING: frozenset(
        {JOB_PROCESSING_STATUS_PROCESSED, JOB_PROCESSING_STATUS_FAILED}
    ),
    JOB_PROCESSING_STATUS_FAILED: frozenset({JOB_PROCESSING_STATUS_PROCESSING}),
    JOB_PROCESSING_STATUS_PROCESSED: frozenset(),
}
_SCORABLE = frozenset({JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL})


class JobRepositoryError(Exception):
    """Base error for job repository invariant violations."""


class JobNotFoundError(JobRepositoryError):
    """Raised when the requested job primary key does not exist."""


class InvalidJobTransitionError(JobRepositoryError):
    """Raised when a status transition is skipped, backward, or terminal."""


class JobCompact(TypedDict):
    """Compact projection: no raw content, hashes, extraction body, or embeddings."""

    id: str
    source_type: str
    source_url: str | None
    processing_status: str
    jd_quality: str | None
    failure_code: str | None
    title: str | None
    company: str | None
    created_at: datetime
    updated_at: datetime


def _sql_null_json() -> Any:
    return null()


def _require_non_empty(name: str, value: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise JobRepositoryError(f"{name} must be a non-empty string")
    return value


async def _require_job(session: AsyncSession, job_id: str) -> JobPost:
    row = await session.get(JobPost, job_id)
    if row is None:
        raise JobNotFoundError(f"job {job_id!r} not found")
    return row


def _assert_transition(row: JobPost, to_status: str) -> None:
    allowed = _ALLOWED.get(row.processing_status, frozenset())
    if to_status not in allowed:
        raise InvalidJobTransitionError(
            f"transition {row.processing_status!r} → {to_status!r} is not allowed"
        )


async def get_by_id(session: AsyncSession, job_id: str) -> JobPost | None:
    """Return the job with primary key *job_id*, or ``None`` if missing."""
    return await session.get(JobPost, job_id)


async def get_by_raw_content_hash(
    session: AsyncSession,
    raw_content_hash: str,
) -> JobPost | None:
    """Return the row with exact *raw_content_hash*, or ``None`` if missing."""
    result = await session.execute(
        select(JobPost).where(JobPost.raw_content_hash == raw_content_hash)
    )
    return result.scalar_one_or_none()


async def create_url_placeholder(
    session: AsyncSession,
    *,
    source_url: str,
) -> JobPost:
    """Insert one ``received`` URL placeholder with null raw content/hash."""
    source_url = _require_non_empty("source_url", source_url)
    now = utc_now()
    row = JobPost(
        source_type=JOB_SOURCE_TYPE_URL,
        source_url=source_url,
        raw_content=None,
        raw_content_hash=None,
        processing_status=JOB_PROCESSING_STATUS_RECEIVED,
        failure_code=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def create_text_job(
    session: AsyncSession,
    *,
    raw_content: str,
    raw_content_hash: str,
) -> JobPost:
    """Insert one ``received`` text job with raw content and exact hash."""
    raw_content = _require_non_empty("raw_content", raw_content)
    raw_content_hash = _require_non_empty("raw_content_hash", raw_content_hash)
    now = utc_now()
    row = JobPost(
        source_type=JOB_SOURCE_TYPE_TEXT,
        source_url=None,
        raw_content=raw_content,
        raw_content_hash=raw_content_hash,
        processing_status=JOB_PROCESSING_STATUS_RECEIVED,
        failure_code=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def set_url_raw_content(
    session: AsyncSession,
    job_id: str,
    *,
    raw_content: str,
    raw_content_hash: str,
) -> JobPost:
    """Attach fetched content to a URL placeholder still without raw fields."""
    raw_content = _require_non_empty("raw_content", raw_content)
    raw_content_hash = _require_non_empty("raw_content_hash", raw_content_hash)
    row = await _require_job(session, job_id)
    if row.source_type != JOB_SOURCE_TYPE_URL:
        raise JobRepositoryError("set_url_raw_content requires source_type='url'")
    if row.raw_content is not None or row.raw_content_hash is not None:
        raise JobRepositoryError(
            "set_url_raw_content requires null raw_content and raw_content_hash"
        )
    if row.processing_status != JOB_PROCESSING_STATUS_RECEIVED:
        raise JobRepositoryError(
            "set_url_raw_content requires processing_status='received'"
        )
    row.raw_content = raw_content
    row.raw_content_hash = raw_content_hash
    row.updated_at = utc_now()
    await session.flush()
    return row


async def mark_processing(session: AsyncSession, job_id: str) -> JobPost:
    """Transition ``received → processing`` (failed retries use retry helper)."""
    row = await _require_job(session, job_id)
    if row.processing_status != JOB_PROCESSING_STATUS_RECEIVED:
        raise InvalidJobTransitionError(
            f"transition {row.processing_status!r} → "
            f"{JOB_PROCESSING_STATUS_PROCESSING!r} is not allowed "
            f"(use retry_failed_as_processing for failed rows)"
        )
    row.processing_status = JOB_PROCESSING_STATUS_PROCESSING
    row.updated_at = utc_now()
    await session.flush()
    return row


async def retry_failed_as_processing(
    session: AsyncSession,
    job_id: str,
) -> JobPost:
    """Transition ``failed → processing`` and clear all terminal result fields."""
    row = await _require_job(session, job_id)
    if row.processing_status != JOB_PROCESSING_STATUS_FAILED:
        raise InvalidJobTransitionError(
            f"transition {row.processing_status!r} → "
            f"{JOB_PROCESSING_STATUS_PROCESSING!r} is not allowed "
            f"via retry_failed_as_processing"
        )
    row.failure_code = None
    row.extraction_json = _sql_null_json()
    row.jd_quality = None
    row.embedding_json = _sql_null_json()
    row.embedding_model = None
    row.embedding_dimensions = None
    row.processing_status = JOB_PROCESSING_STATUS_PROCESSING
    row.updated_at = utc_now()
    await session.flush()
    set_committed_value(row, "extraction_json", None)
    set_committed_value(row, "embedding_json", None)
    return row


async def mark_failed(
    session: AsyncSession,
    job_id: str,
    *,
    failure_code: str,
) -> JobPost:
    """Transition ``received|processing → failed`` with non-empty *failure_code*."""
    failure_code = _require_non_empty("failure_code", failure_code)
    row = await _require_job(session, job_id)
    _assert_transition(row, JOB_PROCESSING_STATUS_FAILED)
    row.processing_status = JOB_PROCESSING_STATUS_FAILED
    row.failure_code = failure_code
    row.updated_at = utc_now()
    await session.flush()
    return row


async def mark_processed(
    session: AsyncSession,
    job_id: str,
    *,
    extraction_json: dict[str, Any],
    jd_quality: str,
    embedding_json: list[Any] | None = None,
    embedding_model: str | None = None,
    embedding_dimensions: int | None = None,
) -> JobPost:
    """Transition ``processing → processed`` with extraction/quality/embeddings."""
    if not isinstance(extraction_json, dict):
        raise JobRepositoryError("extraction_json must be a mapping")
    if jd_quality not in JOB_JD_QUALITIES:
        raise JobRepositoryError(
            f"jd_quality must be one of {sorted(JOB_JD_QUALITIES)}, "
            f"got {jd_quality!r}"
        )
    row = await _require_job(session, job_id)
    _assert_transition(row, JOB_PROCESSING_STATUS_PROCESSED)
    row.processing_status = JOB_PROCESSING_STATUS_PROCESSED
    row.failure_code = None
    row.extraction_json = extraction_json
    row.jd_quality = jd_quality
    if jd_quality in _SCORABLE:
        row.embedding_json = (
            _sql_null_json() if embedding_json is None else embedding_json
        )
        row.embedding_model = embedding_model
        row.embedding_dimensions = embedding_dimensions
    else:
        row.embedding_json = _sql_null_json()
        row.embedding_model = None
        row.embedding_dimensions = None
    row.updated_at = utc_now()
    await session.flush()
    if embedding_json is None or jd_quality not in _SCORABLE:
        set_committed_value(row, "embedding_json", None)
    return row


async def delete_url_placeholder(session: AsyncSession, job_id: str) -> None:
    """Delete a temporary pure URL placeholder only.

    Requires all four: ``source_type='url'``, ``processing_status='received'``,
    ``raw_content is None``, and ``raw_content_hash is None``. Any other Job
    row raises ``JobRepositoryError`` and is left unchanged. Missing IDs raise
    ``JobNotFoundError``.
    """
    row = await _require_job(session, job_id)
    if row.source_type != JOB_SOURCE_TYPE_URL:
        raise JobRepositoryError(
            "delete_url_placeholder requires source_type='url'"
        )
    if row.processing_status != JOB_PROCESSING_STATUS_RECEIVED:
        raise JobRepositoryError(
            "delete_url_placeholder requires processing_status='received'"
        )
    if row.raw_content is not None or row.raw_content_hash is not None:
        raise JobRepositoryError(
            "delete_url_placeholder requires null raw_content and raw_content_hash"
        )
    await session.delete(row)
    await session.flush()


async def delete_by_id(session: AsyncSession, job_id: str) -> None:
    """Delete any ``job_posts`` row by primary key (flush only).

    ``job_evaluations`` rows cascade via FK. Missing IDs raise
    ``JobNotFoundError``. Callers own the commit; graph ordering lives in the
    deletion coordinator, not here.
    """
    row = await _require_job(session, job_id)
    await session.delete(row)
    await session.flush()


async def list_compact(
    session: AsyncSession,
    *,
    limit: int,
    job_id: str | None = None,
    processing_status: str | None = None,
    jd_quality: str | None = None,
) -> list[JobCompact]:
    """Newest-first compact rows; *limit* required in ``1..50`` (no default)."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise JobRepositoryError("limit must be an int in 1..50")
    if limit < JOB_COMPACT_QUERY_LIMIT_MIN or limit > JOB_COMPACT_QUERY_LIMIT_MAX:
        raise JobRepositoryError(
            f"limit must be in {JOB_COMPACT_QUERY_LIMIT_MIN}.."
            f"{JOB_COMPACT_QUERY_LIMIT_MAX}, got {limit!r}"
        )
    if (
        processing_status is not None
        and processing_status not in JOB_PROCESSING_STATUSES
    ):
        raise JobRepositoryError(
            f"processing_status must be one of "
            f"{sorted(JOB_PROCESSING_STATUSES)}, got {processing_status!r}"
        )
    if jd_quality is not None and jd_quality not in JOB_JD_QUALITIES:
        raise JobRepositoryError(
            f"jd_quality must be one of {sorted(JOB_JD_QUALITIES)}, "
            f"got {jd_quality!r}"
        )

    conditions = []
    if job_id is not None:
        conditions.append(JobPost.id == job_id)
    if processing_status is not None:
        conditions.append(JobPost.processing_status == processing_status)
    if jd_quality is not None:
        conditions.append(JobPost.jd_quality == jd_quality)

    stmt = select(JobPost)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(JobPost.created_at.desc(), JobPost.id.desc()).limit(limit)
    result = await session.execute(stmt)
    return [_to_compact(row) for row in result.scalars().all()]


def _to_compact(row: JobPost) -> JobCompact:
    title: str | None = None
    company: str | None = None
    extraction = row.extraction_json
    if isinstance(extraction, dict):
        raw_title = extraction.get("title")
        raw_company = extraction.get("company")
        if isinstance(raw_title, str):
            title = raw_title
        if isinstance(raw_company, str):
            company = raw_company
    return JobCompact(
        id=row.id,
        source_type=row.source_type,
        source_url=row.source_url,
        processing_status=row.processing_status,
        jd_quality=row.jd_quality,
        failure_code=row.failure_code,
        title=title,
        company=company,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
