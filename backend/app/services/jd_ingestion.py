"""Persistence-first JD ingestion orchestration (Plan 5 §7.3 / §7.4 / §7.7).

Raw-text path (Task 02C): exact SHA-256 selection, short SQLite transactions,
extraction/embedding outside transactions, one terminal processed/failed write.

URL path (Task 02D): commit received placeholder before fetch; fetch outside
transactions; exact fetched-hash return/retry with pure-placeholder deletion;
reuse the same downstream processor as raw text.

After a processed scorable (``full|partial``) SQLite commit, optionally runs
direct Job graph sync outside any transaction. Graph failure never changes the
processed row; exact non-failed duplicate return never calls sync.

Reuses ``app.db.session.session_scope`` with an optional injected session
factory for tests; does not define a private short-transaction helper.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    EmbeddingAdapterError,
    ShopAIKeyEmbeddingAdapter,
)
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.db.session import session_scope
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
)
from app.repositories import jobs as jobs_repo
from app.schemas.embeddings import EmbeddingVectorError
from app.schemas.jobs import (
    JOB_INGEST_OUTCOME_CREATED,
    JOB_INGEST_OUTCOME_RETRIED,
    JOB_INGEST_OUTCOME_RETURNED,
    JobIngestOutcome,
    JobPostExtraction,
)
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
from app.services.url_fetch import (
    PASTE_JD_FALLBACK_MESSAGE,
    URL_EMPTY_TEXT,
    URL_FETCH_UNAVAILABLE,
    UrlFetchResult,
    fetch_url_text,
)

logger = logging.getLogger(__name__)

FAILURE_EMPTY_TEXT: Final[str] = "EMPTY_JD_TEXT"
FAILURE_EMPTY_URL: Final[str] = "EMPTY_URL"
_SCORABLE_QUALITIES: Final[frozenset[str]] = frozenset(
    {JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL}
)

# Re-export schema-owned outcome type for existing ingestion callers.
IngestOutcome = JobIngestOutcome
UrlFetcher = Callable[[str], Awaitable[UrlFetchResult]]

class JdIngestionError(Exception):
    """Ingestion rejected input before any durable Job write."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class JdIngestResult:
    """Compact durable outcome of text/URL ingestion (no raw JD body).

    ``paste_instruction`` carries the exact shared url_fetch paste-text
    fallback on URL acquisition failures only. It is None for successful
    acquisition, non-fetch failures, and all raw-text outcomes. The instruction
    is never persisted as free text on the Job row.

    Graph fields are set only when a scorable terminal commit attempted direct
    sync (``sync_ok`` True/False). Non-scorable, failed, and exact-duplicate
    returns leave ``sync_ok`` as None (no graph call).
    """

    job_id: str
    processing_status: str
    jd_quality: str | None
    failure_code: str | None
    outcome: IngestOutcome
    source_type: str
    raw_content_hash: str | None
    source_url: str | None = None
    paste_instruction: str | None = None
    sync_ok: bool | None = None
    sync_code: str | None = None
    rebuild_instruction: str | None = None


def compute_raw_content_hash(raw_content: str) -> str:
    """Exact SHA-256 hex of stored raw content bytes (UTF-8, no normalize)."""
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


def _require_pasted_text(text: str) -> str:
    if not isinstance(text, str) or text.strip() == "":
        raise JdIngestionError(
            FAILURE_EMPTY_TEXT,
            "pasted JD text must be non-empty after stripping whitespace",
        )
    return text


def _require_url(url: str) -> str:
    if not isinstance(url, str) or url.strip() == "":
        raise JdIngestionError(
            FAILURE_EMPTY_URL,
            "source URL must be non-empty after stripping whitespace",
        )
    return url


def _snapshot(
    row: JobPost,
    *,
    outcome: IngestOutcome,
    paste_instruction: str | None = None,
    sync_ok: bool | None = None,
    sync_code: str | None = None,
    rebuild_instruction: str | None = None,
) -> JdIngestResult:
    return JdIngestResult(
        job_id=row.id,
        processing_status=row.processing_status,
        jd_quality=row.jd_quality,
        failure_code=row.failure_code,
        outcome=outcome,
        source_type=row.source_type,
        raw_content_hash=row.raw_content_hash,
        source_url=row.source_url,
        paste_instruction=paste_instruction,
        sync_ok=sync_ok,
        sync_code=sync_code,
        rebuild_instruction=rebuild_instruction,
    )


def _is_scorable_processed(row: JobPost) -> bool:
    return (
        row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
        and row.jd_quality in _SCORABLE_QUALITIES
    )


