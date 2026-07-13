"""Neo4j driver lifecycle and base schema primitives for JobAgent."""

from app.graph.constraints import (
    JOB_EMBEDDING_VECTOR_INDEX,
    SCHEMA_STATEMENTS,
    VECTOR_DIMENSIONS,
    ensure_base_schema,
)
from app.graph.driver import check_connectivity, close_driver, open_driver

__all__ = [
    "JOB_EMBEDDING_VECTOR_INDEX",
    "SCHEMA_STATEMENTS",
    "VECTOR_DIMENSIONS",
    "check_connectivity",
    "close_driver",
    "ensure_base_schema",
    "open_driver",
]
