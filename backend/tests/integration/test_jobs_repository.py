"""Integration tests for focused job_posts repository primitives (Plan 5 / 01C).

Uses migrated temporary SQLite (Alembic head). Covers placeholder/raw creation,
exact-hash and ID reads, legal transitions and UTC timestamps, failed-field
clearing, pure URL-placeholder deletion with durable-row protection, filters,
limit 1..50, and deterministic newest compact ordering without raw content or
embeddings.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_PROCESSING_STATUS_PROCESSING,
    JOB_PROCESSING_STATUS_RECEIVED,
    JOB_SOURCE_TYPE_TEXT,
    JOB_SOURCE_TYPE_URL,
    JobPost,
)
from app.db.session import build_async_engine
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import (
    InvalidJobTransitionError,
    JobNotFoundError,
    JobReextractConflictError,
    JobRepositoryError,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tests.support.db_migration import run_async, session_factory

# Minimal extraction shape for terminal processed writes (repo does not validate).
_EXTRACTION: dict[str, Any] = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": None,
    "seniority": None,
    "work_mode": None,
    "summary": "Build APIs",
    "responsibilities": ["Ship features"],
    "required_skills": [],
    "preferred_skills": [],
    "min_experience_years": None,
    "max_experience_years": None,
    "education_requirements": None,
    "salary_range": None,
    "evidence": [],
}


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


def _embedding(n: int = 3) -> list[float]:
    return [float(i) for i in range(n)]


# ---------------------------------------------------------------------------
# Creation + hash / ID reads
# ---------------------------------------------------------------------------


def test_create_url_placeholder_and_text_job_hash_lookup(db_path: Path) -> None:
    """URL placeholder and text job insert; exact hash and ID reads work."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                placeholder = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/jobs/1"
                )
                assert placeholder.source_type == JOB_SOURCE_TYPE_URL
                assert placeholder.source_url == "https://example.com/jobs/1"
                assert placeholder.raw_content is None
                assert placeholder.raw_content_hash is None
                assert placeholder.processing_status == JOB_PROCESSING_STATUS_RECEIVED
                assert placeholder.failure_code is None
                assert placeholder.id
                assert placeholder.created_at.tzinfo is not None
                assert placeholder.updated_at.tzinfo is not None
                await session.commit()
                ph_id = placeholder.id

            async with factory() as session:
                text_row = await jobs_repo.create_text_job(
                    session,
                    raw_content="Pasted JD body",
                    raw_content_hash="hash-text-1",
                )
                assert text_row.source_type == JOB_SOURCE_TYPE_TEXT
                assert text_row.source_url is None
                assert text_row.raw_content == "Pasted JD body"
                assert text_row.raw_content_hash == "hash-text-1"
                assert text_row.processing_status == JOB_PROCESSING_STATUS_RECEIVED
                await session.commit()
                text_id = text_row.id

            async with factory() as session:
                by_hash = await jobs_repo.get_by_raw_content_hash(
                    session, "hash-text-1"
                )
                assert by_hash is not None
                assert by_hash.id == text_id

                missing_hash = await jobs_repo.get_by_raw_content_hash(
                    session, "no-such-hash"
                )
                assert missing_hash is None

                by_id = await jobs_repo.get_by_id(session, text_id)
                assert by_id is not None
                assert by_id.raw_content_hash == "hash-text-1"

                ph = await jobs_repo.get_by_id(session, ph_id)
                assert ph is not None
                assert ph.source_url == "https://example.com/jobs/1"

                assert await jobs_repo.get_by_id(session, new_uuid()) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_create_rejects_empty_inputs(db_path: Path) -> None:
    """Creation helpers reject empty URL/content/hash strings before flush."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(JobRepositoryError, match="source_url"):
                    await jobs_repo.create_url_placeholder(session, source_url="  ")
                with pytest.raises(JobRepositoryError, match="raw_content"):
                    await jobs_repo.create_text_job(
                        session, raw_content="", raw_content_hash="h"
                    )
                with pytest.raises(JobRepositoryError, match="raw_content_hash"):
                    await jobs_repo.create_text_job(
                        session, raw_content="body", raw_content_hash=""
                    )
        finally:
            await engine.dispose()

    run_async(_body())


def test_unique_raw_content_hash_constraint(db_path: Path) -> None:
    """Second insert with the same content hash fails at the database."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await jobs_repo.create_text_job(
                    session, raw_content="same", raw_content_hash="dup-hash"
                )
                await session.commit()

            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await jobs_repo.create_text_job(
                        session, raw_content="same", raw_content_hash="dup-hash"
                    )
                    await session.commit()
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Legal transitions + failed retry clearing
# ---------------------------------------------------------------------------


