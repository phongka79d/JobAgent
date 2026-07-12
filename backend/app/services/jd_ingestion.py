"""Persistence-first JD ingestion orchestration (Plan 5 §7.3 / §7.4 / §7.6).

One service boundary handles exactly one URL or raw-text input:

1. Acquire / canonicalize / hash (via ``jd_source``; no tool/HTTP logic here).
2. Exact-hash hit → return existing ID with zero new work.
3. Commit novel ``received`` raw content **before** any LLM call.
4. Mark ``processing``; extract, normalize skills, re-classify quality.
5. Atomically mark ``processed`` and either ignored/not-required or active
   pending plus identifier-only ``upsert_job`` enqueue in the same transaction.
6. On extraction/provider failure, retain the raw row as ``failed`` with a
   stable sanitized code. Post-commit graph unavailability is out of scope
   here (outbox remains retryable); canonical Job state is never rolled back
   for Neo4j failure because vectors are not generated in this service.

``force_new_authorized`` is an application-derived Boolean only. It never
overrides an exact hash and must not originate from JD/tool argument parsing
inside this service.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import (
    GraphSyncStatus,
    JdQuality,
    JobSourceType,
    ProcessingStatus,
    RecordStatus,
)
from app.db.models.jobs import JobPost
from app.db.session import DatabaseSessionManager
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import (
    JobPostRecord,
    JobPostRepository,
    build_normalized_job_key,
)
from app.schemas.job_post import JobPostExtraction
from app.schemas.job_tools import (
    DuplicateOutcome,
    JobDisplaySummary,
    ProcessingResult,
    SaveJobResult,
)
from app.services.jd_extraction import (
    JdExtractionError,
    JobExtractionResult,
    extract_job_post,
)
from app.services.jd_quality import apply_jd_quality
from app.services.jd_source import (
    AcquiredJd,
    JdSourceError,
    JdSourceType,
    acquire_jd,
)
from app.services.shopaikey_chat import (
    ShopAIKeyChatAdapter,
    ShopAIKeyChatError,
    ShopAIKeyErrorCode,
)
from app.services.skill_normalization import (
    SkillSeedCatalog,
    normalize_job_skill_lists,
)
from app.services.url_fetcher import UrlFetcher, UrlFetchError

# Identifier-only Job graph operation (matches generic outbox / Plan 5).
JOB_UPSERT_OPERATION: Final[str] = "upsert_job"

# Scorable qualities eligible for embedding identity + graph sync.
_SCORABLE_QUALITIES: Final[frozenset[str]] = frozenset(
    {
        JdQuality.FULL.value,
        JdQuality.PARTIAL.value,
    }
)

AcquireJdFn = Callable[..., AcquiredJd]
ExtractJobFn = Callable[..., JobExtractionResult]


class JdIngestionError(Exception):
    """Sanitized ingestion failure before a durable Job row exists.

    After a row is retained as ``failed``, the service returns a
    ``SaveJobResult`` instead of raising. Acquisition / configuration
    failures that create no row raise this error with a stable code only.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"JdIngestionError(code={self.code!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


