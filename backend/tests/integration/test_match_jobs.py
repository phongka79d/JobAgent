"""Integration tests for top-50 vector retrieval and SQLite hydration."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.db.session import build_async_engine
from app.graph import retrieval as retrieval_mod
from app.graph.constraints import JOB_EMBEDDING_VECTOR_INDEX_NAME
from app.graph.retrieval import JobRetrievalError, retrieve_job_candidates
from app.repositories import jobs as jobs_repo
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    EmbeddingVectorError,
)
from app.schemas.jobs import parse_job_post_extraction

from tests.fakes.matching import ScriptedRead, ScriptedReadDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    embedding_vector,
    extraction_payload,
    seed_scorable_job,
    snapshot_sqlite,
)


@pytest.fixture
def sqlite_factory(migrated_sqlite: Path) -> Iterator[Any]:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    try:
        yield factory
    finally:
        run_async(engine.dispose())


async def _seed_url_scorable_job(
    factory: Any,
    *,
    raw_hash: str,
    source_url: str,
) -> str:
    extraction = parse_job_post_extraction(
        {
            **extraction_payload(),
            "title": "SQLite URL Engineer",
            "company": "SQLite Source Co",
        }
    )
    async with factory() as session:
        placeholder = await jobs_repo.create_url_placeholder(
            session,
            source_url=source_url,
        )
        job_id = placeholder.id
        await jobs_repo.set_url_raw_content(
            session,
            job_id,
            raw_content="URL JD body",
            raw_content_hash=raw_hash,
        )
        await jobs_repo.mark_processing(session, job_id)
        await jobs_repo.mark_processed(
            session,
            job_id,
            extraction_json=extraction.model_dump(mode="json"),
            jd_quality="full",
            embedding_json=embedding_vector(0.04),
            embedding_model=LOCKED_EMBEDDING_MODEL,
            embedding_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
        )
        await session.commit()
    return job_id


def _driver(rows: list[dict[str, Any]]) -> ScriptedReadDriver:
    return ScriptedReadDriver(
        (ScriptedRead("db.index.vector.queryNodes", rows),),
    )


def test_empty_scorable_set_returns_empty_without_graph_query(
    sqlite_factory: Any,
) -> None:
    driver = _driver([])

    async def _body() -> Any:
        async with sqlite_factory() as session:
            return await retrieve_job_candidates(
                session,
                driver,
                candidate_vector=embedding_vector(0.2),
                scorable_job_ids=frozenset(),
            )

    result = run_async(_body())

    assert result == []
    assert driver.session_enter == 0
    assert driver.queries == []


def test_retrieval_clamps_and_hydrates_sqlite_facts_in_vector_order(
    sqlite_factory: Any,
) -> None:
    text_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="retrieval-text")
    )
    url_id = run_async(
        _seed_url_scorable_job(
            sqlite_factory,
            raw_hash="retrieval-url",
            source_url="https://example.com/jobs/sqlite-source",
        )
    )
    vector = embedding_vector(0.3)
    driver = _driver(
        [
            {
                "id": url_id,
                "score": 1.25,
                "title": "Neo4j must not be canonical",
            },
            {"id": text_id, "score": -0.25},
        ]
    )

    async def _body() -> Any:
        async with sqlite_factory() as session:
            return await retrieve_job_candidates(
                session,
                driver,
                candidate_vector=vector,
                scorable_job_ids=frozenset({text_id, url_id}),
            )

    result = run_async(_body())

    assert [candidate.job_id for candidate in result] == [url_id, text_id]
    assert [candidate.semantic_similarity for candidate in result] == [1.0, 0.0]
    assert result[0].source_url == "https://example.com/jobs/sqlite-source"
    assert result[0].extraction.title == "SQLite URL Engineer"
    assert result[0].extraction.company == "SQLite Source Co"
    assert result[1].extraction.title == "Backend Engineer"
    assert driver.parameters[0]["index_name"] == JOB_EMBEDDING_VECTOR_INDEX_NAME
    assert driver.parameters[0]["k"] == 2
    assert driver.parameters[0]["candidate_vector"] == vector
    assert driver.write_queries == []


def test_retrieval_never_requests_more_than_top_50(
    sqlite_factory: Any,
) -> None:
    ids = {
        run_async(
            seed_scorable_job(
                sqlite_factory,
                raw_hash=f"retrieval-limit-{index}",
            )
        )
        for index in range(51)
    }
    driver = _driver([])

    async def _body() -> Any:
        async with sqlite_factory() as session:
            return await retrieve_job_candidates(
                session,
                driver,
                candidate_vector=embedding_vector(0.4),
                scorable_job_ids=frozenset(ids),
            )

    result = run_async(_body())

    assert result == []
    assert driver.parameters[0]["k"] == 50
    assert "db.index.vector.queryNodes" in driver.queries[0]


def test_invalid_candidate_vector_is_rejected_before_graph_query(
    sqlite_factory: Any,
) -> None:
    driver = _driver([])

    async def _body() -> None:
        async with sqlite_factory() as session:
            await retrieve_job_candidates(
                session,
                driver,
                candidate_vector=[0.1],
                scorable_job_ids=frozenset({"job-1"}),
            )

    with pytest.raises(EmbeddingVectorError, match="DIMENSION_MISMATCH"):
        run_async(_body())
    assert driver.session_enter == 0


def test_unknown_vector_result_id_fails_without_ranking(
    sqlite_factory: Any,
) -> None:
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="retrieval-known")
    )
    driver = _driver([{"id": "stale-job", "score": 0.9}])
    before = run_async(snapshot_sqlite(sqlite_factory))

    async def _body() -> None:
        async with sqlite_factory() as session:
            await retrieve_job_candidates(
                session,
                driver,
                candidate_vector=embedding_vector(0.5),
                scorable_job_ids=frozenset({job_id}),
            )

    with pytest.raises(JobRetrievalError, match="not in current scorable set"):
        run_async(_body())
    after = run_async(snapshot_sqlite(sqlite_factory))
    assert before == after
    assert driver.write_queries == []


def test_retrieval_owner_reuses_index_and_snapshot_owners() -> None:
    source = inspect.getsource(retrieval_mod)
    assert "JOB_EMBEDDING_VECTOR_INDEX_NAME" in source
    assert "load_scorable_job_facts" in source
    assert "validate_finite_vector" in source
    assert "select(" not in source
    assert "app.db.models.jobs" not in source
    assert "commit(" not in source
    assert "rollback(" not in source
    assert "flush(" not in source
    assert "db.index.vector.queryNodes" in source
    assert "clamp" in source
