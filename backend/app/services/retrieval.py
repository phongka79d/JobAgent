"""Top-50 Neo4j vector retrieval with SQLite canonical-state join.

Owns the matching retrieval boundary only:

- one bounded Job outbox retry via the existing processor
- parameterized cosine vector query (index identity fixed, k ≤ 50)
- optional explicit saved-Job-ID filter (1–50 unique IDs)
- reload and filter against current SQLite Job rows
- read-only verified ``RELATED_TO`` edge fetch (no writes, no inference)
- never treat Neo4j node properties as canonical application state

Scoring formulas, tools, and match cards are owned by later tasks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol
from uuid import UUID

from app.config import ALLOWED_EMBEDDING_DIMENSIONS
from app.db.session import DatabaseSessionManager
from app.graph.errors import GraphError
from app.graph.job_sync import (
    DEFAULT_JOB_SYNC_BATCH_SIZE,
    JobEmbeddingPort,
    is_graph_eligible,
    process_job_sync_outbox,
)
from app.graph.schema import VECTOR_INDEX_NAME
from app.repositories.job_posts import (
    MAX_LIST_LIMIT,
    JobPostRecord,
    JobPostRepository,
    JobPostValidationError,
)
from app.schemas.job_post import JobPostExtraction
from app.services.skill_matching import (
    MAX_RELATED_SOURCE_LEN,
    VerifiedRelatedEdge,
)

# ---------------------------------------------------------------------------
# Bounds and identity
# ---------------------------------------------------------------------------

MAX_RETRIEVAL_CANDIDATES: Final[int] = 50
RETRIEVAL_VECTOR_DIMENSIONS: Final[int] = ALLOWED_EMBEDDING_DIMENSIONS
RETRIEVAL_VECTOR_INDEX_NAME: Final[str] = VECTOR_INDEX_NAME

# Bounded verified skill-graph read (Master §8.4 / Plan 6 §7.2).
MAX_RELATED_SKILL_KEYS: Final[int] = 200
MAX_RELATED_EDGE_RESULTS: Final[int] = 500

# Static Cypher: index name is bound, never interpolated from untrusted input.
# Returns only Job id + cosine score — no embedding, raw text, or secrets.
_VECTOR_QUERY_CYPHER: Final[str] = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding)
YIELD node, score
RETURN node.id AS job_id, score AS score
LIMIT $k
""".strip()

# Explicit saved-ID path: exact cosine over a bounded ID set (≤50). Still uses
# only id + score; never projects embeddings or unbounded graph records.
_FILTERED_COSINE_CYPHER: Final[str] = """
MATCH (j:Job)
WHERE j.id IN $job_ids AND j.embedding IS NOT NULL
RETURN j.id AS job_id,
       vector.similarity.cosine(j.embedding, $embedding) AS score
ORDER BY score DESC
LIMIT $k
""".strip()

# Read-only verified RELATED_TO: undirected one-hop, verified=true only.
# Returns bounded keys/source/weight — never raw documents or Skill bodies.
_VERIFIED_RELATED_CYPHER: Final[str] = """
MATCH (a:Skill)-[r:RELATED_TO]-(b:Skill)
WHERE a.canonical_key IN $keys
  AND r.verified = true
  AND a.canonical_key <> b.canonical_key
RETURN a.canonical_key AS from_key,
       b.canonical_key AS to_key,
       r.source AS source,
       r.verified AS verified,
       r.weight AS weight
LIMIT $limit
""".strip()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RetrievalErrorCode(StrEnum):
    """Stable, non-sensitive retrieval failure codes."""

    INVALID_INPUT = "retrieval_invalid_input"
    INVALID_VECTOR = "retrieval_invalid_vector"
    INVALID_SAVED_IDS = "retrieval_invalid_saved_ids"
    NEO4J_UNAVAILABLE = "neo4j_unavailable"
    NEO4J_TIMEOUT = "neo4j_timeout"
    NEO4J_QUERY_FAILED = "neo4j_query_failed"
    NEO4J_CLOSED = "neo4j_closed"
    GRAPH_FAILED = "retrieval_graph_failed"


