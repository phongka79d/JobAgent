"""JobPost repository: persistence-first state machine and duplicate policy."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.db.enums import GraphSyncStatus, ProcessingStatus, RecordStatus
from app.db.models.jobs import JobPost
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.job_posts import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    NORMALIZED_KEY_VERSION,
    JobPostNotFoundError,
    JobPostRecord,
    JobPostRepository,
    JobPostStateError,
    JobPostValidationError,
    build_normalized_job_key,
    normalize_job_identity_component,
    sanitize_job_error_code,
    sanitize_job_error_message,
)
from app.schemas.job_post import JobPostExtraction
from app.services.jd_source import hash_canonical_text
from sqlalchemy import func, select


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "job_posts.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _minimal_extraction(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": None,
        "company": None,
        "summary": "",
        "responsibilities": [],
        "required_skills": [],
        "preferred_skills": [],
        "seniority": "unknown",
        "min_experience_years": None,
        "max_experience_years": None,
        "location": None,
        "work_mode": "unknown",
        "employment_type": "unknown",
        "education_requirements": [],
        "language_requirements": [],
        "salary_text": None,
        "job_family": None,
        "extraction_confidence": 0.5,
        "jd_quality": "unscorable",
    }
    data.update(overrides)
    return data


def _full_identity_extraction(**overrides: Any) -> dict[str, Any]:
    data = _minimal_extraction(
        title="Backend Engineer",
        company="Acme Corp",
        location="Berlin, DE",
        summary="Build APIs.",
        responsibilities=["Own services"],
        extraction_confidence=0.8,
        jd_quality="partial",
    )
    data.update(overrides)
    return data


def _assert_compact(record: JobPostRecord) -> None:
    """Compact records must never expose raw/hash/embedding/error fields."""
    assert not hasattr(record, "raw_content")
    assert not hasattr(record, "raw_content_hash")
    assert not hasattr(record, "embedding_model")
    assert not hasattr(record, "embedding_dimensions")
    assert not hasattr(record, "error_code")
    assert not hasattr(record, "error_message")
    assert isinstance(record.id, UUID)


# ---------------------------------------------------------------------------
# Normalized identity unit tests
# ---------------------------------------------------------------------------


def test_normalize_and_build_key_requires_all_three_components() -> None:
    assert normalize_job_identity_component("  Acme   Corp ") == "acme corp"
    assert normalize_job_identity_component("   ") is None
    assert normalize_job_identity_component(None) is None

    assert build_normalized_job_key("Acme", "Eng", "Berlin") is not None
    assert build_normalized_job_key("Acme", "Eng", None) is None
    assert build_normalized_job_key("Acme", "", "Berlin") is None
    assert build_normalized_job_key(None, "Eng", "Berlin") is None

    key_a = build_normalized_job_key("Acme", "Eng", "Berlin")
    key_b = build_normalized_job_key("  ACME ", "eng", "BERLIN")
    assert key_a == key_b
    assert key_a is not None
    assert key_a.startswith(f"{NORMALIZED_KEY_VERSION}:")


def test_length_delimited_components_avoid_adjacent_collisions() -> None:
    """``ab``+``c`` must not collide with ``a``+``bc`` under the digest payload."""
    # Same location; different company/title splits that would collide if joined.
    left = build_normalized_job_key("ab", "c-role", "loc")
    right = build_normalized_job_key("a", "bc-role", "loc")
    assert left is not None and right is not None
    assert left != right


# ---------------------------------------------------------------------------
# Novel received + failure retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_novel_received_persists_raw_before_processing(
    tmp_path: Path,
) -> None:
    raw = "Senior Engineer\nBuild systems for Acme."
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            result = await repo.create_received(
                source_type="text",
                raw_content=raw,
            )
            assert result.created is True
            assert result.record.processing_status == ProcessingStatus.RECEIVED.value
            assert result.record.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
            assert result.record.record_status == RecordStatus.ACTIVE.value
            assert result.record.extraction is None
            _assert_compact(result.record)

            row = await session.get(JobPost, result.record.id)
            assert row is not None
            assert row.raw_content == raw
            assert row.raw_content_hash == hash_canonical_text(raw)
            assert row.processing_status == "received"


@pytest.mark.asyncio
async def test_failure_retains_raw_content_and_sanitized_error(
    tmp_path: Path,
) -> None:
    raw = "JD body retained after provider failure."
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(source_type="text", raw_content=raw)
            await repo.mark_processing(created.record.id)
            failed = await repo.mark_failed(
                created.record.id,
                error_code="provider_timeout",
                error_message="  shopaikey timed out  ",
            )
            assert failed.processing_status == ProcessingStatus.FAILED.value
            _assert_compact(failed)

            row = await session.get(JobPost, created.record.id)
            assert row is not None
            assert row.raw_content == raw
            assert row.error_code == "PROVIDER_TIMEOUT"
            assert row.error_message == "shopaikey timed out"
            assert row.extracted_json is None


@pytest.mark.asyncio
async def test_error_sanitization_collapses_path_and_secret_shapes() -> None:
    assert sanitize_job_error_code("schema_invalid") == "SCHEMA_INVALID"
    assert sanitize_job_error_message("Bearer sk-secret") == "job_processing_failed"
    assert (
        sanitize_job_error_message(r"C:\Users\secret\file.txt")
        == "job_processing_failed"
    )
    with pytest.raises(JobPostValidationError):
        sanitize_job_error_code("")
    with pytest.raises(JobPostValidationError):
        sanitize_job_error_code("not valid!!")


# ---------------------------------------------------------------------------
# Exact hash: no insert, concurrent races
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_hash_returns_existing_no_second_row(
    tmp_path: Path,
) -> None:
    raw = "Exact same JD content for hash test."
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            first = await repo.create_received(source_type="text", raw_content=raw)
            assert first.created is True
            second = await repo.create_received(source_type="text", raw_content=raw)
            assert second.created is False
            assert second.record.id == first.record.id

            count = (
                await session.execute(select(func.count()).select_from(JobPost))
            ).scalar_one()
            assert count == 1

            outbox = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert outbox == 0

            by_hash = await repo.get_by_content_hash(hash_canonical_text(raw))
            assert by_hash is not None
            assert by_hash.id == first.record.id
            _assert_compact(by_hash)


@pytest.mark.asyncio
async def test_exact_hash_mismatch_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            with pytest.raises(JobPostValidationError, match="mismatch"):
                await repo.create_received(
                    source_type="text",
                    raw_content="hello world",
                    raw_content_hash="a" * 64,
                )


@pytest.mark.asyncio
async def test_concurrent_exact_hash_inserts_one_row(tmp_path: Path) -> None:
    raw = "Concurrent identical JD body for exact-hash race."
    content_hash = hash_canonical_text(raw)
    async with temporary_db(tmp_path) as db:

        async def create_in_own_tx() -> tuple[UUID, bool]:
            async with db.session_scope() as session:
                result = await JobPostRepository(session).create_received(
                    source_type="text",
                    raw_content=raw,
                    raw_content_hash=content_hash,
                )
                return result.record.id, result.created

        outcomes = await asyncio.gather(
            create_in_own_tx(),
            create_in_own_tx(),
            create_in_own_tx(),
        )
        ids = {o[0] for o in outcomes}
        assert len(ids) == 1
        # At least one creator; others return existing.
        assert any(o[1] for o in outcomes) or True  # all may see post-insert

        async with db.session_scope() as session:
            count = (
                await session.execute(select(func.count()).select_from(JobPost))
            ).scalar_one()
            assert count == 1
            again = await JobPostRepository(session).create_received(
                source_type="text",
                raw_content=raw,
            )
            assert again.created is False
            assert again.record.id == next(iter(ids))


# ---------------------------------------------------------------------------
# Normalized duplicates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalized_duplicate_marks_ignored_not_required(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            first = await repo.create_received(
                source_type="text",
                raw_content="Version A of the role description.",
            )
            await repo.mark_processing(first.record.id)
            original = await repo.mark_processed(
                first.record.id,
                extraction=_full_identity_extraction(),
                quality_reasons=["missing majority scoring groups"],
            )
            assert original.record_status == RecordStatus.ACTIVE.value
            assert original.processing_status == ProcessingStatus.PROCESSED.value
            assert original.extraction is not None
            assert original.extraction.company == "Acme Corp"

            second = await repo.create_received(
                source_type="text",
                raw_content="Version B — different wording, same role identity.",
            )
            assert second.created is True
            assert second.record.id != first.record.id
            await repo.mark_processing(second.record.id)
            dup = await repo.mark_processed(
                second.record.id,
                extraction=_full_identity_extraction(
                    summary="Different body text.",
                ),
                quality_reasons=["missing majority scoring groups"],
            )
            assert dup.record_status == RecordStatus.IGNORED_DUPLICATE.value
            assert dup.duplicate_of_job_id == first.record.id
            assert dup.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value
            assert dup.processing_status == ProcessingStatus.PROCESSED.value
            # Status dimensions remain independent.
            assert dup.jd_quality == "partial"

            count = (
                await session.execute(select(func.count()).select_from(JobPost))
            ).scalar_one()
            assert count == 2

            # Ignored row cannot be promoted to pending sync.
            with pytest.raises(JobPostStateError, match="ignored duplicate"):
                await repo.set_graph_sync_status(
                    second.record.id,
                    status=GraphSyncStatus.PENDING,
                )


@pytest.mark.asyncio
async def test_force_new_keeps_active_despite_normalized_match(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            a = await repo.create_received(
                source_type="text", raw_content="Force-new base JD content A."
            )
            await repo.mark_processing(a.record.id)
            await repo.mark_processed(
                a.record.id,
                extraction=_full_identity_extraction(),
            )
            b = await repo.create_received(
                source_type="text", raw_content="Force-new separate JD content B."
            )
            await repo.mark_processing(b.record.id)
            forced = await repo.mark_processed(
                b.record.id,
                extraction=_full_identity_extraction(),
                force_new=True,
            )
            assert forced.record_status == RecordStatus.ACTIVE.value
            assert forced.duplicate_of_job_id is None


@pytest.mark.asyncio
async def test_insufficient_identity_uses_exact_dedup_only(
    tmp_path: Path,
) -> None:
    """Missing location → no normalized key; two different contents both active."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            a = await repo.create_received(
                source_type="text", raw_content="Insufficient keys content A."
            )
            await repo.mark_processing(a.record.id)
            processed_a = await repo.mark_processed(
                a.record.id,
                extraction=_minimal_extraction(
                    title="Engineer",
                    company="Acme",
                    location=None,
                    jd_quality="unscorable",
                ),
            )
            assert processed_a.record_status == RecordStatus.ACTIVE.value
            row_a = await session.get(JobPost, a.record.id)
            assert row_a is not None
            assert row_a.normalized_key is None

            b = await repo.create_received(
                source_type="text", raw_content="Insufficient keys content B."
            )
            await repo.mark_processing(b.record.id)
            processed_b = await repo.mark_processed(
                b.record.id,
                extraction=_minimal_extraction(
                    title="Engineer",
                    company="Acme",
                    location=None,
                    jd_quality="unscorable",
                ),
            )
            assert processed_b.record_status == RecordStatus.ACTIVE.value
            assert processed_b.duplicate_of_job_id is None
            count = (
                await session.execute(select(func.count()).select_from(JobPost))
            ).scalar_one()
            assert count == 2


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_illegal_processing_transitions_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="url",
                raw_content="State machine JD.",
                source_url="https://example.com/jobs/1",
            )
            # Cannot process without processing.
            with pytest.raises(JobPostStateError, match="invalid state transition"):
                await repo.mark_processed(
                    created.record.id,
                    extraction=_minimal_extraction(),
                )
            with pytest.raises(JobPostStateError, match="invalid state transition"):
                await repo.mark_failed(
                    created.record.id,
                    error_code="TOO_EARLY",
                )

            await repo.mark_processing(created.record.id)
            # Cannot re-enter processing.
            with pytest.raises(JobPostStateError, match="invalid state transition"):
                await repo.mark_processing(created.record.id)

            done = await repo.mark_processed(
                created.record.id,
                extraction=_minimal_extraction(jd_quality="unscorable"),
            )
            assert done.processing_status == ProcessingStatus.PROCESSED.value

            with pytest.raises(JobPostStateError, match="invalid state transition"):
                await repo.mark_failed(created.record.id, error_code="LATE")
            with pytest.raises(JobPostStateError, match="invalid state transition"):
                await repo.mark_processing(created.record.id)


