"""Retrieval boundary: outbox retry, top-50 vector query, SQLite rejoin."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.config import ALLOWED_EMBEDDING_DIMENSIONS, ALLOWED_EMBEDDING_MODEL
from app.db.enums import GraphSyncStatus, RecordStatus
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.errors import GraphError, GraphErrorCode
from app.graph.job_sync import JOB_UPSERT_OPERATION, is_graph_eligible
from app.graph.schema import VECTOR_INDEX_NAME
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository
from app.schemas.job_post import JobPostExtraction
from app.services.embeddings import (
    JOB_TEXT_REPRESENTATION_VERSION,
    EmbeddingVector,
    JobEmbeddingResult,
)
from app.services.jd_source import hash_canonical_text
from app.services.retrieval import (
    MAX_RELATED_EDGE_RESULTS,
    MAX_RELATED_SKILL_KEYS,
    MAX_RETRIEVAL_CANDIDATES,
    RETRIEVAL_VECTOR_INDEX_NAME,
    GraphRankHit,
    RetrievalCandidate,
    RetrievalError,
    RetrievalErrorCode,
    clamp_semantic_similarity,
    join_canonical_jobs,
    query_job_vector_index,
    query_verified_related_edges,
    retrieve_top_job_candidates,
    retry_pending_job_graph_work,
)
from app.services.skill_matching import MAX_RELATED_SOURCE_LEN, VerifiedRelatedEdge

VECTOR_DIM = ALLOWED_EMBEDDING_DIMENSIONS


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "retrieval.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _skill(
    key: str = "python",
    *,
    evidence: str = "Required: Python",
    confidence: float = 0.9,
) -> dict[str, Any]:
    return {
        "skill": {
            "canonical_key": key,
            "display_name": key.replace("_", " ").title(),
            "aliases": [],
            "category": "language" if key == "python" else None,
            "status": "verified",
            "confidence": confidence,
            "evidence": [evidence],
        },
        "confidence": confidence,
        "evidence": [evidence],
    }


def _extraction(**overrides: Any) -> JobPostExtraction:
    data: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build APIs and services.",
        "responsibilities": ["Own production services"],
        "required_skills": [_skill("python")],
        "preferred_skills": [
            _skill("kubernetes", evidence="Preferred: Kubernetes", confidence=0.7)
        ],
        "seniority": "senior",
        "min_experience_years": 5.0,
        "max_experience_years": 10.0,
        "location": "Berlin, DE",
        "work_mode": "hybrid",
        "employment_type": "full_time",
        "education_requirements": [],
        "language_requirements": [],
        "salary_text": None,
        "job_family": "Software Engineering",
        "extraction_confidence": 0.85,
        "jd_quality": "full",
    }
    data.update(overrides)
    return JobPostExtraction.model_validate(data)


def _query_vector(seed: float = 0.01) -> list[float]:
    return [float(seed)] * VECTOR_DIM


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[JobPostExtraction] = []

    def embed_job(self, job: JobPostExtraction) -> JobEmbeddingResult:
        self.calls.append(job)
        return JobEmbeddingResult(
            vectors=(
                EmbeddingVector(index=0, values=tuple(_query_vector(0.02))),
            ),
            model=ALLOWED_EMBEDDING_MODEL,
            dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
            representation_version=JOB_TEXT_REPRESENTATION_VERSION,
        )


class FakeGraphClient:
    """Injectable graph client recording queries; optional failure injection."""

    def __init__(
        self,
        *,
        vector_rows: list[dict[str, Any]] | None = None,
        run_error: BaseException | None = None,
        fetch_error: BaseException | None = None,
        project_ok: bool = True,
    ) -> None:
        self.vector_rows = list(vector_rows or [])
        self.run_error = run_error
        self.fetch_error = fetch_error
        self.project_ok = project_ok
        self.run_queries: list[tuple[str, Mapping[str, Any]]] = []
        self.fetch_queries: list[tuple[str, Mapping[str, Any]]] = []

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        params = dict(parameters) if parameters is not None else {}
        self.run_queries.append((query, params))
        if self.run_error is not None:
            raise self.run_error
        if not self.project_ok:
            raise GraphError(GraphErrorCode.UNAVAILABLE)

    async def fetch_records(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = dict(parameters) if parameters is not None else {}
        self.fetch_queries.append((query, params))
        if self.fetch_error is not None:
            raise self.fetch_error
        return list(self.vector_rows)


async def _seed_processed_job(
    db: DatabaseSessionManager,
    *,
    raw: str,
    extraction: JobPostExtraction | None = None,
    quality: str = "full",
    record_status: str = RecordStatus.ACTIVE.value,
    enqueue_outbox: bool = False,
) -> UUID:
    extraction = extraction or _extraction(jd_quality=quality)
    async with db.session_scope() as session:
        jobs = JobPostRepository(session)
        created = await jobs.create_received(
            source_type="text",
            raw_content=raw,
            raw_content_hash=hash_canonical_text(raw),
        )
        job_id = created.record.id
        await jobs.mark_processing(job_id)
        record = await jobs.mark_processed(job_id, extraction=extraction)
        if record_status == RecordStatus.IGNORED_DUPLICATE.value:
            # Peer for explicit ignore path
            peer = await jobs.create_received(
                source_type="text",
                raw_content=raw + "\npeer",
            )
            await jobs.mark_processing(peer.record.id)
            await jobs.mark_processed(
                peer.record.id,
                extraction=_extraction(
                    title="Other Role",
                    company="Other Co",
                    location="Remote",
                    jd_quality="full",
                ),
            )
            await jobs.mark_ignored_duplicate(
                job_id, duplicate_of_job_id=peer.record.id
            )
        elif record.record_status != record_status:
            # force active already default
            pass
        current = await jobs.get_by_id(job_id)
        if enqueue_outbox and current is not None and is_graph_eligible(current):
            outbox = GraphOutboxRepository(session)
            await outbox.enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=str(job_id),
                payload={"job_id": str(job_id)},
                requeue_existing=True,
            )
            await jobs.set_graph_sync_status(
                job_id, status=GraphSyncStatus.PENDING
            )
        return job_id


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_clamp_semantic_similarity_bounds() -> None:
    assert clamp_semantic_similarity(0.5) == 0.5
    assert clamp_semantic_similarity(-0.2) == 0.0
    assert clamp_semantic_similarity(1.5) == 1.0
    assert clamp_semantic_similarity(float("nan")) is None
    assert clamp_semantic_similarity(float("inf")) is None
    assert clamp_semantic_similarity("0.5") is None
    assert clamp_semantic_similarity(True) is None


def test_index_identity_locked() -> None:
    assert RETRIEVAL_VECTOR_INDEX_NAME == VECTOR_INDEX_NAME
    assert RETRIEVAL_VECTOR_INDEX_NAME == "job_embedding_vector"
    assert MAX_RETRIEVAL_CANDIDATES == 50


# ---------------------------------------------------------------------------
# Vector query boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vector_query_parameterized_and_capped() -> None:
    ids = [uuid4() for _ in range(55)]
    rows = [
        {"job_id": str(job_id), "score": 1.0 - (i * 0.01)}
        for i, job_id in enumerate(ids)
    ]
    client = FakeGraphClient(vector_rows=rows)
    hits = await query_job_vector_index(client, _query_vector())
    assert len(hits) == MAX_RETRIEVAL_CANDIDATES
    assert len({h.job_id for h in hits}) == MAX_RETRIEVAL_CANDIDATES
    assert all(0.0 <= h.semantic_similarity <= 1.0 for h in hits)

    assert len(client.fetch_queries) == 1
    query, params = client.fetch_queries[0]
    assert "db.index.vector.queryNodes" in query
    assert "$index_name" in query
    assert "$embedding" in query
    assert params["index_name"] == VECTOR_INDEX_NAME
    assert params["k"] == 50
    assert len(params["embedding"]) == VECTOR_DIM
    # No vector payload in returned hits; only id + similarity.
    assert all(isinstance(h, GraphRankHit) for h in hits)


@pytest.mark.asyncio
async def test_vector_query_dedupes_malformed_and_clamps() -> None:
    good_a = uuid4()
    good_b = uuid4()
    rows = [
        {"job_id": str(good_a), "score": 1.25},
        {"job_id": "not-a-uuid", "score": 0.9},
        {"job_id": str(good_a), "score": 0.5},  # duplicate
        {"job_id": str(good_b), "score": float("nan")},
        {"job_id": None, "score": 0.8},
        {"job_id": str(good_b), "score": -0.1},
        {"score": 0.7},
    ]
    client = FakeGraphClient(vector_rows=rows)
    hits = await query_job_vector_index(client, _query_vector())
    assert [h.job_id for h in hits] == [good_a, good_b]
    assert hits[0].semantic_similarity == 1.0
    assert hits[1].semantic_similarity == 0.0


@pytest.mark.asyncio
async def test_saved_id_filter_bounds() -> None:
    client = FakeGraphClient(vector_rows=[])
    with pytest.raises(RetrievalError) as empty:
        await query_job_vector_index(client, _query_vector(), saved_job_ids=[])
    assert empty.value.code is RetrievalErrorCode.INVALID_SAVED_IDS

    too_many = [uuid4() for _ in range(51)]
    with pytest.raises(RetrievalError) as overflow:
        await query_job_vector_index(
            client, _query_vector(), saved_job_ids=too_many
        )
    assert overflow.value.code is RetrievalErrorCode.INVALID_SAVED_IDS

    dup = uuid4()
    with pytest.raises(RetrievalError) as dups:
        await query_job_vector_index(
            client, _query_vector(), saved_job_ids=[dup, dup]
        )
    assert dups.value.code is RetrievalErrorCode.INVALID_SAVED_IDS

    # Valid filter uses exact cosine path and bound parameters.
    a, b = uuid4(), uuid4()
    client = FakeGraphClient(
        vector_rows=[
            {"job_id": str(a), "score": 0.9},
            {"job_id": str(b), "score": 0.4},
        ]
    )
    hits = await query_job_vector_index(
        client, _query_vector(), saved_job_ids=[a, b]
    )
    assert len(hits) == 2
    query, params = client.fetch_queries[0]
    assert "vector.similarity.cosine" in query
    assert params["job_ids"] == [str(a), str(b)]
    assert params["k"] == 50
    assert "index_name" not in params or params.get("index_name") is None


@pytest.mark.asyncio
async def test_invalid_vector_and_neo4j_failure_sanitized() -> None:
    client = FakeGraphClient()
    with pytest.raises(RetrievalError) as short:
        await query_job_vector_index(client, [0.1, 0.2])
    assert short.value.code is RetrievalErrorCode.INVALID_VECTOR
    assert "0.1" not in str(short.value)
    assert short.value.__cause__ is None

    bad = _query_vector()
    bad[0] = float("nan")
    with pytest.raises(RetrievalError) as nonfinite:
        await query_job_vector_index(client, bad)
    assert nonfinite.value.code is RetrievalErrorCode.INVALID_VECTOR

    client = FakeGraphClient(
        fetch_error=GraphError(GraphErrorCode.UNAVAILABLE)
    )
    with pytest.raises(RetrievalError) as down:
        await query_job_vector_index(client, _query_vector())
    assert down.value.code is RetrievalErrorCode.NEO4J_UNAVAILABLE
    assert "bolt" not in repr(down.value).lower()
    assert down.value.__cause__ is None


# ---------------------------------------------------------------------------
# Outbox retry + full retrieve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outbox_retry_success_then_retrieve(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        job_id = await _seed_processed_job(
            db,
            raw="Eligible job for outbox and retrieval.",
            enqueue_outbox=True,
        )
        client = FakeGraphClient(
            vector_rows=[{"job_id": str(job_id), "score": 0.88}]
        )
        emb = FakeEmbeddingService()
        processed = await retry_pending_job_graph_work(db, client, emb)
        assert processed == 1
        assert emb.calls  # projection embedded
        assert client.run_queries

        results = await retrieve_top_job_candidates(
            query_vector=_query_vector(),
            database=db,
            graph_client=client,
            embedding_service=emb,
            retry_outbox=False,
        )
        assert len(results) == 1
        cand = results[0]
        assert isinstance(cand, RetrievalCandidate)
        assert cand.job_id == job_id
        assert cand.semantic_similarity == pytest.approx(0.88)
        assert cand.extraction.title == "Backend Engineer"
        assert cand.record.jd_quality == "full"
        assert cand.graph_evidence == ()


@pytest.mark.asyncio
async def test_neo4j_failure_zero_claimed_matches(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        await _seed_processed_job(
            db, raw="Job present but graph down.", enqueue_outbox=True
        )
        client = FakeGraphClient(
            run_error=GraphError(GraphErrorCode.UNAVAILABLE),
            fetch_error=GraphError(GraphErrorCode.UNAVAILABLE),
        )
        emb = FakeEmbeddingService()
        with pytest.raises(RetrievalError) as excinfo:
            await retrieve_top_job_candidates(
                query_vector=_query_vector(),
                database=db,
                graph_client=client,
                embedding_service=emb,
                retry_outbox=True,
            )
        # Outbox item failure is absorbed; fetch must still fail closed.
        err = excinfo.value
        assert err.code in {
            RetrievalErrorCode.NEO4J_UNAVAILABLE,
            RetrievalErrorCode.GRAPH_FAILED,
        }
        # No successful match tuple was returned (exception path).
        assert "password" not in str(err).lower()
        assert err.__cause__ is None


@pytest.mark.asyncio
async def test_retrieve_excludes_ignored_unscorable_stale(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        active_id = await _seed_processed_job(
            db, raw="Active full job A.", quality="full"
        )
        partial_id = await _seed_processed_job(
            db,
            raw="Active partial job B.",
            extraction=_extraction(jd_quality="partial", title="Partial Role"),
            quality="partial",
        )
        unscorable_id = await _seed_processed_job(
            db,
            raw="Unscorable job C.",
            extraction=_extraction(jd_quality="unscorable", title="Bad Role"),
            quality="unscorable",
        )
        ignored_id = await _seed_processed_job(
            db,
            raw="Ignored duplicate job D.",
            record_status=RecordStatus.IGNORED_DUPLICATE.value,
        )
        stale_id = uuid4()

        # Graph title/company must not win: SQLite extraction stays canonical.
        rows = [
            {
                "job_id": str(active_id),
                "score": 0.95,
                "title": "GRAPH TITLE MUST NOT WIN",
            },
            {"job_id": str(partial_id), "score": 0.90},
            {"job_id": str(unscorable_id), "score": 0.99},
            {"job_id": str(ignored_id), "score": 0.98},
            {"job_id": str(stale_id), "score": 0.97},
            {"job_id": "garbage", "score": 0.5},
        ]
        client = FakeGraphClient(vector_rows=rows)
        emb = FakeEmbeddingService()
        results = await retrieve_top_job_candidates(
            query_vector=_query_vector(),
            database=db,
            graph_client=client,
            embedding_service=emb,
            retry_outbox=False,
        )
        assert [c.job_id for c in results] == [active_id, partial_id]
        assert results[0].extraction.title == "Backend Engineer"
        assert results[0].extraction.title != "GRAPH TITLE MUST NOT WIN"
        assert results[1].record.jd_quality == "partial"
        assert all(is_graph_eligible(c.record) for c in results)


@pytest.mark.asyncio
async def test_join_preserves_neo4j_rank_order(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        first = await _seed_processed_job(db, raw="Rank first job.")
        second = await _seed_processed_job(
            db,
            raw="Rank second job.",
            extraction=_extraction(title="Second", company="Beta"),
        )
        third = await _seed_processed_job(
            db,
            raw="Rank third job.",
            extraction=_extraction(title="Third", company="Gamma"),
        )
        # Graph returns second, first, third — join must keep that order.
        hits = [
            GraphRankHit(job_id=second, semantic_similarity=0.9),
            GraphRankHit(job_id=first, semantic_similarity=0.8),
            GraphRankHit(job_id=third, semantic_similarity=0.7),
        ]
        async with db.session_scope() as session:
            repo = JobPostRepository(session)
            joined = await join_canonical_jobs(repo, hits)
        assert [c.job_id for c in joined] == [second, first, third]
        assert [c.semantic_similarity for c in joined] == [0.9, 0.8, 0.7]


@pytest.mark.asyncio
async def test_retrieve_with_saved_id_filter(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        keep = await _seed_processed_job(db, raw="Keep via filter.")
        drop = await _seed_processed_job(
            db,
            raw="Drop not in filter.",
            extraction=_extraction(title="Drop", company="Zed"),
        )
        client = FakeGraphClient(
            vector_rows=[{"job_id": str(keep), "score": 0.77}]
        )
        results = await retrieve_top_job_candidates(
            query_vector=_query_vector(),
            database=db,
            graph_client=client,
            embedding_service=FakeEmbeddingService(),
            saved_job_ids=[keep],
            retry_outbox=False,
        )
        assert len(results) == 1
        assert results[0].job_id == keep
        query, params = client.fetch_queries[0]
        assert str(keep) in params["job_ids"]
        assert str(drop) not in params.get("job_ids", [])
        assert "vector.similarity.cosine" in query


@pytest.mark.asyncio
async def test_retrieve_empty_success_when_graph_returns_none(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        await _seed_processed_job(db, raw="Present but not in graph hits.")
        client = FakeGraphClient(vector_rows=[])
        results = await retrieve_top_job_candidates(
            query_vector=_query_vector(),
            database=db,
            graph_client=client,
            embedding_service=FakeEmbeddingService(),
            retry_outbox=False,
        )
        assert results == ()


@pytest.mark.asyncio
async def test_error_repr_hides_secrets_and_content() -> None:
    err = RetrievalError(RetrievalErrorCode.NEO4J_QUERY_FAILED)
    text = f"{err!s}{err!r}"
    assert "neo4j_query_failed" in text
    assert "password" not in text.lower()
    assert "authorization" not in text.lower()
    assert "embedding" not in text or "retrieval" in text


# ---------------------------------------------------------------------------
# Verified RELATED_TO read-only query (02A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_verified_related_filters_and_bounds() -> None:
    long_source = "s" * (MAX_RELATED_SOURCE_LEN + 50)
    client = FakeGraphClient(
        vector_rows=[
            {
                "from_key": "django",
                "to_key": "python",
                "source": "seed_taxonomy",
                "verified": True,
                "weight": 0.7,
            },
            {
                "from_key": "flask",
                "to_key": "python",
                "source": "llm_guess",
                "verified": False,
                "weight": 0.9,
            },
            {
                "from_key": "python",
                "to_key": "django",  # reverse duplicate
                "source": "seed_taxonomy",
                "verified": True,
                "weight": 0.7,
            },
            {
                "from_key": "rust",
                "to_key": "go",
                "source": long_source,
                "verified": True,
                "weight": None,
            },
            {
                "from_key": "missing_flag",
                "to_key": "python",
                "source": "ambiguous",
                # verified absent → dropped
                "weight": 1.0,
            },
            {
                "from_key": "self",
                "to_key": "self",
                "source": "noop",
                "verified": True,
            },
        ]
    )
    edges = await query_verified_related_edges(
        client, ["django", "python", "rust", "flask"]
    )
    assert len(edges) == 2
    by_pair = {
        (e.from_key, e.to_key) if e.from_key <= e.to_key else (e.to_key, e.from_key): e
        for e in edges
    }
    assert ("django", "python") in by_pair
    assert ("go", "rust") in by_pair
    assert all(isinstance(e, VerifiedRelatedEdge) for e in edges)
    assert all(e.verified is True for e in edges)
    rust_edge = by_pair[("go", "rust")]
    assert len(rust_edge.source) == MAX_RELATED_SOURCE_LEN

    query, params = client.fetch_queries[0]
    assert "RELATED_TO" in query
    assert "r.verified = true" in query
    assert "CREATE" not in query.upper().replace("RELATED_TO", "")
    assert set(params["keys"]) == {"django", "python", "rust", "flask"}
    assert params["limit"] == MAX_RELATED_EDGE_RESULTS


@pytest.mark.asyncio
async def test_query_verified_related_empty_keys_no_graph_call() -> None:
    client = FakeGraphClient(vector_rows=[{"from_key": "a", "to_key": "b"}])
    edges = await query_verified_related_edges(client, [])
    assert edges == ()
    assert client.fetch_queries == []


@pytest.mark.asyncio
async def test_query_verified_related_rejects_overlimit_keys() -> None:
    client = FakeGraphClient()
    keys = [f"skill_{i}" for i in range(MAX_RELATED_SKILL_KEYS + 1)]
    with pytest.raises(RetrievalError) as excinfo:
        await query_verified_related_edges(client, keys)
    assert excinfo.value.code is RetrievalErrorCode.INVALID_INPUT
    assert client.fetch_queries == []


@pytest.mark.asyncio
async def test_query_verified_related_graph_failure_sanitized() -> None:
    client = FakeGraphClient(
        fetch_error=GraphError(GraphErrorCode.UNAVAILABLE),
    )
    with pytest.raises(RetrievalError) as excinfo:
        await query_verified_related_edges(client, ["python"])
    err = excinfo.value
    assert err.code is RetrievalErrorCode.NEO4J_UNAVAILABLE
    assert err.__cause__ is None
    assert "password" not in str(err).lower()