def test_received_to_processing_to_processed_and_failed(db_path: Path) -> None:
    """Legal paths: received→processing→processed and received→failed."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                ok = await jobs_repo.create_text_job(
                    session, raw_content="ok body", raw_content_hash="h-ok"
                )
                fail = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/gone"
                )
                await session.commit()
                ok_id, fail_id = ok.id, fail.id
                before = ok.updated_at

            async with factory() as session:
                processing = await jobs_repo.mark_processing(session, ok_id)
                assert processing.processing_status == JOB_PROCESSING_STATUS_PROCESSING
                assert processing.updated_at.tzinfo is not None
                assert processing.updated_at >= before
                assert processing.failure_code is None

                processed = await jobs_repo.mark_processed(
                    session,
                    ok_id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(4),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=4,
                )
                assert processed.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                assert processed.jd_quality == JOB_JD_QUALITY_FULL
                assert processed.extraction_json is not None
                assert processed.embedding_model == "text-embedding-3-small"
                assert processed.embedding_dimensions == 4
                assert processed.failure_code is None
                assert processed.updated_at.tzinfo is not None
                await session.commit()

            async with factory() as session:
                failed = await jobs_repo.mark_failed(
                    session, fail_id, failure_code="URL_FETCH_TIMEOUT"
                )
                assert failed.processing_status == JOB_PROCESSING_STATUS_FAILED
                assert failed.failure_code == "URL_FETCH_TIMEOUT"
                assert failed.updated_at.tzinfo is not None
                # URL retained on fetch failure
                assert failed.source_url == "https://example.com/gone"
                assert failed.raw_content is None
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_retry_failed_clears_terminal_fields_same_row(db_path: Path) -> None:
    """failed→processing clears failure/extraction/quality/all embeddings."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                failed_src = await jobs_repo.create_text_job(
                    session,
                    raw_content="failed body 2",
                    raw_content_hash="h-failed-retry-2",
                )
                await jobs_repo.mark_processing(session, failed_src.id)
                await jobs_repo.mark_failed(
                    session, failed_src.id, failure_code="EXTRACTION_FAILED"
                )
                # Leftover extraction/quality on a failed row (no embeddings —
                # non-scorable statuses require embedding triplet SQL NULL).
                failed_src.extraction_json = {"title": "Old", "company": "X"}
                failed_src.jd_quality = JOB_JD_QUALITY_PARTIAL
                await session.flush()
                await session.commit()
                job_id = failed_src.id
                before = failed_src.updated_at

            async with factory() as session:
                retried = await jobs_repo.retry_failed_as_processing(session, job_id)
                assert retried.id == job_id
                assert retried.processing_status == JOB_PROCESSING_STATUS_PROCESSING
                assert retried.failure_code is None
                assert retried.extraction_json is None
                assert retried.jd_quality is None
                assert retried.embedding_json is None
                assert retried.embedding_model is None
                assert retried.embedding_dimensions is None
                assert retried.raw_content == "failed body 2"
                assert retried.raw_content_hash == "h-failed-retry-2"
                assert retried.updated_at.tzinfo is not None
                assert retried.updated_at >= before
                await session.commit()

            async with factory() as session:
                # SQL NULL (not JSON null) for cleared JSON columns
                raw = (
                    await session.execute(
                        text(
                            "SELECT extraction_json IS NULL, embedding_json IS NULL, "
                            "failure_code IS NULL, jd_quality IS NULL "
                            "FROM job_posts WHERE id = :id"
                        ),
                        {"id": job_id},
                    )
                ).one()
                assert raw == (1, 1, 1, 1)
        finally:
            await engine.dispose()

    run_async(_body())


