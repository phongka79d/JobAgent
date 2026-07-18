"""Unit tests for shared exact-Job scoring (02A) and evaluation service (02B)."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_TIMEOUT,
    EmbeddingAdapterError,
)
from app.db.models.jobs import JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL
from app.db.session import build_async_engine
from app.graph import retrieval as retrieval_mod
from app.graph.consistency import NEO4J_REBUILD_REQUIRED, NEO4J_UNAVAILABLE
from app.graph.rebuild_snapshot import load_source_revision_snapshot
from app.graph.retrieval import (
    JobRetrievalError,
    RetrievedJobCandidate,
    retrieve_exact_job_candidate,
)
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as eval_repo
from app.repositories import profiles as prof_repo
from app.schemas.jobs import parse_job_post_extraction
from app.schemas.matching import MatchResult, parse_match_result
from app.schemas.profile import parse_candidate_profile, parse_job_preferences
from app.services import job_evaluation as job_evaluation_mod
from app.services import match_scoring as match_scoring_mod
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.job_evaluation import (
    ERROR_ACTIVE_PROFILE_REQUIRED,
    ERROR_EVALUATION_CONTEXT_CHANGED,
    ERROR_INVALID_MATCH_RESULT,
    ERROR_JOB_NOT_FOUND,
    ERROR_JOB_NOT_SCORABLE,
    evaluate_job,
)
from app.services.match_components import score_match_candidate
from app.services.match_explanations import project_match_result
from app.services.match_scoring import (
    build_match_score_components,
    project_single_job_match,
    score_retrieved_candidates,
    score_single_job,
)
from app.services.skill_normalization import SkillNormalizer

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.matching import ScriptedRead, ScriptedReadDriver
from tests.support.db_migration import run_async, session_factory
from tests.support.graph_rebuild import (
    embedding_vector,
    extraction_payload,
    profile_payload,
    seed_scorable_job,
    seed_unscorable_job,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"
_CV_SOURCE_HASH = "cv-source-hash-for-evaluation-tests-0001"


@pytest.fixture
def normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(FIXTURE_PATH)


@pytest.fixture
def sqlite_factory(migrated_sqlite: Path) -> Iterator[Any]:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    try:
        yield factory
    finally:
        run_async(engine.dispose())


def _profile() -> Any:
    return parse_candidate_profile(profile_payload(include_excluded=False))


def _preferences() -> Any:
    return parse_job_preferences(
        {
            "target_roles": ["Backend Engineer"],
            "preferred_locations": ["Berlin"],
            "acceptable_work_modes": ["hybrid"],
            "target_seniority": ["mid"],
        }
    )


def _job(
    *,
    job_id: str = "job-exact-1",
    semantic_similarity: float = 0.91,
    quality: str = JOB_JD_QUALITY_FULL,
    source_url: str | None = None,
) -> RetrievedJobCandidate:
    extraction = parse_job_post_extraction(extraction_payload())
    return RetrievedJobCandidate(
        job_id=job_id,
        semantic_similarity=semantic_similarity,
        extraction=extraction,
        jd_quality=quality,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# 02A pure scoring boundary
# ---------------------------------------------------------------------------


def test_pure_scoring_module_has_no_provider_graph_or_sqlite_io() -> None:
    source = inspect.getsource(match_scoring_mod)
    assert "session_scope" not in source
    assert "AsyncSession" not in source
    assert "embed_text" not in source
    assert "check_graph_revision_consistency" not in source
    assert "neo4j" not in source.lower()
    assert "commit(" not in source
    assert "upsert_" not in source
    assert "compute_skill_coverage" in source
    assert "score_match_candidate" in source
    assert "project_match_result" in source
    assert "rank_match_candidates" in source


def test_exact_and_top_n_share_component_map_and_explanation(
    normalizer: SkillNormalizer,
) -> None:
    profile = _profile()
    preferences = _preferences()
    job = _job(semantic_similarity=0.88, quality=JOB_JD_QUALITY_PARTIAL)

    components, coverage = build_match_score_components(
        profile=profile,
        preferences=preferences,
        job=job,
        normalizer=normalizer,
    )
    exact_input = score_single_job(
        profile=profile,
        preferences=preferences,
        job=job,
        normalizer=normalizer,
    )
    exact_result = project_single_job_match(
        profile=profile,
        preferences=preferences,
        job=job,
        normalizer=normalizer,
    )
    multi = score_retrieved_candidates(
        profile=profile,
        preferences=preferences,
        candidates=[job],
        normalizer=normalizer,
        limit=1,
    )

    scored_via_owner = score_match_candidate(components)
    projected = project_match_result(exact_input)

    assert exact_input.scored == scored_via_owner
    assert exact_input.skill_coverage == coverage
    assert exact_result == projected
    assert multi.count == 1
    assert multi.results[0] == exact_result
    assert multi.results[0].job_id == job.job_id
    assert multi.results[0].components.semantic_similarity == 0.88
    assert multi.results[0].quality_multiplier == 0.85
    assert multi.results[0].matched_required_skills
    parse_match_result(exact_result.model_dump(mode="json"))


def test_score_retrieved_candidates_orders_with_shared_single_job_path(
    normalizer: SkillNormalizer,
) -> None:
    profile = _profile()
    preferences = _preferences()
    high = _job(job_id="job-high", semantic_similarity=0.95)
    low = _job(job_id="job-low", semantic_similarity=0.20)

    ranked = score_retrieved_candidates(
        profile=profile,
        preferences=preferences,
        candidates=[low, high],
        normalizer=normalizer,
        limit=2,
    )
    high_only = project_single_job_match(
        profile=profile,
        preferences=preferences,
        job=high,
        normalizer=normalizer,
    )
    low_only = project_single_job_match(
        profile=profile,
        preferences=preferences,
        job=low,
        normalizer=normalizer,
    )

    assert [row.job_id for row in ranked.results] == ["job-high", "job-low"]
    assert ranked.results[0] == high_only
    assert ranked.results[1] == low_only
    assert ranked.results[0].final_score > ranked.results[1].final_score


def test_exact_job_outside_vector_top_50_is_scorable(
    sqlite_factory: Any,
    normalizer: SkillNormalizer,
) -> None:
    """A consistent scorable Job outside vector top-50 still scores exactly."""
    outside_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-outside-top50")
    )
    distractors = {
        run_async(
            seed_scorable_job(
                sqlite_factory,
                raw_hash=f"eval-distractor-{index}",
            )
        )
        for index in range(50)
    }
    scorable = frozenset(distractors | {outside_id})
    assert outside_id in scorable
    assert len(scorable) == 51

    vector = embedding_vector(0.61)
    # Vector top-50 deliberately omits the target job.
    vector_driver = ScriptedReadDriver(
        (
            ScriptedRead(
                "db.index.vector.queryNodes",
                [
                    {"id": job_id, "score": 0.99 - (index * 0.001)}
                    for index, job_id in enumerate(sorted(distractors))
                ],
            ),
        ),
    )
    exact_driver = ScriptedReadDriver(
        (
            ScriptedRead(
                "vector.similarity.cosine",
                [{"id": outside_id, "score": 0.73}],
            ),
        ),
    )

    async def _vector_body() -> list[RetrievedJobCandidate]:
        async with sqlite_factory() as session:
            return await retrieval_mod.retrieve_job_candidates(
                session,
                vector_driver,
                candidate_vector=vector,
                scorable_job_ids=scorable,
            )

    async def _exact_body() -> RetrievedJobCandidate:
        async with sqlite_factory() as session:
            return await retrieve_exact_job_candidate(
                session,
                exact_driver,
                job_id=outside_id,
                candidate_vector=vector,
                scorable_job_ids=scorable,
            )

    vector_hits = run_async(_vector_body())
    exact_hit = run_async(_exact_body())

    assert outside_id not in {candidate.job_id for candidate in vector_hits}
    assert exact_hit.job_id == outside_id
    assert exact_hit.semantic_similarity == 0.73
    assert "vector.similarity.cosine" in exact_driver.queries[0]
    assert "db.index.vector.queryNodes" not in exact_driver.queries[0]
    assert exact_driver.parameters[0]["job_id"] == outside_id
    assert vector_driver.parameters[0]["k"] == 50

    profile = _profile()
    preferences = _preferences()
    result: MatchResult = project_single_job_match(
        profile=profile,
        preferences=preferences,
        job=exact_hit,
        normalizer=normalizer,
    )
    assert result.job_id == outside_id
    assert result.components.semantic_similarity == 0.73
    assert result.final_score is not None
    assert result.matched_required_skills
    parse_match_result(result.model_dump(mode="json"))


def test_exact_job_missing_graph_embedding_fails_safely(
    sqlite_factory: Any,
) -> None:
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-missing-embedding")
    )
    driver = ScriptedReadDriver(
        (ScriptedRead("vector.similarity.cosine", []),),
    )

    async def _body() -> None:
        async with sqlite_factory() as session:
            await retrieve_exact_job_candidate(
                session,
                driver,
                job_id=job_id,
                candidate_vector=embedding_vector(0.2),
                scorable_job_ids=frozenset({job_id}),
            )

    with pytest.raises(JobRetrievalError, match="no embedding"):
        run_async(_body())


def test_exact_job_wrong_returned_id_fails_safely(sqlite_factory: Any) -> None:
    job_id = run_async(seed_scorable_job(sqlite_factory, raw_hash="eval-wrong-id"))
    driver = ScriptedReadDriver(
        (
            ScriptedRead(
                "vector.similarity.cosine",
                [{"id": "someone-else", "score": 0.5}],
            ),
        ),
    )

    async def _body() -> None:
        async with sqlite_factory() as session:
            await retrieve_exact_job_candidate(
                session,
                driver,
                job_id=job_id,
                candidate_vector=embedding_vector(0.3),
                scorable_job_ids=frozenset({job_id}),
            )

    with pytest.raises(JobRetrievalError, match="requested Job id"):
        run_async(_body())


@dataclass(frozen=True, slots=True)
class _FakeJobFacts:
    job_id: str
    semantic_similarity: float
    extraction: Any
    jd_quality: str
    source_url: str | None


def test_job_scoring_facts_protocol_accepts_plain_hydrated_facts(
    normalizer: SkillNormalizer,
) -> None:
    """Exact path can feed pure scoring without top-N retrieval DTO coupling."""
    extraction = parse_job_post_extraction(extraction_payload())
    facts = _FakeJobFacts(
        job_id="plain-job",
        semantic_similarity=0.66,
        extraction=extraction,
        jd_quality=JOB_JD_QUALITY_FULL,
        source_url="https://example.com/j",
    )
    result = project_single_job_match(
        profile=_profile(),
        preferences=_preferences(),
        job=facts,
        normalizer=normalizer,
    )
    assert result.job_id == "plain-job"
    assert result.components.semantic_similarity == 0.66
    assert result.source_url == "https://example.com/j"


# ---------------------------------------------------------------------------
# 02B evaluation service orchestration
# ---------------------------------------------------------------------------


def _as_z(value: datetime) -> str:
    if value.tzinfo is None:
        stamp = value.replace(tzinfo=UTC)
    else:
        stamp = value.astimezone(UTC)
    return stamp.isoformat().replace("+00:00", "Z")


async def _seed_eval_profile(
    factory: Any,
    *,
    source_hash: str = _CV_SOURCE_HASH,
    preferences: dict[str, Any] | None = None,
) -> str:
    """Seed active profile + approved CV document + preferences; return att id."""
    profile = parse_candidate_profile(profile_payload(include_excluded=False))
    prefs = preferences or {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Berlin"],
        "acceptable_work_modes": ["hybrid"],
        "target_seniority": ["mid"],
    }
    async with factory() as session:
        att = await att_repo.create_staged(
            session,
            file_hash="eval-cv-hash",
            original_name="cv.pdf",
            size_bytes=100,
            storage_path="eval/cv.pdf",
            page_count=1,
        )
        await att_repo.mark_active(session, att.id)
        await prof_repo.upsert_active_profile(
            session,
            active_attachment_id=att.id,
            profile_json=profile.model_dump(mode="json"),
        )
        await cv_doc_repo.upsert_document(
            session,
            attachment_id=att.id,
            document_json={"sections": []},
            profile_json=profile.model_dump(mode="json"),
            outline_json={"sections": []},
            extraction_version="cv-document-v1",
            source_hash=source_hash,
        )
        await prof_repo.upsert_job_preferences(
            session,
            preferences_json=prefs,
        )
        await session.commit()
        return att.id


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


def _eval_driver(
    *,
    candidates: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    exact_rows: list[dict[str, Any]] | None = None,
    failure: Exception | None = None,
    fail_on_query_contains: str | None = None,
) -> ScriptedReadDriver:
    scripts: list[ScriptedRead] = [
        ScriptedRead("MATCH (c:Candidate)", candidates),
        ScriptedRead("MATCH (j:Job)", jobs),
    ]
    if exact_rows is not None:
        scripts.append(ScriptedRead("vector.similarity.cosine", exact_rows))
    return ScriptedReadDriver(
        tuple(scripts),
        failure=failure,
        fail_on_query_contains=fail_on_query_contains,
    )


def _run_eval(
    factory: Any,
    *,
    job_id: str,
    driver: ScriptedReadDriver,
    embedding_client: FakeEmbeddingClient,
    normalizer: SkillNormalizer | None = None,
) -> Any:
    return run_async(
        evaluate_job(
            session_factory=factory,
            job_id=job_id,
            graph_driver=driver,
            embedding_client=embedding_client,
            normalizer=normalizer or SkillNormalizer.from_path(FIXTURE_PATH),
        )
    )


def test_evaluate_job_no_profile_before_provider_work(
    sqlite_factory: Any,
) -> None:
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-no-profile")
    )
    emb = FakeEmbeddingClient()
    driver = _eval_driver(candidates=[], jobs=[], exact_rows=[])

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.outcome is None
    assert result.error_code == ERROR_ACTIVE_PROFILE_REQUIRED
    assert result.evaluation is None
    assert emb.call_count == 0
    assert driver.session_enter == 0
    assert driver.queries == []


def test_evaluate_job_missing_returns_job_not_found(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    emb = FakeEmbeddingClient()
    driver = _eval_driver(candidates=[], jobs=[], exact_rows=[])

    result = _run_eval(
        sqlite_factory,
        job_id="00000000-0000-4000-8000-000000000099",
        driver=driver,
        embedding_client=emb,
    )

    assert result.ok is False
    assert result.error_code == ERROR_JOB_NOT_FOUND
    assert emb.call_count == 0
    assert driver.session_enter == 0


def test_evaluate_job_unscorable_before_provider_work(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_unscorable_job(sqlite_factory, raw_hash="eval-unscorable")
    )
    emb = FakeEmbeddingClient()
    driver = _eval_driver(candidates=[], jobs=[], exact_rows=[])

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == ERROR_JOB_NOT_SCORABLE
    assert emb.call_count == 0
    assert driver.session_enter == 0
    assert driver.queries == []


def test_evaluate_job_creates_then_reuses_with_zero_repeat_calls(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-create-reuse")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.87}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.21))

    first = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )
    assert first.ok is True
    assert first.outcome == "created"
    assert first.evaluation is not None
    assert first.evaluation.job_id == job_id
    assert first.evaluation.result.job_id == job_id
    assert first.evaluation.result.components.semantic_similarity == 0.87
    assert first.evaluation.matching_contract_version == MATCHING_CONTRACT_VERSION
    assert emb.call_count == 1
    cosine_queries = [
        q for q in driver.queries if "vector.similarity.cosine" in q
    ]
    assert len(cosine_queries) == 1
    first_session_enter = driver.session_enter
    first_query_count = len(driver.queries)

    second = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )
    assert second.ok is True
    assert second.outcome == "reused"
    assert second.evaluation is not None
    assert second.evaluation.id == first.evaluation.id
    assert second.evaluation.result.summary == first.evaluation.result.summary
    # Zero repeat provider / graph-scoring / explanation work.
    assert emb.call_count == 1
    assert driver.session_enter == first_session_enter
    assert len(driver.queries) == first_query_count

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 1


def test_evaluate_job_context_change_discards_without_new_row(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-context-drift")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.71}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.31))

    original_resolve = job_evaluation_mod._resolve_context
    resolve_count = {"n": 0}

    async def resolve_with_drift(
        session: Any, *, job_id: str
    ) -> Any:
        resolved = await original_resolve(session, job_id=job_id)
        resolve_count["n"] += 1
        # Post-score revalidation returns a drifted context hash.
        if resolve_count["n"] >= 2 and isinstance(
            resolved, job_evaluation_mod._ResolvedContext
        ):
            drifted_facts = EvaluationContextFacts(
                job_id=resolved.facts.job_id,
                job_revision=resolved.facts.job_revision,
                active_attachment_id=resolved.facts.active_attachment_id,
                cv_source_hash="cv-source-hash-CHANGED-after-score-9999",
                profile_revision=resolved.facts.profile_revision,
                preferences_revision=resolved.facts.preferences_revision,
                matching_contract_version=(
                    resolved.facts.matching_contract_version
                ),
            )
            return job_evaluation_mod._ResolvedContext(
                job_id=resolved.job_id,
                profile=resolved.profile,
                preferences=resolved.preferences,
                facts=drifted_facts,
                context_hash=evaluation_context_hash(drifted_facts),
            )
        return resolved

    monkeypatch.setattr(
        job_evaluation_mod, "_resolve_context", resolve_with_drift
    )

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == ERROR_EVALUATION_CONTEXT_CHANGED
    assert result.evaluation is None
    assert result.outcome is None
    assert resolve_count["n"] >= 2
    assert emb.call_count == 1

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 0


def test_evaluate_job_uniqueness_race_reloads_winner(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-unique-race")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.64}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.41))

    real_insert = eval_repo.insert_evaluation
    winner_id: dict[str, str] = {}
    original_resolve = job_evaluation_mod._resolve_context
    recheck_count = {"n": 0}

    async def resolve_with_race(session: Any, *, job_id: str) -> Any:
        resolved = await original_resolve(session, job_id=job_id)
        recheck_count["n"] += 1
        # On post-score revalidation, plant a concurrent unique winner.
        if recheck_count["n"] == 2 and isinstance(
            resolved, job_evaluation_mod._ResolvedContext
        ):
            row, created = await real_insert(
                session,
                job_id=resolved.job_id,
                active_attachment_id=resolved.facts.active_attachment_id,
                evaluation_context_hash=resolved.context_hash,
                job_revision=resolved.facts.job_revision,
                profile_revision=resolved.facts.profile_revision,
                preferences_revision=resolved.facts.preferences_revision,
                cv_source_hash=resolved.facts.cv_source_hash,
                matching_contract_version=(
                    resolved.facts.matching_contract_version
                ),
                result={
                    "job_id": resolved.job_id,
                    "title": "Backend Engineer",
                    "company": "Acme",
                    "location": None,
                    "work_mode": "hybrid",
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
                    "summary": "concurrent-winner",
                },
            )
            assert created is True
            winner_id["id"] = row.id
        return resolved

    monkeypatch.setattr(job_evaluation_mod, "_resolve_context", resolve_with_race)

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is True
    assert result.outcome == "reused"
    assert result.evaluation is not None
    assert result.evaluation.id == winner_id["id"]
    assert result.evaluation.result.summary == "concurrent-winner"
    assert emb.call_count == 1

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 1


def test_evaluate_job_graph_unavailable_no_false_success(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-graph-down")
    )
    emb = FakeEmbeddingClient()
    driver = _eval_driver(
        candidates=[],
        jobs=[],
        failure=OSError("neo4j down"),
    )

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == NEO4J_UNAVAILABLE
    assert result.evaluation is None
    assert emb.call_count == 0

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 0


def test_evaluate_job_rebuild_required_no_false_success(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-rebuild")
    )
    candidates, _jobs = run_async(_revision_rows(sqlite_factory))
    # Empty graph jobs while SQLite has a scorable Job → rebuild required.
    driver = _eval_driver(candidates=candidates, jobs=[])
    emb = FakeEmbeddingClient()

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == NEO4J_REBUILD_REQUIRED
    assert result.evaluation is None
    assert emb.call_count == 0


def test_evaluate_job_embedding_failure_no_persist(
    sqlite_factory: Any,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-embed-fail")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.9}],
    )
    emb = FakeEmbeddingClient(
        error=EmbeddingAdapterError(
            FAILURE_EMBEDDING_TIMEOUT, "timeout"
        )
    )

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == FAILURE_EMBEDDING_TIMEOUT
    assert result.evaluation is None
    assert emb.call_count == 1
    assert not any("vector.similarity.cosine" in q for q in driver.queries)

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 0


def test_evaluate_job_invalid_result_not_persisted(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-invalid-result")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.55}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.15))

    monkeypatch.setattr(
        job_evaluation_mod,
        "project_single_job_match",
        lambda **kwargs: {"job_id": job_id, "summary": "incomplete"},
    )

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is False
    assert result.error_code == ERROR_INVALID_MATCH_RESULT
    assert result.evaluation is None

    async def _count() -> int:
        async with sqlite_factory() as session:
            return await eval_repo.count_for_job(session, job_id)

    assert run_async(_count()) == 0


def test_evaluate_job_no_open_transaction_during_external_work(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-txn-probe")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.82}],
    )

    active_scopes = {"depth": 0}
    real_session_scope = job_evaluation_mod.session_scope

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

    monkeypatch.setattr(job_evaluation_mod, "session_scope", tracking_scope)

    embed_depths: list[int] = []
    project_depths: list[int] = []

    class ProbeEmbedding(FakeEmbeddingClient):
        def embed_text(self, text: str) -> list[float]:
            embed_depths.append(active_scopes["depth"])
            return super().embed_text(text)

    real_project = job_evaluation_mod.project_single_job_match

    def project_probe(*args: Any, **kwargs: Any) -> MatchResult:
        project_depths.append(active_scopes["depth"])
        return real_project(*args, **kwargs)

    monkeypatch.setattr(
        job_evaluation_mod, "project_single_job_match", project_probe
    )

    emb = ProbeEmbedding(vector=embedding_vector(0.27))
    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )

    assert result.ok is True
    assert result.outcome == "created"
    assert embed_depths == [0]
    assert project_depths == [0]
    assert emb.call_count == 1


def test_evaluate_job_orchestrator_composes_accepted_owners() -> None:
    source = inspect.getsource(job_evaluation_mod)
    assert "check_graph_revision_consistency" in source
    assert "retrieve_exact_job_candidate" in source
    assert "project_single_job_match" in source
    assert "evaluation_context_hash" in source
    assert "insert_evaluation" in source
    assert "ERROR_EVALUATION_CONTEXT_CHANGED" in source
    assert "build_candidate_embedding_text_v1" in source
    # No formula fork / second component map.
    assert "compute_skill_coverage" not in source
    assert "rank_match_candidates" not in source
    assert "score_match_candidate" not in source
    # No Agent / API / deletion.
    assert "match_jobs" not in source or "score_retrieved_candidates" not in source


def test_evaluate_job_exact_score_uses_shared_scorer_once(
    sqlite_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_async(_seed_eval_profile(sqlite_factory))
    job_id = run_async(
        seed_scorable_job(sqlite_factory, raw_hash="eval-shared-scorer")
    )
    candidates, jobs = run_async(_revision_rows(sqlite_factory))
    driver = _eval_driver(
        candidates=candidates,
        jobs=jobs,
        exact_rows=[{"id": job_id, "score": 0.77}],
    )
    emb = FakeEmbeddingClient(vector=embedding_vector(0.19))

    real_project = job_evaluation_mod.project_single_job_match
    score_calls = {"n": 0}

    def counting_project(*args: Any, **kwargs: Any) -> MatchResult:
        score_calls["n"] += 1
        return real_project(*args, **kwargs)

    monkeypatch.setattr(
        job_evaluation_mod, "project_single_job_match", counting_project
    )

    result = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )
    assert result.ok is True
    assert score_calls["n"] == 1
    assert emb.call_count == 1
    assert sum(1 for q in driver.queries if "vector.similarity.cosine" in q) == 1

    # Reuse: zero scoring calls.
    second = _run_eval(
        sqlite_factory, job_id=job_id, driver=driver, embedding_client=emb
    )
    assert second.ok is True
    assert second.outcome == "reused"
    assert score_calls["n"] == 1
    assert emb.call_count == 1
