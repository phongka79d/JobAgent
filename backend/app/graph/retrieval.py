"""Read-only Neo4j vector retrieval with SQLite-authoritative hydration."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.graph.consistency import AsyncGraphReadDriver
from app.graph.constraints import JOB_EMBEDDING_VECTOR_INDEX_NAME
from app.graph.rebuild_snapshot import load_scorable_job_facts
from app.schemas.embeddings import validate_finite_vector
from app.schemas.jobs import JobPostExtraction

MAX_VECTOR_RETRIEVAL_K = 50

_VECTOR_RETRIEVAL_CYPHER = (
    "CALL db.index.vector.queryNodes($index_name, $k, $candidate_vector) "
    "YIELD node, score "
    "RETURN node.id AS id, score AS score"
)

# Exact Job.id cosine read — independent of vector top-k membership.
_EXACT_JOB_SIMILARITY_CYPHER = (
    "MATCH (j:Job {id: $job_id}) "
    "WHERE j.embedding IS NOT NULL "
    "RETURN j.id AS id, "
    "vector.similarity.cosine(j.embedding, $candidate_vector) AS score"
)


class JobRetrievalError(Exception):
    """Raised when vector retrieval cannot safely return ranked candidates."""


@dataclass(frozen=True, slots=True)
class RetrievedJobCandidate:
    """One Neo4j-ordered Job candidate hydrated from SQLite."""

    job_id: str
    semantic_similarity: float
    extraction: JobPostExtraction
    jd_quality: str
    source_url: str | None


def _clamp_similarity(value: object) -> float:
    """Clamp a Neo4j cosine score into the Plan 6 semantic_similarity range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JobRetrievalError("Neo4j vector result score is not numeric")
    score = float(value)
    if math.isnan(score):
        raise JobRetrievalError("Neo4j vector result score is not numeric")
    return max(0.0, min(1.0, score))


async def _query_job_vector_index(
    driver: AsyncGraphReadDriver,
    *,
    candidate_vector: list[float],
    k: int,
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            _VECTOR_RETRIEVAL_CYPHER,
            {
                "index_name": JOB_EMBEDDING_VECTOR_INDEX_NAME,
                "k": k,
                "candidate_vector": candidate_vector,
            },
        )
        return await result.data()


def _retrieved_ids_and_scores(
    rows: Iterable[Mapping[str, Any]],
) -> list[tuple[str, float]]:
    retrieved: list[tuple[str, float]] = []
    for row in rows:
        raw_id = row.get("id")
        if not isinstance(raw_id, str) or raw_id.strip() == "":
            raise JobRetrievalError("Neo4j vector result is missing a Job id")
        retrieved.append((raw_id, _clamp_similarity(row.get("score"))))
    return retrieved


async def retrieve_job_candidates(
    session: Any,
    driver: AsyncGraphReadDriver,
    *,
    candidate_vector: Any,
    scorable_job_ids: Iterable[str],
) -> list[RetrievedJobCandidate]:
    """Return at most top-50 vector candidates in Neo4j order.

    The caller must pass the proven revision-consistent scorable ID set from the
    pre-match consistency gate. Neo4j provides only ordered IDs/scores; all Job
    facts used by later scoring and explanation are hydrated from SQLite.
    """
    vector = validate_finite_vector(candidate_vector)
    current_scorable_ids = frozenset(scorable_job_ids)
    if not current_scorable_ids:
        return []

    rows = await _query_job_vector_index(
        driver,
        candidate_vector=vector,
        k=min(MAX_VECTOR_RETRIEVAL_K, len(current_scorable_ids)),
    )
    ids_and_scores = _retrieved_ids_and_scores(rows)
    unknown_ids = [
        job_id
        for job_id, _score in ids_and_scores
        if job_id not in current_scorable_ids
    ]
    if unknown_ids:
        raise JobRetrievalError(
            "Neo4j vector result contains Job IDs not in current scorable set"
        )

    facts = await load_scorable_job_facts(
        session,
        (job_id for job_id, _score in ids_and_scores),
    )
    missing_facts = [
        job_id for job_id, _score in ids_and_scores if job_id not in facts
    ]
    if missing_facts:
        raise JobRetrievalError(
            "SQLite hydration missing current scorable Job facts"
        )

    return [
        RetrievedJobCandidate(
            job_id=job_id,
            semantic_similarity=score,
            extraction=facts[job_id].extraction,
            jd_quality=facts[job_id].jd_quality,
            source_url=facts[job_id].source_url,
        )
        for job_id, score in ids_and_scores
    ]


async def _query_exact_job_similarity(
    driver: AsyncGraphReadDriver,
    *,
    job_id: str,
    candidate_vector: list[float],
) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(
            _EXACT_JOB_SIMILARITY_CYPHER,
            {
                "job_id": job_id,
                "candidate_vector": candidate_vector,
            },
        )
        return await result.data()


async def retrieve_exact_job_candidate(
    session: Any,
    driver: AsyncGraphReadDriver,
    *,
    job_id: str,
    candidate_vector: Any,
    scorable_job_ids: Iterable[str],
) -> RetrievedJobCandidate:
    """Return one scorable Job by exact id with Neo4j semantic similarity.

    Requires ``job_id`` in the revision-consistent scorable set from the
    pre-match consistency gate. Uses a direct Job-node cosine read and never
    depends on vector top-50 membership.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobRetrievalError("exact Job id must be a non-empty string")

    vector = validate_finite_vector(candidate_vector)
    current_scorable_ids = frozenset(scorable_job_ids)
    if job_id not in current_scorable_ids:
        raise JobRetrievalError(
            "exact Job id is not in the current scorable set"
        )

    rows = await _query_exact_job_similarity(
        driver,
        job_id=job_id,
        candidate_vector=vector,
    )
    if not rows:
        raise JobRetrievalError(
            "Neo4j exact Job read returned no embedding for requested id"
        )
    ids_and_scores = _retrieved_ids_and_scores(rows)
    if len(ids_and_scores) != 1 or ids_and_scores[0][0] != job_id:
        raise JobRetrievalError(
            "Neo4j exact Job read did not return the requested Job id"
        )
    _, score = ids_and_scores[0]

    facts = await load_scorable_job_facts(session, (job_id,))
    if job_id not in facts:
        raise JobRetrievalError(
            "SQLite hydration missing current scorable Job facts"
        )

    return RetrievedJobCandidate(
        job_id=job_id,
        semantic_similarity=score,
        extraction=facts[job_id].extraction,
        jd_quality=facts[job_id].jd_quality,
        source_url=facts[job_id].source_url,
    )


__all__ = [
    "MAX_VECTOR_RETRIEVAL_K",
    "JobRetrievalError",
    "RetrievedJobCandidate",
    "retrieve_exact_job_candidate",
    "retrieve_job_candidates",
]
