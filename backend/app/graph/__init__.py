"""Neo4j derived-graph client and schema bootstrap primitives.

Neo4j is rebuildable derived data only. SQLite remains the canonical store;
graph unavailability must not mutate or delete SQLite/filesystem state.
"""

from __future__ import annotations

from app.graph.client import DEFAULT_HEALTH_TIMEOUT_SECONDS, Neo4jClient
from app.graph.errors import (
    GraphError,
    GraphErrorCode,
    GraphHealth,
    GraphHealthStatus,
)
from app.graph.schema import (
    EMBEDDING_VECTOR_DIMENSIONS,
    SCHEMA_STATEMENTS,
    VECTOR_INDEX_NAME,
    VECTOR_SIMILARITY_FUNCTION,
    ensure_graph_schema,
    schema_statements_for_dimensions,
)

__all__ = [
    "DEFAULT_HEALTH_TIMEOUT_SECONDS",
    "EMBEDDING_VECTOR_DIMENSIONS",
    "SCHEMA_STATEMENTS",
    "VECTOR_INDEX_NAME",
    "VECTOR_SIMILARITY_FUNCTION",
    "GraphError",
    "GraphErrorCode",
    "GraphHealth",
    "GraphHealthStatus",
    "Neo4jClient",
    "ensure_graph_schema",
    "schema_statements_for_dimensions",
]
