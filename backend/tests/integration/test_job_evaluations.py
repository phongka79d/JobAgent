"""Integration tests for job_evaluations repository and currentness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.session import build_async_engine
from app.repositories import job_evaluations as eval_repo
from app.schemas.matching import MatchResult
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.db_migration import run_async, session_factory

_TS = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
_JOB_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
_ATT_ID = "11111111-2222-4333-8444-555555555555"
_ATT_OTHER = "22222222-2222-4333-8444-555555555555"


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def _match_payload(job_id: str = _JOB_ID, *, summary: str = "ok") -> dict[str, Any]:
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
        "summary": summary,
    }


def _facts(**overrides: object) -> EvaluationContextFacts:
    base: dict[str, object] = {
        "job_id": _JOB_ID,
        "job_revision": _TS,
        "active_attachment_id": _ATT_ID,
        "cv_source_hash": "cv-source-1",
        "profile_revision": _TS,
        "preferences_revision": _TS,
        "matching_contract_version": MATCHING_CONTRACT_VERSION,
    }
    base.update(overrides)
    return EvaluationContextFacts(**base)  # type: ignore[arg-type]


async def _seed_parents(session: AsyncSession) -> None:
    for sql in (
        "INSERT INTO attachments ("
        "id, file_hash, original_name, mime_type, size_bytes, page_count, "
        "storage_path, state, created_at, updated_at) VALUES "
        f"('{_ATT_ID}', 'h-att', 'cv.pdf', 'application/pdf', 10, 1, "
        f"'p/cv.pdf', 'active', '{_TS.isoformat()}', '{_TS.isoformat()}')",
        "INSERT INTO attachments ("
        "id, file_hash, original_name, mime_type, size_bytes, page_count, "
        "storage_path, state, created_at, updated_at) VALUES "
        f"('{_ATT_OTHER}', 'h-att2', 'old.pdf', 'application/pdf', 10, 1, "
        f"'p/old.pdf', 'archived', '{_TS.isoformat()}', '{_TS.isoformat()}')",
        "INSERT INTO job_posts ("
        "id, source_type, source_url, raw_content, raw_content_hash, "
        "extraction_json, processing_status, jd_quality, failure_code, "
        "embedding_json, embedding_model, embedding_dimensions, "
        "created_at, updated_at) VALUES ("
        f"'{_JOB_ID}', 'text', NULL, 'JD body', 'raw-hash-1', NULL, "
        f"'received', NULL, NULL, NULL, NULL, NULL, "
        f"'{_TS.isoformat()}', '{_TS.isoformat()}')",
    ):
        await session.execute(text(sql))
    await session.commit()


def test_insert_validates_match_result_and_rejects_invalid(
    db_path: Path,
) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _seed_parents(s)
            facts = _facts()
            digest = evaluation_context_hash(facts)
            async with f() as s:
                row, created = await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=digest,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=facts.matching_contract_version,
                    result=_match_payload(),
                )
                await s.commit()
                assert created is True
                assert row.evaluation_context_hash == digest
                assert row.result_json["summary"] == "ok"
                assert isinstance(
                    MatchResult.model_validate(row.result_json), MatchResult
                )

            async with f() as s:
                with pytest.raises(ValidationError):
                    await eval_repo.insert_evaluation(
                        s,
                        job_id=_JOB_ID,
                        active_attachment_id=_ATT_ID,
                        evaluation_context_hash="other-hash",
                        job_revision=facts.job_revision,
                        profile_revision=facts.profile_revision,
                        preferences_revision=facts.preferences_revision,
                        cv_source_hash=facts.cv_source_hash,
                        matching_contract_version=(
                            facts.matching_contract_version
                        ),
                        result={"job_id": _JOB_ID, "summary": "incomplete"},
                    )
        finally:
            await e.dispose()

    run_async(_c())


def test_lookup_none_current_stale_without_rewriting_history(
    db_path: Path,
) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _seed_parents(s)

            current_facts = _facts()
            current_hash = evaluation_context_hash(current_facts)
            async with f() as s:
                lookup = await eval_repo.lookup_for_job(
                    s, job_id=_JOB_ID, current_context_hash=current_hash
                )
                assert lookup.currentness == "none"
                assert lookup.evaluation is None

            stale_facts = _facts(matching_contract_version="match_v2")
            stale_hash = evaluation_context_hash(stale_facts)
            async with f() as s:
                await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=stale_hash,
                    job_revision=stale_facts.job_revision,
                    profile_revision=stale_facts.profile_revision,
                    preferences_revision=stale_facts.preferences_revision,
                    cv_source_hash=stale_facts.cv_source_hash,
                    matching_contract_version=(
                        stale_facts.matching_contract_version
                    ),
                    result=_match_payload(summary="stale-result"),
                )
                await s.commit()

            async with f() as s:
                lookup = await eval_repo.lookup_for_job(
                    s, job_id=_JOB_ID, current_context_hash=current_hash
                )
                assert lookup.currentness == "stale"
                assert lookup.evaluation is not None
                assert lookup.evaluation.result.summary == "stale-result"
                assert (
                    lookup.evaluation.evaluation_context_hash == stale_hash
                )
                # Historical row remains; currentness is derived only.
                assert await eval_repo.count_for_job(s, _JOB_ID) == 1

            async with f() as s:
                await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=current_hash,
                    job_revision=current_facts.job_revision,
                    profile_revision=current_facts.profile_revision,
                    preferences_revision=current_facts.preferences_revision,
                    cv_source_hash=current_facts.cv_source_hash,
                    matching_contract_version=(
                        current_facts.matching_contract_version
                    ),
                    result=_match_payload(summary="current-result"),
                )
                await s.commit()

            async with f() as s:
                lookup = await eval_repo.lookup_for_job(
                    s, job_id=_JOB_ID, current_context_hash=current_hash
                )
                assert lookup.currentness == "current"
                assert lookup.evaluation is not None
                assert lookup.evaluation.result.summary == "current-result"
                assert await eval_repo.count_for_job(s, _JOB_ID) == 2
        finally:
            await e.dispose()

    run_async(_c())


def test_unique_context_race_reloads_committed_winner(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _seed_parents(s)
            facts = _facts()
            digest = evaluation_context_hash(facts)
            kwargs = {
                "job_id": _JOB_ID,
                "active_attachment_id": _ATT_ID,
                "evaluation_context_hash": digest,
                "job_revision": facts.job_revision,
                "profile_revision": facts.profile_revision,
                "preferences_revision": facts.preferences_revision,
                "cv_source_hash": facts.cv_source_hash,
                "matching_contract_version": facts.matching_contract_version,
            }

            async with f() as s1, f() as s2:
                first, created1 = await eval_repo.insert_evaluation(
                    s1,
                    result=_match_payload(summary="winner"),
                    **kwargs,
                )
                await s1.commit()
                assert created1 is True
                second, created2 = await eval_repo.insert_evaluation(
                    s2,
                    result=_match_payload(summary="loser-not-stored"),
                    **kwargs,
                )
                await s2.commit()
                assert created2 is False
                assert second.id == first.id
                assert second.result_json["summary"] == "winner"

            async with f() as s:
                assert await eval_repo.count_for_job(s, _JOB_ID) == 1
                row = await eval_repo.get_by_job_context(
                    s, job_id=_JOB_ID, evaluation_context_hash=digest
                )
                assert row is not None
                assert row.result_json["summary"] == "winner"
        finally:
            await e.dispose()

    run_async(_c())


def test_job_and_attachment_delete_cascade_evaluations(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f: async_sessionmaker[AsyncSession] = session_factory(e)
        try:
            async with f() as s:
                await _seed_parents(s)
            facts = _facts()
            digest = evaluation_context_hash(facts)
            async with f() as s:
                await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=digest,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=(
                        facts.matching_contract_version
                    ),
                    result=_match_payload(),
                )
                await s.commit()
                assert await eval_repo.count_for_job(s, _JOB_ID) == 1

            async with f() as s:
                await s.execute(
                    text(f"DELETE FROM job_posts WHERE id = '{_JOB_ID}'")
                )
                await s.commit()
                assert await eval_repo.count_for_job(s, _JOB_ID) == 0

            # Re-seed job + evaluation for attachment cascade.
            async with f() as s:
                await s.execute(
                    text(
                        "INSERT INTO job_posts ("
                        "id, source_type, source_url, raw_content, "
                        "raw_content_hash, extraction_json, processing_status, "
                        "jd_quality, failure_code, embedding_json, "
                        "embedding_model, embedding_dimensions, "
                        "created_at, updated_at) VALUES ("
                        f"'{_JOB_ID}', 'text', NULL, 'JD body', "
                        f"'raw-hash-2', NULL, 'received', NULL, NULL, "
                        f"NULL, NULL, NULL, '{_TS.isoformat()}', "
                        f"'{_TS.isoformat()}')"
                    )
                )
                await s.commit()
            other_hash = evaluation_context_hash(
                _facts(active_attachment_id=_ATT_OTHER)
            )
            async with f() as s:
                await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_OTHER,
                    evaluation_context_hash=other_hash,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=(
                        facts.matching_contract_version
                    ),
                    result=_match_payload(),
                )
                await s.commit()
            async with f() as s:
                await s.execute(
                    text(
                        f"DELETE FROM attachments WHERE id = '{_ATT_OTHER}'"
                    )
                )
                await s.commit()
                assert await eval_repo.count_for_job(s, _JOB_ID) == 0
                job_left = (
                    await s.execute(
                        text(
                            f"SELECT COUNT(*) FROM job_posts "
                            f"WHERE id = '{_JOB_ID}'"
                        )
                    )
                ).scalar_one()
                assert int(job_left) == 1
        finally:
            await e.dispose()

    run_async(_c())


def test_same_context_second_insert_reuses_without_new_row(
    db_path: Path,
) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _seed_parents(s)
            facts = _facts()
            digest = evaluation_context_hash(facts)
            async with f() as s:
                first, c1 = await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=digest,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=(
                        facts.matching_contract_version
                    ),
                    result=_match_payload(summary="first"),
                )
                await s.commit()
                assert c1 is True
            async with f() as s:
                second, c2 = await eval_repo.insert_evaluation(
                    s,
                    job_id=_JOB_ID,
                    active_attachment_id=_ATT_ID,
                    evaluation_context_hash=digest,
                    job_revision=facts.job_revision,
                    profile_revision=facts.profile_revision,
                    preferences_revision=facts.preferences_revision,
                    cv_source_hash=facts.cv_source_hash,
                    matching_contract_version=(
                        facts.matching_contract_version
                    ),
                    result=_match_payload(summary="second-ignored"),
                )
                await s.commit()
                assert c2 is False
                assert second.id == first.id
                assert second.result_json["summary"] == "first"
        finally:
            await e.dispose()

    run_async(_c())
