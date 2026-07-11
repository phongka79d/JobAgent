"""Idempotent Neo4j constraint and vector-index bootstrap.

Creates the four source-required uniqueness constraints and the Job embedding
vector index. Statements are static named Cypher with ``IF NOT EXISTS``. Neo4j
is derived only; this module never writes or deletes SQLite state.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from app.config import ALLOWED_EMBEDDING_DIMENSIONS
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphErrorCode

# Locked embedding contract (must match settings / Phase 0 decision).
EMBEDDING_VECTOR_DIMENSIONS: Final[int] = ALLOWED_EMBEDDING_DIMENSIONS
VECTOR_SIMILARITY_FUNCTION: Final[str] = "cosine"
VECTOR_INDEX_NAME: Final[str] = "job_embedding_vector"

# Named uniqueness constraints (master §8.3 / Plan 2 §7.4).
CANDIDATE_ID_CONSTRAINT: Final[str] = (
    "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS "
    "FOR (c:Candidate) REQUIRE c.id IS UNIQUE"
)
JOB_ID_CONSTRAINT: Final[str] = (
    "CREATE CONSTRAINT job_id_unique IF NOT EXISTS "
    "FOR (j:Job) REQUIRE j.id IS UNIQUE"
)
SKILL_CANONICAL_KEY_CONSTRAINT: Final[str] = (
    "CREATE CONSTRAINT skill_canonical_key_unique IF NOT EXISTS "
    "FOR (s:Skill) REQUIRE s.canonical_key IS UNIQUE"
)
JOB_FAMILY_CANONICAL_KEY_CONSTRAINT: Final[str] = (
    "CREATE CONSTRAINT job_family_canonical_key_unique IF NOT EXISTS "
    "FOR (f:JobFamily) REQUIRE f.canonical_key IS UNIQUE"
)

# Static vector index: dimension is the locked constant 1536, cosine only.
# Dimension is not interpolated from untrusted input; see
# ``schema_statements_for_dimensions`` which rejects any other value.
JOB_EMBEDDING_VECTOR_INDEX: Final[str] = (
    f"CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS "
    f"FOR (j:Job) ON (j.embedding) "
    f"OPTIONS {{indexConfig: {{"
    f"`vector.dimensions`: {EMBEDDING_VECTOR_DIMENSIONS}, "
    f"`vector.similarity_function`: '{VECTOR_SIMILARITY_FUNCTION}'"
    f"}}}}"
)

SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    CANDIDATE_ID_CONSTRAINT,
    JOB_ID_CONSTRAINT,
    SKILL_CANONICAL_KEY_CONSTRAINT,
    JOB_FAMILY_CANONICAL_KEY_CONSTRAINT,
    JOB_EMBEDDING_VECTOR_INDEX,
)

_REQUIRED_CONSTRAINT_MARKERS: Final[tuple[str, ...]] = (
    "candidate_id_unique",
    "job_id_unique",
    "skill_canonical_key_unique",
    "job_family_canonical_key_unique",
)


def schema_statements_for_dimensions(dimensions: int) -> tuple[str, ...]:
    """Return the static schema statements after validating embedding dimensions.

    Only the locked 1536-dimensional contract is accepted. Alternate dimensions
    or vector stores are out of scope and require explicit approval.
    """
    if dimensions != EMBEDDING_VECTOR_DIMENSIONS:
        raise GraphError(GraphErrorCode.INVALID_DIMENSION) from None
    return SCHEMA_STATEMENTS


def _assert_schema_contract(statements: Sequence[str]) -> None:
    """Internal invariant: exactly four uniqueness constraints + one vector index."""
    if len(statements) != 5:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
    joined = "\n".join(statements)
    for marker in _REQUIRED_CONSTRAINT_MARKERS:
        if marker not in joined:
            raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
    if VECTOR_INDEX_NAME not in joined:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
    if "`vector.dimensions`: 1536" not in joined:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
    if "`vector.similarity_function`: 'cosine'" not in joined:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
    # No alternate similarity or store markers.
    if "euclidean" in joined.lower():
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None


async def ensure_graph_schema(
    client: Neo4jClient,
    *,
    embedding_dimensions: int = EMBEDDING_VECTOR_DIMENSIONS,
) -> None:
    """Idempotently apply uniqueness constraints and the Job vector index.

    Safe to run repeatedly: every statement uses ``IF NOT EXISTS``. Failures
    raise sanitized ``GraphError`` codes only. Does not open or mutate SQLite.
    """
    prepare_error: GraphError | None = None
    prepare_failed = False
    statements: tuple[str, ...] = ()
    try:
        statements = schema_statements_for_dimensions(embedding_dimensions)
        _assert_schema_contract(statements)
    except GraphError as exc:
        prepare_error = exc
    except Exception:
        prepare_failed = True
    if prepare_error is not None:
        raise GraphError(prepare_error.code) from None
    if prepare_failed:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None

    for statement in statements:
        run_error: GraphError | None = None
        run_failed = False
        try:
            # DDL is fully static; empty parameter map keeps the bound-query path.
            await client.run_query(statement, {})
        except GraphError as exc:
            run_error = exc
        except Exception:
            run_failed = True
        if run_error is not None:
            if run_error.code is GraphErrorCode.QUERY_FAILED:
                raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
            raise GraphError(run_error.code) from None
        if run_failed:
            raise GraphError(GraphErrorCode.SCHEMA_FAILED) from None
