"""Integration tests for pre-match SQLite/Neo4j revision consistency."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from app.core.settings import clear_settings_cache
from app.db.session import build_async_engine
from app.graph import consistency as consistency_mod
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    check_graph_revision_consistency,
)
from app.graph.rebuild_snapshot import (
    SourceRevision,
    SourceRevisionSnapshot,
    load_rebuild_inputs,
    load_source_revision_snapshot,
)
from app.graph.rebuild_target import CANONICAL_COMPOSE_REBUILD_COMMAND
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
)

from tests.fakes.matching import ScriptedReadDriver, revision_read_driver
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    seed_candidate,
    seed_scorable_job,
    seed_unscorable_job,
    snapshot_sqlite,
)


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def sqlite_factory(migrated_sqlite: Path) -> Iterator[Any]:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    try:
        yield factory
    finally:
        run_async(engine.dispose())


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_z(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _as_offset(value: datetime) -> str:
    return _utc(value).astimezone(timezone(timedelta(hours=7))).isoformat()


def _candidate_rows(
    snapshot: SourceRevisionSnapshot,
    *,
    updated_at: str | None = None,
) -> list[dict[str, Any]]:
    if snapshot.candidate is None:
        return []
    stamp = (
        updated_at
        if updated_at is not None
        else _as_z(snapshot.candidate.updated_at)
    )
    return [{"id": snapshot.candidate.id, "source_updated_at": stamp}]


def _job_rows(
    snapshot: SourceRevisionSnapshot,
    *,
    omit: str | None = None,
    override: tuple[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    override_id, override_stamp = override if override is not None else (None, None)
    for job in snapshot.jobs:
        if job.id == omit:
            continue
        stamp = override_stamp if job.id == override_id else _as_offset(job.updated_at)
        rows.append({"id": job.id, "source_updated_at": stamp})
    if extra is not None:
        rows.append(extra)
    return rows


async def _seed_candidate_and_jobs(factory: Any) -> SourceRevisionSnapshot:
    await seed_candidate(factory)
    await seed_scorable_job(factory, raw_hash="match-revisions-a")
    await seed_scorable_job(factory, raw_hash="match-revisions-b")
    await seed_unscorable_job(factory, raw_hash="match-revisions-unscorable")
    async with factory() as session:
        return await load_source_revision_snapshot(session)


def _check(factory: Any, driver: ScriptedReadDriver) -> tuple[
    Any,
    list[tuple[Any, ...]],
    list[tuple[Any, ...]],
]:
    before = run_async(snapshot_sqlite(factory))

    async def _body() -> Any:
        async with factory() as session:
            return await check_graph_revision_consistency(session, driver)

    result = run_async(_body())
    after = run_async(snapshot_sqlite(factory))
    return result, before, after


def test_exact_match_accepts_equivalent_utc_timestamp_formats(
    sqlite_factory: Any,
) -> None:
    snapshot = run_async(_seed_candidate_and_jobs(sqlite_factory))
    driver = revision_read_driver(
        candidates=_candidate_rows(snapshot),
        jobs=_job_rows(snapshot),
    )

    result, before, after = _check(sqlite_factory, driver)

    assert result.is_consistent is True
    assert result.error_code is None
    assert result.rebuild_instruction is None
    assert result.scorable_job_ids == frozenset(job.id for job in snapshot.jobs)
    assert before == after
    assert driver.write_queries == []
    assert all("source_updated_at" in query for query in driver.queries)


@pytest.mark.parametrize(
    "case",
    [
        "missing_candidate",
        "extra_candidate",
        "mismatched_candidate",
        "missing_job",
        "extra_job",
        "mismatched_job",
    ],
)
def test_revision_difference_rebuild_required(
    sqlite_factory: Any,
    case: str,
) -> None:
    snapshot = run_async(_seed_candidate_and_jobs(sqlite_factory))
    candidate_rows = _candidate_rows(snapshot)
    job_rows = _job_rows(snapshot)

    if case == "missing_candidate":
        candidate_rows = []
    elif case == "extra_candidate":
        candidate_rows.append(
            {"id": "unexpected", "source_updated_at": "2026-01-01T00:00:00Z"}
        )
    elif case == "mismatched_candidate":
        candidate_rows = _candidate_rows(
            snapshot,
            updated_at="2026-01-01T00:00:00Z",
        )
    elif case == "missing_job":
        job_rows = _job_rows(snapshot, omit=snapshot.jobs[0].id)
    elif case == "extra_job":
        job_rows = _job_rows(
            snapshot,
            extra={
                "id": "99999999-9999-4999-8999-999999999999",
                "source_updated_at": "2026-01-01T00:00:00Z",
            },
        )
    elif case == "mismatched_job":
        job_rows = _job_rows(
            snapshot,
            override=(snapshot.jobs[0].id, "2026-01-01T00:00:00Z"),
        )
    driver = revision_read_driver(candidates=candidate_rows, jobs=job_rows)

    result, before, after = _check(sqlite_factory, driver)

    assert result.is_consistent is False
    assert result.error_code == NEO4J_REBUILD_REQUIRED
    assert result.scorable_job_ids == frozenset()
    assert result.rebuild_instruction is not None
    assert CANONICAL_COMPOSE_REBUILD_COMMAND in result.rebuild_instruction
    assert before == after
    assert driver.write_queries == []


def test_neo4j_query_failure_returns_unavailable_without_details(
    sqlite_factory: Any,
) -> None:
    snapshot = run_async(_seed_candidate_and_jobs(sqlite_factory))
    driver = revision_read_driver(
        candidates=_candidate_rows(snapshot),
        jobs=_job_rows(snapshot),
        failure=OSError("bolt://neo4j:7687 password=super-secret"),
    )

    result, before, after = _check(sqlite_factory, driver)

    assert result.is_consistent is False
    assert result.error_code == NEO4J_UNAVAILABLE
    assert result.rebuild_instruction is None
    assert result.scorable_job_ids == frozenset()
    assert "bolt://" not in result.message.lower()
    assert "password" not in result.message.lower()
    assert "super-secret" not in result.message
    assert before == after


def test_empty_scorable_corpus_with_candidate_is_consistent(
    sqlite_factory: Any,
) -> None:
    async def _setup() -> SourceRevisionSnapshot:
        await seed_candidate(sqlite_factory)
        async with sqlite_factory() as session:
            return await load_source_revision_snapshot(session)

    snapshot = run_async(_setup())
    assert snapshot.candidate is not None
    assert snapshot.jobs == ()
    driver = revision_read_driver(candidates=_candidate_rows(snapshot), jobs=[])

    result, before, after = _check(sqlite_factory, driver)

    assert result.is_consistent is True
    assert result.error_code is None
    assert result.scorable_job_ids == frozenset()
    assert before == after
    assert driver.write_queries == []


def test_consistency_owner_is_read_only_and_reuses_snapshot_query() -> None:
    source = inspect.getsource(consistency_mod)
    assert "load_source_revision_snapshot" in source
    assert "select(" not in source
    assert "JobPost" not in source
    assert "sync_candidate" not in source
    assert "sync_job" not in source
    assert "commit(" not in source
    assert "rollback(" not in source
    assert "flush(" not in source
    assert "ShopAIKey" not in source
    assert "provider" not in source
    assert "MERGE" not in source
    assert "DELETE" not in source
    assert "ponytail: O(n)" in source


def test_rebuild_inputs_and_revision_snapshot_share_scorable_boundary(
    sqlite_factory: Any,
) -> None:
    snapshot = run_async(_seed_candidate_and_jobs(sqlite_factory))

    async def _body() -> tuple[Any, Any, Any]:
        async with sqlite_factory() as session:
            return await load_rebuild_inputs(
                session,
                expected_model=LOCKED_EMBEDDING_MODEL,
                expected_dimensions=LOCKED_EMBEDDING_DIMENSIONS,
            )

    profile, profile_updated_at, scorable = run_async(_body())

    assert profile is not None
    assert snapshot.candidate == SourceRevision("active", profile_updated_at)
    assert {
        SourceRevision(job.job_id, job.source_updated_at) for job in scorable
    } == set(snapshot.jobs)