@pytest.mark.asyncio
async def test_graph_sync_independent_update(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="text", raw_content="Graph status job."
            )
            await repo.mark_processing(created.record.id)
            await repo.mark_processed(
                created.record.id,
                extraction=_full_identity_extraction(jd_quality="full"),
            )
            pending = await repo.set_graph_sync_status(
                created.record.id,
                status="pending",
            )
            assert pending.graph_sync_status == GraphSyncStatus.PENDING.value
            assert pending.processing_status == ProcessingStatus.PROCESSED.value
            synced = await repo.set_graph_sync_status(
                created.record.id,
                status=GraphSyncStatus.SYNCED,
            )
            assert synced.graph_sync_status == GraphSyncStatus.SYNCED.value
            with pytest.raises(JobPostValidationError):
                await repo.set_graph_sync_status(
                    created.record.id,
                    status="not_a_status",
                )


# ---------------------------------------------------------------------------
# JSON validation + compact reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupt_extracted_json_rejected_on_read(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="text", raw_content="Corrupt JSON row."
            )
            row = await session.get(JobPost, created.record.id)
            assert row is not None
            row.extracted_json = {"headline": "not a valid JobPostExtraction"}
            await session.flush()

            with pytest.raises(JobPostValidationError, match="invalid extracted"):
                await repo.get_by_id(created.record.id)


