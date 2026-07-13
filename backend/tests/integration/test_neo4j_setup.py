"""Live-local Neo4j base-schema integration (04B).

Connects to a host-published Bolt endpoint (Compose loopback 127.0.0.1:7687).
Skips when Neo4j is unreachable or process-level credentials are absent so
offline ``pytest tests/integration`` still passes. Never prints secrets or
loads the root ``.env`` file.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from app.core.settings import Settings
from app.graph.constraints import (
    VECTOR_DIMENSIONS,
    VECTOR_SIMILARITY,
    ensure_base_schema,
)
from app.graph.driver import check_connectivity, close_driver, open_driver
from neo4j import AsyncDriver
from pydantic import AnyHttpUrl, SecretStr

from tests.support.db_migration import run_async

# Host-side Bolt only (Compose publishes 127.0.0.1:7687).
_HOST_BOLT_URI = "bolt://127.0.0.1:7687"
_EXPECTED_CONSTRAINT_NAMES = frozenset(
    {
        "candidate_id_unique",
        "job_id_unique",
        "skill_canonical_key_unique",
    }
)
_VECTOR_INDEX_NAME = "job_embedding_vector"
# Default SHOW VECTOR INDEXES omits options; YIELD is required for config.
_VECTOR_INDEX_QUERY = (
    "SHOW VECTOR INDEXES YIELD name, options RETURN name, options"
)


def _process_password() -> str | None:
    """Return NEO4J_PASSWORD from the process environment only (no .env read)."""
    value = os.environ.get("NEO4J_PASSWORD")
    if value is None or value.strip() == "":
        return None
    return value


def _host_settings() -> Settings:
    """Minimal settings for a host-side driver; password never asserted as text."""
    password = _process_password()
    assert password is not None
    user = os.environ.get("NEO4J_USER") or "neo4j"
    return Settings(
        FRONTEND_ORIGIN="http://127.0.0.1:5173",
        SQLITE_PATH=":memory:",
        FILES_DIR="files",
        NEO4J_URI=_HOST_BOLT_URI,
        NEO4J_USER=user,
        NEO4J_PASSWORD=SecretStr(password),
        SHOPAIKEY_BASE_URL=AnyHttpUrl("https://example.test/v1"),
        SHOPAIKEY_API_KEY=SecretStr("live-local-not-a-real-shopaikey"),
    )


def _require_live_credentials() -> None:
    if _process_password() is None:
        pytest.skip(
            "NEO4J_PASSWORD not set in process environment (Compose live gate)"
        )


async def _fetch_uniqueness_constraint_names(driver: AsyncDriver) -> set[str]:
    names: set[str] = set()
    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS")
        records = await result.data()
    for row in records:
        name = row.get("name")
        ctype = str(row.get("type") or "")
        if name and "UNIQUE" in ctype.upper():
            names.add(str(name))
    return names


async def _fetch_vector_index_rows(driver: AsyncDriver) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(_VECTOR_INDEX_QUERY)
        return await result.data()


def _vector_config(row: dict[str, Any]) -> dict[str, Any]:
    options = row.get("options") or {}
    if not isinstance(options, dict):
        return {}
    config = options.get("indexConfig", options)
    return config if isinstance(config, dict) else {}


def _vector_options_ok(row: dict[str, Any]) -> bool:
    """Require 1536 dimensions and cosine similarity (case-insensitive)."""
    config = _vector_config(row)
    dims = config.get("vector.dimensions") or config.get("`vector.dimensions`")
    sim = config.get("vector.similarity_function") or config.get(
        "`vector.similarity_function`"
    )
    if dims is None or sim is None:
        return False
    return int(dims) == VECTOR_DIMENSIONS and str(sim).lower() == VECTOR_SIMILARITY


async def _run_live_schema_probe() -> tuple[set[str], list[dict[str, Any]]]:
    """Open, setup twice, inspect, close — all on one event loop."""
    settings = _host_settings()
    driver = open_driver(settings)
    try:
        if not await check_connectivity(driver):
            raise ConnectionError("neo4j connectivity failed")
        await ensure_base_schema(driver)
        await ensure_base_schema(driver)
        names = await _fetch_uniqueness_constraint_names(driver)
        vectors = await _fetch_vector_index_rows(driver)
        return names, vectors
    finally:
        await close_driver(driver)


def test_live_ensure_base_schema_twice_yields_exact_constraints_and_vector() -> None:
    """Run schema setup twice; prove three uniqueness constraints + cosine/1536."""
    _require_live_credentials()
    try:
        names, vector_rows = run_async(_run_live_schema_probe())
    except ConnectionError as exc:
        pytest.skip(f"Live Neo4j unavailable: {exc}")
    except OSError as exc:
        pytest.skip(f"Live Neo4j unavailable: {exc}")

    # Complete live uniqueness-constraint name set must equal exactly the three
    # approved names (reject every extra UNIQUE constraint).
    assert names == _EXPECTED_CONSTRAINT_NAMES
    assert len(names) == 3

    # Complete live VECTOR-index set must be only job_embedding_vector with
    # cosine similarity and 1536 dimensions (reject every extra vector index).
    vector_names = {str(r.get("name")) for r in vector_rows if r.get("name")}
    assert vector_names == {_VECTOR_INDEX_NAME}, (
        f"expected only vector index {_VECTOR_INDEX_NAME!r}, got {sorted(vector_names)}"
    )
    named = [r for r in vector_rows if r.get("name") == _VECTOR_INDEX_NAME]
    assert len(named) == 1
    assert _vector_options_ok(named[0]), (
        "vector index must be cosine similarity at 1536 dimensions"
    )
    assert VECTOR_DIMENSIONS == 1536
    assert VECTOR_SIMILARITY == "cosine"


def test_live_schema_inspection_contains_no_secret_material() -> None:
    """SHOW output and setup must not surface the process password."""
    password = _process_password()
    _require_live_credentials()
    assert password is not None
    try:
        names, vectors = run_async(_run_live_schema_probe())
    except (ConnectionError, OSError) as exc:
        pytest.skip(f"Live Neo4j unavailable: {exc}")

    blob = repr(names) + repr(vectors)
    assert password not in blob
    assert password not in str(vectors)
