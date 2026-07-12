"""Graph rebuild parity verification and post-success sync-state updates.

Verification uses bounded parameterized reads only. Job/outbox sync state is
updated only after observed Neo4j IDs/counts match the SQLite snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.db.enums import GraphSyncStatus
from app.db.session import DatabaseSessionManager
from app.graph.job_sync import JOB_UPSERT_OPERATION
from app.graph.rebuild_jobs import RebuildSnapshot
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRepository

# Static, parameter-free aggregate reads (no untrusted interpolation).
_JOB_IDS_CYPHER = "MATCH (j:Job) RETURN collect(j.id) AS job_ids"
_SKILL_COUNT_CYPHER = "MATCH (s:Skill) RETURN count(s) AS skill_count"
_FAMILY_COUNT_CYPHER = "MATCH (f:JobFamily) RETURN count(f) AS family_count"
_REQUIRES_COUNT_CYPHER = "MATCH ()-[r:REQUIRES]->() RETURN count(r) AS requires_count"
_PREFERS_COUNT_CYPHER = "MATCH ()-[r:PREFERS]->() RETURN count(r) AS prefers_count"
_IN_FAMILY_COUNT_CYPHER = (
    "MATCH ()-[r:IN_FAMILY]->() RETURN count(r) AS in_family_count"
)
_CANDIDATE_COUNT_CYPHER = "MATCH (c:Candidate) RETURN count(c) AS candidate_count"
_HAS_SKILL_COUNT_CYPHER = (
    "MATCH ()-[r:HAS_SKILL]->() RETURN count(r) AS has_skill_count"
)


class RebuildVerifyError(Exception):
    """Sanitized rebuild verification or sync-state failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"RebuildVerifyError(code={self.code!r})"


class RebuildReadClient(Protocol):
    """Bounded read surface required for parity checks."""

    async def fetch_records(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class GraphParityObservation:
    """Observed JobAgent-derived entity/edge counts and Job IDs."""

    job_ids: frozenset[str]
    skill_count: int
    family_count: int
    requires_count: int
    prefers_count: int
    in_family_count: int
    candidate_count: int
    has_skill_count: int


async def _scalar_count(
    client: RebuildReadClient,
    query: str,
    key: str,
) -> int:
    rows = await client.fetch_records(query, {})
    if not rows:
        return 0
    value = rows[0].get(key, 0)
    if isinstance(value, bool):
        raise RebuildVerifyError("parity_count_invalid")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise RebuildVerifyError("parity_count_invalid")


async def observe_graph_parity(client: RebuildReadClient) -> GraphParityObservation:
    """Read Job IDs and entity/edge counts from Neo4j (parameter-bound)."""
    try:
        id_rows = await client.fetch_records(_JOB_IDS_CYPHER, {})
        raw_ids = id_rows[0].get("job_ids", []) if id_rows else []
        if raw_ids is None:
            raw_ids = []
        if not isinstance(raw_ids, (list, tuple)):
            raise RebuildVerifyError("parity_job_ids_invalid")
        job_ids = frozenset(str(item) for item in raw_ids)

        skill_count = await _scalar_count(client, _SKILL_COUNT_CYPHER, "skill_count")
        family_count = await _scalar_count(
            client, _FAMILY_COUNT_CYPHER, "family_count"
        )
        requires_count = await _scalar_count(
            client, _REQUIRES_COUNT_CYPHER, "requires_count"
        )
        prefers_count = await _scalar_count(
            client, _PREFERS_COUNT_CYPHER, "prefers_count"
        )
        in_family_count = await _scalar_count(
            client, _IN_FAMILY_COUNT_CYPHER, "in_family_count"
        )
        candidate_count = await _scalar_count(
            client, _CANDIDATE_COUNT_CYPHER, "candidate_count"
        )
        has_skill_count = await _scalar_count(
            client, _HAS_SKILL_COUNT_CYPHER, "has_skill_count"
        )
    except RebuildVerifyError:
        raise
    except Exception:
        raise RebuildVerifyError("parity_read_failed") from None

    return GraphParityObservation(
        job_ids=job_ids,
        skill_count=skill_count,
        family_count=family_count,
        requires_count=requires_count,
        prefers_count=prefers_count,
        in_family_count=in_family_count,
        candidate_count=candidate_count,
        has_skill_count=has_skill_count,
    )


def compare_parity(
    expected: RebuildSnapshot,
    observed: GraphParityObservation,
) -> None:
    """Raise ``RebuildVerifyError`` with a stable code when parity fails."""
    expected_jobs = frozenset(expected.eligible_job_ids)
    if observed.job_ids != expected_jobs:
        raise RebuildVerifyError("parity_job_ids_mismatch")
    if observed.skill_count != len(expected.expected_skill_keys):
        raise RebuildVerifyError("parity_skill_count_mismatch")
    if observed.family_count != len(expected.expected_family_keys):
        raise RebuildVerifyError("parity_family_count_mismatch")
    if observed.requires_count != expected.expected_requires_count:
        raise RebuildVerifyError("parity_requires_count_mismatch")
    if observed.prefers_count != expected.expected_prefers_count:
        raise RebuildVerifyError("parity_prefers_count_mismatch")
    if observed.in_family_count != expected.expected_in_family_count:
        raise RebuildVerifyError("parity_in_family_count_mismatch")
    if observed.candidate_count != expected.expected_candidate_count:
        raise RebuildVerifyError("parity_candidate_count_mismatch")
    if observed.has_skill_count != expected.expected_has_skill_count:
        raise RebuildVerifyError("parity_has_skill_count_mismatch")


async def verify_rebuild_parity(
    client: RebuildReadClient,
    expected: RebuildSnapshot,
) -> GraphParityObservation:
    """Observe Neo4j state and compare to the SQLite rebuild snapshot."""
    observed = await observe_graph_parity(client)
    compare_parity(expected, observed)
    return observed


async def mark_rebuild_sync_states(
    database: DatabaseSessionManager,
    eligible_job_ids: Sequence[str],
) -> int:
    """Mark eligible Jobs and outbox rows synced after verified rebuild success.

    Must not be called on partial failure. Uses identifier-only outbox payloads.
    """
    marked = 0
    async with database.session_scope() as session:
        jobs = JobPostRepository(session)
        outbox = GraphOutboxRepository(session)
        for job_id_str in eligible_job_ids:
            try:
                job_id = UUID(job_id_str)
            except (TypeError, ValueError):
                raise RebuildVerifyError("invalid_job_id") from None
            record = await jobs.get_by_id(job_id)
            if record is None:
                raise RebuildVerifyError("job_missing_on_sync_mark")
            await jobs.set_graph_sync_status(
                job_id,
                status=GraphSyncStatus.SYNCED,
            )
            row = await outbox.enqueue(
                operation=JOB_UPSERT_OPERATION,
                entity_id=job_id_str,
                payload={"job_id": job_id_str},
                requeue_existing=True,
            )
            await outbox.mark_synced(row.id)
            marked += 1
    return marked


__all__ = [
    "GraphParityObservation",
    "RebuildReadClient",
    "RebuildVerifyError",
    "compare_parity",
    "mark_rebuild_sync_states",
    "observe_graph_parity",
    "verify_rebuild_parity",
]
