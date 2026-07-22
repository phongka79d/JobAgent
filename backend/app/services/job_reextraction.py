"""Staged same-ID Job re-extraction coordinator (Plan 15).

Loads an immutable retained-JD snapshot, runs guarded extraction / quality /
embedding outside any SQLite transaction, then performs one revision-checked
replacement. After commit, projects the same Job ID via existing ``sync_job``.

Never evaluates or scores. Pre-commit failures leave the durable Job and
evaluation rows unchanged. Graph failure after SQLite commit retains SQLite
truth and returns partial-success sync fields.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    EmbeddingAdapterError,
    ShopAIKeyEmbeddingAdapter,
)
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JobPost,
)
from app.db.session import session_scope
from app.graph.sync_job import AsyncGraphDriver
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import JobNotFoundError, JobReextractConflictError
from app.schemas.embeddings import EmbeddingVectorError
from app.schemas.jobs import JobPostExtraction
from app.services.jd_extraction import (
    JdExtractionError,
    StructuredJdInvoker,
    extract_job_post_from_text,
)
from app.services.jd_quality import classify_jd_quality
from app.services.job_projection import (
    EmbeddingClient,
    JobSyncFn,
    embed_job_extraction,
    sync_persisted_job,
)
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

ERROR_JOB_NOT_FOUND: Final[str] = "JOB_NOT_FOUND"
ERROR_JD_SOURCE_NOT_RECOVERABLE: Final[str] = "JD_SOURCE_NOT_RECOVERABLE"
ERROR_JOB_NOT_SCORABLE: Final[str] = "JOB_NOT_SCORABLE"
ERROR_JOB_REEXTRACT_CONFLICT: Final[str] = "JOB_REEXTRACT_CONFLICT"

JOB_NOT_FOUND_MESSAGE: Final[str] = "The requested Job was not found."
JD_SOURCE_NOT_RECOVERABLE_MESSAGE: Final[str] = (
    "Retained Job source text is missing or blank; re-extraction cannot proceed."
)
JOB_NOT_SCORABLE_MESSAGE: Final[str] = (
    "Re-extraction produced an unscorable result; the prior Job was preserved."
)
JOB_REEXTRACT_CONFLICT_MESSAGE: Final[str] = (
    "The Job was modified concurrently; re-extraction did not overwrite it."
)

_SCORABLE_QUALITIES: Final[frozenset[str]] = frozenset(
    {JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL}
)

class JobReextractError(Exception):
    """Stable-coded re-extraction failure for service/API mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class _JobWorkingSnapshot:
    """Immutable retained-Job facts captured before external work."""

    job_id: str
    source_type: str
    source_url: str | None
    raw_content: str
    raw_content_hash: str | None
    created_at: datetime
    updated_at: datetime
    processing_status: str
    jd_quality: str | None
    failure_code: str | None
    extraction_json: dict[str, Any] | None
    embedding_json: list[Any] | None
    embedding_model: str | None
    embedding_dimensions: int | None


@dataclass(frozen=True, slots=True)
class JobReextractResult:
    """Successful same-ID replacement outcome (SQLite committed).

    ``sync_ok`` is False only when post-commit graph projection failed; SQLite
    extraction replacement remains durable. Pre-commit failures raise
    :class:`JobReextractError` instead of returning this type.
    """

    job_id: str
    processing_status: str
    jd_quality: str | None
    failure_code: str | None
    source_type: str
    source_url: str | None
    raw_content_hash: str | None
    updated_at: datetime
    sync_ok: bool
    sync_code: str | None
    rebuild_instruction: str | None


