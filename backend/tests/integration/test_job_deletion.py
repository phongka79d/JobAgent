"""Integration tests for graph-first / SQLite-second Job deletion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.session import build_async_engine
from app.graph.delete_job import (
    DELETE_JOB_CYPHER,
    JOB_ABSENCE_CYPHER,
    JobGraphDeleteError,
    assert_delete_job_query_allowlisted,
    delete_job_node,
)
from app.repositories import job_deletion as job_del_repo
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import JobNotFoundError
from app.services.job_deletion import (
    ERROR_JOB_DELETE_GRAPH_FAILED,
    ERROR_JOB_NOT_FOUND,
    JOB_DELETE_RETRY_SUMMARY,
    JobDeleteError,
    delete_job,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import run_async, session_factory

_TS = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)
_JOB_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
_JOB_B = "bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"
_ATT_ID = "11111111-2222-4333-8444-555555555555"
_EVAL_A = "eeeeeeee-1111-4111-8111-eeeeeeeeeeee"
_EVAL_B = "eeeeeeee-2222-4111-8111-eeeeeeeeeeee"


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows if rows is not None else []

    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, driver: ExactJobFakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        del kwargs
        if self._driver.fail_on_run:
            raise OSError("simulated neo4j write failure")
        self._driver.queries.append(query)
        params = dict(parameters) if parameters is not None else {}
        self._driver.parameters.append(params)
        return _FakeResult(self._driver.apply(query, params))


class ExactJobFakeDriver:
    """Per-id Job graph state; Skills/Candidate/CV/unrelated survive exact delete."""

    def __init__(
        self,
        *,
        fail_on_run: bool = False,
        jobs: set[str] | None = None,
    ) -> None:
        self.fail_on_run = fail_on_run
        self.jobs: set[str] = set(jobs or ())
        self.skills: set[str] = {"python", "fastapi"}
        self.related_to: int = 3
        self.candidates: set[str] = {"active"}
        self.cvs: set[str] = {"cv-keep"}
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.session_enter = 0
        self.session_exit = 0
        self.mutation_count = 0

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)

    def apply(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        q = " ".join(query.split())
        job_id = str(params.get("job_id", ""))
        if q == " ".join(DELETE_JOB_CYPHER.split()):
            assert_delete_job_query_allowlisted(q)
            if job_id in self.jobs:
                self.jobs.discard(job_id)
                self.mutation_count += 1
            return []
        if q == " ".join(JOB_ABSENCE_CYPHER.split()):
            return [{"n": 1 if job_id in self.jobs else 0}]
        raise AssertionError(f"unexpected Cypher in exact job delete tests: {q}")


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


async def _seed_job(
    session: AsyncSession,
    job_id: str,
    *,
    title: str = "Backend Engineer",
) -> None:
    del title  # compact seed only; extraction body not required for deletion
    await session.execute(
        text(
            "INSERT INTO job_posts ("
            "id, source_type, source_url, raw_content, raw_content_hash, "
            "extraction_json, processing_status, jd_quality, failure_code, "
            "embedding_json, embedding_model, embedding_dimensions, "
            "created_at, updated_at) VALUES ("
            ":id, 'text', NULL, :raw, :raw_hash, "
            "NULL, 'received', NULL, NULL, NULL, NULL, NULL, "
            ":ts, :ts)"
        ),
        {
            "id": job_id,
            "raw": f"JD body {job_id}",
            "raw_hash": f"raw-hash-{job_id}",
            "ts": _TS.isoformat(),
        },
    )


async def _seed_evaluation(
    session: AsyncSession,
    *,
    eval_id: str,
    job_id: str,
) -> None:
    payload = {
        "job_id": job_id,
        "title": "T",
        "company": "C",
        "location": None,
        "work_mode": None,
        "source_url": None,
        "final_score": 0.5,
        "quality_multiplier": 1.0,
        "components": {
            "semantic_similarity": 0.5,
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
        "summary": "s",
    }
    await session.execute(
        text(
            "INSERT INTO job_evaluations ("
            "id, job_id, active_attachment_id, evaluation_context_hash, "
            "job_revision, profile_revision, preferences_revision, "
            "cv_source_hash, matching_contract_version, result_json, "
            "created_at, updated_at) VALUES ("
            ":id, :job_id, :att_id, :ctx, "
            ":ts, :ts, :ts, "
            ":cv_hash, :version, :result_json, "
            ":ts, :ts)"
        ),
        {
            "id": eval_id,
            "job_id": job_id,
            "att_id": _ATT_ID,
            "ctx": f"ctx-{eval_id}",
            "ts": _TS.isoformat(),
            "cv_hash": "cv-hash",
            "version": "v1",
            "result_json": json.dumps(payload),
        },
    )


def test_complete_delete_graph_first_cascades_evaluations_preserves_others(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A, _JOB_B})

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A, title="Target")
                await _seed_job(session, _JOB_B, title="Keep")
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_B, job_id=_JOB_B)
                await session.commit()

            result = await delete_job(
                _JOB_A,
                driver=driver,
                session_factory=factory,
            )
            assert result.job_id == _JOB_A

            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_A) is None
                keep = await jobs_repo.get_by_id(session, _JOB_B)
                assert keep is not None
                assert keep.id == _JOB_B
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 0
                )
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_B)
                    == 1
                )
        finally:
            await engine.dispose()

    run_async(_body())
    assert _JOB_A not in driver.jobs
    assert _JOB_B in driver.jobs
    assert driver.skills == {"python", "fastapi"}
    assert driver.related_to == 3
    assert driver.candidates == {"active"}
    assert driver.cvs == {"cv-keep"}
    assert driver.mutation_count == 1
    for q in driver.queries:
        if "DETACH DELETE" in q:
            assert_delete_job_query_allowlisted(q)
            assert ":Skill" not in q
            assert ":Candidate" not in q
            assert ":CV" not in q


def test_graph_failure_preserves_sqlite_job_and_evaluations(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A}, fail_on_run=True)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await session.commit()

            with pytest.raises(JobDeleteError) as ei:
                await delete_job(
                    _JOB_A,
                    driver=driver,
                    session_factory=factory,
                )
            assert ei.value.code == ERROR_JOB_DELETE_GRAPH_FAILED
            assert JOB_DELETE_RETRY_SUMMARY in ei.value.message

            async with factory() as session:
                row = await jobs_repo.get_by_id(session, _JOB_A)
                assert row is not None
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 1
                )
        finally:
            await engine.dispose()

    run_async(_body())
    assert _JOB_A in driver.jobs  # graph not mutated if fail-before-apply
    assert driver.mutation_count == 0


def test_graph_failure_then_retry_completes(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A}, fail_on_run=True)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await session.commit()

            with pytest.raises(JobDeleteError) as ei:
                await delete_job(
                    _JOB_A,
                    driver=driver,
                    session_factory=factory,
                )
            assert ei.value.code == ERROR_JOB_DELETE_GRAPH_FAILED

            driver.fail_on_run = False
            result = await delete_job(
                _JOB_A,
                driver=driver,
                session_factory=factory,
            )
            assert result.job_id == _JOB_A

            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_A) is None
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 0
                )
        finally:
            await engine.dispose()

    run_async(_body())
    assert _JOB_A not in driver.jobs


def test_missing_graph_node_is_success_then_sqlite_deleted(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs=set())  # already absent in graph

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await session.commit()

            result = await delete_job(
                _JOB_A,
                driver=driver,
                session_factory=factory,
            )
            assert result.job_id == _JOB_A
            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_A) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_repeat_complete_delete_returns_job_not_found_without_mutation(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A})

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await session.commit()

            await delete_job(_JOB_A, driver=driver, session_factory=factory)
            mutations_after_first = driver.mutation_count
            queries_after_first = len(driver.queries)

            with pytest.raises(JobDeleteError) as ei:
                await delete_job(
                    _JOB_A,
                    driver=driver,
                    session_factory=factory,
                )
            assert ei.value.code == ERROR_JOB_NOT_FOUND
            # No further graph mutation or queries after complete deletion.
            assert driver.mutation_count == mutations_after_first
            assert len(driver.queries) == queries_after_first
        finally:
            await engine.dispose()

    run_async(_body())


def test_unknown_id_never_mutates(
    db_path: Path,
) -> None:
    missing = "ffffffff-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    driver = ExactJobFakeDriver(jobs={_JOB_B})

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_job(session, _JOB_B)
                await session.commit()

            with pytest.raises(JobDeleteError) as ei:
                await delete_job(
                    missing,
                    driver=driver,
                    session_factory=factory,
                )
            assert ei.value.code == ERROR_JOB_NOT_FOUND
            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_B) is not None
        finally:
            await engine.dispose()

    run_async(_body())
    assert driver.queries == []
    assert driver.mutation_count == 0
    assert _JOB_B in driver.jobs


def test_sqlite_delete_primitive_cascades_and_raises_when_missing(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await session.commit()

            async with factory() as session:
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 1
                )
                await job_del_repo.delete_job_row(session, _JOB_A)
                await session.commit()

            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_A) is None
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 0
                )
                with pytest.raises(JobNotFoundError):
                    await job_del_repo.delete_job_row(session, _JOB_A)
        finally:
            await engine.dispose()

    run_async(_body())


def test_injected_graph_delete_failure_preserves_sqlite(
    db_path: Path,
) -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A})

    async def _failing_graph(_driver: Any, _job_id: str) -> None:
        raise JobGraphDeleteError(
            "JOB_DELETE_GRAPH_FAILED",
            "injected graph fault",
        )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_attachment(session)
                await _seed_job(session, _JOB_A)
                await _seed_evaluation(session, eval_id=_EVAL_A, job_id=_JOB_A)
                await session.commit()

            with pytest.raises(JobDeleteError) as ei:
                await delete_job(
                    _JOB_A,
                    driver=driver,
                    session_factory=factory,
                    graph_delete_fn=_failing_graph,
                )
            assert ei.value.code == ERROR_JOB_DELETE_GRAPH_FAILED
            async with factory() as session:
                assert await jobs_repo.get_by_id(session, _JOB_A) is not None
                assert (
                    await job_del_repo.count_evaluations_for_job(session, _JOB_A)
                    == 1
                )
        finally:
            await engine.dispose()

    run_async(_body())
    assert _JOB_A in driver.jobs


def test_delete_job_node_standalone_idempotent() -> None:
    driver = ExactJobFakeDriver(jobs={_JOB_A, _JOB_B})

    async def _body() -> None:
        await delete_job_node(driver, _JOB_A)
        await delete_job_node(driver, _JOB_A)

    run_async(_body())
    assert _JOB_A not in driver.jobs
    assert _JOB_B in driver.jobs
    assert driver.skills == {"python", "fastapi"}
    assert driver.related_to == 3
