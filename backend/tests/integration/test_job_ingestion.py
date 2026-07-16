"""Integration tests for persistence-first JD ingestion (Plan 5 / 02C + 02D).

Migrated temporary SQLite + injected fakes only. Covers raw-text path (new input,
non-failed exact duplicate return, failed same-ID retry, quality/embedding
coupling, durable extraction/embedding failures) and URL path (placeholder
before fetch, fetch failures, fetched-hash reuse/retry, placeholder deletion,
retained acquired text after later provider failure). No network access.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

import pytest
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    FAILURE_EMBEDDING_TIMEOUT,
    EmbeddingAdapterError,
)
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_PROCESSING_STATUS_RECEIVED,
    JOB_SOURCE_TYPE_TEXT,
    JOB_SOURCE_TYPE_URL,
    JobPost,
)
from app.db.session import build_async_engine, session_scope
from app.repositories import jobs as jobs_repo
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS, LOCKED_EMBEDDING_MODEL
from app.services.jd_extraction import (
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    FAILURE_PROVIDER_ERROR,
    ExtractedJobPost,
)
from app.services.jd_ingestion import (
    FAILURE_EMPTY_TEXT,
    FAILURE_EMPTY_URL,
    JdIngestionError,
    compute_raw_content_hash,
    ingest_raw_text,
    ingest_url,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.url_fetch import (
    PASTE_JD_FALLBACK_MESSAGE,
    URL_EMPTY_TEXT,
    URL_FETCH_UNAVAILABLE,
    URL_UNSUPPORTED_SCHEME,
    UrlFetchResult,
)
from pydantic import ValidationError
from sqlalchemy import func, select, text

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.structured_output import FakeJdInvoker
from tests.support.db_migration import run_async, session_factory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _vector(seed: float = 0.01) -> list[float]:
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


def _full_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python"],
            }
        ],
        "preferred_skills": [
            {
                "name": "FastAPI",
                "confidence": 0.6,
                "evidence": ["Preferred: FastAPI"],
            }
        ],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


def _partial_extracted(**overrides: Any) -> ExtractedJobPost:
    # Summary + usable signal, missing title and most scoring groups → partial.
    return _full_extracted(
        title=None,
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        **overrides,
    )


def _unscorable_extracted(**overrides: Any) -> ExtractedJobPost:
    # Thin facts: no usable responsibilities/skills evidence → unscorable.
    base: dict[str, Any] = {
        "title": None,
        "company": None,
        "summary": "Contact us for details.",
        "responsibilities": [],
        "required_skills": [],
        "preferred_skills": [],
        "seniority": "unknown",
        "min_experience_years": None,
        "max_experience_years": None,
        "location": None,
        "work_mode": "unknown",
        "extraction_confidence": 0.1,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


def _factory(db_path: Path):
    engine = build_async_engine(db_path)
    return engine, session_factory(engine)


async def _count_jobs(factory: Any) -> int:
    async with factory() as session:
        count = await session.execute(select(func.count()).select_from(JobPost))
        return int(count.scalar_one())


async def _get_job(factory: Any, job_id: str) -> JobPost:
    async with factory() as session:
        row = await jobs_repo.get_by_id(session, job_id)
        assert row is not None
        # Touch attributes while session is open.
        _ = (
            row.raw_content,
            row.raw_content_hash,
            row.processing_status,
            row.jd_quality,
            row.failure_code,
            row.embedding_json,
            row.embedding_model,
            row.embedding_dimensions,
            row.extraction_json,
            row.source_url,
            row.source_type,
        )
        return row


class FakeUrlFetcher:
    """Scripted URL fetcher recording call order for placeholder-before-fetch."""

    def __init__(
        self,
        result: UrlFetchResult | None = None,
        *,
        text: str | None = None,
        failure_code: str | None = None,
        on_fetch: Any = None,
    ) -> None:
        if result is not None:
            self._result = result
        elif failure_code is not None:
            self._result = UrlFetchResult(text=None, failure_code=failure_code)
        else:
            body = text if text is not None else "Fetched JD body from URL."
            self._result = UrlFetchResult(text=body, failure_code=None)
        self.calls: list[str] = []
        self._on_fetch = on_fetch

    async def __call__(self, url: str) -> UrlFetchResult:
        self.calls.append(url)
        if self._on_fetch is not None:
            await self._on_fetch(url)
        return self._result


# ---------------------------------------------------------------------------
# Hash / empty input
# ---------------------------------------------------------------------------


def test_compute_raw_content_hash_is_exact_sha256() -> None:
    body = "Exact pasted JD\nwith newlines"
    assert compute_raw_content_hash(body) == _sha(body)
    # No whitespace normalization for dedup hash.
    assert compute_raw_content_hash("a b") != compute_raw_content_hash("a  b")


def test_empty_text_rejected_without_row(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient()
            for bad in ("", "   ", "\n\t"):
                with pytest.raises(JdIngestionError) as ei:
                    await ingest_raw_text(
                        bad,
                        invoker=invoker,
                        normalizer=_normalizer(),
                        embedding_client=emb,
                        session_factory=factory,
                    )
                assert ei.value.code == FAILURE_EMPTY_TEXT
            assert await _count_jobs(factory) == 0
            assert invoker.calls == []
            assert emb.calls == []
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# New raw input → processed full with embedding
# ---------------------------------------------------------------------------


def test_new_raw_text_persists_before_processing_and_embeds_full(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Synthetic full JD about Python and FastAPI services."
            invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient(vector=_vector(0.02))
            result = await ingest_raw_text(
                jd,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality == JOB_JD_QUALITY_FULL
            assert result.failure_code is None
            assert result.source_type == JOB_SOURCE_TYPE_TEXT
            assert result.raw_content_hash == _sha(jd)
            assert len(invoker.calls) == 1
            assert len(emb.calls) == 1

            row = await _get_job(factory, result.job_id)
            assert row.raw_content == jd
            assert row.raw_content_hash == _sha(jd)
            assert row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert row.jd_quality == JOB_JD_QUALITY_FULL
            assert row.extraction_json is not None
            assert "jd_quality" not in row.extraction_json
            assert isinstance(row.embedding_json, list)
            assert len(row.embedding_json) == LOCKED_EMBEDDING_DIMENSIONS
            assert row.embedding_model == LOCKED_EMBEDDING_MODEL
            assert row.embedding_dimensions == LOCKED_EMBEDDING_DIMENSIONS
            assert await _count_jobs(factory) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_processed_partial_has_embedding_triplet(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Partial JD text with some signal."
            result = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([_partial_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            assert result.jd_quality == JOB_JD_QUALITY_PARTIAL
            row = await _get_job(factory, result.job_id)
            assert row.embedding_model == LOCKED_EMBEDDING_MODEL
            assert row.embedding_dimensions == LOCKED_EMBEDDING_DIMENSIONS
            assert isinstance(row.embedding_json, list)
            assert len(row.embedding_json) == LOCKED_EMBEDDING_DIMENSIONS
        finally:
            await engine.dispose()

    run_async(_body())


def test_processed_unscorable_null_embeddings(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Contact only thin JD."
            emb = FakeEmbeddingClient()
            result = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([_unscorable_extracted()]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality == JOB_JD_QUALITY_UNSCORABLE
            assert emb.calls == []  # no embed for unscorable
            row = await _get_job(factory, result.job_id)
            assert row.embedding_json is None
            assert row.embedding_model is None
            assert row.embedding_dimensions is None
            async with factory() as session:
                raw = (
                    await session.execute(
                        text(
                            "SELECT embedding_json IS NULL, embedding_model IS NULL, "
                            "embedding_dimensions IS NULL FROM job_posts WHERE id = :id"
                        ),
                        {"id": result.job_id},
                    )
                ).one()
            assert raw == (1, 1, 1)
            assert row.raw_content == jd
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Exact duplicate return (zero external calls)
# ---------------------------------------------------------------------------


def test_non_failed_exact_duplicate_returns_same_id_zero_external_calls(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Duplicate candidate JD body."
            invoker1 = FakeJdInvoker([_full_extracted()])
            emb1 = FakeEmbeddingClient()
            first = await ingest_raw_text(
                jd,
                invoker=invoker1,
                normalizer=_normalizer(),
                embedding_client=emb1,
                session_factory=factory,
            )
            assert first.outcome == "created"
            assert first.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            updated_before = (await _get_job(factory, first.job_id)).updated_at

            invoker2 = FakeJdInvoker([_full_extracted()])
            emb2 = FakeEmbeddingClient()
            second = await ingest_raw_text(
                jd,
                invoker=invoker2,
                normalizer=_normalizer(),
                embedding_client=emb2,
                session_factory=factory,
            )
            assert second.outcome == "returned"
            assert second.job_id == first.job_id
            assert second.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert second.jd_quality == first.jd_quality
            assert invoker2.calls == []
            assert emb2.calls == []
            assert await _count_jobs(factory) == 1
            after = await _get_job(factory, first.job_id)
            assert after.updated_at == updated_before
            assert after.raw_content == jd
        finally:
            await engine.dispose()

    run_async(_body())


def test_different_content_creates_new_row(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            a = await ingest_raw_text(
                "Content A unique",
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            b = await ingest_raw_text(
                "Content B unique",
                invoker=FakeJdInvoker([_partial_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(vector=_vector(0.5)),
                session_factory=factory,
            )
            assert a.job_id != b.job_id
            assert await _count_jobs(factory) == 2
            assert a.raw_content_hash != b.raw_content_hash
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Failed retry in place
# ---------------------------------------------------------------------------


def test_failed_exact_duplicate_retries_same_id_and_clears_terminal_fields(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Retryable failed JD content."
            sync_calls = 0

            async def _sync(**kwargs: Any) -> None:
                nonlocal sync_calls
                del kwargs
                sync_calls += 1

            # First pass: non-retryable provider failure → failed terminal
            fail_invoker = FakeJdInvoker([RuntimeError("provider down")])
            emb_fail = FakeEmbeddingClient()
            first = await ingest_raw_text(
                jd,
                invoker=fail_invoker,
                normalizer=_normalizer(),
                embedding_client=emb_fail,
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert first.outcome == "created"
            assert first.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert first.failure_code == FAILURE_PROVIDER_ERROR
            job_id = first.job_id
            failed_row = await _get_job(factory, job_id)
            assert failed_row.raw_content == jd
            assert failed_row.raw_content_hash == _sha(jd)
            # Failed attempt: one provider call, no embed, no graph, one Job row.
            assert len(fail_invoker.calls) == 1
            assert emb_fail.calls == []
            assert sync_calls == 0
            assert await _count_jobs(factory) == 1

            # Second pass: same text → retry same ID, success
            ok_invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient()
            second = await ingest_raw_text(
                jd,
                invoker=ok_invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert second.outcome == "retried"
            assert second.job_id == job_id
            assert second.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert second.jd_quality == JOB_JD_QUALITY_FULL
            assert second.failure_code is None
            assert second.sync_ok is True
            # Retry: exactly one extract, one embed, one graph on the same row.
            assert len(ok_invoker.calls) == 1
            assert len(emb.calls) == 1
            assert sync_calls == 1
            assert await _count_jobs(factory) == 1

            row = await _get_job(factory, job_id)
            assert row.raw_content == jd
            assert row.failure_code is None
            assert row.extraction_json is not None
            assert row.embedding_model == LOCKED_EMBEDDING_MODEL
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Durable failures retain raw text
# ---------------------------------------------------------------------------


def test_extraction_failure_retains_raw_text(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Durable raw after extraction fail."
            emb = FakeEmbeddingClient()
            schema_err = ValidationError.from_exception_data(
                "ExtractedJobPost",
                [{"type": "missing", "loc": ("summary",), "input": {}}],
            )
            # Two invalid payloads exhaust the single schema-repair attempt.
            result = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([schema_err, schema_err]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == FAILURE_INVALID_STRUCTURED_OUTPUT
            assert emb.calls == []
            row = await _get_job(factory, result.job_id)
            assert row.raw_content == jd
            assert row.raw_content_hash == _sha(jd)
            assert row.extraction_json is None
            assert row.jd_quality is None
            assert row.embedding_json is None
            # Row was committed as received/processing before external work:
            # still exactly one row and raw retained.
            assert await _count_jobs(factory) == 1
            assert result.outcome == "created"
        finally:
            await engine.dispose()

    run_async(_body())


def test_embedding_failure_retains_raw_text_and_marks_failed(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Durable raw after embedding fail."
            emb = FakeEmbeddingClient(
                error=EmbeddingAdapterError(
                    FAILURE_EMBEDDING_TIMEOUT, "embedding request timed out"
                )
            )
            result = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == FAILURE_EMBEDDING_TIMEOUT
            assert len(emb.calls) == 1
            row = await _get_job(factory, result.job_id)
            assert row.raw_content == jd
            assert row.raw_content_hash == _sha(jd)
            assert row.embedding_json is None
            assert row.jd_quality is None
            # Extraction was not committed on embedding failure (terminal failed).
            assert row.extraction_json is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_invalid_embedding_vector_fails_terminal_write(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Bad vector JD."
            emb = FakeEmbeddingClient(vector=[1.0, 2.0])  # wrong length
            result = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == FAILURE_EMBEDDING_INVALID_RESPONSE
            row = await _get_job(factory, result.job_id)
            assert row.raw_content == jd
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Commit-before-external-work evidence + session_scope injection
# ---------------------------------------------------------------------------


def test_received_row_visible_if_extract_never_runs(db_path: Path) -> None:
    """Selection commits processing before external work (no spanning TX)."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Visible before extract."
            # Manual selection path parity: create + mark processing commits.
            h = _sha(jd)
            async with session_scope(factory) as session:
                row = await jobs_repo.create_text_job(
                    session, raw_content=jd, raw_content_hash=h
                )
                await jobs_repo.mark_processing(session, row.id)
                job_id = row.id

            # After commit, row is durable before any extract/embed.
            async with factory() as session:
                loaded = await jobs_repo.get_by_id(session, job_id)
                assert loaded is not None
                assert loaded.raw_content == jd
                assert loaded.processing_status != JOB_PROCESSING_STATUS_RECEIVED
                assert loaded.processing_status == "processing"

            # Full ingest of different content still works with injected factory.
            other = "Another JD after partial pipeline."
            result = await ingest_raw_text(
                other,
                invoker=FakeJdInvoker([_unscorable_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            assert result.outcome == "created"
            assert await _count_jobs(factory) == 2
        finally:
            await engine.dispose()

    run_async(_body())


def test_processed_row_cannot_be_reprocessed(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            jd = "Terminal processed content."
            first = await ingest_raw_text(
                jd,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            invoker = FakeJdInvoker([_partial_extracted()])
            emb = FakeEmbeddingClient(vector=_vector(0.9))
            again = await ingest_raw_text(
                jd,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
            )
            assert again.outcome == "returned"
            assert again.job_id == first.job_id
            assert again.jd_quality == JOB_JD_QUALITY_FULL  # not partial
            assert invoker.calls == []
            assert emb.calls == []
        finally:
            await engine.dispose()

    run_async(_body())


def test_ingestion_uses_session_scope_not_local_short_transaction() -> None:
    import app.services.jd_ingestion as mod

    source = inspect.getsource(mod)
    assert "async def _short_transaction" not in source
    assert "def _short_transaction" not in source
    assert "session_scope" in source
    # 02D: single owner reuses url_fetch + one downstream processor.
    assert "url_fetch" in source
    assert "ingest_url" in source
    assert "fetch_url_text" in source
    assert source.count("async def _run_processing") == 1


def test_no_force_new_or_near_duplicate_api() -> None:
    import app.services.jd_ingestion as mod

    assert not hasattr(mod, "force_new")
    source = inspect.getsource(mod)
    assert "force_new" not in source
    assert "near_duplicate" not in source
    assert "compute_raw_content_hash" in source


# ---------------------------------------------------------------------------
# URL path (02D): placeholder, fetch failure, hash reuse, retained content
# ---------------------------------------------------------------------------


def test_empty_url_rejected_without_row(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            fetcher = FakeUrlFetcher(text="should not run")
            for bad in ("", "   ", "\n\t"):
                with pytest.raises(JdIngestionError) as ei:
                    await ingest_url(
                        bad,
                        invoker=FakeJdInvoker([_full_extracted()]),
                        normalizer=_normalizer(),
                        embedding_client=FakeEmbeddingClient(),
                        session_factory=factory,
                        url_fetcher=fetcher,
                    )
                assert ei.value.code == FAILURE_EMPTY_URL
            assert await _count_jobs(factory) == 0
            assert fetcher.calls == []
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_placeholder_committed_before_fetch_begins(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            url = "https://example.com/jobs/placeholder-before-fetch"
            acquired = "Unique fetched JD for placeholder visibility."
            seen_placeholder: dict[str, Any] = {}

            async def on_fetch(_u: str) -> None:
                # Fetch has started: placeholder must already be committed.
                async with factory() as session:
                    rows = (
                        await session.execute(select(JobPost))
                    ).scalars().all()
                    assert len(rows) == 1
                    ph = rows[0]
                    seen_placeholder["id"] = ph.id
                    seen_placeholder["status"] = ph.processing_status
                    seen_placeholder["source_url"] = ph.source_url
                    seen_placeholder["raw_content"] = ph.raw_content
                    seen_placeholder["raw_content_hash"] = ph.raw_content_hash

            fetcher = FakeUrlFetcher(text=acquired, on_fetch=on_fetch)
            result = await ingest_url(
                url,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                url_fetcher=fetcher,
            )
            assert fetcher.calls == [url]
            assert seen_placeholder["status"] == JOB_PROCESSING_STATUS_RECEIVED
            assert seen_placeholder["source_url"] == url
            assert seen_placeholder["raw_content"] is None
            assert seen_placeholder["raw_content_hash"] is None
            # Unique content kept the same placeholder row through processing.
            assert result.job_id == seen_placeholder["id"]
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.source_type == JOB_SOURCE_TYPE_URL
            assert result.source_url == url
            assert result.raw_content_hash == _sha(acquired)

            row = await _get_job(factory, result.job_id)
            assert row.raw_content == acquired
            assert row.source_url == url
            assert await _count_jobs(factory) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_fetch_failure_leaves_placeholder_failed_with_stable_code(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            url = "https://example.com/jobs/unavailable"
            fetcher = FakeUrlFetcher(failure_code=URL_FETCH_UNAVAILABLE)
            invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient()
            result = await ingest_url(
                url,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=fetcher,
            )
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == URL_FETCH_UNAVAILABLE
            assert result.raw_content_hash is None
            assert result.source_url == url
            assert result.paste_instruction == PASTE_JD_FALLBACK_MESSAGE
            assert invoker.calls == []
            assert emb.calls == []
            assert fetcher.calls == [url]

            row = await _get_job(factory, result.job_id)
            assert row.source_type == JOB_SOURCE_TYPE_URL
            assert row.source_url == url
            assert row.raw_content is None
            assert row.raw_content_hash is None
            assert row.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert row.failure_code == URL_FETCH_UNAVAILABLE
            # Paste instruction is result-only; never persisted as free text.
            assert await _count_jobs(factory) == 1

            # Unsupported scheme after placeholder also fails that row.
            bad = "ftp://example.com/jd"
            scheme_fetcher = FakeUrlFetcher(failure_code=URL_UNSUPPORTED_SCHEME)
            second = await ingest_url(
                bad,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                url_fetcher=scheme_fetcher,
            )
            assert second.failure_code == URL_UNSUPPORTED_SCHEME
            assert second.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert second.paste_instruction == PASTE_JD_FALLBACK_MESSAGE
            assert (await _get_job(factory, second.job_id)).source_url == bad
            assert await _count_jobs(factory) == 2

            # Empty acquired text path.
            empty_fetcher = FakeUrlFetcher(failure_code=URL_EMPTY_TEXT)
            third = await ingest_url(
                "https://example.com/empty",
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                url_fetcher=empty_fetcher,
            )
            assert third.failure_code == URL_EMPTY_TEXT
            assert third.paste_instruction == PASTE_JD_FALLBACK_MESSAGE
            assert await _count_jobs(factory) == 3
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_to_text_exact_match_deletes_placeholder_returns_existing(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Exact shared JD body across text and URL."
            text_result = await ingest_raw_text(
                body,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            assert text_result.outcome == "created"
            existing_id = text_result.job_id
            updated_before = (await _get_job(factory, existing_id)).updated_at

            invoker = FakeJdInvoker([_partial_extracted()])
            emb = FakeEmbeddingClient(vector=_vector(0.7))
            fetcher = FakeUrlFetcher(text=body)
            url_result = await ingest_url(
                "https://example.com/same-as-text",
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=fetcher,
            )
            assert url_result.outcome == "returned"
            assert url_result.job_id == existing_id
            assert url_result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert url_result.jd_quality == JOB_JD_QUALITY_FULL
            assert invoker.calls == []
            assert emb.calls == []
            assert await _count_jobs(factory) == 1  # placeholder deleted
            after = await _get_job(factory, existing_id)
            assert after.updated_at == updated_before
            assert after.source_type == JOB_SOURCE_TYPE_TEXT
            assert after.raw_content == body
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_to_url_exact_match_deletes_placeholder_zero_external_calls(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Same fetched content from two URLs."
            first = await ingest_url(
                "https://example.com/jobs/a",
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert first.outcome == "created"
            assert first.source_url == "https://example.com/jobs/a"

            invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient()
            second = await ingest_url(
                "https://example.com/jobs/b",
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert second.outcome == "returned"
            assert second.job_id == first.job_id
            assert invoker.calls == []
            assert emb.calls == []
            assert await _count_jobs(factory) == 1
            row = await _get_job(factory, first.job_id)
            # Original row retained; second URL's placeholder was deleted only.
            assert row.source_url == "https://example.com/jobs/a"
            assert row.raw_content == body
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_failed_exact_match_deletes_placeholder_retries_same_id(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Retryable URL-acquired JD content."
            # Seed a failed text row with the same content hash.
            fail_first = await ingest_raw_text(
                body,
                invoker=FakeJdInvoker([RuntimeError("provider down")]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
            )
            assert fail_first.processing_status == JOB_PROCESSING_STATUS_FAILED
            failed_id = fail_first.job_id

            ok_invoker = FakeJdInvoker([_full_extracted()])
            emb = FakeEmbeddingClient()
            retried = await ingest_url(
                "https://example.com/retry-failed",
                invoker=ok_invoker,
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert retried.outcome == "retried"
            assert retried.job_id == failed_id
            assert retried.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert retried.jd_quality == JOB_JD_QUALITY_FULL
            assert len(ok_invoker.calls) == 1
            assert len(emb.calls) == 1
            assert await _count_jobs(factory) == 1  # placeholder deleted
            row = await _get_job(factory, failed_id)
            assert row.raw_content == body
            assert row.failure_code is None
            assert row.embedding_model == LOCKED_EMBEDDING_MODEL
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_unique_content_processed_on_placeholder_row(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Brand new URL-only JD content."
            url = "https://example.com/unique-jd"
            result = await ingest_url(
                url,
                invoker=FakeJdInvoker([_partial_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(vector=_vector(0.03)),
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality == JOB_JD_QUALITY_PARTIAL
            assert result.source_type == JOB_SOURCE_TYPE_URL
            assert result.source_url == url
            assert result.raw_content_hash == _sha(body)
            row = await _get_job(factory, result.job_id)
            assert row.raw_content == body
            assert row.source_url == url
            assert isinstance(row.embedding_json, list)
            assert len(row.embedding_json) == LOCKED_EMBEDDING_DIMENSIONS
            assert await _count_jobs(factory) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_extraction_failure_retains_acquired_text_and_hash(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Acquired URL text retained after extract fail."
            url = "https://example.com/extract-fail"
            schema_err = ValidationError.from_exception_data(
                "ExtractedJobPost",
                [{"type": "missing", "loc": ("summary",), "input": {}}],
            )
            emb = FakeEmbeddingClient()
            result = await ingest_url(
                url,
                invoker=FakeJdInvoker([schema_err, schema_err]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == FAILURE_INVALID_STRUCTURED_OUTPUT
            assert result.outcome == "created"
            assert emb.calls == []
            row = await _get_job(factory, result.job_id)
            assert row.source_url == url
            assert row.raw_content == body
            assert row.raw_content_hash == _sha(body)
            assert row.extraction_json is None
            assert row.jd_quality is None
            assert await _count_jobs(factory) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_embedding_failure_retains_url_text_and_hash(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Acquired URL text retained after embed fail."
            url = "https://example.com/embed-fail"
            emb = FakeEmbeddingClient(
                error=EmbeddingAdapterError(
                    FAILURE_EMBEDDING_TIMEOUT, "embedding request timed out"
                )
            )
            result = await ingest_url(
                url,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=emb,
                session_factory=factory,
                url_fetcher=FakeUrlFetcher(text=body),
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_FAILED
            assert result.failure_code == FAILURE_EMBEDDING_TIMEOUT
            assert len(emb.calls) == 1
            row = await _get_job(factory, result.job_id)
            assert row.source_url == url
            assert row.raw_content == body
            assert row.raw_content_hash == _sha(body)
            assert row.embedding_json is None
            assert row.extraction_json is None
            assert await _count_jobs(factory) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_url_and_text_share_one_downstream_processor() -> None:
    import app.services.jd_ingestion as mod

    source = inspect.getsource(mod)
    # Both entry points call the same private processor; no second extract loop.
    assert "await _run_processing(" in source
    assert source.count("extract_job_post_from_text(") == 1
    assert "delete_url_placeholder" in source
    assert "create_url_placeholder" in source
    assert "set_url_raw_content" in source


# ---------------------------------------------------------------------------
# Direct Job graph sync after scorable terminal commit (03A)
# ---------------------------------------------------------------------------


def test_scorable_processed_calls_job_sync_after_sqlite_commit(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            sync_calls: list[dict[str, Any]] = []

            async def _sync(**kwargs: Any) -> None:
                del kwargs
                # SQLite must already show processed scorable truth.
                async with factory() as session:
                    rows = (
                        await session.execute(select(JobPost))
                    ).scalars().all()
                    assert len(rows) == 1
                    row = rows[0]
                    assert row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                    assert row.jd_quality == JOB_JD_QUALITY_FULL
                    assert row.embedding_json is not None
                    sync_calls.append({"job_id": row.id})

            result = await ingest_raw_text(
                "Scorable JD for post-commit sync.",
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(vector=_vector(0.04)),
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.sync_ok is True
            assert result.sync_code is None
            assert result.rebuild_instruction is None
            assert len(sync_calls) == 1
            assert sync_calls[0]["job_id"] == result.job_id
        finally:
            await engine.dispose()

    run_async(_body())


def test_unscorable_processed_never_calls_job_sync(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            sync_calls = 0

            async def _sync(**kwargs: Any) -> None:
                nonlocal sync_calls
                del kwargs
                sync_calls += 1

            result = await ingest_raw_text(
                "Contact only.",
                invoker=FakeJdInvoker([_unscorable_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality == JOB_JD_QUALITY_UNSCORABLE
            assert result.sync_ok is None
            assert sync_calls == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_exact_duplicate_return_does_not_call_job_sync(db_path: Path) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            body = "Duplicate body for no-sync return."
            sync_calls = 0

            async def _sync(**kwargs: Any) -> None:
                nonlocal sync_calls
                del kwargs
                sync_calls += 1

            first = await ingest_raw_text(
                body,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert first.sync_ok is True
            assert sync_calls == 1

            again = await ingest_raw_text(
                body,
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(),
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert again.outcome == "returned"
            assert again.job_id == first.job_id
            assert again.sync_ok is None
            assert sync_calls == 1  # no second sync
        finally:
            await engine.dispose()

    run_async(_body())


def test_graph_failure_after_commit_returns_neo4j_sync_failed_row_unchanged(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            from app.graph.sync_job import (
                NEO4J_REBUILD_INSTRUCTION,
                NEO4J_SYNC_FAILED,
                JobSyncError,
            )

            async def _fail(**kwargs: Any) -> None:
                del kwargs
                raise JobSyncError("simulated graph failure")

            result = await ingest_raw_text(
                "Scorable JD whose graph projection fails.",
                invoker=FakeJdInvoker([_full_extracted()]),
                normalizer=_normalizer(),
                embedding_client=FakeEmbeddingClient(vector=_vector(0.05)),
                session_factory=factory,
                job_sync_fn=_fail,
            )
            assert result.outcome == "created"
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality == JOB_JD_QUALITY_FULL
            assert result.failure_code is None  # SQLite not marked failed
            assert result.sync_ok is False
            assert result.sync_code == NEO4J_SYNC_FAILED
            assert result.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION

            row = await _get_job(factory, result.job_id)
            assert row.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert row.jd_quality == JOB_JD_QUALITY_FULL
            assert row.failure_code is None
            assert row.embedding_json is not None
        finally:
            await engine.dispose()

    run_async(_body())