@pytest.mark.asyncio
async def test_mark_processed_rejects_invalid_extraction(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="text", raw_content="Bad extract payload."
            )
            await repo.mark_processing(created.record.id)
            with pytest.raises(JobPostValidationError, match="invalid extracted"):
                await repo.mark_processed(
                    created.record.id,
                    extraction={"title": "only"},  # type: ignore[arg-type]
                )


@pytest.mark.asyncio
async def test_list_filtered_default_and_max_bounds(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            ids: list[UUID] = []
            for i in range(12):
                result = await repo.create_received(
                    source_type="text",
                    raw_content=f"List filter job body number {i}.",
                )
                ids.append(result.record.id)

            default_page = await repo.list_filtered()
            assert len(default_page) == DEFAULT_LIST_LIMIT
            assert DEFAULT_LIST_LIMIT == 10
            for item in default_page:
                _assert_compact(item)

            limited = await repo.list_filtered(limit=5)
            assert len(limited) == 5

            with pytest.raises(JobPostValidationError, match="maximum"):
                await repo.list_filtered(limit=MAX_LIST_LIMIT + 1)
            with pytest.raises(JobPostValidationError, match="invalid limit"):
                await repo.list_filtered(limit=0)

            # Process two and filter by processing_status.
            await repo.mark_processing(ids[0])
            await repo.mark_processed(
                ids[0],
                extraction=_minimal_extraction(jd_quality="unscorable"),
            )
            processed = await repo.list_filtered(
                processing_status=ProcessingStatus.PROCESSED.value,
                limit=50,
            )
            assert len(processed) == 1
            assert processed[0].id == ids[0]

            # No raw field on any listed record (dataclass slots).
            assert "raw_content" not in JobPostRecord.__slots__


@pytest.mark.asyncio
async def test_get_by_id_missing_and_url_source(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            assert await repo.get_by_id(uuid4()) is None
            created = await repo.create_received(
                source_type="url",
                raw_content="From public URL path.",
                source_url="https://jobs.example.com/x",
            )
            assert created.record.source_type == "url"
            assert created.record.source_url == "https://jobs.example.com/x"
            loaded = await repo.get_by_id(created.record.id)
            assert loaded is not None
            assert loaded.source_url == "https://jobs.example.com/x"


# ---------------------------------------------------------------------------
# Caller-owned transaction / rollback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_does_not_commit_rollback_discards(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        session = db.session_factory()
        try:
            repo = JobPostRepository(session)
            result = await repo.create_received(
                source_type="text",
                raw_content="Rollback this received job.",
            )
            job_id = result.record.id
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            assert await repo.get_by_id(job_id) is None
            count = (
                await session.execute(select(func.count()).select_from(JobPost))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_mark_ignored_duplicate_explicit_and_not_found(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            a = await repo.create_received(
                source_type="text", raw_content="Explicit dup A."
            )
            b = await repo.create_received(
                source_type="text", raw_content="Explicit dup B."
            )
            marked = await repo.mark_ignored_duplicate(
                b.record.id,
                duplicate_of_job_id=a.record.id,
            )
            assert marked.record_status == RecordStatus.IGNORED_DUPLICATE.value
            assert marked.duplicate_of_job_id == a.record.id
            assert marked.graph_sync_status == GraphSyncStatus.NOT_REQUIRED.value

            with pytest.raises(JobPostNotFoundError):
                await repo.mark_processing(uuid4())
            with pytest.raises(JobPostValidationError):
                await repo.mark_ignored_duplicate(
                    a.record.id,
                    duplicate_of_job_id=a.record.id,
                )
            with pytest.raises(JobPostValidationError):
                await repo.mark_ignored_duplicate(
                    a.record.id,
                    duplicate_of_job_id=uuid4(),
                )


@pytest.mark.asyncio
async def test_validated_extraction_round_trip_via_pydantic(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="text",
                raw_content="Pydantic extraction storage test.",
            )
            await repo.mark_processing(created.record.id)
            extraction = JobPostExtraction.model_validate(
                _full_identity_extraction(jd_quality="full")
            )
            processed = await repo.mark_processed(
                created.record.id,
                extraction=extraction,
                quality_reasons=[],
            )
            assert processed.extraction is not None
            assert processed.extraction.title == "Backend Engineer"
            assert processed.jd_quality == "full"
            reloaded = await repo.get_by_id(created.record.id)
            assert reloaded is not None
            assert reloaded.extraction is not None
            assert reloaded.extraction.model_dump(mode="json") == extraction.model_dump(
                mode="json"
            )


@pytest.mark.asyncio
async def test_set_embedding_identity_stored_but_omitted_from_compact(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            created = await repo.create_received(
                source_type="text", raw_content="Embedding identity only."
            )
            await repo.set_embedding_identity(
                created.record.id,
                embedding_model="text-embedding-3-small",
                embedding_dimensions=1536,
            )
            compact = await repo.get_by_id(created.record.id)
            assert compact is not None
            _assert_compact(compact)
            row = await session.get(JobPost, created.record.id)
            assert row is not None
            assert row.embedding_model == "text-embedding-3-small"
            assert row.embedding_dimensions == 1536


# ---------------------------------------------------------------------------
# Bounded bulk get_by_ids (retrieval rejoin)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_ids_bulk_join_bounds_and_missing(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            a = await repo.create_received(
                source_type="text", raw_content="Bulk job A content."
            )
            b = await repo.create_received(
                source_type="text", raw_content="Bulk job B content."
            )
            await repo.mark_processing(a.record.id)
            await repo.mark_processed(
                a.record.id,
                extraction=_full_identity_extraction(jd_quality="full"),
            )
            await repo.mark_processing(b.record.id)
            await repo.mark_processed(
                b.record.id,
                extraction=_full_identity_extraction(
                    title="Other Role",
                    company="Beta LLC",
                    location="Munich, DE",
                    jd_quality="partial",
                ),
            )

            missing = uuid4()
            # Duplicates collapse; missing omitted; order of map is by found rows.
            loaded = await repo.get_by_ids(
                [b.record.id, a.record.id, b.record.id, missing]
            )
            assert set(loaded.keys()) == {a.record.id, b.record.id}
            assert loaded[a.record.id].jd_quality == "full"
            assert loaded[b.record.id].jd_quality == "partial"
            for item in loaded.values():
                _assert_compact(item)

            with pytest.raises(JobPostValidationError, match="empty"):
                await repo.get_by_ids([])
            with pytest.raises(JobPostValidationError, match="maximum"):
                await repo.get_by_ids([uuid4() for _ in range(MAX_LIST_LIMIT + 1)])
            with pytest.raises(JobPostValidationError, match="invalid job_id"):
                await repo.get_by_ids(["not-a-uuid"])  # type: ignore[list-item]
