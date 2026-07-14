"""Rebuild behavior: scoped clear, counts, Candidate/Job reuse, repeat, failure."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from app.core.settings import clear_settings_cache
from app.db.session import build_async_engine
from app.graph.rebuild import RebuildError, rebuild_graph
from app.services.skill_normalization import SkillNormalizer

from tests.fakes.graph_rebuild import FakeNeo4jDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    embedding_vector,
    seed_candidate,
    seed_scorable_job,
    seed_unscorable_job,
    settings,
    skills_fixture,
    snapshot_sqlite,
)


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_scoped_clear_preserves_unrelated_and_rebuilds_jobs(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()
    driver.seed_unrelated("unrelated-node")
    driver.candidates.add("stale")
    driver.jobs.add("stale-job")
    driver.skills.add("stale-skill")

    async def _setup() -> None:
        await seed_scorable_job(factory, raw_hash="hash-job-a", quality="full")
        await seed_scorable_job(
            factory,
            raw_hash="hash-job-b",
            quality="partial",
            vector=embedding_vector(0.02),
        )
        await seed_unscorable_job(factory, raw_hash="hash-unscorable")

    run_async(_setup())
    before = run_async(snapshot_sqlite(factory))

    async def _body() -> None:
        return await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    counts = run_async(_body())
    joined = "\n".join(driver.queries)
    assert "MATCH (c:Candidate) DETACH DELETE c" in joined
    assert "MATCH (j:Job) DETACH DELETE j" in joined
    assert "MATCH (s:Skill) DETACH DELETE s" in joined
    assert "MATCH (n) DETACH DELETE n" not in joined
    assert driver.other_nodes == {"unrelated-node"}
    assert "stale" not in driver.candidates
    assert counts.Job == 2
    assert counts.Candidate == 0
    assert counts.Skill >= 1
    assert driver.schema_statements >= 1
    after = run_async(snapshot_sqlite(factory))
    assert after == before
    assert any("MERGE (j:Job" in q for q in driver.queries)


def test_unrelated_same_type_relationships_survive_and_do_not_inflate_counts(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()
    driver.seed_unrelated("foreign-label-node")
    driver.seed_unrelated_same_type_relationships()

    async def _setup() -> None:
        await seed_candidate(factory)
        await seed_scorable_job(factory, raw_hash="hash-scoped-counts")

    run_async(_setup())

    async def _body() -> None:
        return await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    counts = run_async(_body())
    # Foreign same-type edges survive the label-scoped clear.
    assert driver.foreign_has_skill == 7
    assert driver.foreign_requires == 5
    assert driver.foreign_prefers == 3
    assert driver.foreign_related_to == 9
    assert "foreign-label-node" in driver.other_nodes
    # Printed rebuilt counts exclude foreign relationships.
    assert counts.HAS_SKILL == driver.has_skill == 1
    assert counts.REQUIRES == driver.requires == 1
    assert counts.PREFERS == driver.prefers == 1
    assert counts.HAS_SKILL != driver.foreign_has_skill
    assert counts.REQUIRES != driver.foreign_requires
    # Count Cypher is endpoint-scoped.
    count_queries = [q for q in driver.queries if "RETURN count" in q]
    assert any("(:Candidate)-[r:HAS_SKILL]->(:Skill)" in q for q in count_queries)
    assert any("(:Job)-[r:REQUIRES]->(:Skill)" in q for q in count_queries)
    assert any("(:Job)-[r:PREFERS]->(:Skill)" in q for q in count_queries)
    assert any("(:Skill)-[r:RELATED_TO]->(:Skill)" in q for q in count_queries)
    assert not any(re.search(r"MATCH\s*\(\s*\)-\[r:", q) for q in count_queries)


def test_empty_candidate_seed_only_and_scorable_jobs(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()

    async def _seed_only() -> None:
        return await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    counts = run_async(_seed_only())
    assert counts.Candidate == 0
    assert counts.Job == 0
    assert counts.Skill >= 1
    assert counts.RELATED_TO >= 0
    assert any(
        "RELATED_TO" in q or "seed_skills" in str(p)
        for q, p in zip(driver.queries, driver.parameters, strict=False)
    )


def test_with_candidate_reuses_sync_candidate_owner(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()

    async def _setup() -> None:
        await seed_candidate(factory)
        await seed_scorable_job(factory, raw_hash="hash-with-cand")

    run_async(_setup())

    async def _body() -> None:
        return await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    counts = run_async(_body())
    assert counts.Candidate == 1
    assert counts.Job == 1
    assert any("MERGE (c:Candidate" in q for q in driver.queries)
    assert any("HAS_SKILL" in q for q in driver.queries)
    has_skill_params = [
        p for p in driver.parameters if "skills" in p and "candidate_id" in p
    ]
    assert has_skill_params
    keys = {
        row["skill"]["canonical_key"]
        for row in has_skill_params[0]["skills"]
    }
    assert "python" in keys
    assert "react" not in keys


def test_rebuild_repeat_safe(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver()

    async def _setup() -> None:
        await seed_candidate(factory)
        await seed_scorable_job(factory, raw_hash="hash-repeat")

    run_async(_setup())

    async def _once() -> Any:
        return await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    first = run_async(_once())
    second = run_async(_once())
    assert first.Candidate == second.Candidate == 1
    assert first.Job == second.Job == 1


def test_rebuild_sync_failure_nonzero(
    migrated_sqlite: Path,
) -> None:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    normalizer = SkillNormalizer.from_path(skills_fixture())
    driver = FakeNeo4jDriver(fail_on_run=True)

    async def _setup() -> None:
        await seed_scorable_job(factory, raw_hash="hash-fail")

    run_async(_setup())

    async def _body() -> None:
        await rebuild_graph(
            driver,
            session_factory=factory,
            normalizer=normalizer,
            settings=settings(),
        )

    with pytest.raises(RebuildError):
        run_async(_body())
