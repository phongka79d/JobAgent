"""Embedding preflight gates for provider-free Neo4j rebuild (03D)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.settings import clear_settings_cache
from app.db.session import build_async_engine
from app.graph.rebuild import (
    CONFIGURATION_RESTORATION_GUIDANCE,
    RebuildError,
    rebuild_graph,
)
from app.repositories import jobs as jobs_repo
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS
from app.services.skill_normalization import SkillNormalizer

from tests.fakes.graph_rebuild import FakeNeo4jDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    embedding_vector,
    seed_scorable_job,
    settings,
    skills_fixture,
    snapshot_sqlite,
)


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_preflight_mismatch_before_clear_no_provider(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()
    driver.seed_unrelated()

    async def _setup() -> None:
        await seed_scorable_job(
            factory,
            raw_hash="hash-mismatch-model",
            model="wrong-model",
            dimensions=LOCKED_EMBEDDING_DIMENSIONS,
        )

    run_async(_setup())
    before = run_async(snapshot_sqlite(factory))

    async def _body() -> None:
        await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
            enforce_local_target=True,
        )

    with pytest.raises(RebuildError) as exc:
        run_async(_body())
    assert exc.value.code == "EMBEDDING_CONFIG_MISMATCH"
    assert "restore" in exc.value.message.lower() or "Restore" in exc.value.message
    assert CONFIGURATION_RESTORATION_GUIDANCE.split(".")[0] in exc.value.message
    assert not any("DETACH DELETE" in q for q in driver.queries)
    assert driver.other_nodes == {"keep-me"}
    after = run_async(snapshot_sqlite(factory))
    assert after == before


def test_preflight_non_finite_vector_before_clear(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()
    bad = embedding_vector()
    bad[0] = float("inf")

    async def _setup() -> None:
        await seed_scorable_job(
            factory,
            raw_hash="hash-nan",
            vector=bad,
        )

    run_async(_setup())

    async def _body() -> None:
        await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    with pytest.raises(RebuildError) as exc:
        run_async(_body())
    assert exc.value.code == "EMBEDDING_CONFIG_MISMATCH"
    assert not any("DETACH DELETE" in q for q in driver.queries)


def test_preflight_wrong_dimension_count(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()
    short = [0.1] * 10

    async def _setup() -> None:
        job_id = await seed_scorable_job(factory, raw_hash="hash-short-vec")
        async with factory() as session:
            row = await jobs_repo.get_by_id(session, job_id)
            assert row is not None
            row.embedding_json = short  # type: ignore[assignment]
            row.embedding_dimensions = LOCKED_EMBEDDING_DIMENSIONS
            await session.commit()

    run_async(_setup())

    async def _body() -> None:
        await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    with pytest.raises(RebuildError) as exc:
        run_async(_body())
    assert exc.value.code == "EMBEDDING_CONFIG_MISMATCH"
    assert not any("DETACH DELETE" in q for q in driver.queries)


def test_runtime_settings_model_mismatch_fails_before_clear(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()

    async def _setup() -> None:
        await seed_scorable_job(factory, raw_hash="hash-ok-model")

    run_async(_setup())

    async def _body() -> None:
        await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(model="text-embedding-3-large"),
        )

    with pytest.raises(RebuildError) as exc:
        run_async(_body())
    assert exc.value.code == "EMBEDDING_CONFIG_MISMATCH"
    assert not any("DETACH DELETE" in q for q in driver.queries)