def _snapshot_from_row(row: JobPost) -> _JobWorkingSnapshot:
    raw = row.raw_content
    if not isinstance(raw, str) or raw.strip() == "":
        raise JobReextractError(
            ERROR_JD_SOURCE_NOT_RECOVERABLE,
            JD_SOURCE_NOT_RECOVERABLE_MESSAGE,
        )
    extraction = row.extraction_json
    extraction_copy: dict[str, Any] | None
    if isinstance(extraction, dict):
        extraction_copy = deepcopy(extraction)
    else:
        extraction_copy = None
    embedding = row.embedding_json
    embedding_copy: list[Any] | None
    if isinstance(embedding, list):
        embedding_copy = list(embedding)
    else:
        embedding_copy = None
    return _JobWorkingSnapshot(
        job_id=row.id,
        source_type=row.source_type,
        source_url=row.source_url,
        raw_content=raw,
        raw_content_hash=row.raw_content_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
        processing_status=row.processing_status,
        jd_quality=row.jd_quality,
        failure_code=row.failure_code,
        extraction_json=extraction_copy,
        embedding_json=embedding_copy,
        embedding_model=row.embedding_model,
        embedding_dimensions=row.embedding_dimensions,
    )


async def _load_snapshot(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> _JobWorkingSnapshot:
    async with session_scope(session_factory) as session:
        row = await jobs_repo.get_by_id(session, job_id)
        if row is None:
            raise JobReextractError(
                ERROR_JOB_NOT_FOUND,
                JOB_NOT_FOUND_MESSAGE,
            )
        # Touch all fields used in the immutable snapshot while session is open.
        _ = (
            row.id,
            row.source_type,
            row.source_url,
            row.raw_content,
            row.raw_content_hash,
            row.created_at,
            row.updated_at,
            row.processing_status,
            row.jd_quality,
            row.failure_code,
            row.extraction_json,
            row.embedding_json,
            row.embedding_model,
            row.embedding_dimensions,
        )
        return _snapshot_from_row(row)


async def _commit_replacement(
    snapshot: _JobWorkingSnapshot,
    *,
    extraction: JobPostExtraction,
    jd_quality: str,
    embedding_json: list[float],
    embedding_model: str,
    embedding_dimensions: int,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    async with session_scope(session_factory) as session:
        try:
            return await jobs_repo.replace_extraction_if_unchanged(
                session,
                snapshot.job_id,
                expected_updated_at=snapshot.updated_at,
                extraction_json=extraction.model_dump(mode="json"),
                jd_quality=jd_quality,
                embedding_json=embedding_json,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
            )
        except JobReextractConflictError as exc:
            raise JobReextractError(
                ERROR_JOB_REEXTRACT_CONFLICT,
                JOB_REEXTRACT_CONFLICT_MESSAGE,
            ) from exc
        except JobNotFoundError as exc:
            raise JobReextractError(
                ERROR_JOB_NOT_FOUND,
                JOB_NOT_FOUND_MESSAGE,
            ) from exc


async def _load_committed(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    async with session_scope(session_factory) as session:
        row = await jobs_repo.get_by_id(session, job_id)
        if row is None:  # pragma: no cover - post-commit invariant
            raise JobReextractError(
                ERROR_JOB_NOT_FOUND,
                JOB_NOT_FOUND_MESSAGE,
            )
        _ = (
            row.id,
            row.processing_status,
            row.jd_quality,
            row.failure_code,
            row.source_type,
            row.source_url,
            row.raw_content,
            row.raw_content_hash,
            row.created_at,
            row.updated_at,
            row.extraction_json,
            row.embedding_json,
            row.embedding_model,
            row.embedding_dimensions,
        )
        return row


async def _sync_committed(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> tuple[bool, str | None, str | None]:
    """Run same-ID graph sync after SQLite commit. Never mutates SQLite."""
    projection = await sync_persisted_job(
        row,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
        log_context="job reextraction",
    )
    return projection.ok, projection.code, projection.rebuild_instruction


async def reextract_job(
    job_id: str,
    *,
    invoker: StructuredJdInvoker,
    normalizer: SkillNormalizer,
    embedding_client: EmbeddingClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    graph_driver: AsyncGraphDriver | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> JobReextractResult:
    """Re-extract one retained Job under a revision-checked replacement.

    Flow:
    1. Short read: load Job, copy immutable snapshot, capture ``updated_at``.
       Reject unknown ID or blank/missing retained raw content before providers.
    2. Outside transactions: guarded extractor, quality classification, and
       locked embedding only when quality is ``full|partial``.
    3. Reject ``unscorable`` without mutation (``JOB_NOT_SCORABLE``).
    4. Short CAS transaction: replace only approved mutable fields when
       ``id`` + captured ``updated_at`` still match.
    5. After commit: same-ID ``sync_job``. Graph failure returns partial success.

    Makes zero evaluation/scoring calls. Does not change ordinary ingestion.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobReextractError(ERROR_JOB_NOT_FOUND, JOB_NOT_FOUND_MESSAGE)
    jid = job_id.strip()

    snapshot = await _load_snapshot(jid, session_factory=session_factory)
    embedder: EmbeddingClient = (
        embedding_client
        if embedding_client is not None
        else ShopAIKeyEmbeddingAdapter()
    )

    # --- All provider/embedding work outside any SQLite transaction ---
    try:
        extract_outcome = extract_job_post_from_text(
            snapshot.raw_content,
            invoker=invoker,
            normalizer=normalizer,
        )
    except JdExtractionError as exc:
        logger.info(
            "job reextraction extraction failed job_id=%s code=%s",
            snapshot.job_id,
            exc.code,
        )
        raise JobReextractError(exc.code, exc.message) from exc

    extraction = extract_outcome.extraction
    jd_quality = classify_jd_quality(extraction)
    if jd_quality not in _SCORABLE_QUALITIES:
        raise JobReextractError(
            ERROR_JOB_NOT_SCORABLE,
            JOB_NOT_SCORABLE_MESSAGE,
        )

    try:
        embedding_json, embedding_model, embedding_dimensions = embed_job_extraction(
            extraction, embedder
        )
    except EmbeddingAdapterError as exc:
        logger.info(
            "job reextraction embedding failed job_id=%s code=%s",
            snapshot.job_id,
            exc.code,
        )
        raise JobReextractError(exc.code, exc.message) from exc
    except EmbeddingVectorError:
        logger.info(
            "job reextraction embedding invalid job_id=%s code=%s",
            snapshot.job_id,
            FAILURE_EMBEDDING_INVALID_RESPONSE,
        )
        raise JobReextractError(
            FAILURE_EMBEDDING_INVALID_RESPONSE,
            "Embedding response failed locked-vector validation",
        ) from None

    # --- One short revision-checked replacement transaction ---
    await _commit_replacement(
        snapshot,
        extraction=extraction,
        jd_quality=jd_quality,
        embedding_json=embedding_json,
        embedding_model=embedding_model,
        embedding_dimensions=embedding_dimensions,
        session_factory=session_factory,
    )

    # Reload durable truth after commit (session_scope already committed).
    committed = await _load_committed(
        snapshot.job_id, session_factory=session_factory
    )
    sync_ok, sync_code, rebuild = await _sync_committed(
        committed,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
    )
    return JobReextractResult(
        job_id=committed.id,
        processing_status=committed.processing_status,
        jd_quality=committed.jd_quality,
        failure_code=committed.failure_code,
        source_type=committed.source_type,
        source_url=committed.source_url,
        raw_content_hash=committed.raw_content_hash,
        updated_at=committed.updated_at,
        sync_ok=sync_ok,
        sync_code=sync_code,
        rebuild_instruction=rebuild,
    )


__all__ = [
    "ERROR_JD_SOURCE_NOT_RECOVERABLE",
    "ERROR_JOB_NOT_FOUND",
    "ERROR_JOB_NOT_SCORABLE",
    "ERROR_JOB_REEXTRACT_CONFLICT",
    "JD_SOURCE_NOT_RECOVERABLE_MESSAGE",
    "JOB_NOT_FOUND_MESSAGE",
    "JOB_NOT_SCORABLE_MESSAGE",
    "JOB_REEXTRACT_CONFLICT_MESSAGE",
    "JobReextractError",
    "JobReextractResult",
    "reextract_job",
]
