"""Neo4j derived-graph client and schema bootstrap primitives.

Neo4j is rebuildable derived data only. SQLite remains the canonical store;
graph unavailability must not mutate or delete SQLite/filesystem state.
"""

from __future__ import annotations

from app.graph.candidate_sync import (
    CANDIDATE_SYNC_OPERATION,
    DEFAULT_CANDIDATE_SYNC_BATCH_SIZE,
    CandidateGraphClient,
    process_candidate_sync_outbox,
    rebuild_candidate_projection,
)
from app.graph.client import DEFAULT_HEALTH_TIMEOUT_SECONDS, Neo4jClient
from app.graph.errors import (
    GraphError,
    GraphErrorCode,
    GraphHealth,
    GraphHealthStatus,
)
from app.graph.job_sync import (
    DEFAULT_JOB_SYNC_BATCH_SIZE,
    JOB_UPSERT_OPERATION,
    process_job_sync_outbox,
    project_eligible_job,
)
from app.graph.rebuild_jobs import (
    RebuildLoadError,
    RebuildSnapshot,
    load_rebuild_snapshot,
    project_jobs_for_rebuild,
)
from app.graph.rebuild_verify import (
    GraphParityObservation,
    RebuildVerifyError,
    mark_rebuild_sync_states,
    verify_rebuild_parity,
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
    "CANDIDATE_SYNC_OPERATION",
    "CandidateGraphClient",
    "DEFAULT_CANDIDATE_SYNC_BATCH_SIZE",
    "DEFAULT_JOB_SYNC_BATCH_SIZE",
    "EMBEDDING_VECTOR_DIMENSIONS",
    "JOB_UPSERT_OPERATION",
    "SCHEMA_STATEMENTS",
    "VECTOR_INDEX_NAME",
    "VECTOR_SIMILARITY_FUNCTION",
    "GraphError",
    "GraphErrorCode",
    "GraphHealth",
    "GraphHealthStatus",
    "GraphParityObservation",
    "Neo4jClient",
    "RebuildLoadError",
    "RebuildSnapshot",
    "RebuildVerifyError",
    "load_rebuild_snapshot",
    "mark_rebuild_sync_states",
    "process_candidate_sync_outbox",
    "process_job_sync_outbox",
    "project_eligible_job",
    "project_jobs_for_rebuild",
    "rebuild_candidate_projection",
    "ensure_graph_schema",
    "schema_statements_for_dimensions",
    "verify_rebuild_parity",
]
