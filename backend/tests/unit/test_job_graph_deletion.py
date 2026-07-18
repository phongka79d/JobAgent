"""Unit tests for exact Job Neo4j deletion allowlist and idempotency."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from app.graph import delete_job as delete_mod
from app.graph.delete_job import (
    DELETE_JOB_CYPHER,
    JOB_ABSENCE_CYPHER,
    JobGraphDeleteError,
    allowed_delete_labels,
    allowed_delete_relationships,
    assert_delete_job_query_allowlisted,
    delete_job_cypher,
    delete_job_node,
    job_absence_cypher,
    job_node_absent,
)
from app.graph.rebuild_ops import CLEAR_JOB_CYPHER


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


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
    def __init__(self, driver: FakeNeo4jDriver) -> None:
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
            raise OSError("simulated neo4j failure")
        self._driver.queries.append(query)
        params = dict(parameters) if parameters is not None else {}
        self._driver.parameters.append(params)
        return _FakeResult(self._driver._rows_for(query, params))


class FakeNeo4jDriver:
    """Tracks exact Job nodes for parameterized delete + absence checks."""

    def __init__(
        self,
        *,
        fail_on_run: bool = False,
        jobs: set[str] | None = None,
    ) -> None:
        self.fail_on_run = fail_on_run
        self.jobs: set[str] = set(jobs or ())
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.session_enter = 0
        self.session_exit = 0

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)

    def _rows_for(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        q = " ".join(query.split())
        job_id = str(params.get("job_id", ""))
        if q == " ".join(DELETE_JOB_CYPHER.split()):
            self.jobs.discard(job_id)
            return []
        if q == " ".join(JOB_ABSENCE_CYPHER.split()):
            return [{"n": 1 if job_id in self.jobs else 0}]
        return []


def test_delete_job_cypher_is_exact_and_parameterized() -> None:
    cypher = delete_job_cypher()
    assert cypher == DELETE_JOB_CYPHER
    assert "$job_id" in cypher
    assert "MATCH (j:Job {id: $job_id})" in cypher
    assert "DETACH DELETE j" in cypher
    assert CLEAR_JOB_CYPHER != cypher
    assert CLEAR_JOB_CYPHER == "MATCH (j:Job) DETACH DELETE j"
    assert cypher != CLEAR_JOB_CYPHER


def test_delete_job_query_allowlist_accepts_template_rejects_broad() -> None:
    assert_delete_job_query_allowlisted(DELETE_JOB_CYPHER)
    with pytest.raises(ValueError, match="allowlisted"):
        assert_delete_job_query_allowlisted("MATCH (n) DETACH DELETE n")
    with pytest.raises(ValueError, match="allowlisted"):
        assert_delete_job_query_allowlisted(CLEAR_JOB_CYPHER)
    with pytest.raises(ValueError, match="allowlisted"):
        assert_delete_job_query_allowlisted(
            "MATCH (s:Skill {canonical_key: $job_id}) DETACH DELETE s"
        )
    with pytest.raises(ValueError, match="allowlisted"):
        assert_delete_job_query_allowlisted(
            "MATCH (j:Job {id: $job_id}) DETACH DELETE j WITH 1 AS x "
            "MATCH (s:Skill) DETACH DELETE s"
        )


def test_allowed_labels_are_job_only() -> None:
    assert allowed_delete_labels() == frozenset({"Job"})
    assert allowed_delete_relationships() == frozenset()
    src = Path(delete_mod.__file__).read_text(encoding="utf-8")
    assert ":Skill" not in DELETE_JOB_CYPHER
    assert ":Candidate" not in DELETE_JOB_CYPHER
    assert ":CV" not in DELETE_JOB_CYPHER
    assert "RELATED_TO" not in DELETE_JOB_CYPHER
    assert "MATCH (n)" not in src
    assert "sessionmaker" not in src
    assert "app.repositories" not in src


def test_delete_job_node_parameterized_and_idempotent() -> None:
    job_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    other = "bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    driver = FakeNeo4jDriver(jobs={job_id, other})

    async def _body() -> None:
        await delete_job_node(driver, job_id)
        await delete_job_node(driver, job_id)  # idempotent missing
        assert await job_node_absent(driver, job_id)
        assert not await job_node_absent(driver, other)

    run_async(_body())
    assert job_id not in driver.jobs
    assert other in driver.jobs
    delete_queries = [
        q for q in driver.queries if "DETACH DELETE j" in q
    ]
    assert len(delete_queries) == 2
    for q, params in zip(driver.queries, driver.parameters, strict=True):
        if "DETACH DELETE j" in q:
            assert_delete_job_query_allowlisted(q)
            assert params == {"job_id": job_id}


def test_delete_job_node_missing_is_success() -> None:
    job_id = "cccccccc-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    driver = FakeNeo4jDriver(jobs=set())

    async def _body() -> None:
        await delete_job_node(driver, job_id)
        assert await job_node_absent(driver, job_id)

    run_async(_body())
    assert any("DETACH DELETE j" in q for q in driver.queries)


def test_delete_job_node_driver_failure_raises_stable_code() -> None:
    driver = FakeNeo4jDriver(fail_on_run=True)

    async def _body() -> None:
        with pytest.raises(JobGraphDeleteError) as ei:
            await delete_job_node(driver, "dddddddd-bbbb-4ccc-8ddd-eeeeeeeeeeee")
        assert ei.value.code == "JOB_DELETE_GRAPH_FAILED"
        assert "retry" in ei.value.message.lower()

    run_async(_body())


def test_delete_job_node_rejects_empty_id() -> None:
    driver = FakeNeo4jDriver()

    async def _body() -> None:
        with pytest.raises(JobGraphDeleteError):
            await delete_job_node(driver, "  ")
        with pytest.raises(JobGraphDeleteError):
            await delete_job_node(driver, "")

    run_async(_body())
    assert driver.queries == []


def test_absence_cypher_is_parameterized() -> None:
    assert job_absence_cypher() == JOB_ABSENCE_CYPHER
    assert "$job_id" in JOB_ABSENCE_CYPHER
    assert "count(j)" in JOB_ABSENCE_CYPHER
    assert "DETACH" not in JOB_ABSENCE_CYPHER


def test_delete_job_module_exports_and_source_contract() -> None:
    assert callable(delete_job_node)
    assert callable(assert_delete_job_query_allowlisted)
    src = inspect.getsource(delete_mod)
    assert "DETACH DELETE j" in src
    assert "MATCH (j:Job {id: $job_id})" in src
    assert "MATCH (j:Job) DETACH DELETE j" not in src
    assert "JobGraphDeleteError" in src