def test_processed_unscorable_null_embeddings(db_path: Path) -> None:
    """Processed unscorable writes extraction/quality with all embeddings null."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session, raw_content="thin", raw_content_hash="h-thin"
                )
                await jobs_repo.mark_processing(session, row.id)
                done = await jobs_repo.mark_processed(
                    session,
                    row.id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_UNSCORABLE,
                )
                assert done.jd_quality == JOB_JD_QUALITY_UNSCORABLE
                assert done.embedding_json is None
                assert done.embedding_model is None
                assert done.embedding_dimensions is None
                await session.commit()

            async with factory() as session:
                flags = (
                    await session.execute(
                        text(
                            "SELECT embedding_json IS NULL, embedding_model IS NULL, "
                            "embedding_dimensions IS NULL FROM job_posts WHERE id = :id"
                        ),
                        {"id": row.id},
                    )
                ).one()
                assert flags == (1, 1, 1)
        finally:
            await engine.dispose()

    run_async(_body())


def test_forbidden_transitions_leave_row_unchanged(db_path: Path) -> None:
    """Illegal transitions raise and leave status/fields untouched."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session, raw_content="locked", raw_content_hash="h-locked"
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_processed(
                    session,
                    row.id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(2),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=2,
                )
                await session.commit()
                job_id = row.id
                status_before = row.processing_status
                updated_before = row.updated_at

            async with factory() as session:
                with pytest.raises(InvalidJobTransitionError):
                    await jobs_repo.mark_processing(session, job_id)
                with pytest.raises(InvalidJobTransitionError):
                    await jobs_repo.mark_failed(
                        session, job_id, failure_code="X"
                    )
                with pytest.raises(InvalidJobTransitionError):
                    await jobs_repo.retry_failed_as_processing(session, job_id)

                reloaded = await jobs_repo.get_by_id(session, job_id)
                assert reloaded is not None
                assert reloaded.processing_status == status_before
                # SQLite may drop tzinfo on reload; compare UTC instants.
                reloaded_ts = reloaded.updated_at.replace(tzinfo=UTC)
                before_ts = updated_before.replace(tzinfo=UTC)
                assert reloaded_ts == before_ts
                assert reloaded.jd_quality == JOB_JD_QUALITY_FULL
        finally:
            await engine.dispose()

    run_async(_body())


def test_mark_failed_requires_failure_code(db_path: Path) -> None:
    """Empty failure_code is rejected."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/x"
                )
                with pytest.raises(JobRepositoryError, match="failure_code"):
                    await jobs_repo.mark_failed(session, row.id, failure_code="")
                with pytest.raises(JobRepositoryError, match="failure_code"):
                    await jobs_repo.mark_failed(session, row.id, failure_code="  ")
        finally:
            await engine.dispose()

    run_async(_body())


def test_missing_job_raises_not_found(db_path: Path) -> None:
    """Mutations on unknown IDs raise JobNotFoundError."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                missing = new_uuid()
                with pytest.raises(JobNotFoundError):
                    await jobs_repo.mark_processing(session, missing)
                with pytest.raises(JobNotFoundError):
                    await jobs_repo.delete_url_placeholder(session, missing)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# URL raw content attach + pure placeholder deletion
# ---------------------------------------------------------------------------