class RetrievalError(Exception):
    """Sanitized retrieval failure (code-only str/repr; zero claimed matches)."""

    def __init__(self, code: RetrievalErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RetrievalError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GraphRankHit:
    """One sanitized vector-index hit (id + clamped similarity only)."""

    job_id: UUID
    semantic_similarity: float


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """Canonical scorable Job after SQLite rejoin (Neo4j rank preserved).

    ``record`` is always the current SQLite compact row. Graph properties never
    override title/skills/status. ``graph_evidence`` holds only bounded
    verified ``RELATED_TO`` facts when a caller attaches them; the vector join
    itself leaves it empty (skill edges are skill-global, not Job rank hits).
    """

    job_id: UUID
    semantic_similarity: float
    record: JobPostRecord
    extraction: JobPostExtraction
    graph_evidence: tuple[VerifiedRelatedEdge, ...] = ()


class GraphReadClient(Protocol):
    """Bounded read surface required for vector retrieval."""

    async def fetch_records(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


class JobGraphWriteClient(Protocol):
    """Outbox projector write surface (existing Job graph client)."""

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None: ...


class RetrievalGraphClient(GraphReadClient, JobGraphWriteClient, Protocol):
    """Combined graph surface used by retrieval (read + outbox projection)."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_query_vector(values: Sequence[float]) -> list[float]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise RetrievalError(RetrievalErrorCode.INVALID_VECTOR)
    if len(values) != RETRIEVAL_VECTOR_DIMENSIONS:
        raise RetrievalError(RetrievalErrorCode.INVALID_VECTOR)
    out: list[float] = []
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise RetrievalError(RetrievalErrorCode.INVALID_VECTOR)
        number = float(item)
        if not math.isfinite(number):
            raise RetrievalError(RetrievalErrorCode.INVALID_VECTOR)
        out.append(number)
    return out


def _normalize_saved_job_ids(
    saved_job_ids: Sequence[UUID] | None,
) -> tuple[str, ...] | None:
    """Validate optional explicit saved-ID filter; reject empty/dup/>50."""
    if saved_job_ids is None:
        return None
    if not isinstance(saved_job_ids, Sequence) or isinstance(
        saved_job_ids, (str, bytes)
    ):
        raise RetrievalError(RetrievalErrorCode.INVALID_SAVED_IDS)
    if len(saved_job_ids) < 1:
        raise RetrievalError(RetrievalErrorCode.INVALID_SAVED_IDS)
    if len(saved_job_ids) > MAX_RETRIEVAL_CANDIDATES:
        raise RetrievalError(RetrievalErrorCode.INVALID_SAVED_IDS)

    seen: set[UUID] = set()
    ordered: list[str] = []
    for item in saved_job_ids:
        if not isinstance(item, UUID):
            raise RetrievalError(RetrievalErrorCode.INVALID_SAVED_IDS)
        if item in seen:
            raise RetrievalError(RetrievalErrorCode.INVALID_SAVED_IDS)
        seen.add(item)
        ordered.append(str(item))
    return tuple(ordered)


def clamp_semantic_similarity(score: object) -> float | None:
    """Clamp a finite cosine score to [0, 1]; drop non-finite/non-numeric."""
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    value = float(score)
    if not math.isfinite(value):
        return None
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _parse_job_id(raw: object) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return UUID(text)
    except (ValueError, TypeError, AttributeError):
        return None


def _map_graph_error(exc: GraphError) -> RetrievalError:
    code = exc.code.value if hasattr(exc.code, "value") else str(exc.code)
    if code == "neo4j_unavailable":
        return RetrievalError(RetrievalErrorCode.NEO4J_UNAVAILABLE)
    if code == "neo4j_timeout":
        return RetrievalError(RetrievalErrorCode.NEO4J_TIMEOUT)
    if code == "neo4j_closed":
        return RetrievalError(RetrievalErrorCode.NEO4J_CLOSED)
    if code == "neo4j_query_failed":
        return RetrievalError(RetrievalErrorCode.NEO4J_QUERY_FAILED)
    return RetrievalError(RetrievalErrorCode.GRAPH_FAILED)


def _sanitize_graph_hits(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
) -> list[GraphRankHit]:
    """Deduplicate, clamp, and cap graph rows; preserve first-seen rank order."""
    hits: list[GraphRankHit] = []
    seen: set[UUID] = set()
    for row in rows:
        if len(hits) >= limit:
            break
        if not isinstance(row, Mapping):
            continue
        job_id = _parse_job_id(row.get("job_id"))
        if job_id is None or job_id in seen:
            continue
        similarity = clamp_semantic_similarity(row.get("score"))
        if similarity is None:
            continue
        seen.add(job_id)
        hits.append(
            GraphRankHit(job_id=job_id, semantic_similarity=similarity)
        )
    return hits


def _normalize_skill_keys_for_related(
    skill_keys: Sequence[str],
) -> tuple[str, ...]:
    """Validate and dedupe skill keys for the verified RELATED_TO read."""
    if not isinstance(skill_keys, Sequence) or isinstance(skill_keys, (str, bytes)):
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    if len(skill_keys) > MAX_RELATED_SKILL_KEYS:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in skill_keys:
        if not isinstance(raw, str):
            raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
        key = raw.strip()
        if not key:
            raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _parse_related_weight(raw: object) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value):
        return None
    return value


def _sanitize_related_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int = MAX_RELATED_EDGE_RESULTS,
) -> tuple[VerifiedRelatedEdge, ...]:
    """Keep only verified=true edges with bounded keys/source; undirected dedupe."""
    edges: list[VerifiedRelatedEdge] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        if len(edges) >= limit:
            break
        if not isinstance(row, Mapping):
            continue
        verified_raw = row.get("verified")
        if verified_raw is not True:
            # Fail closed: ambiguous/missing/false verified never boosts.
            continue
        from_raw = row.get("from_key")
        to_raw = row.get("to_key")
        if not isinstance(from_raw, str) or not isinstance(to_raw, str):
            continue
        from_key = from_raw.strip()
        to_key = to_raw.strip()
        if not from_key or not to_key or from_key == to_key:
            continue
        pair = (from_key, to_key) if from_key <= to_key else (to_key, from_key)
        if pair in seen_pairs:
            continue
        source_raw = row.get("source")
        if source_raw is None:
            source = ""
        elif not isinstance(source_raw, str):
            continue
        else:
            source = source_raw.strip()
            if len(source) > MAX_RELATED_SOURCE_LEN:
                source = source[:MAX_RELATED_SOURCE_LEN]
        seen_pairs.add(pair)
        edges.append(
            VerifiedRelatedEdge(
                from_key=from_key,
                to_key=to_key,
                source=source,
                verified=True,
                weight=_parse_related_weight(row.get("weight")),
            )
        )
    return tuple(edges)


# ---------------------------------------------------------------------------
# Graph query boundary
# ---------------------------------------------------------------------------


async def query_job_vector_index(
    client: GraphReadClient,
    embedding: Sequence[float],
    *,
    saved_job_ids: Sequence[UUID] | None = None,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
) -> list[GraphRankHit]:
    """Run the fixed parameterized top-k vector (or filtered cosine) query.

    Never returns embeddings, secrets, raw content, or unbounded graph records.
    Index name is always the locked ``job_embedding_vector`` identity.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    if limit > MAX_RETRIEVAL_CANDIDATES:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)

    vector = _validate_query_vector(embedding)
    filter_ids = _normalize_saved_job_ids(
        list(saved_job_ids) if saved_job_ids is not None else None
    )

    if RETRIEVAL_VECTOR_INDEX_NAME != VECTOR_INDEX_NAME:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)  # pragma: no cover

    if filter_ids is None:
        query = _VECTOR_QUERY_CYPHER
        parameters: dict[str, Any] = {
            "index_name": RETRIEVAL_VECTOR_INDEX_NAME,
            "k": limit,
            "embedding": vector,
        }
    else:
        query = _FILTERED_COSINE_CYPHER
        parameters = {
            "job_ids": list(filter_ids),
            "k": limit,
            "embedding": vector,
        }

    try:
        rows = await client.fetch_records(query, parameters)
    except GraphError as exc:
        raise _map_graph_error(exc) from None
    except RetrievalError:
        raise
    except Exception:
        raise RetrievalError(RetrievalErrorCode.GRAPH_FAILED) from None

    if not isinstance(rows, list):
        raise RetrievalError(RetrievalErrorCode.GRAPH_FAILED)
    return _sanitize_graph_hits(rows, limit=limit)