async def _maybe_sync_scorable_job(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> tuple[bool | None, str | None, str | None]:
    """Run direct Job sync after scorable terminal commit when a graph seam exists.

    Returns ``(sync_ok, sync_code, rebuild_instruction)``. When no driver/sync
    function is injected, returns ``(None, None, None)`` without graph I/O
    (tests that only exercise SQLite paths). Exact-duplicate and unscorable
    callers must not invoke this helper.
    """
    result = await sync_persisted_job(
        row,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
        log_context="jd ingestion",
    )
    if not result.attempted:
        return None, None, None
    return result.ok, result.code, result.rebuild_instruction


def _default_url_fetcher(url: str) -> Awaitable[UrlFetchResult]:
    return fetch_url_text(url)


async def _select_raw_text_for_processing(
    *,
    raw_content: str,
    raw_content_hash: str,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> tuple[str, IngestOutcome, bool]:
    """Persist/select and move to processing when work is required.

    Returns ``(job_id, outcome, needs_processing)``. When
    ``needs_processing`` is False, the existing non-failed row is returned
    unchanged and no external work must run.
    """
    async with session_scope(session_factory) as session:
        existing = await jobs_repo.get_by_raw_content_hash(session, raw_content_hash)
        if existing is not None:
            if existing.processing_status != JOB_PROCESSING_STATUS_FAILED:
                # Non-failed exact match: return unchanged (no reprocess).
                return existing.id, JOB_INGEST_OUTCOME_RETURNED, False

            retried = await jobs_repo.retry_failed_as_processing(session, existing.id)
            return retried.id, JOB_INGEST_OUTCOME_RETRIED, True

        created = await jobs_repo.create_text_job(
            session,
            raw_content=raw_content,
            raw_content_hash=raw_content_hash,
        )
        processing = await jobs_repo.mark_processing(session, created.id)
        return processing.id, JOB_INGEST_OUTCOME_CREATED, True


async def _commit_url_placeholder(
    source_url: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> str:
    """Commit one received URL placeholder with null content/hash."""
    async with session_scope(session_factory) as session:
        row = await jobs_repo.create_url_placeholder(session, source_url=source_url)
        return row.id


async def _dispose_url_after_fetch(
    *,
    placeholder_id: str,
    raw_content: str,
    raw_content_hash: str,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> tuple[str, IngestOutcome, bool, str]:
    """Exact fetched-hash disposition after successful acquisition.

    Returns ``(job_id, outcome, needs_processing, raw_content_for_processor)``.

    - Non-failed match: delete only the pristine placeholder; return existing.
    - Failed match: delete placeholder; retry that failed row in place.
    - No match: attach content/hash to the placeholder and mark processing.
    """
    async with session_scope(session_factory) as session:
        existing = await jobs_repo.get_by_raw_content_hash(session, raw_content_hash)
        if existing is not None:
            # Never delete anything but the temporary pristine placeholder.
            await jobs_repo.delete_url_placeholder(session, placeholder_id)
            if existing.processing_status != JOB_PROCESSING_STATUS_FAILED:
                stored = existing.raw_content or raw_content
                return existing.id, JOB_INGEST_OUTCOME_RETURNED, False, stored

            retried = await jobs_repo.retry_failed_as_processing(session, existing.id)
            # Same hash ⇒ same exact stored text as the acquired body.
            body = (
                retried.raw_content
                if retried.raw_content is not None
                else raw_content
            )
            return retried.id, JOB_INGEST_OUTCOME_RETRIED, True, body

        await jobs_repo.set_url_raw_content(
            session,
            placeholder_id,
            raw_content=raw_content,
            raw_content_hash=raw_content_hash,
        )
        processing = await jobs_repo.mark_processing(session, placeholder_id)
        return processing.id, JOB_INGEST_OUTCOME_CREATED, True, raw_content


async def _load_row(
    job_id: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    async with session_scope(session_factory) as session:
        row = await jobs_repo.get_by_id(session, job_id)
        if row is None:  # pragma: no cover - invariant after select
            raise RuntimeError(f"job {job_id!r} missing after selection")
        # Detach scalars needed after commit; expire_on_commit=False keeps attrs.
        _ = (
            row.id,
            row.processing_status,
            row.jd_quality,
            row.failure_code,
            row.source_type,
            row.raw_content_hash,
            row.raw_content,
            row.source_url,
            row.extraction_json,
            row.embedding_json,
            row.updated_at,
        )
        return row


async def _mark_failed(
    job_id: str,
    failure_code: str,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    async with session_scope(session_factory) as session:
        return await jobs_repo.mark_failed(
            session, job_id, failure_code=failure_code
        )


async def _mark_processed(
    job_id: str,
    *,
    extraction: JobPostExtraction,
    jd_quality: str,
    embedding_json: list[float] | None,
    embedding_model: str | None,
    embedding_dimensions: int | None,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    async with session_scope(session_factory) as session:
        return await jobs_repo.mark_processed(
            session,
            job_id,
            extraction_json=extraction.model_dump(mode="json"),
            jd_quality=jd_quality,
            embedding_json=embedding_json,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
        )


def _embed_if_scorable(
    extraction: JobPostExtraction,
    jd_quality: str,
    embedding_client: EmbeddingClient,
) -> tuple[list[float] | None, str | None, int | None]:
    """Embed only full/partial; validate finite 1536 before terminal write."""
    if jd_quality not in _SCORABLE_QUALITIES:
        return None, None, None

    return embed_job_extraction(extraction, embedding_client)


async def _run_processing(
    job_id: str,
    raw_content: str,
    *,
    invoker: StructuredJdInvoker,
    normalizer: SkillNormalizer,
    embedding_client: EmbeddingClient,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> JobPost:
    """Extract/classify/embed outside transactions; one terminal write after.

    Shared by raw-text and URL paths after a row is selected for processing.
    """
    try:
        # External: structured extraction (no open SQLite transaction).
        extract_outcome = extract_job_post_from_text(
            raw_content,
            invoker=invoker,
            normalizer=normalizer,
        )
        extraction = extract_outcome.extraction
        jd_quality = classify_jd_quality(extraction)

        # External: embedding only for scorable qualities.
        try:
            embedding_json, embedding_model, embedding_dimensions = (
                _embed_if_scorable(extraction, jd_quality, embedding_client)
            )
        except EmbeddingAdapterError as exc:
            logger.info(
                "jd ingestion embedding failed job_id=%s code=%s",
                job_id,
                exc.code,
            )
            return await _mark_failed(
                job_id, exc.code, session_factory=session_factory
            )
        except EmbeddingVectorError:
            logger.info(
                "jd ingestion embedding invalid job_id=%s code=%s",
                job_id,
                FAILURE_EMBEDDING_INVALID_RESPONSE,
            )
            return await _mark_failed(
                job_id,
                FAILURE_EMBEDDING_INVALID_RESPONSE,
                session_factory=session_factory,
            )

        return await _mark_processed(
            job_id,
            extraction=extraction,
            jd_quality=jd_quality,
            embedding_json=embedding_json,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            session_factory=session_factory,
        )
    except JdExtractionError as exc:
        logger.info(
            "jd ingestion extraction failed job_id=%s code=%s",
            job_id,
            exc.code,
        )
        return await _mark_failed(
            job_id, exc.code, session_factory=session_factory
        )


async def ingest_raw_text(
    text: str,
    *,
    invoker: StructuredJdInvoker,
    normalizer: SkillNormalizer,
    embedding_client: EmbeddingClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    graph_driver: AsyncGraphDriver | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> JdIngestResult:
    """Ingest pasted JD text with persistence-first exact-hash semantics.

    Flow:
    1. Reject whitespace-only input (no row).
    2. Compute exact SHA-256 of the accepted string.
    3. Short transaction: return existing non-failed row, retry failed in place,
       or insert ``received`` and move to ``processing``.
    4. Outside transactions: extract, classify, embed full|partial only.
    5. Short transaction: one terminal ``processed`` or ``failed`` write.
       Accepted raw text is never rolled back.
    6. After scorable processed commit only: direct Job graph sync outside
       transactions when ``graph_driver`` / ``job_sync_fn`` is provided. Exact
       non-failed duplicate return never syncs.

    Does not call tools or public routes.
    """
    raw_content = _require_pasted_text(text)
    raw_hash = compute_raw_content_hash(raw_content)
    embedder: EmbeddingClient = (
        embedding_client
        if embedding_client is not None
        else ShopAIKeyEmbeddingAdapter()
    )

    job_id, outcome, needs_processing = await _select_raw_text_for_processing(
        raw_content=raw_content,
        raw_content_hash=raw_hash,
        session_factory=session_factory,
    )

    if not needs_processing:
        # Exact non-failed duplicate: no extraction/embedding/sync.
        row = await _load_row(job_id, session_factory=session_factory)
        return _snapshot(row, outcome=outcome)

    terminal = await _run_processing(
        job_id,
        raw_content,
        invoker=invoker,
        normalizer=normalizer,
        embedding_client=embedder,
        session_factory=session_factory,
    )
    # Reload after commit so sync sees durable SQLite truth + updated_at.
    terminal = await _load_row(terminal.id, session_factory=session_factory)
    sync_ok, sync_code, rebuild = await _maybe_sync_scorable_job(
        terminal,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
    )
    return _snapshot(
        terminal,
        outcome=outcome,
        sync_ok=sync_ok,
        sync_code=sync_code,
        rebuild_instruction=rebuild,
    )


async def ingest_url(
    url: str,
    *,
    invoker: StructuredJdInvoker,
    normalizer: SkillNormalizer,
    embedding_client: EmbeddingClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    url_fetcher: UrlFetcher | None = None,
    graph_driver: AsyncGraphDriver | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> JdIngestResult:
    """Ingest a public URL with placeholder-before-fetch and exact-hash reuse.

    Flow:
    1. Reject whitespace-only URL (no row).
    2. Commit a ``received`` URL placeholder (original URL, null content/hash).
    3. Fetch outside any SQLite transaction (injected or production fetcher).
    4. Fetch failure: mark that placeholder ``failed`` with stable code; URL kept.
    5. Hash exact acquired text; disposition:
       - non-failed match → delete placeholder, return existing (no process/sync)
       - failed match → delete placeholder, retry that row in place
       - unique → attach content/hash to placeholder, mark processing
    6. Reuse the same downstream processor as raw text. Provider/embedding
       failure retains URL, acquired text, and hash on the selected row.
    7. After scorable processed commit only: direct Job graph sync outside
       transactions when a graph seam is provided.

    Does not call public routes. Does not delete any row other than a pristine
    temporary placeholder when another exact row is selected.
    """
    source_url = _require_url(url)
    embedder: EmbeddingClient = (
        embedding_client
        if embedding_client is not None
        else ShopAIKeyEmbeddingAdapter()
    )
    fetcher: UrlFetcher = (
        url_fetcher if url_fetcher is not None else _default_url_fetcher
    )

    # 1) Placeholder committed before any network/fetch work.
    placeholder_id = await _commit_url_placeholder(
        source_url, session_factory=session_factory
    )

    # 2) Fetch outside transactions (and outside any open session).
    fetch_result = await fetcher(source_url)
    if not fetch_result.ok:
        # Stable acquisition failure codes + exact shared paste instruction
        # from url_fetch (not persisted as free text on the Job row).
        code = fetch_result.failure_code or URL_FETCH_UNAVAILABLE
        instruction = (
            fetch_result.paste_fallback_message or PASTE_JD_FALLBACK_MESSAGE
        )
        logger.info(
            "jd ingestion url fetch failed placeholder_id=%s code=%s",
            placeholder_id,
            code,
        )
        failed = await _mark_failed(
            placeholder_id, code, session_factory=session_factory
        )
        return _snapshot(
            failed,
            outcome=JOB_INGEST_OUTCOME_CREATED,
            paste_instruction=instruction,
        )

    acquired = fetch_result.text
    if acquired is None:  # pragma: no cover - ok implies non-None text
        failed = await _mark_failed(
            placeholder_id,
            URL_EMPTY_TEXT,
            session_factory=session_factory,
        )
        return _snapshot(
            failed,
            outcome=JOB_INGEST_OUTCOME_CREATED,
            paste_instruction=PASTE_JD_FALLBACK_MESSAGE,
        )

    raw_hash = compute_raw_content_hash(acquired)
    job_id, outcome, needs_processing, raw_for_processing = (
        await _dispose_url_after_fetch(
            placeholder_id=placeholder_id,
            raw_content=acquired,
            raw_content_hash=raw_hash,
            session_factory=session_factory,
        )
    )

    if not needs_processing:
        # Exact non-failed duplicate: no extraction/embedding/sync.
        row = await _load_row(job_id, session_factory=session_factory)
        return _snapshot(row, outcome=outcome)

    terminal = await _run_processing(
        job_id,
        raw_for_processing,
        invoker=invoker,
        normalizer=normalizer,
        embedding_client=embedder,
        session_factory=session_factory,
    )
    terminal = await _load_row(terminal.id, session_factory=session_factory)
    sync_ok, sync_code, rebuild = await _maybe_sync_scorable_job(
        terminal,
        normalizer=normalizer,
        graph_driver=graph_driver,
        job_sync_fn=job_sync_fn,
    )
    return _snapshot(
        terminal,
        outcome=outcome,
        sync_ok=sync_ok,
        sync_code=sync_code,
        rebuild_instruction=rebuild,
    )


__all__ = [
    "FAILURE_EMPTY_TEXT",
    "FAILURE_EMPTY_URL",
    "NEO4J_REBUILD_INSTRUCTION",
    "NEO4J_SYNC_FAILED",
    "IngestOutcome",
    "JdIngestResult",
    "JdIngestionError",
    "JobSyncFn",
    "UrlFetcher",
    "compute_raw_content_hash",
    "ingest_raw_text",
    "ingest_url",
]