def test_set_url_raw_content_and_delete_placeholder(db_path: Path) -> None:
    """URL placeholder accepts content; pure temporary placeholder can be deleted."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                ph = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/job"
                )
                filled = await jobs_repo.set_url_raw_content(
                    session,
                    ph.id,
                    raw_content="Fetched JD",
                    raw_content_hash="h-fetched",
                )
                assert filled.raw_content == "Fetched JD"
                assert filled.raw_content_hash == "h-fetched"
                assert filled.processing_status == JOB_PROCESSING_STATUS_RECEIVED
                assert filled.source_url == "https://example.com/job"
                await session.commit()
                filled_id = filled.id

            async with factory() as session:
                # Second attach rejected
                with pytest.raises(JobRepositoryError, match="null raw_content"):
                    await jobs_repo.set_url_raw_content(
                        session,
                        filled_id,
                        raw_content="again",
                        raw_content_hash="h2",
                    )

            async with factory() as session:
                # Delete a pure placeholder (duplicate disposition)
                temp = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/temp"
                )
                temp_id = temp.id
                await session.commit()

            async with factory() as session:
                await jobs_repo.delete_url_placeholder(session, temp_id)
                await session.commit()

            async with factory() as session:
                assert await jobs_repo.get_by_id(session, temp_id) is None
                remaining = await jobs_repo.get_by_id(session, filled_id)
                assert remaining is not None
                assert remaining.raw_content_hash == "h-fetched"
        finally:
            await engine.dispose()

    run_async(_body())


def test_delete_url_placeholder_rejects_durable_rows(db_path: Path) -> None:
    """Text, filled URL, failed, and processed rows cannot be deleted."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                text_row = await jobs_repo.create_text_job(
                    session,
                    raw_content="durable text",
                    raw_content_hash="h-durable-text",
                )
                filled = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/filled"
                )
                await jobs_repo.set_url_raw_content(
                    session,
                    filled.id,
                    raw_content="Fetched durable",
                    raw_content_hash="h-durable-url",
                )
                failed = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/failed"
                )
                await jobs_repo.mark_failed(
                    session, failed.id, failure_code="URL_FETCH_FAILED"
                )
                processed = await jobs_repo.create_text_job(
                    session,
                    raw_content="processed body",
                    raw_content_hash="h-processed",
                )
                await jobs_repo.mark_processing(session, processed.id)
                await jobs_repo.mark_processed(
                    session,
                    processed.id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(2),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=2,
                )
                await session.commit()
                text_id, filled_id, failed_id, processed_id = (
                    text_row.id,
                    filled.id,
                    failed.id,
                    processed.id,
                )

            async with factory() as session:
                with pytest.raises(JobRepositoryError, match="source_type"):
                    await jobs_repo.delete_url_placeholder(session, text_id)
                with pytest.raises(JobRepositoryError, match="null raw_content"):
                    await jobs_repo.delete_url_placeholder(session, filled_id)
                with pytest.raises(JobRepositoryError, match="processing_status"):
                    await jobs_repo.delete_url_placeholder(session, failed_id)
                with pytest.raises(JobRepositoryError, match="source_type"):
                    await jobs_repo.delete_url_placeholder(session, processed_id)
                await session.rollback()

            async with factory() as session:
                assert await jobs_repo.get_by_id(session, text_id) is not None
                assert await jobs_repo.get_by_id(session, filled_id) is not None
                assert await jobs_repo.get_by_id(session, failed_id) is not None
                assert await jobs_repo.get_by_id(session, processed_id) is not None
                text_reloaded = await jobs_repo.get_by_id(session, text_id)
                filled_reloaded = await jobs_repo.get_by_id(session, filled_id)
                failed_reloaded = await jobs_repo.get_by_id(session, failed_id)
                processed_reloaded = await jobs_repo.get_by_id(
                    session, processed_id
                )
                assert text_reloaded is not None
                assert text_reloaded.raw_content == "durable text"
                assert filled_reloaded is not None
                assert filled_reloaded.raw_content_hash == "h-durable-url"
                assert failed_reloaded is not None
                assert (
                    failed_reloaded.processing_status
                    == JOB_PROCESSING_STATUS_FAILED
                )
                assert processed_reloaded is not None
                assert (
                    processed_reloaded.processing_status
                    == JOB_PROCESSING_STATUS_PROCESSED
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_set_url_raw_content_rejects_text_jobs(db_path: Path) -> None:
    """set_url_raw_content is URL-placeholder only."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                text_row = await jobs_repo.create_text_job(
                    session, raw_content="t", raw_content_hash="h-t"
                )
                with pytest.raises(JobRepositoryError, match="source_type"):
                    await jobs_repo.set_url_raw_content(
                        session,
                        text_row.id,
                        raw_content="x",
                        raw_content_hash="h-x",
                    )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Compact filtered queries
# ---------------------------------------------------------------------------


def test_list_compact_filters_limit_and_newest_order(db_path: Path) -> None:
    """Filters use DB vocabulary; limit 1..50; order created_at DESC, id DESC."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                # Stagger created_at via explicit timestamps for deterministic order
                base = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
                ids: list[str] = []
                for i, (status, quality, title) in enumerate(
                    (
                        (JOB_PROCESSING_STATUS_RECEIVED, None, None),
                        (JOB_PROCESSING_STATUS_PROCESSED, JOB_JD_QUALITY_FULL, "A"),
                        (JOB_PROCESSING_STATUS_PROCESSED, JOB_JD_QUALITY_PARTIAL, "B"),
                        (JOB_PROCESSING_STATUS_FAILED, None, None),
                    )
                ):
                    if status == JOB_PROCESSING_STATUS_RECEIVED:
                        row = await jobs_repo.create_text_job(
                            session,
                            raw_content=f"body-{i}",
                            raw_content_hash=f"hash-{i}",
                        )
                    elif status == JOB_PROCESSING_STATUS_FAILED:
                        row = await jobs_repo.create_text_job(
                            session,
                            raw_content=f"body-{i}",
                            raw_content_hash=f"hash-{i}",
                        )
                        await jobs_repo.mark_failed(
                            session, row.id, failure_code="X"
                        )
                    else:
                        row = await jobs_repo.create_text_job(
                            session,
                            raw_content=f"body-{i}",
                            raw_content_hash=f"hash-{i}",
                        )
                        await jobs_repo.mark_processing(session, row.id)
                        ext = dict(_EXTRACTION)
                        ext["title"] = title
                        ext["company"] = f"Co{i}"
                        emb_kw: dict[str, Any] = {}
                        if quality in (
                            JOB_JD_QUALITY_FULL,
                            JOB_JD_QUALITY_PARTIAL,
                        ):
                            emb_kw = {
                                "embedding_json": _embedding(2),
                                "embedding_model": "text-embedding-3-small",
                                "embedding_dimensions": 2,
                            }
                        await jobs_repo.mark_processed(
                            session,
                            row.id,
                            extraction_json=ext,
                            jd_quality=quality,  # type: ignore[arg-type]
                            **emb_kw,
                        )
                    # Force deterministic created_at / id ordering input
                    ts = base + timedelta(seconds=i)
                    row.created_at = ts
                    row.updated_at = ts
                    ids.append(row.id)
                await session.flush()
                await session.commit()

            async with factory() as session:
                all_rows = await jobs_repo.list_compact(session, limit=50)
                assert len(all_rows) == 4
                # Newest first: last inserted timestamps first
                assert [r["id"] for r in all_rows] == list(reversed(ids))

                processed = await jobs_repo.list_compact(
                    session,
                    limit=50,
                    processing_status=JOB_PROCESSING_STATUS_PROCESSED,
                )
                assert len(processed) == 2
                assert all(
                    r["processing_status"] == JOB_PROCESSING_STATUS_PROCESSED
                    for r in processed
                )

                full_only = await jobs_repo.list_compact(
                    session,
                    limit=50,
                    jd_quality=JOB_JD_QUALITY_FULL,
                )
                assert len(full_only) == 1
                assert full_only[0]["title"] == "A"
                assert full_only[0]["company"] == "Co1"

                by_id = await jobs_repo.list_compact(
                    session, limit=10, job_id=ids[0]
                )
                assert len(by_id) == 1
                assert by_id[0]["id"] == ids[0]

                limited = await jobs_repo.list_compact(session, limit=2)
                assert len(limited) == 2
                assert limited[0]["id"] == ids[3]
                assert limited[1]["id"] == ids[2]

                # Compact projection hygiene
                for item in all_rows:
                    assert set(item.keys()) == {
                        "id",
                        "source_type",
                        "source_url",
                        "processing_status",
                        "jd_quality",
                        "failure_code",
                        "title",
                        "company",
                        "created_at",
                        "updated_at",
                    }
                    assert "raw_content" not in item
                    assert "raw_content_hash" not in item
                    assert "extraction_json" not in item
                    assert "embedding_json" not in item
                    assert "embedding_model" not in item
                    assert "embedding_dimensions" not in item
        finally:
            await engine.dispose()

    run_async(_body())


def test_list_compact_rejects_bad_limit_and_vocabulary(db_path: Path) -> None:
    """limit outside 1..50 and unknown status/quality vocabulary fail."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(JobRepositoryError, match="limit"):
                    await jobs_repo.list_compact(session, limit=0)
                with pytest.raises(JobRepositoryError, match="limit"):
                    await jobs_repo.list_compact(session, limit=51)
                with pytest.raises(JobRepositoryError, match="processing_status"):
                    await jobs_repo.list_compact(
                        session, limit=10, processing_status="done"
                    )
                with pytest.raises(JobRepositoryError, match="jd_quality"):
                    await jobs_repo.list_compact(
                        session, limit=10, jd_quality="great"
                    )
        finally:
            await engine.dispose()

    run_async(_body())


def test_equal_created_at_orders_by_id_desc(db_path: Path) -> None:
    """Equal timestamps use id DESC for deterministic newest order."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
            async with factory() as session:
                a = await jobs_repo.create_text_job(
                    session, raw_content="a", raw_content_hash="ha"
                )
                b = await jobs_repo.create_text_job(
                    session, raw_content="b", raw_content_hash="hb"
                )
                a.created_at = ts
                a.updated_at = ts
                b.created_at = ts
                b.updated_at = ts
                await session.flush()
                await session.commit()
                id_a, id_b = a.id, b.id

            async with factory() as session:
                rows = await jobs_repo.list_compact(session, limit=50)
                assert [r["id"] for r in rows] == sorted(
                    [id_a, id_b], reverse=True
                )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Hygiene: flush-only repository module
# ---------------------------------------------------------------------------


def test_repository_is_flush_only_without_schema_shortcuts() -> None:
    """jobs repository source has no unit-of-work finalization or schema DDL."""
    source = inspect.getsource(jobs_repo)
    assert "commit(" not in source
    assert "metadata.create_all" not in source
    assert "Base.metadata.create_all" not in source
    assert "rollback(" not in source
    banned = (
        "httpx",
        "neo4j",
        "openai",
        "trafilatura",
        "langchain",
        "ToolResult",
    )
    for needle in banned:
        assert needle not in source
    public = {
        n
        for n in dir(jobs_repo)
        if not n.startswith("_") and callable(getattr(jobs_repo, n, None))
    }
    expected = {
        "create_url_placeholder",
        "create_text_job",
        "set_url_raw_content",
        "get_by_id",
        "get_by_raw_content_hash",
        "mark_processing",
        "retry_failed_as_processing",
        "mark_failed",
        "mark_processed",
        "delete_url_placeholder",
        "list_compact",
    }
    assert expected.issubset(public)
    assert "delete" not in public


def test_row_count_helpers_use_orm_table(db_path: Path) -> None:
    """Smoke: repository inserts are visible on job_posts after commit."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                n0 = (
                    await session.execute(select(func.count()).select_from(JobPost))
                ).scalar_one()
                assert n0 == 0
                await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/z"
                )
                await session.commit()
            async with factory() as session:
                n1 = (
                    await session.execute(select(func.count()).select_from(JobPost))
                ).scalar_one()
                assert n1 == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_processing_to_failed_path(db_path: Path) -> None:
    """processing → failed is legal (extraction failure after start)."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session, raw_content="mid", raw_content_hash="h-mid"
                )
                await jobs_repo.mark_processing(session, row.id)
                failed = await jobs_repo.mark_failed(
                    session, row.id, failure_code="PROVIDER_TIMEOUT"
                )
                assert failed.processing_status == JOB_PROCESSING_STATUS_FAILED
                assert failed.failure_code == "PROVIDER_TIMEOUT"
                assert failed.raw_content == "mid"
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_utc_now_used_for_transition_timestamps(db_path: Path) -> None:
    """Transition timestamps are timezone-aware UTC."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session, raw_content="ts", raw_content_hash="h-ts"
                )
                before = utc_now()
                processing = await jobs_repo.mark_processing(session, row.id)
                after = utc_now()
                assert processing.updated_at.tzinfo == UTC or (
                    processing.updated_at.tzinfo is not None
                    and processing.updated_at.utcoffset() == timedelta(0)
                )
                assert before <= processing.updated_at <= after + timedelta(seconds=1)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Plan 15 revision-checked extraction replacement (CAS)
# ---------------------------------------------------------------------------


_EXTRACTION_V2: dict[str, Any] = {
    **_EXTRACTION,
    "title": "Senior Backend Engineer",
    "summary": "Own platform APIs",
    "responsibilities": ["Ship features", "Own on-call"],
}


def test_replace_extraction_if_unchanged_success_and_field_ownership(
    db_path: Path,
) -> None:
    """CAS replaces only approved fields and advances revision strictly."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session,
                    raw_content="retained JD body",
                    raw_content_hash="h-cas-ok",
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_processed(
                    session,
                    row.id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(3),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=3,
                )
                await session.commit()
                job_id = row.id
                created_at = row.created_at
                captured = row.updated_at
                source_type = row.source_type
                raw = row.raw_content
                raw_hash = row.raw_content_hash

            async with factory() as session:
                replaced = await jobs_repo.replace_extraction_if_unchanged(
                    session,
                    job_id,
                    expected_updated_at=captured,
                    extraction_json=dict(_EXTRACTION_V2),
                    jd_quality=JOB_JD_QUALITY_PARTIAL,
                    embedding_json=_embedding(5),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=5,
                )
                await session.commit()
                assert replaced.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                assert replaced.jd_quality == JOB_JD_QUALITY_PARTIAL
                assert replaced.failure_code is None
                assert replaced.extraction_json is not None
                assert replaced.extraction_json["title"] == "Senior Backend Engineer"
                assert replaced.embedding_dimensions == 5
                assert replaced.embedding_model == "text-embedding-3-small"
                assert replaced.raw_content == raw
                assert replaced.raw_content_hash == raw_hash
                assert replaced.source_type == source_type
                created_ts = (
                    created_at
                    if created_at.tzinfo is not None
                    else created_at.replace(tzinfo=UTC)
                )
                replaced_created = (
                    replaced.created_at
                    if replaced.created_at.tzinfo is not None
                    else replaced.created_at.replace(tzinfo=UTC)
                )
                assert replaced_created == created_ts
                reloaded_ts = (
                    replaced.updated_at
                    if replaced.updated_at.tzinfo is not None
                    else replaced.updated_at.replace(tzinfo=UTC)
                )
                cap_ts = (
                    captured
                    if captured.tzinfo is not None
                    else captured.replace(tzinfo=UTC)
                )
                assert reloaded_ts > cap_ts
        finally:
            await engine.dispose()

    run_async(_body())


