"""Integration tests for staged same-ID Job re-extraction (Plan 15 / 02A).

Uses migrated temporary SQLite, fake invoker/embedder/graph only. Covers staged
success, unscorable preservation, pre-commit failure families, CAS conflict,
post-commit graph partial success, evaluation currentness without evaluate, and
identity/raw preservation. No network or real secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_TIMEOUT,
    EmbeddingAdapterError,
)
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.db.session import build_async_engine
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    JobSyncError,
)
from app.repositories import job_evaluations as eval_repo
from app.repositories import jobs as jobs_repo
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.jd_extraction import (
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    FAILURE_PROVIDER_ERROR,
    ExtractedJobPost,
)
from app.services.job_reextraction import (
    ERROR_JD_SOURCE_NOT_RECOVERABLE,
    ERROR_JOB_NOT_FOUND,
    ERROR_JOB_NOT_SCORABLE,
    ERROR_JOB_REEXTRACT_CONFLICT,
    JobReextractError,
    reextract_job,
)
from app.services.skill_normalization import SkillNormalizer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.structured_output import FakeJdInvoker
from tests.support.db_migration import run_async, session_factory

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"

_TS = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
_ATT_ID = "11111111-2222-4333-8444-555555555555"

_GROUNDED_CORE: str = (
    "Title: Backend Engineer\n"
    "Company: Acme\n"
    "Location: Berlin\n"
    "Responsibilities:\n"
    "- Design REST services\n"
    "- Own deployments\n"
    "Required: 3+ years Python.\n"
    "Preferred: FastAPI\n"
)

_EXTRACTION_V1: dict[str, Any] = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Berlin",
    "seniority": "mid",
    "work_mode": "hybrid",
    "summary": "Build APIs",
    "responsibilities": ["Design REST services"],
    "required_skills": [],
    "preferred_skills": [],
    "min_experience_years": 3.0,
    "max_experience_years": 5.0,
    "education_requirements": None,
    "salary_range": None,
    "evidence": [],
    "extraction_confidence": 0.8,
}


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _vector(seed: float = 0.01) -> list[float]:
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


def _full_extracted(**overrides: Any) -> ExtractedJobPost:
    # Evidence/metadata must be verbatim-grounded in _GROUNDED_CORE for the guard.
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Design REST services",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python."],
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


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-reloaded naive timestamps for instant equality."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _unscorable_extracted(**overrides: Any) -> ExtractedJobPost:
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


def _factory(db_path: Path) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    engine = build_async_engine(db_path)
    return engine, session_factory(engine)


async def _seed_processed_job(
    session: AsyncSession,
    *,
    raw_content: str = _GROUNDED_CORE,
    raw_hash: str = "hash-reextract-1",
    extraction: dict[str, Any] | None = None,
    quality: str = JOB_JD_QUALITY_FULL,
) -> JobPost:
    row = await jobs_repo.create_text_job(
        session,
        raw_content=raw_content,
        raw_content_hash=raw_hash,
    )
    await jobs_repo.mark_processing(session, row.id)
    done = await jobs_repo.mark_processed(
        session,
        row.id,
        extraction_json=dict(extraction or _EXTRACTION_V1),
        jd_quality=quality,
        embedding_json=_vector(0.02),
        embedding_model="text-embedding-3-small",
        embedding_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
    )
    await session.commit()
    return done


async def _get_job(factory: async_sessionmaker[AsyncSession], job_id: str) -> JobPost:
    async with factory() as session:
        row = await jobs_repo.get_by_id(session, job_id)
        assert row is not None
        _ = (
            row.raw_content,
            row.raw_content_hash,
            row.processing_status,
            row.jd_quality,
            row.failure_code,
            row.extraction_json,
            row.embedding_json,
            row.embedding_model,
            row.embedding_dimensions,
            row.source_type,
            row.source_url,
            row.created_at,
            row.updated_at,
        )
        return row


def _match_payload(job_id: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "title": "Backend Engineer",
        "company": "Acme",
        "location": None,
        "work_mode": "remote",
        "source_url": None,
        "final_score": 0.81,
        "quality_multiplier": 1.0,
        "components": {
            "semantic_similarity": 0.81,
            "skill_score": None,
            "seniority_score": None,
            "experience_score": None,
            "location_score": None,
            "work_mode_score": None,
        },
        "effective_weights": {"semantic_similarity": 1.0},
        "matched_required_skills": [],
        "matched_preferred_skills": [],
        "related_skills": [],
        "missing_required_skills": [],
        "summary": "ok",
    }


async def _seed_attachment(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO attachments ("
            "id, file_hash, original_name, mime_type, size_bytes, page_count, "
            "storage_path, state, created_at, updated_at) VALUES "
            f"('{_ATT_ID}', 'h-att', 'cv.pdf', 'application/pdf', 10, 1, "
            f"'p/cv.pdf', 'active', '{_TS.isoformat()}', '{_TS.isoformat()}')"
        )
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_reextract_success_replaces_extraction_and_advances_revision(
    db_path: Path,
) -> None:
    """Staged full success replaces scorable fields and preserves identity/raw."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session)
                job_id = prior.id
                prior_updated = prior.updated_at
                prior_created = prior.created_at
                prior_hash = prior.raw_content_hash
                prior_raw = prior.raw_content

            invoker = FakeJdInvoker(
                [_full_extracted(extraction_confidence=0.91)]
            )
            embedder = FakeEmbeddingClient(vector=_vector(0.11))
            sync_calls: list[str] = []

            async def _sync(**kwargs: Any) -> None:
                del kwargs
                sync_calls.append(job_id)

            result = await reextract_job(
                job_id,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert result.job_id == job_id
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.jd_quality in (JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL)
            assert result.failure_code is None
            assert result.raw_content_hash == prior_hash
            assert result.sync_ok is True
            assert result.sync_code is None
            assert result.rebuild_instruction is None
            assert invoker.call_count == 1
            assert embedder.call_count == 1
            assert sync_calls == [job_id]

            row = await _get_job(factory, job_id)
            assert row.raw_content == prior_raw
            assert row.raw_content_hash == prior_hash
            assert _as_utc(row.created_at) == _as_utc(prior_created)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == "Backend Engineer"
            assert row.extraction_json["extraction_confidence"] == 0.91
            assert row.embedding_json is not None
            assert row.embedding_json[0] == pytest.approx(0.11)
            assert _as_utc(row.updated_at) > _as_utc(prior_updated)
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_unscorable_preserves_prior_without_embed_or_sync(
    db_path: Path,
) -> None:
    """Unscorable candidate never mutates Job, embeds, or syncs."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session, raw_hash="hash-unscorable")
                job_id = prior.id
                prior_title = prior.extraction_json["title"]  # type: ignore[index]
                prior_updated = prior.updated_at

            invoker = FakeJdInvoker([_unscorable_extracted()])
            embedder = FakeEmbeddingClient(vector=_vector())
            sync_calls = 0

            async def _sync(**_kwargs: Any) -> None:
                nonlocal sync_calls
                sync_calls += 1

            with pytest.raises(JobReextractError) as ei:
                await reextract_job(
                    job_id,
                    invoker=invoker,
                    normalizer=_normalizer(),
                    embedding_client=embedder,
                    session_factory=factory,
                    job_sync_fn=_sync,
                )
            assert ei.value.code == ERROR_JOB_NOT_SCORABLE
            assert embedder.call_count == 0
            assert sync_calls == 0

            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == prior_title
            assert _as_utc(row.updated_at) == _as_utc(prior_updated)
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Pre-commit failures
# ---------------------------------------------------------------------------


def test_reextract_unknown_job_and_blank_source(db_path: Path) -> None:
    """Unknown ID and blank retained source reject before provider work."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient()

            with pytest.raises(JobReextractError) as missing:
                await reextract_job(
                    "00000000-0000-4000-8000-000000000000",
                    invoker=invoker,
                    normalizer=_normalizer(),
                    embedding_client=embedder,
                    session_factory=factory,
                )
            assert missing.value.code == ERROR_JOB_NOT_FOUND
            assert invoker.call_count == 0

            async with factory() as session:
                # URL placeholder without retained content.
                ph = await jobs_repo.create_url_placeholder(
                    session, source_url="https://example.com/jobs/x"
                )
                await session.commit()
                ph_id = ph.id

            with pytest.raises(JobReextractError) as blank:
                await reextract_job(
                    ph_id,
                    invoker=invoker,
                    normalizer=_normalizer(),
                    embedding_client=embedder,
                    session_factory=factory,
                )
            assert blank.value.code == ERROR_JD_SOURCE_NOT_RECOVERABLE
            assert invoker.call_count == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_extraction_failure_preserves_prior(db_path: Path) -> None:
    """Provider/extraction failure leaves durable Job untouched."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session, raw_hash="hash-extract-fail")
                job_id = prior.id
                prior_title = prior.extraction_json["title"]  # type: ignore[index]
                prior_updated = prior.updated_at

            # Scripted provider error via exception that maps through retry.
            invoker = FakeJdInvoker([RuntimeError("provider down")])
            embedder = FakeEmbeddingClient()

            with pytest.raises(JobReextractError) as ei:
                await reextract_job(
                    job_id,
                    invoker=invoker,
                    normalizer=_normalizer(),
                    embedding_client=embedder,
                    session_factory=factory,
                )
            # Shared provider retry maps unexpected errors to PROVIDER_ERROR.
            assert ei.value.code in {
                FAILURE_PROVIDER_ERROR,
                FAILURE_INVALID_STRUCTURED_OUTPUT,
            }
            assert embedder.call_count == 0

            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == prior_title
            assert _as_utc(row.updated_at) == _as_utc(prior_updated)
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_embedding_failure_preserves_prior(db_path: Path) -> None:
    """Embedding failure after scorable extract does not mutate Job."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session, raw_hash="hash-embed-fail")
                job_id = prior.id
                prior_title = prior.extraction_json["title"]  # type: ignore[index]
                prior_updated = prior.updated_at

            invoker = FakeJdInvoker([_full_extracted()])
            embedder = FakeEmbeddingClient(
                error=EmbeddingAdapterError(
                    FAILURE_EMBEDDING_TIMEOUT, "timeout"
                )
            )

            with pytest.raises(JobReextractError) as ei:
                await reextract_job(
                    job_id,
                    invoker=invoker,
                    normalizer=_normalizer(),
                    embedding_client=embedder,
                    session_factory=factory,
                )
            assert ei.value.code == FAILURE_EMBEDDING_TIMEOUT
            assert invoker.call_count == 1
            assert embedder.call_count == 1

            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == prior_title
            assert _as_utc(row.updated_at) == _as_utc(prior_updated)
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_conflict_discards_candidate_without_overwrite(
    db_path: Path,
) -> None:
    """Stale revision returns JOB_REEXTRACT_CONFLICT and preserves concurrent row."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session, raw_hash="hash-conflict")
                job_id = prior.id

            # Concurrent revision advance after our load would race; simulate by
            # advancing updated_at while reextract is between load and CAS via a
            # custom path: load happens inside reextract — inject by updating
            # between snapshot and CAS using a hook is hard, so mutate after a
            # partial setup: capture, advance, then call replace-level path via
            # service by racing: update job right after seeding so a second
            # reextract with an in-flight stale snapshot is approximated by
            # monkeypatching load to return an older snapshot.

            async with factory() as session:
                row = await jobs_repo.get_by_id(session, job_id)
                assert row is not None
                stale = row.updated_at
                row.updated_at = utc_now_plus()
                await session.flush()
                await session.commit()
                concurrent_title = row.extraction_json["title"]  # type: ignore[index]
                concurrent_ts = row.updated_at

            # Force service to use stale capture by patching snapshot loader.
            import app.services.job_reextraction as rex_mod

            real_load = rex_mod._load_snapshot

            async def _stale_load(
                jid: str,
                *,
                session_factory: async_sessionmaker[AsyncSession] | None,
            ) -> Any:
                snap = await real_load(jid, session_factory=session_factory)
                return rex_mod._JobWorkingSnapshot(
                    job_id=snap.job_id,
                    source_type=snap.source_type,
                    source_url=snap.source_url,
                    raw_content=snap.raw_content,
                    raw_content_hash=snap.raw_content_hash,
                    created_at=snap.created_at,
                    updated_at=stale,
                    processing_status=snap.processing_status,
                    jd_quality=snap.jd_quality,
                    failure_code=snap.failure_code,
                    extraction_json=snap.extraction_json,
                    embedding_json=snap.embedding_json,
                    embedding_model=snap.embedding_model,
                    embedding_dimensions=snap.embedding_dimensions,
                )

            original = rex_mod._load_snapshot
            rex_mod._load_snapshot = _stale_load  # type: ignore[assignment]
            try:
                invoker = FakeJdInvoker(
                    [_full_extracted(extraction_confidence=0.99)]
                )
                embedder = FakeEmbeddingClient(vector=_vector(0.22))
                with pytest.raises(JobReextractError) as ei:
                    await reextract_job(
                        job_id,
                        invoker=invoker,
                        normalizer=_normalizer(),
                        embedding_client=embedder,
                        session_factory=factory,
                    )
                assert ei.value.code == ERROR_JOB_REEXTRACT_CONFLICT
            finally:
                rex_mod._load_snapshot = original  # type: ignore[assignment]

            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == concurrent_title
            assert row.extraction_json.get("extraction_confidence") != 0.99
            assert _as_utc(row.updated_at) == _as_utc(concurrent_ts)
        finally:
            await engine.dispose()

    run_async(_body())


def utc_now_plus() -> datetime:
    from app.core.time import utc_now

    return utc_now() + timedelta(seconds=3)


# ---------------------------------------------------------------------------
# Graph partial success + evaluation currentness
# ---------------------------------------------------------------------------


def test_reextract_graph_failure_keeps_sqlite_truth(db_path: Path) -> None:
    """Post-commit Neo4j failure returns partial success without SQLite rollback."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                prior = await _seed_processed_job(session, raw_hash="hash-graph-fail")
                job_id = prior.id
                prior_updated = prior.updated_at

            invoker = FakeJdInvoker(
                [_full_extracted(extraction_confidence=0.77)]
            )
            embedder = FakeEmbeddingClient(vector=_vector(0.33))

            async def _fail_sync(**_kwargs: Any) -> None:
                raise JobSyncError("simulated graph failure")

            result = await reextract_job(
                job_id,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                session_factory=factory,
                job_sync_fn=_fail_sync,
            )
            assert result.sync_ok is False
            assert result.sync_code == NEO4J_SYNC_FAILED
            assert result.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED

            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["extraction_confidence"] == 0.77
            assert _as_utc(row.updated_at) > _as_utc(prior_updated)
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_success_projects_evaluation_stale_without_evaluate(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful replacement makes prior evaluation stale with zero evaluate calls."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                prior = await _seed_processed_job(session, raw_hash="hash-stale-eval")
                job_id = prior.id
                job_revision = prior.updated_at
                facts = EvaluationContextFacts(
                    job_id=job_id,
                    job_revision=job_revision,
                    active_attachment_id=_ATT_ID,
                    cv_source_hash="cv-source-1",
                    profile_revision=_TS,
                    preferences_revision=_TS,
                    matching_contract_version=MATCHING_CONTRACT_VERSION,
                )
                digest = evaluation_context_hash(facts)
                eval_row, created = await eval_repo.insert_evaluation(
                    session,
                    job_id=job_id,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=digest,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=facts.matching_contract_version,
                    result=_match_payload(job_id),
                )
                await session.commit()
                assert created is True
                evaluation_id = eval_row.id

                # Prove current under pre-reextract revision.
                lookup = await eval_repo.lookup_for_job(
                    session,
                    job_id=job_id,
                    current_context_hash=digest,
                )
                assert lookup.currentness == "current"

            evaluate_spy = MagicMock()
            monkeypatch.setattr(
                "app.services.job_evaluation.evaluate_job",
                evaluate_spy,
                raising=True,
            )

            invoker = FakeJdInvoker(
                [_full_extracted(extraction_confidence=0.88)]
            )
            embedder = FakeEmbeddingClient(vector=_vector(0.44))

            async def _sync_ok(**_kwargs: Any) -> None:
                return None

            result = await reextract_job(
                job_id,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                session_factory=factory,
                job_sync_fn=_sync_ok,
            )
            assert result.sync_ok is True
            evaluate_spy.assert_not_called()

            from app.db.models.job_evaluations import JobEvaluation

            async with factory() as session:
                count = await session.execute(
                    select(func.count())
                    .select_from(JobEvaluation)
                    .where(JobEvaluation.job_id == job_id)
                )
                assert int(count.scalar_one()) == 1
                stored = await eval_repo.get_by_id(session, evaluation_id)
                assert stored is not None
                assert stored.evaluation_context_hash == digest

                row = await jobs_repo.get_by_id(session, job_id)
                assert row is not None
                job_rev = _as_utc(row.updated_at)
                new_facts = EvaluationContextFacts(
                    job_id=job_id,
                    job_revision=job_rev,
                    active_attachment_id=_ATT_ID,
                    cv_source_hash="cv-source-1",
                    profile_revision=_TS,
                    preferences_revision=_TS,
                    matching_contract_version=MATCHING_CONTRACT_VERSION,
                )
                new_digest = evaluation_context_hash(new_facts)
                assert new_digest != digest
                lookup = await eval_repo.lookup_for_job(
                    session,
                    job_id=job_id,
                    current_context_hash=new_digest,
                )
                assert lookup.currentness == "stale"
                assert lookup.evaluation is not None
                assert lookup.evaluation.id == evaluation_id
        finally:
            await engine.dispose()

    run_async(_body())


def test_reextract_repairs_failed_row_when_scorable(db_path: Path) -> None:
    """Failed retained Job can become processed full after scorable re-extract."""

    async def _body() -> None:
        engine, factory = _factory(db_path)
        try:
            async with factory() as session:
                row = await jobs_repo.create_text_job(
                    session,
                    raw_content=_GROUNDED_CORE,
                    raw_content_hash="hash-failed-repair",
                )
                await jobs_repo.mark_processing(session, row.id)
                await jobs_repo.mark_failed(
                    session, row.id, failure_code="PROVIDER_ERROR"
                )
                await session.commit()
                job_id = row.id
                assert row.processing_status == JOB_PROCESSING_STATUS_FAILED

            invoker = FakeJdInvoker(
                [_full_extracted(extraction_confidence=0.66)]
            )
            embedder = FakeEmbeddingClient(vector=_vector(0.55))

            async def _sync(**_kwargs: Any) -> None:
                return None

            result = await reextract_job(
                job_id,
                invoker=invoker,
                normalizer=_normalizer(),
                embedding_client=embedder,
                session_factory=factory,
                job_sync_fn=_sync,
            )
            assert result.processing_status == JOB_PROCESSING_STATUS_PROCESSED
            assert result.failure_code is None
            assert result.jd_quality == JOB_JD_QUALITY_FULL
            row = await _get_job(factory, job_id)
            assert row.extraction_json is not None
            assert row.extraction_json["title"] == "Backend Engineer"
            assert row.extraction_json["extraction_confidence"] == 0.66
            assert row.raw_content == _GROUNDED_CORE
        finally:
            await engine.dispose()

    run_async(_body())