class JDIngestionService:
    """Canonical save state machine and same-transaction Job outbox creation."""

    def __init__(
        self,
        database: DatabaseSessionManager,
        *,
        chat_adapter: ShopAIKeyChatAdapter | None = None,
        url_fetcher: UrlFetcher | None = None,
        skill_catalog: SkillSeedCatalog | None = None,
        acquire_fn: AcquireJdFn | None = None,
        extract_fn: ExtractJobFn | None = None,
        embedding_model: str = ALLOWED_EMBEDDING_MODEL,
        embedding_dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
    ) -> None:
        self._database = database
        self._chat_adapter = chat_adapter
        self._url_fetcher = url_fetcher
        self._skill_catalog = skill_catalog
        self._acquire_fn = acquire_fn
        self._extract_fn = extract_fn
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions

    async def save_job(
        self,
        *,
        url: str | None = None,
        raw_text: str | None = None,
        force_new_authorized: bool = False,
    ) -> SaveJobResult:
        """Ingest one JD with persistence-first ordering and duplicate policy.

        Parameters
        ----------
        url / raw_text:
            Exactly one must be provided (enforced by acquisition).
        force_new_authorized:
            Application-owned authorization that this is a distinct position.
            Never overrides an exact content hash. Must not be derived from
            the JD payload or tool Boolean alone inside this service.
        """
        if not isinstance(force_new_authorized, bool):
            raise JdIngestionError("INVALID_FORCE_NEW")

        acquired = self._acquire(url=url, raw_text=raw_text)
        source_type = _map_source_type(acquired.source_type)

        # --- TX1: exact-hash check + novel received commit (before LLM) ---
        async with self._database.session_scope() as session:
            jobs = JobPostRepository(session)
            create_result = await jobs.create_received(
                source_type=source_type,
                raw_content=acquired.canonical_text,
                raw_content_hash=acquired.content_hash,
                source_url=acquired.source_url,
            )
            if not create_result.created:
                # Exact duplicate: zero extraction / embedding / outbox work.
                return _result_from_record(
                    create_result.record,
                    processing_result=ProcessingResult.EXACT_DUPLICATE,
                    duplicate_outcome=DuplicateOutcome.EXACT,
                    error_code=None,
                )
            job_id = create_result.record.id

        # Prove novel content is durable before any provider call.
        await self._assert_raw_retained(job_id, acquired.content_hash)

        # --- TX2: mark processing (committed before extract) ---
        async with self._database.session_scope() as session:
            jobs = JobPostRepository(session)
            await jobs.mark_processing(job_id)

        # --- Extract / normalize / classify (no open write transaction) ---
        try:
            extraction, quality_reasons = await self._extract_and_normalize(
                acquired.canonical_text
            )
        except (JdExtractionError, ShopAIKeyChatError) as exc:
            code = _stable_failure_code(exc)
            return await self._retain_failed(job_id, error_code=code)
        except JdIngestionError as exc:
            return await self._retain_failed(job_id, error_code=exc.code)
        except Exception:
            # Never leak exception text; retain raw with stable code.
            return await self._retain_failed(
                job_id,
                error_code="JD_PROCESSING_FAILED",
            )

        # --- TX3: processed + eligibility / outbox (atomic) ---
        async with self._database.session_scope() as session:
            jobs = JobPostRepository(session)
            record = await jobs.mark_processed(
                job_id,
                extraction=extraction,
                quality_reasons=quality_reasons,
                force_new=force_new_authorized,
            )

            duplicate_outcome = await _duplicate_outcome_for_processed(
                session,
                record,
                force_new_authorized=force_new_authorized,
            )

            if _is_graph_eligible(record):
                await jobs.set_embedding_identity(
                    job_id,
                    embedding_model=self._embedding_model,
                    embedding_dimensions=self._embedding_dimensions,
                )
                record = await jobs.set_graph_sync_status(
                    job_id,
                    status=GraphSyncStatus.PENDING,
                )
                await GraphOutboxRepository(session).enqueue(
                    operation=JOB_UPSERT_OPERATION,
                    entity_id=str(job_id),
                    payload={"job_id": str(job_id)},
                    requeue_existing=True,
                )
            elif record.graph_sync_status != GraphSyncStatus.NOT_REQUIRED.value:
                # Ensure ignored/unscorable never leave a pending sync.
                record = await jobs.set_graph_sync_status(
                    job_id,
                    status=GraphSyncStatus.NOT_REQUIRED,
                )

            return _result_from_record(
                record,
                processing_result=ProcessingResult.PROCESSED,
                duplicate_outcome=duplicate_outcome,
                error_code=None,
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _acquire(
        self,
        *,
        url: str | None,
        raw_text: str | None,
    ) -> AcquiredJd:
        try:
            if self._acquire_fn is not None:
                return self._acquire_fn(url=url, raw_text=raw_text)
            return acquire_jd(
                url=url,
                raw_text=raw_text,
                fetcher=self._url_fetcher,
            )
        except JdSourceError as exc:
            raise JdIngestionError(exc.code.value) from None
        except UrlFetchError as exc:
            raise JdIngestionError(exc.code.value) from None

    async def _extract_and_normalize(
        self,
        canonical_text: str,
    ) -> tuple[JobPostExtraction, list[str] | None]:
        if self._extract_fn is not None:
            maybe = self._extract_fn(canonical_jd_text=canonical_text)
            if inspect.isawaitable(maybe):
                extraction_result = await maybe
            else:
                extraction_result = maybe
        else:
            if self._chat_adapter is None:
                raise JdIngestionError("JD_EXTRACTION_NOT_CONFIGURED")
            extraction_result = extract_job_post(
                self._chat_adapter,
                canonical_jd_text=canonical_text,
            )

        if not isinstance(extraction_result, JobExtractionResult):
            raise JdIngestionError("JD_PROCESSING_FAILED")

        extraction = extraction_result.extraction
        required, preferred = normalize_job_skill_lists(
            required_skills=extraction.required_skills,
            preferred_skills=extraction.preferred_skills,
            catalog=self._skill_catalog,
        )
        normalized = extraction.model_copy(
            update={
                "required_skills": required,
                "preferred_skills": preferred,
            }
        )
        # Re-classify after skill normalization (master order: normalize → quality).
        with_quality, assessment = apply_jd_quality(normalized)
        reasons = assessment.reason_list
        return with_quality, reasons if reasons else None

    async def _retain_failed(
        self,
        job_id: UUID,
        *,
        error_code: str,
    ) -> SaveJobResult:
        async with self._database.session_scope() as session:
            jobs = JobPostRepository(session)
            record = await jobs.mark_failed(
                job_id,
                error_code=error_code,
                error_message=None,
            )
            return _result_from_record(
                record,
                processing_result=ProcessingResult.FAILED,
                duplicate_outcome=DuplicateOutcome.NONE,
                error_code=error_code,
            )

    async def _assert_raw_retained(
        self,
        job_id: UUID,
        content_hash: str,
    ) -> None:
        """Sanity: novel row is durable with matching hash before LLM."""
        async with self._database.session_scope() as session:
            row = await session.get(JobPost, job_id)
            if row is None or row.raw_content_hash != content_hash:
                raise JdIngestionError("JD_PERSISTENCE_FAILED")
            if row.processing_status != ProcessingStatus.RECEIVED.value:
                raise JdIngestionError("JD_PERSISTENCE_FAILED")


def _map_source_type(source: JdSourceType) -> str:
    if source == JdSourceType.URL:
        return JobSourceType.URL.value
    return JobSourceType.TEXT.value


def _is_graph_eligible(record: JobPostRecord) -> bool:
    return (
        record.record_status == RecordStatus.ACTIVE.value
        and record.processing_status == ProcessingStatus.PROCESSED.value
        and record.jd_quality in _SCORABLE_QUALITIES
    )


async def _duplicate_outcome_for_processed(
    session: object,
    record: JobPostRecord,
    *,
    force_new_authorized: bool,
) -> DuplicateOutcome:
    if record.record_status == RecordStatus.IGNORED_DUPLICATE.value:
        return DuplicateOutcome.IGNORED_NORMALIZED
    if not force_new_authorized:
        return DuplicateOutcome.NONE
    if record.record_status != RecordStatus.ACTIVE.value:
        return DuplicateOutcome.NONE
    extraction = record.extraction
    if extraction is None:
        return DuplicateOutcome.NONE
    norm_key = build_normalized_job_key(
        extraction.company,
        extraction.title,
        extraction.location,
    )
    if norm_key is None:
        return DuplicateOutcome.NONE
    # force_new only when an older active peer already owns the identity.
    if not isinstance(session, AsyncSession):
        return DuplicateOutcome.NONE
    result = await session.execute(
        select(JobPost)
        .where(
            JobPost.normalized_key == norm_key,
            JobPost.record_status == RecordStatus.ACTIVE.value,
            JobPost.processing_status == ProcessingStatus.PROCESSED.value,
            JobPost.id != record.id,
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return DuplicateOutcome.FORCE_NEW
    return DuplicateOutcome.NONE


# Map provider codes to domain-stable codes (no vendor name in surfaces).
_PROVIDER_CODE_MAP: Final[dict[str, str]] = {
    ShopAIKeyErrorCode.TIMEOUT.value: "JD_PROVIDER_TIMEOUT",
    ShopAIKeyErrorCode.RATE_LIMIT.value: "JD_PROVIDER_RATE_LIMIT",
    ShopAIKeyErrorCode.SCHEMA_INVALID.value: "JD_SCHEMA_INVALID",
    ShopAIKeyErrorCode.PROVIDER_ERROR.value: "JD_PROVIDER_ERROR",
    ShopAIKeyErrorCode.CANCELLED.value: "JD_PROVIDER_CANCELLED",
    ShopAIKeyErrorCode.EMPTY_RESPONSE.value: "JD_PROVIDER_EMPTY",
    ShopAIKeyErrorCode.MODEL_MISMATCH.value: "JD_PROVIDER_MODEL",
    ShopAIKeyErrorCode.CONFIG.value: "JD_PROVIDER_CONFIG",
}


def _stable_failure_code(exc: BaseException) -> str:
    if isinstance(exc, ShopAIKeyChatError):
        return _PROVIDER_CODE_MAP.get(exc.code.value, "JD_PROVIDER_ERROR")
    if isinstance(exc, JdExtractionError):
        code = str(exc.code).upper().replace("-", "_")
        if not code.startswith("JD_"):
            code = f"JD_{code}"
        return code
    return "JD_PROCESSING_FAILED"


def _result_from_record(
    record: JobPostRecord,
    *,
    processing_result: ProcessingResult,
    duplicate_outcome: DuplicateOutcome,
    error_code: str | None,
) -> SaveJobResult:
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
    # Exact duplicate of an already-processed row: surface stored quality.
    return SaveJobResult(
        job_id=record.id,
        source_type=record.source_type,
        source_url=record.source_url,
        processing_result=processing_result,
        processing_status=record.processing_status,
        jd_quality=record.jd_quality,
        quality_reasons=record.quality_reasons,
        record_status=record.record_status,
        duplicate_outcome=duplicate_outcome,
        duplicate_of_job_id=record.duplicate_of_job_id,
        graph_sync_status=record.graph_sync_status,
        error_code=error_code,
        display=display,
    )


__all__ = [
    "JOB_UPSERT_OPERATION",
    "JDIngestionService",
    "JdIngestionError",
]