async def query_verified_related_edges(
    client: GraphReadClient,
    skill_keys: Sequence[str],
    *,
    limit: int = MAX_RELATED_EDGE_RESULTS,
) -> tuple[VerifiedRelatedEdge, ...]:
    """Read-only verified ``RELATED_TO`` edges for the given skill keys.

    Never writes, never infers missing edges, and never returns unverified or
    provisional relationships. Empty ``skill_keys`` yields an empty tuple with
    zero graph calls. Failures map to sanitized ``RetrievalError`` codes.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    if limit > MAX_RELATED_EDGE_RESULTS:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)

    keys = _normalize_skill_keys_for_related(skill_keys)
    if not keys:
        return ()

    # Static guard: related query must filter verified=true and must not mutate.
    if "RELATED_TO" not in _VERIFIED_RELATED_CYPHER:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)  # pragma: no cover
    if "r.verified = true" not in _VERIFIED_RELATED_CYPHER:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)  # pragma: no cover
    lowered = _VERIFIED_RELATED_CYPHER.lower()
    for banned in ("create ", "merge ", "delete ", "set ", "remove ", "detach "):
        if banned in lowered:
            raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)  # pragma: no cover

    parameters: dict[str, Any] = {
        "keys": list(keys),
        "limit": limit,
    }
    try:
        rows = await client.fetch_records(_VERIFIED_RELATED_CYPHER, parameters)
    except GraphError as exc:
        raise _map_graph_error(exc) from None
    except RetrievalError:
        raise
    except Exception:
        raise RetrievalError(RetrievalErrorCode.GRAPH_FAILED) from None

    if not isinstance(rows, list):
        raise RetrievalError(RetrievalErrorCode.GRAPH_FAILED)
    return _sanitize_related_rows(rows, limit=limit)


# ---------------------------------------------------------------------------
# SQLite join
# ---------------------------------------------------------------------------


async def join_canonical_jobs(
    repo: JobPostRepository,
    hits: Sequence[GraphRankHit],
) -> tuple[RetrievalCandidate, ...]:
    """Rejoin graph rank hits to current SQLite rows; drop ineligible/stale.

    Ordering follows Neo4j rank (``hits`` order). SQLite title/skills/status
    always override any graph copies because only ``JobPostRecord`` is used.
    """
    if not hits:
        return ()
    if len(hits) > MAX_RETRIEVAL_CANDIDATES:
        hits = hits[:MAX_RETRIEVAL_CANDIDATES]

    id_list = [hit.job_id for hit in hits]
    try:
        records = await repo.get_by_ids(id_list)
    except JobPostValidationError:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT) from None

    candidates: list[RetrievalCandidate] = []
    for hit in hits:
        record = records.get(hit.job_id)
        if record is None:
            continue
        if not is_graph_eligible(record):
            continue
        extraction = record.extraction
        if extraction is None:
            continue
        candidates.append(
            RetrievalCandidate(
                job_id=record.id,
                semantic_similarity=hit.semantic_similarity,
                record=record,
                extraction=extraction,
                graph_evidence=(),
            )
        )
    return tuple(candidates)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def retry_pending_job_graph_work(
    database: DatabaseSessionManager,
    client: RetrievalGraphClient,
    embedding_service: JobEmbeddingPort,
    *,
    limit: int = DEFAULT_JOB_SYNC_BATCH_SIZE,
) -> int:
    """One visibly bounded Job outbox attempt before retrieval.

    Uses the existing processor only. Per-item Neo4j failures stay retryable in
    the outbox; unexpected processor crashes surface as sanitized retrieval
    failures so callers never claim matches after an opaque graph fault.
    """
    try:
        return await process_job_sync_outbox(
            database,
            client,
            embedding_service,
            limit=limit,
        )
    except GraphError as exc:
        raise _map_graph_error(exc) from None
    except RetrievalError:
        raise
    except Exception:
        raise RetrievalError(RetrievalErrorCode.GRAPH_FAILED) from None


async def retrieve_top_job_candidates(
    *,
    query_vector: Sequence[float],
    database: DatabaseSessionManager,
    graph_client: RetrievalGraphClient,
    embedding_service: JobEmbeddingPort,
    saved_job_ids: Sequence[UUID] | None = None,
    retry_outbox: bool = True,
    limit: int = MAX_RETRIEVAL_CANDIDATES,
) -> tuple[RetrievalCandidate, ...]:
    """Retry outbox once, query top-k graph hits, rejoin scorable SQLite Jobs.

    On Neo4j failure after the bounded retry, raises ``RetrievalError`` with a
    sanitized code and never returns a successful empty-match claim for an
    outage. Successful empty results are only returned when the graph answered
    and no eligible SQLite rows remained.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    if limit > MAX_RETRIEVAL_CANDIDATES:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)
    if limit > MAX_LIST_LIMIT:
        raise RetrievalError(RetrievalErrorCode.INVALID_INPUT)

    # Validate filter/vector early so bad inputs never open graph work claims.
    _validate_query_vector(query_vector)
    _normalize_saved_job_ids(
        list(saved_job_ids) if saved_job_ids is not None else None
    )

    if retry_outbox:
        await retry_pending_job_graph_work(
            database,
            graph_client,
            embedding_service,
        )

    hits = await query_job_vector_index(
        graph_client,
        query_vector,
        saved_job_ids=saved_job_ids,
        limit=limit,
    )

    async with database.session_scope() as session:
        repo = JobPostRepository(session)
        return await join_canonical_jobs(repo, hits)


__all__ = [
    "MAX_RELATED_EDGE_RESULTS",
    "MAX_RELATED_SKILL_KEYS",
    "MAX_RETRIEVAL_CANDIDATES",
    "RETRIEVAL_VECTOR_DIMENSIONS",
    "RETRIEVAL_VECTOR_INDEX_NAME",
    "GraphRankHit",
    "GraphReadClient",
    "RetrievalCandidate",
    "RetrievalError",
    "RetrievalErrorCode",
    "RetrievalGraphClient",
    "clamp_semantic_similarity",
    "join_canonical_jobs",
    "query_job_vector_index",
    "query_verified_related_edges",
    "retry_pending_job_graph_work",
    "retrieve_top_job_candidates",
]
