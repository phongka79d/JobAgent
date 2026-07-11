"""Fake-driver tests for idempotent Neo4j schema bootstrap."""

from __future__ import annotations

import os

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphErrorCode
from app.graph.schema import (
    EMBEDDING_VECTOR_DIMENSIONS,
    SCHEMA_STATEMENTS,
    VECTOR_INDEX_NAME,
    VECTOR_SIMILARITY_FUNCTION,
    ensure_graph_schema,
    schema_statements_for_dimensions,
)
from tests.graph.fakes import FakeDriver

SENTINEL_PASSWORD = "sentinel-schema-secret-never-emit"


def _client(driver: FakeDriver) -> Neo4jClient:
    return Neo4jClient(
        uri="bolt://neo4j:7687",
        user="neo4j",
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )


def test_schema_statements_match_source_contract() -> None:
    assert EMBEDDING_VECTOR_DIMENSIONS == 1536
    assert EMBEDDING_VECTOR_DIMENSIONS == ALLOWED_EMBEDDING_DIMENSIONS
    assert VECTOR_SIMILARITY_FUNCTION == "cosine"
    assert len(SCHEMA_STATEMENTS) == 5

    joined = "\n".join(SCHEMA_STATEMENTS)
    assert "candidate_id_unique" in joined
    assert "job_id_unique" in joined
    assert "skill_canonical_key_unique" in joined
    assert "job_family_canonical_key_unique" in joined
    assert "FOR (c:Candidate) REQUIRE c.id IS UNIQUE" in joined
    assert "FOR (j:Job) REQUIRE j.id IS UNIQUE" in joined
    assert "FOR (s:Skill) REQUIRE s.canonical_key IS UNIQUE" in joined
    assert "FOR (f:JobFamily) REQUIRE f.canonical_key IS UNIQUE" in joined
    assert VECTOR_INDEX_NAME in joined
    assert "CREATE VECTOR INDEX" in joined
    assert "ON (j.embedding)" in joined
    assert "`vector.dimensions`: 1536" in joined
    assert "`vector.similarity_function`: 'cosine'" in joined
    for statement in SCHEMA_STATEMENTS:
        assert "IF NOT EXISTS" in statement
        # No parameter placeholders in static DDL (values are fixed constants).
        assert "$" not in statement


def test_schema_statements_for_dimensions_rejects_non_locked() -> None:
    with pytest.raises(GraphError) as exc_info:
        schema_statements_for_dimensions(768)
    assert exc_info.value.code is GraphErrorCode.INVALID_DIMENSION
    assert schema_statements_for_dimensions(1536) == SCHEMA_STATEMENTS


@pytest.mark.asyncio
async def test_ensure_graph_schema_runs_all_statements_once() -> None:
    driver = FakeDriver()
    client = _client(driver)
    await ensure_graph_schema(client)
    assert len(driver.queries) == 5
    executed = [item.query for item in driver.queries]
    assert executed == list(SCHEMA_STATEMENTS)
    for item in driver.queries:
        assert item.parameters == {}


@pytest.mark.asyncio
async def test_ensure_graph_schema_is_idempotent_on_rerun() -> None:
    driver = FakeDriver()
    client = _client(driver)
    await ensure_graph_schema(client)
    await ensure_graph_schema(client)
    # Two full runs: ten IF NOT EXISTS statements, no alternate DDL.
    assert len(driver.queries) == 10
    first = [item.query for item in driver.queries[:5]]
    second = [item.query for item in driver.queries[5:]]
    assert first == second == list(SCHEMA_STATEMENTS)
    # Logical names appear twice (once per run), never expanded to CREATE without IF NOT EXISTS.
    names = [
        "candidate_id_unique",
        "job_id_unique",
        "skill_canonical_key_unique",
        "job_family_canonical_key_unique",
        VECTOR_INDEX_NAME,
    ]
    joined = "\n".join(item.query for item in driver.queries)
    for name in names:
        assert joined.count(name) == 2
    assert "CREATE CONSTRAINT" in joined
    assert "CREATE VECTOR INDEX" in joined
    assert "DROP " not in joined


@pytest.mark.asyncio
async def test_ensure_graph_schema_invalid_dimension() -> None:
    driver = FakeDriver()
    client = _client(driver)
    with pytest.raises(GraphError) as exc_info:
        await ensure_graph_schema(client, embedding_dimensions=512)
    assert exc_info.value.code is GraphErrorCode.INVALID_DIMENSION
    assert driver.queries == []


@pytest.mark.asyncio
async def test_schema_failure_is_sanitized() -> None:
    driver = FakeDriver(
        run_error=RuntimeError(
            f"Cypher error near password={SENTINEL_PASSWORD} "
            f"query=CREATE CONSTRAINT ..."
        )
    )
    client = _client(driver)
    with pytest.raises(GraphError) as exc_info:
        await ensure_graph_schema(client)
    err = exc_info.value
    assert err.code is GraphErrorCode.SCHEMA_FAILED
    assert SENTINEL_PASSWORD not in str(err)
    assert SENTINEL_PASSWORD not in repr(err)
    assert err.__cause__ is None
    assert err.__context__ is None


@pytest.mark.asyncio
async def test_schema_setup_does_not_mutate_sqlite(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = tmp_path_factory.mktemp("schema_sqlite_guard")
    db_path = root / "jobagent.db"
    db_path.write_bytes(b"untouched-sqlite")
    before = db_path.read_bytes()

    driver = FakeDriver(run_error=OSError("neo4j schema unavailable"))
    client = _client(driver)
    with pytest.raises(GraphError):
        await ensure_graph_schema(client)
    assert db_path.read_bytes() == before


@pytest.mark.neo4j
@pytest.mark.asyncio
async def test_live_schema_idempotent_optional() -> None:
    """Optional live check against a running Neo4j (Compose after 05A).

    Requires NEO4J_PASSWORD (and optional NEO4J_URI / NEO4J_USER) in the process
    environment. Never reads the repository root ``.env`` file from this test.
    """
    password = os.environ.get("NEO4J_PASSWORD", "").strip()
    if not password:
        pytest.skip("NEO4J_PASSWORD not set for optional live Neo4j validation")

    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687").strip()
    user = os.environ.get("NEO4J_USER", "neo4j").strip()
    client = Neo4jClient(uri=uri, user=user, password=password)
    try:
        await ensure_graph_schema(client)
        await ensure_graph_schema(client)
        health = await client.health()
        assert health.status.value == "up"
    finally:
        await client.close()