def test_replace_extraction_conflict_on_stale_revision(db_path: Path) -> None:
    """Zero-row CAS when captured updated_at no longer matches leaves row intact."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session,
                    raw_content="conflict body",
                    raw_content_hash="h-cas-conflict",
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_processed(
                    session,
                    row.id,
                    extraction_json=dict(_EXTRACTION),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(2),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=2,
                )
                await session.commit()
                job_id = row.id
                stale_capture = row.updated_at
                title_before = row.extraction_json["title"]  # type: ignore[index]

            # Concurrent writer advances revision.
            async with factory() as session:
                concurrent = await jobs_repo.get_by_id(session, job_id)
                assert concurrent is not None
                concurrent.updated_at = utc_now() + timedelta(seconds=5)
                await session.flush()
                await session.commit()
                concurrent_ts = concurrent.updated_at
                concurrent_title = concurrent.extraction_json["title"]  # type: ignore[index]

            async with factory() as session:
                with pytest.raises(JobReextractConflictError):
                    await jobs_repo.replace_extraction_if_unchanged(
                        session,
                        job_id,
                        expected_updated_at=stale_capture,
                        extraction_json=dict(_EXTRACTION_V2),
                        jd_quality=JOB_JD_QUALITY_PARTIAL,
                        embedding_json=_embedding(9),
                        embedding_model="text-embedding-3-small",
                        embedding_dimensions=9,
                    )
                await session.rollback()

            async with factory() as session:
                final = await jobs_repo.get_by_id(session, job_id)
                assert final is not None
                assert final.extraction_json is not None
                assert final.extraction_json["title"] == concurrent_title
                assert final.extraction_json["title"] == title_before
                assert final.embedding_dimensions == 2
                final_ts = (
                    final.updated_at
                    if final.updated_at.tzinfo is not None
                    else final.updated_at.replace(tzinfo=UTC)
                )
                conc_ts = (
                    concurrent_ts
                    if concurrent_ts.tzinfo is not None
                    else concurrent_ts.replace(tzinfo=UTC)
                )
                assert final_ts == conc_ts
        finally:
            await engine.dispose()

    run_async(_body())


def test_replace_extraction_repairs_failed_row_and_rejects_unscorable(
    db_path: Path,
) -> None:
    """Failed retained rows can be replaced; unscorable quality is rejected."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session,
                    raw_content="failed retained",
                    raw_content_hash="h-cas-failed",
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_failed(
                    session, row.id, failure_code="PROVIDER_ERROR"
                )
                await session.commit()
                job_id = row.id
                captured = row.updated_at
                raw_hash = row.raw_content_hash

            async with factory() as session:
                with pytest.raises(JobRepositoryError, match="full|partial"):
                    await jobs_repo.replace_extraction_if_unchanged(
                        session,
                        job_id,
                        expected_updated_at=captured,
                        extraction_json=dict(_EXTRACTION),
                        jd_quality=JOB_JD_QUALITY_UNSCORABLE,
                        embedding_json=_embedding(2),
                        embedding_model="text-embedding-3-small",
                        embedding_dimensions=2,
                    )

                repaired = await jobs_repo.replace_extraction_if_unchanged(
                    session,
                    job_id,
                    expected_updated_at=captured,
                    extraction_json=dict(_EXTRACTION_V2),
                    jd_quality=JOB_JD_QUALITY_FULL,
                    embedding_json=_embedding(4),
                    embedding_model="text-embedding-3-small",
                    embedding_dimensions=4,
                )
                await session.commit()
                assert repaired.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                assert repaired.failure_code is None
                assert repaired.jd_quality == JOB_JD_QUALITY_FULL
                assert repaired.raw_content_hash == raw_hash
                assert repaired.raw_content == "failed retained"
        finally:
            await engine.dispose()

    run_async(_body())
