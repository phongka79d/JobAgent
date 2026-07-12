"""JDIngestionService: persistence-first order, duplicates, eligibility, sanitization."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, ProcessingStatus, RecordStatus
from app.db.models.jobs import JobPost
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.graph_outbox import GraphOutboxRepository
from app.schemas.job_post import JobPostExtraction
from app.schemas.job_tools import DuplicateOutcome, ProcessingResult, SaveJobResult
from app.services.jd_extraction import JobExtractionResult
from app.services.jd_ingestion import (
    JOB_UPSERT_OPERATION,
    JdIngestionError,
    JDIngestionService,
)
from app.services.jd_quality import apply_jd_quality
from app.services.jd_source import AcquiredJd, JdSourceType, hash_canonical_text
from app.services.shopaikey_chat import ShopAIKeyChatError, ShopAIKeyErrorCode
from app.services.skill_normalization import empty_skill_seed_catalog
from sqlalchemy import func, select


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "jd_ingestion.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _skill(
    *,
    key: str = "python",
    evidence: str = "Required: Python",
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.title(),
            "aliases": [],
            "category": None,
            "status": "provisional",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _extraction_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs and data services for the platform.",
        "responsibilities": ["Design REST APIs", "Own production services"],
        "required_skills": [_skill()],
        "preferred_skills": [
            _skill(key="kubernetes", evidence="Preferred: Kubernetes", confidence=0.7)
        ],
        "seniority": "senior",
        "min_experience_years": 5.0,
        "max_experience_years": 10.0,
        "location": "Berlin, DE",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "education_requirements": ["BS Computer Science"],
        "language_requirements": ["English"],
        "salary_text": "EUR 80k-100k",
        "job_family": "software_engineering",
        "extraction_confidence": 0.85,
        "jd_quality": "partial",
    }
    data.update(overrides)
    return data


def _extraction_result(**overrides: Any) -> JobExtractionResult:
    extraction = JobPostExtraction.model_validate(_extraction_payload(**overrides))
    with_quality, assessment = apply_jd_quality(extraction)
    return JobExtractionResult(extraction=with_quality, quality=assessment)


def _unscorable_result(**overrides: Any) -> JobExtractionResult:
    data = _extraction_payload(
        title=None,
        summary="",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        employment_type="unknown",
        education_requirements=[],
        language_requirements=[],
        job_family=None,
        extraction_confidence=0.2,
        jd_quality="unscorable",
    )
    data.update(overrides)
    extraction = JobPostExtraction.model_validate(data)
    with_quality, assessment = apply_jd_quality(extraction)
    return JobExtractionResult(extraction=with_quality, quality=assessment)


def _acquire_for(text: str, *, source_url: str | None = None) -> AcquiredJd:
    canonical = text  # tests pass already-canonical snippets
    return AcquiredJd(
        source_type=JdSourceType.RAW_TEXT if source_url is None else JdSourceType.URL,
        canonical_text=canonical,
        content_hash=hash_canonical_text(canonical),
        source_url=source_url,
    )


class CallTracker:
    """Injected collaborators that record call order and counts."""

    def __init__(
        self,
        *,
        extraction: JobExtractionResult | Exception | None = None,
        texts: dict[str, JobExtractionResult | Exception] | None = None,
    ) -> None:
        self.extract_calls = 0
        self.acquire_calls = 0
        self.call_log: list[str] = []
        self._extraction = extraction
        self._texts = texts or {}
        self.received_before_extract: list[tuple[UUID, str]] = []
        self._db: DatabaseSessionManager | None = None

    def bind_db(self, db: DatabaseSessionManager) -> None:
        self._db = db

    def acquire(self, *, url: str | None = None, raw_text: str | None = None) -> AcquiredJd:
        self.acquire_calls += 1
        self.call_log.append("acquire")
        if raw_text is not None:
            return _acquire_for(raw_text)
        if url is not None:
            return _acquire_for(f"JD from {url}", source_url=url)
        raise JdIngestionError("INVALID_INPUT")

    def extract(self, *, canonical_jd_text: str) -> JobExtractionResult:
        self.extract_calls += 1
        self.call_log.append("extract")
        # Capture durable state before LLM work (async assertion done via runner).
        if self._db is not None:
            # Synchronous peek via stored pre-check from service is not available;
            # tests assert retention after failure / call order via logs + ORM.
            pass
        if canonical_jd_text in self._texts:
            outcome = self._texts[canonical_jd_text]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if isinstance(self._extraction, Exception):
            raise self._extraction
        if self._extraction is None:
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.TIMEOUT)
        return self._extraction


def _service(
    db: DatabaseSessionManager,
    tracker: CallTracker,
) -> JDIngestionService:
    tracker.bind_db(db)
    return JDIngestionService(
        db,
        skill_catalog=empty_skill_seed_catalog(),
        acquire_fn=tracker.acquire,
        extract_fn=tracker.extract,
        embedding_model=ALLOWED_EMBEDDING_MODEL,
        embedding_dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
    )


async def _job_count(db: DatabaseSessionManager) -> int:
    async with db.session_scope() as session:
        result = await session.execute(select(func.count()).select_from(JobPost))
        return int(result.scalar_one())


async def _outbox_count(
    db: DatabaseSessionManager,
    *,
    job_id: UUID | None = None,
) -> int:
    async with db.session_scope() as session:
        stmt = select(func.count()).select_from(GraphSyncOutbox).where(
            GraphSyncOutbox.operation == JOB_UPSERT_OPERATION
        )
        if job_id is not None:
            stmt = stmt.where(GraphSyncOutbox.entity_id == str(job_id))
        result = await session.execute(stmt)
        return int(result.scalar_one())


async def _orm_job(db: DatabaseSessionManager, job_id: UUID) -> JobPost:
    async with db.session_scope() as session:
        row = await session.get(JobPost, job_id)
        assert row is not None
        # Detach fields for use outside session
        session.expunge(row)
        return row


def _assert_result_sanitized(result: SaveJobResult) -> None:
    dumped = result.model_dump(mode="json")
    text = str(dumped).lower()
    for banned in (
        "api_key",
        "authorization",
        "bearer ",
        "raw_content",
        "document_text",
        "shopaikey",
        "password",
    ):
        assert banned not in text
    assert "raw_content" not in dumped
    assert "raw_content_hash" not in dumped


# ---------------------------------------------------------------------------
# Novel path: commit before LLM + success + outbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_novel_raw_commits_before_extract_and_enqueues_outbox(
    tmp_path: Path,
) -> None:
    jd_text = (
        "Backend Engineer at Acme Corp\n"
        "Location: Berlin, DE\n"
        "Summary: Build APIs and data services for the platform.\n"
        "Responsibilities: Design REST APIs\n"
        "Required: Python\n"
        "Preferred: Kubernetes\n"
    )
    tracker = CallTracker(extraction=_extraction_result())
    extract_saw_received = {"ok": False}

    async with temporary_db(tmp_path) as db:

        async def extract_with_db_check(
            *, canonical_jd_text: str
        ) -> JobExtractionResult:
            tracker.extract_calls += 1
            tracker.call_log.append("extract")
            content_hash = hash_canonical_text(canonical_jd_text)
            async with db.session_scope() as session:
                row = (
                    await session.execute(
                        select(JobPost).where(JobPost.raw_content_hash == content_hash)
                    )
                ).scalar_one()
                assert row.processing_status in {
                    ProcessingStatus.RECEIVED.value,
                    ProcessingStatus.PROCESSING.value,
                }
                assert row.raw_content == canonical_jd_text
                extract_saw_received["ok"] = True
            assert isinstance(tracker._extraction, JobExtractionResult)
            return tracker._extraction

        service = JDIngestionService(
            db,
            skill_catalog=empty_skill_seed_catalog(),
            acquire_fn=tracker.acquire,
            extract_fn=extract_with_db_check,
        )
        result = await service.save_job(raw_text=jd_text)

        assert extract_saw_received["ok"] is True
        assert tracker.call_log[0] == "acquire"
        assert "extract" in tracker.call_log
        assert result.processing_result == ProcessingResult.PROCESSED
        assert result.processing_status == ProcessingStatus.PROCESSED.value
        assert result.record_status == RecordStatus.ACTIVE.value
        assert result.duplicate_outcome == DuplicateOutcome.NONE
        assert result.jd_quality in {"full", "partial"}
        assert result.graph_sync_status == GraphSyncStatus.PENDING.value
        assert await _outbox_count(db, job_id=result.job_id) == 1

        async with db.session_scope() as session:
            outbox = await GraphOutboxRepository(session).get_by_identity(
                JOB_UPSERT_OPERATION,
                str(result.job_id),
            )
            assert outbox is not None
            assert outbox.payload == {"job_id": str(result.job_id)}
            assert "raw" not in str(outbox.payload).lower()
            assert "content" not in outbox.payload

            orm = await session.get(JobPost, result.job_id)
            assert orm is not None
            assert orm.embedding_model == ALLOWED_EMBEDDING_MODEL
            assert orm.embedding_dimensions == ALLOWED_EMBEDDING_DIMENSIONS

        _assert_result_sanitized(result)


# ---------------------------------------------------------------------------
# Failure retention after received commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ShopAIKeyChatError(ShopAIKeyErrorCode.TIMEOUT),
        ShopAIKeyChatError(ShopAIKeyErrorCode.RATE_LIMIT),
        ShopAIKeyChatError(ShopAIKeyErrorCode.SCHEMA_INVALID),
    ],
)
async def test_provider_failure_retains_raw_after_received_commit(
    tmp_path: Path,
    failure: ShopAIKeyChatError,
) -> None:
    jd_text = "Unique JD body for failure retention path number one."
    tracker = CallTracker(extraction=failure)

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        result = await service.save_job(raw_text=jd_text)

        assert result.processing_result == ProcessingResult.FAILED
        assert result.processing_status == ProcessingStatus.FAILED.value
        assert result.error_code is not None
        assert result.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        assert await _outbox_count(db) == 0
        assert await _job_count(db) == 1

        orm = await _orm_job(db, result.job_id)
        assert orm.raw_content == jd_text
        assert orm.raw_content_hash == hash_canonical_text(jd_text)
        assert orm.error_code is not None
        assert orm.error_code.startswith("JD_")
        assert "shopaikey" not in orm.error_code.lower()
        assert result.error_code == orm.error_code
        _assert_result_sanitized(result)


# ---------------------------------------------------------------------------
# Exact duplicate: zero new work even with force_new
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_duplicate_skips_extract_embedding_outbox_even_with_force_new(
    tmp_path: Path,
) -> None:
    jd_text = "Exact same canonical content for duplicate policy tests."
    tracker = CallTracker(extraction=_extraction_result())

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        first = await service.save_job(raw_text=jd_text)
        assert first.processing_result == ProcessingResult.PROCESSED
        first_extracts = tracker.extract_calls
        first_jobs = await _job_count(db)
        first_outbox = await _outbox_count(db)

        second = await service.save_job(
            raw_text=jd_text,
            force_new_authorized=True,
        )
        assert second.job_id == first.job_id
        assert second.processing_result == ProcessingResult.EXACT_DUPLICATE
        assert second.duplicate_outcome == DuplicateOutcome.EXACT
        assert tracker.extract_calls == first_extracts
        assert await _job_count(db) == first_jobs
        assert await _outbox_count(db) == first_outbox
        _assert_result_sanitized(second)


# ---------------------------------------------------------------------------
# Normalized duplicate default ignore vs authorized force_new
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalized_duplicate_ignored_by_default(tmp_path: Path) -> None:
    text_a = "JD content version A with unique body about APIs."
    text_b = "JD content version B with different body about services."
    # Same company/title/location in extraction for both.
    shared = _extraction_result()
    tracker = CallTracker(
        texts={
            text_a: shared,
            text_b: _extraction_result(),  # same identity fields
        }
    )

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        first = await service.save_job(raw_text=text_a)
        assert first.record_status == RecordStatus.ACTIVE.value
        assert first.graph_sync_status == GraphSyncStatus.PENDING.value

        second = await service.save_job(raw_text=text_b)
        assert second.job_id != first.job_id
        assert second.processing_result == ProcessingResult.PROCESSED
        assert second.record_status == RecordStatus.IGNORED_DUPLICATE.value
        assert second.duplicate_outcome == DuplicateOutcome.IGNORED_NORMALIZED
        assert second.duplicate_of_job_id == first.job_id
        assert second.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        assert await _outbox_count(db, job_id=second.job_id) == 0
        assert await _outbox_count(db, job_id=first.job_id) == 1

        # Earlier canonical row unchanged
        first_orm = await _orm_job(db, first.job_id)
        assert first_orm.record_status == RecordStatus.ACTIVE.value
        assert first_orm.processing_status == ProcessingStatus.PROCESSED.value

        second_orm = await _orm_job(db, second.job_id)
        assert second_orm.embedding_model is None
        assert second_orm.embedding_dimensions is None
        _assert_result_sanitized(second)


@pytest.mark.asyncio
async def test_authorized_force_new_creates_active_separate_record(
    tmp_path: Path,
) -> None:
    text_a = "Canonical position posting body alpha unique."
    text_b = "Distinct position posting body beta unique."
    tracker = CallTracker(
        texts={
            text_a: _extraction_result(),
            text_b: _extraction_result(),
        }
    )

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        first = await service.save_job(raw_text=text_a)
        second = await service.save_job(
            raw_text=text_b,
            force_new_authorized=True,
        )
        assert second.job_id != first.job_id
        assert second.record_status == RecordStatus.ACTIVE.value
        assert second.duplicate_outcome == DuplicateOutcome.FORCE_NEW
        assert second.duplicate_of_job_id is None
        assert second.graph_sync_status == GraphSyncStatus.PENDING.value
        assert await _outbox_count(db, job_id=second.job_id) == 1

        first_orm = await _orm_job(db, first.job_id)
        assert first_orm.record_status == RecordStatus.ACTIVE.value
        assert first_orm.id == first.job_id
        _assert_result_sanitized(second)


# ---------------------------------------------------------------------------
# Unscorable: no embedding identity / outbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unscorable_active_skips_embedding_and_outbox(tmp_path: Path) -> None:
    jd_text = "Sparse JD that cannot support scoring signals."
    tracker = CallTracker(extraction=_unscorable_result())

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        result = await service.save_job(raw_text=jd_text)
        assert result.processing_result == ProcessingResult.PROCESSED
        assert result.jd_quality == "unscorable"
        assert result.record_status == RecordStatus.ACTIVE.value
        assert result.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
        assert await _outbox_count(db) == 0
        orm = await _orm_job(db, result.job_id)
        assert orm.embedding_model is None
        assert orm.embedding_dimensions is None


# ---------------------------------------------------------------------------
# Idempotency of exact path and outbox identifier payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeated_exact_save_is_idempotent(tmp_path: Path) -> None:
    jd_text = "Idempotent save content for three repeated calls."
    tracker = CallTracker(extraction=_extraction_result())

    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        r1 = await service.save_job(raw_text=jd_text)
        r2 = await service.save_job(raw_text=jd_text)
        r3 = await service.save_job(raw_text=jd_text)
        assert r1.job_id == r2.job_id == r3.job_id
        assert tracker.extract_calls == 1
        assert await _job_count(db) == 1
        assert await _outbox_count(db) == 1


# ---------------------------------------------------------------------------
# Acquisition failure creates no row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_input_creates_no_job(tmp_path: Path) -> None:
    def bad_acquire(**_: object) -> AcquiredJd:
        raise JdIngestionError("INVALID_INPUT")

    async with temporary_db(tmp_path) as db:
        service = JDIngestionService(
            db,
            skill_catalog=empty_skill_seed_catalog(),
            acquire_fn=bad_acquire,
            extract_fn=lambda **_: _extraction_result(),
        )
        with pytest.raises(JdIngestionError) as exc_info:
            await service.save_job(raw_text="x")
        assert exc_info.value.code == "INVALID_INPUT"
        assert await _job_count(db) == 0


@pytest.mark.asyncio
async def test_force_new_must_be_boolean(tmp_path: Path) -> None:
    tracker = CallTracker(extraction=_extraction_result())
    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        with pytest.raises(JdIngestionError) as exc_info:
            await service.save_job(raw_text="body", force_new_authorized="yes")  # type: ignore[arg-type]
        assert exc_info.value.code == "INVALID_FORCE_NEW"
        assert await _job_count(db) == 0


# ---------------------------------------------------------------------------
# Result schema bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_is_strict_save_job_result(tmp_path: Path) -> None:
    tracker = CallTracker(extraction=_extraction_result())
    async with temporary_db(tmp_path) as db:
        service = _service(db, tracker)
        result = await service.save_job(raw_text="Strict schema result body content.")
        assert isinstance(result, SaveJobResult)
        # Round-trip through schema forbids extras
        again = SaveJobResult.model_validate(result.model_dump(mode="json"))
        assert again.job_id == result.job_id
        assert again.display.title == "Backend Engineer"
        assert again.display.company == "Acme Corp"
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SaveJobResult.model_validate(
                {**result.model_dump(mode="json"), "raw_content": "leak"}
            )
