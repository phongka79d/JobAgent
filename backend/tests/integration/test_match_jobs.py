"""Integration tests for top-50 retrieval, match_jobs orchestration, and tool."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_TIMEOUT,
    EmbeddingAdapterError,
)
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
)
from app.db.session import build_async_engine
from app.graph import retrieval as retrieval_mod
from app.graph.consistency import NEO4J_REBUILD_REQUIRED, NEO4J_UNAVAILABLE
from app.graph.constraints import JOB_EMBEDDING_VECTOR_INDEX_NAME
from app.graph.rebuild_snapshot import load_source_revision_snapshot
from app.graph.rebuild_target import CANONICAL_COMPOSE_REBUILD_COMMAND
from app.graph.retrieval import JobRetrievalError, retrieve_job_candidates
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as prof_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    EmbeddingVectorError,
)
from app.schemas.jobs import parse_job_post_extraction
from app.schemas.profile import (
    parse_candidate_profile,
    parse_job_preferences,
    parse_profile_draft_payload,
)
from app.schemas.tools import ToolResult
from app.services import matching as matching_mod
from app.services.chat_history import get_history_page, history_page_as_dict
from app.services.embedding_text import build_candidate_embedding_text_v1
from app.services.matching import (
    DEFAULT_MATCH_LIMIT,
    ERROR_ACTIVE_PROFILE_MISSING,
    NO_PROFILE_MATCH_MESSAGE,
    match_jobs,
)
from app.services.skill_normalization import SkillNormalizer
from app.tools.matching import (
    ERROR_INVALID_MATCH_LIMIT,
    MATCH_JOBS_NAME,
    build_match_jobs_tool,
)
from app.tools.registry import production_registry
from sqlalchemy import text

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.matching import (
    ScriptedRead,
    ScriptedReadDriver,
    orchestration_read_driver,
)
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    embedding_vector,
    extraction_payload,
    profile_payload,
    seed_candidate,
    seed_scorable_job,
    snapshot_sqlite,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"


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


# ---------------------------------------------------------------------------
# match_jobs orchestration (Plan 6 03A)
# ---------------------------------------------------------------------------


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _as_z(value: datetime) -> str:
    if value.tzinfo is None:
        stamp = value.replace(tzinfo=UTC)
    else:
        stamp = value.astimezone(UTC)
    return stamp.isoformat().replace("+00:00", "Z")


async def _seed_match_profile(
    factory: Any,
    *,
    preferences: dict[str, Any] | None = None,
) -> None:
    await seed_candidate(factory)
    prefs = preferences or {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Berlin"],
        "acceptable_work_modes": ["hybrid"],
        "target_seniority": ["mid"],
    }
    async with factory() as session:
        await prof_repo.upsert_job_preferences(
            session,
            preferences_json=prefs,
        )
        await session.commit()


async def _seed_pending_draft_with_different_profile(factory: Any) -> None:
    """Pending replacement draft that must not affect matching."""
    draft = parse_profile_draft_payload(
        {
            "candidate_profile": {
                **profile_payload(include_excluded=False),
                "summary": "DRAFT ONLY MUST NOT MATCH",
                "skills": [
                    {
                        "skill": {
                            "canonical_key": "react",
                            "display_name": "React",
                            "aliases": ["reactjs"],
                            "category": "framework",
                        },
                        "confidence": 0.9,
                        "proficiency": "advanced",
                        "years": 2.0,
                        "source": "user_correction",
                        "excluded": False,
                        "evidence": ["Draft React only"],
                    }
                ],
            },
            "job_preferences": {
                "target_roles": ["Frontend Only Draft"],
                "preferred_locations": ["Remote Draft"],
                "acceptable_work_modes": ["remote"],
                "target_seniority": ["senior"],
            },
        }
    )
    async with factory() as session:
        await prof_repo.upsert_current_draft(
            session,
            draft_json=draft.model_dump(mode="json"),
            source_attachment_id=None,
        )
        await session.commit()


async def _revision_rows(
    factory: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with factory() as session:
        snapshot = await load_source_revision_snapshot(session)
    candidates: list[dict[str, Any]] = []
    if snapshot.candidate is not None:
        candidates.append(
            {
                "id": snapshot.candidate.id,
                "source_updated_at": _as_z(snapshot.candidate.updated_at),
            }
        )
    jobs = [
        {"id": job.id, "source_updated_at": _as_z(job.updated_at)}
        for job in snapshot.jobs
    ]
    return candidates, jobs


def _run_match(
    factory: Any,
    *,
    driver: ScriptedReadDriver,
    embedding_client: FakeEmbeddingClient,
    limit: int = DEFAULT_MATCH_LIMIT,
) -> Any:
    return run_async(
        match_jobs(
            session_factory=factory,
            graph_driver=driver,
            embedding_client=embedding_client,
            normalizer=_normalizer(),
            limit=limit,
        )
    )


def test_match_jobs_no_profile_before_provider_work(sqlite_factory: Any) -> None:
    emb = FakeEmbeddingClient()
    driver = orchestration_read_driver(candidates=[], jobs=[], vector_rows=[])
    before = run_async(snapshot_sqlite(sqlite_factory))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is False
    assert result.error_code == ERROR_ACTIVE_PROFILE_MISSING
    assert result.data.count == 0
    assert result.data.results == []
    assert "upload" in result.message.lower() or "approve" in result.message.lower()
    assert NO_PROFILE_MATCH_MESSAGE in result.message or "approve" in result.message
    assert emb.call_count == 0
    assert driver.session_enter == 0
    assert driver.queries == []
    assert run_async(snapshot_sqlite(sqlite_factory)) == before


def test_match_jobs_uses_approved_profile_with_pending_draft(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    run_async(_seed_pending_draft_with_different_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="match-approved-draft")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=[{"id": job_id, "score": 0.91}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.11))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is True
    assert result.data.count == 1
    assert emb.call_count == 1
    # Approved profile text only — draft summary/roles must not enter embedding.
    assert "DRAFT ONLY MUST NOT MATCH" not in emb.calls[0]
    assert "Frontend Only Draft" not in emb.calls[0]
    assert "Backend engineer" in emb.calls[0] or "Backend Engineer" in emb.calls[0]
    assert result.data.results[0].job_id == job_id
    assert result.data.results[0].matched_required_skills
    assert (
        result.data.results[0].matched_required_skills[0].job_skill_key == "python"
    )


def test_match_jobs_empty_corpus_success_zero_results(sqlite_factory: Any) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    assert jobs == []
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=[],
    )
    emb = FakeEmbeddingClient()

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is True
    assert result.data.count == 0
    assert result.data.limit == DEFAULT_MATCH_LIMIT
    assert emb.call_count == 1
    # Empty scorable set skips vector query inside retrieval owner.
    assert not any("queryNodes" in q for q in driver.queries)


def test_match_jobs_default_limit_and_bounds(sqlite_factory: Any) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    ids = [
        run_async(
            seed_scorable_job(
                sqlite_factory,
                raw_hash=f"match-limit-{index}",
            )
        )
        for index in range(3)
    ]
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    vector_rows = [
        {"id": ids[0], "score": 0.9},
        {"id": ids[1], "score": 0.8},
        {"id": ids[2], "score": 0.7},
    ]
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=vector_rows,
    )
    emb = FakeEmbeddingClient()

    default_result = _run_match(
        sqlite_factory, driver=driver, embedding_client=emb
    )
    assert default_result.ok is True
    assert default_result.data.limit == 10
    assert default_result.data.count == 3

    driver2 = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=vector_rows,
    )
    limited = _run_match(
        sqlite_factory,
        driver=driver2,
        embedding_client=FakeEmbeddingClient(),
        limit=1,
    )
    assert limited.ok is True
    assert limited.data.limit == 1
    assert limited.data.count == 1
    assert limited.data.results[0].job_id == ids[0]

    with pytest.raises(ValueError, match="limit must be"):
        _run_match(
            sqlite_factory,
            driver=driver2,
            embedding_client=FakeEmbeddingClient(),
            limit=0,
        )
    with pytest.raises(ValueError, match="limit must be"):
        _run_match(
            sqlite_factory,
            driver=driver2,
            embedding_client=FakeEmbeddingClient(),
            limit=11,
        )


def test_match_jobs_success_order_evidence_and_no_persistence(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    high_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="match-success-high")
    )
    low_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="match-success-low")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=[
            {"id": high_id, "score": 0.95},
            {"id": low_id, "score": 0.2},
        ],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.22))
    before = run_async(snapshot_sqlite(sqlite_factory))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is True
    assert result.error_code is None
    assert result.data.count == 2
    assert result.data.count <= 10
    ordered_ids = [row.job_id for row in result.data.results]
    assert ordered_ids == [high_id, low_id]
    top = result.data.results[0]
    assert top.final_score > result.data.results[1].final_score
    assert top.components.semantic_similarity == 0.95
    assert top.matched_required_skills
    assert top.summary
    assert "python" in {
        item.job_skill_key for item in top.matched_required_skills
    }
    assert emb.call_count == 1

    async def _expected_embedding_text() -> str:
        async with sqlite_factory() as session:
            profile_row = await prof_repo.get_active_profile(session)
            prefs_row = await prof_repo.get_job_preferences(session)
            assert profile_row is not None and prefs_row is not None
            return build_candidate_embedding_text_v1(
                parse_candidate_profile(profile_row.profile_json),
                parse_job_preferences(prefs_row.preferences_json),
            )

    assert emb.calls[0] == run_async(_expected_embedding_text())
    after = run_async(snapshot_sqlite(sqlite_factory))
    assert before == after
    assert driver.write_queries == []

    async def _tables() -> list[str]:
        async with sqlite_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' ORDER BY name"
                    )
                )
            ).all()
            return [str(row[0]) for row in rows]

    table_names = run_async(_tables())
    assert not any("score" in name.lower() for name in table_names)
    assert "match_scores" not in table_names


def test_match_jobs_provider_failure_zero_results(sqlite_factory: Any) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    run_async(seed_scorable_job(sqlite_factory, raw_hash="match-provider-fail"))
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=[],
    )
    emb = FakeEmbeddingClient(
        error=EmbeddingAdapterError(
            FAILURE_EMBEDDING_TIMEOUT,
            "simulated provider timeout",
        )
    )
    before = run_async(snapshot_sqlite(sqlite_factory))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is False
    assert result.error_code == FAILURE_EMBEDDING_TIMEOUT
    assert result.data.count == 0
    assert result.data.results == []
    assert emb.call_count == 1
    # Provider fails after consistency; vector retrieval must not run.
    assert not any("queryNodes" in q for q in driver.queries)
    assert run_async(snapshot_sqlite(sqlite_factory)) == before
    assert driver.write_queries == []


def test_match_jobs_unavailable_graph_zero_partial(sqlite_factory: Any) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    run_async(seed_scorable_job(sqlite_factory, raw_hash="match-neo4j-down"))
    emb = FakeEmbeddingClient()
    driver = orchestration_read_driver(
        candidates=[],
        jobs=[],
        failure=OSError("bolt://neo4j:7687 password=super-secret"),
    )
    before = run_async(snapshot_sqlite(sqlite_factory))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is False
    assert result.error_code == NEO4J_UNAVAILABLE
    assert result.data.count == 0
    assert emb.call_count == 0
    assert "password" not in result.message.lower()
    assert "bolt://" not in result.message.lower()
    assert run_async(snapshot_sqlite(sqlite_factory)) == before
    assert driver.write_queries == []


def test_match_jobs_stale_graph_rebuild_required_zero_partial(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    run_async(seed_scorable_job(sqlite_factory, raw_hash="match-stale"))
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    # Drop the scorable job from Neo4j revision snapshot.
    stale_jobs = jobs[1:] if jobs else []
    emb = FakeEmbeddingClient()
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=stale_jobs,
        vector_rows=[],
    )
    before = run_async(snapshot_sqlite(sqlite_factory))

    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is False
    assert result.error_code == NEO4J_REBUILD_REQUIRED
    assert result.data.count == 0
    assert result.data.results == []
    assert result.rebuild_instruction is not None
    assert CANONICAL_COMPOSE_REBUILD_COMMAND in result.rebuild_instruction
    assert emb.call_count == 0
    assert not any("queryNodes" in q for q in driver.queries)
    assert run_async(snapshot_sqlite(sqlite_factory)) == before
    assert driver.write_queries == []


def test_match_jobs_no_open_transaction_during_provider_call(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_match_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="match-txn-probe")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = orchestration_read_driver(
        candidates=candidates,
        jobs=jobs,
        vector_rows=[{"id": job_id, "score": 0.88}],
    )

    active_scopes = {"depth": 0}
    real_session_scope = matching_mod.session_scope

    @asynccontextmanager
    async def tracking_scope(
        session_factory: Any = None,
    ) -> AsyncIterator[Any]:
        active_scopes["depth"] += 1
        try:
            async with real_session_scope(session_factory) as session:
                yield session
        finally:
            active_scopes["depth"] -= 1

    monkeypatch.setattr(matching_mod, "session_scope", tracking_scope)

    depths: list[int] = []

    class ProbeEmbedding(FakeEmbeddingClient):
        def embed_text(self, text: str) -> list[float]:
            depths.append(active_scopes["depth"])
            return super().embed_text(text)

    emb = ProbeEmbedding(vector=embedding_vector(0.33))
    result = _run_match(sqlite_factory, driver=driver, embedding_client=emb)

    assert result.ok is True
    assert depths == [0]
    assert emb.call_count == 1


def test_match_jobs_orchestrator_delegates_and_is_read_only() -> None:
    source = inspect.getsource(matching_mod)
    assert "check_graph_revision_consistency" in source
    assert "build_candidate_embedding_text_v1" in source
    assert "retrieve_job_candidates" in source
    assert "compute_skill_coverage" in source
    assert "rank_match_candidates" in source
    assert "project_match_jobs_result" in source
    assert "ERROR_ACTIVE_PROFILE_MISSING" in source
    assert "profile_drafts" in source or "ERROR_ACTIVE_PROFILE_MISSING" in source
    assert "MERGE" not in source
    assert "upsert_" not in source
    assert "sync_job" not in source
    assert "sync_candidate" not in source


# ---------------------------------------------------------------------------
# match_jobs tool registration / replay / history (Plan 6 03B)
# ---------------------------------------------------------------------------


async def _seed_run(session: Any, content: str = "match tool turn") -> str:
    user = await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content=content,
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    await session.flush()
    return run.id


async def _ainvoke_match(
    tool_fn: Any,
    *,
    run_id: str,
    tool_call_id: str,
    limit: int | None = None,
) -> ToolResult:
    args: dict[str, Any] = {}
    if limit is not None:
        args["limit"] = limit
    raw = await tool_fn.ainvoke(
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": tool_fn.name,
            "args": {**args, "state": {"run_id": run_id}},
        }
    )
    if isinstance(raw, str):
        payload = json.loads(raw)
    elif hasattr(raw, "content"):
        content = raw.content
        payload = json.loads(content) if isinstance(content, str) else content
    else:
        payload = raw
    return ToolResult.model_validate(payload)


def test_production_registry_includes_match_jobs_sixth() -> None:
    names = production_registry().tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
    ]
    assert names[-1] == MATCH_JOBS_NAME
    assert "synthetic_interrupt" not in names


def test_match_jobs_tool_no_profile_terminal_failed(sqlite_factory: Any) -> None:
    async def _body() -> None:
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "no profile match")
            await session.commit()

        emb = FakeEmbeddingClient()
        driver = orchestration_read_driver(
            candidates=[], jobs=[], vector_rows=[]
        )
        tool_fn = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=driver,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        result = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_no_profile"
        )
        assert result.ok is False
        assert result.code == ERROR_ACTIVE_PROFILE_MISSING
        assert result.data is not None
        assert result.data["count"] == 0
        assert result.data["results"] == []
        assert emb.call_count == 0
        assert driver.session_enter == 0

        async with sqlite_factory() as session:
            row = await tool_repo.get_by_identity(
                session, run_id=run_id, tool_call_id="match_no_profile"
            )
            assert row is not None
            assert row.tool_name == MATCH_JOBS_NAME
            assert row.status == TOOL_EXECUTION_STATUS_FAILED
            assert row.error_code == ERROR_ACTIVE_PROFILE_MISSING

    run_async(_body())


def test_match_jobs_tool_success_replay_no_recompute(
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        await _seed_match_profile(sqlite_factory)
        job_id = await seed_scorable_job(
            sqlite_factory, raw_hash="match-tool-replay"
        )
        candidates, jobs = await _revision_rows(sqlite_factory)
        driver = orchestration_read_driver(
            candidates=candidates,
            jobs=jobs,
            vector_rows=[{"id": job_id, "score": 0.88}],
        )
        emb = FakeEmbeddingClient(vector=embedding_vector(0.22))
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "match replay")
            await session.commit()

        tool_fn = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=driver,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        first = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_replay_once", limit=5
        )
        assert first.ok is True
        assert first.data is not None
        assert first.data["count"] == 1
        assert first.data["limit"] == 5
        assert first.data["results"][0]["job_id"] == job_id
        assert emb.call_count == 1
        first_queries = list(driver.queries)

        second = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_replay_once", limit=5
        )
        assert second.model_dump(mode="json") == first.model_dump(mode="json")
        # Terminal replay must not re-embed or re-query Neo4j.
        assert emb.call_count == 1
        assert driver.queries == first_queries

        async with sqlite_factory() as session:
            rows = await tool_repo.list_for_run_ids(session, [run_id])
            matching = [r for r in rows if r.tool_call_id == "match_replay_once"]
            assert len(matching) == 1
            assert matching[0].tool_name == MATCH_JOBS_NAME
            assert matching[0].status == TOOL_EXECUTION_STATUS_COMPLETED
            assert matching[0].error_code is None
            assert matching[0].arguments_summary_json == {"limit": 5}

    run_async(_body())


def test_match_jobs_tool_pending_draft_uses_approved_only(
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        await _seed_match_profile(sqlite_factory)
        await _seed_pending_draft_with_different_profile(sqlite_factory)
        job_id = await seed_scorable_job(
            sqlite_factory, raw_hash="match-tool-draft"
        )
        candidates, jobs = await _revision_rows(sqlite_factory)
        driver = orchestration_read_driver(
            candidates=candidates,
            jobs=jobs,
            vector_rows=[{"id": job_id, "score": 0.9}],
        )
        emb = FakeEmbeddingClient(vector=embedding_vector(0.15))
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "match with draft")
            await session.commit()

        tool_fn = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=driver,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        result = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_with_draft"
        )
        assert result.ok is True
        assert emb.call_count == 1
        assert "DRAFT ONLY MUST NOT MATCH" not in emb.calls[0]
        assert "Frontend Only Draft" not in emb.calls[0]
        assert result.data is not None
        assert result.data["results"][0]["job_id"] == job_id

    run_async(_body())


def test_match_jobs_tool_provider_failure_terminal_and_history(
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        await _seed_match_profile(sqlite_factory)
        await seed_scorable_job(sqlite_factory, raw_hash="match-tool-provider")
        candidates, jobs = await _revision_rows(sqlite_factory)
        driver = orchestration_read_driver(
            candidates=candidates,
            jobs=jobs,
            vector_rows=[],
        )
        emb = FakeEmbeddingClient(
            error=EmbeddingAdapterError(
                FAILURE_EMBEDDING_TIMEOUT,
                "simulated provider timeout",
            )
        )
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "match provider fail")
            await session.commit()

        tool_fn = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=driver,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        result = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_provider_fail"
        )
        assert result.ok is False
        assert result.code == FAILURE_EMBEDDING_TIMEOUT
        assert result.data is not None
        assert result.data["count"] == 0
        assert result.data["results"] == []
        assert emb.call_count == 1

        # Replay failure without recomputation.
        replay = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_provider_fail"
        )
        assert replay.model_dump(mode="json") == result.model_dump(mode="json")
        assert emb.call_count == 1

        async with sqlite_factory() as session:
            row = await tool_repo.get_by_identity(
                session,
                run_id=run_id,
                tool_call_id="match_provider_fail",
            )
            assert row is not None
            assert row.status == TOOL_EXECUTION_STATUS_FAILED
            assert row.error_code == FAILURE_EMBEDDING_TIMEOUT
            assert row.result_json is not None
            await runs_repo.complete_run(session, run_id)
            await session.commit()

        async with sqlite_factory() as session:
            page = await get_history_page(session, limit=50, before=None)
            hist = history_page_as_dict(page)
        hist_blob = json.dumps(hist, default=str)
        assert "embedding_json" not in hist_blob
        assert "password" not in hist_blob.lower()
        user_items = [i for i in page.items if i.role == CHAT_MESSAGE_ROLE_USER]
        assert user_items
        run_view = user_items[0].run
        assert run_view is not None
        assert len(run_view.tool_executions) == 1
        te = run_view.tool_executions[0]
        assert te.tool_name == MATCH_JOBS_NAME
        assert te.status == TOOL_EXECUTION_STATUS_FAILED
        assert te.result is not None
        assert te.result.ok is False
        assert te.result.code == FAILURE_EMBEDDING_TIMEOUT
        assert te.result.data is not None
        assert te.result.data["count"] == 0

    run_async(_body())


def test_match_jobs_tool_unavailable_and_invalid_limit(
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        await _seed_match_profile(sqlite_factory)
        emb = FakeEmbeddingClient()
        driver = orchestration_read_driver(
            candidates=[],
            jobs=[],
            failure=OSError("bolt://neo4j:7687 password=super-secret"),
        )
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "match unavailable")
            await session.commit()

        tool_fn = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=driver,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        unavailable = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_unavailable"
        )
        assert unavailable.ok is False
        assert unavailable.code == NEO4J_UNAVAILABLE
        assert unavailable.data is not None
        assert unavailable.data["count"] == 0
        assert "password" not in unavailable.summary.lower()
        assert "bolt://" not in unavailable.summary.lower()
        assert emb.call_count == 0

        bad = await _ainvoke_match(
            tool_fn, run_id=run_id, tool_call_id="match_bad_limit", limit=0
        )
        assert bad.ok is False
        assert bad.code == ERROR_INVALID_MATCH_LIMIT
        # Invalid limit fails before durable execute_tool identity path.
        async with sqlite_factory() as session:
            row = await tool_repo.get_by_identity(
                session, run_id=run_id, tool_call_id="match_bad_limit"
            )
            assert row is None

        # Missing graph driver fails terminal inside durable path.
        no_driver = build_match_jobs_tool(
            session_factory=sqlite_factory,
            driver=None,
            embedding_client=emb,
            normalizer=_normalizer(),
        )
        missing = await _ainvoke_match(
            no_driver, run_id=run_id, tool_call_id="match_no_driver"
        )
        assert missing.ok is False
        assert missing.code == NEO4J_UNAVAILABLE
        async with sqlite_factory() as session:
            row = await tool_repo.get_by_identity(
                session, run_id=run_id, tool_call_id="match_no_driver"
            )
            assert row is not None
            assert row.status == TOOL_EXECUTION_STATUS_FAILED

    run_async(_body())


def test_match_jobs_tool_no_new_api_sse_or_score_store() -> None:
    """Scope: tool reuses executor; no routes/events/score tables introduced."""
    import app.tools.matching as matching_tools
    from app.tools import registry as reg_mod

    source = inspect.getsource(matching_tools)
    assert "execute_tool" in source
    assert MATCH_JOBS_NAME in source
    assert "APIRouter" not in source
    assert "include_router" not in source
    assert "EventSourceResponse" not in source
    assert "CREATE TABLE" not in source
    assert "match_scores" not in source
    assert "chat_messages" not in source

    reg_src = inspect.getsource(reg_mod)
    assert "build_production_match_tools" in reg_src
    assert reg_src.count("class ToolRegistry") == 1

