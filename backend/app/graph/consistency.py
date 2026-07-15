"""Read-only pre-match SQLite/Neo4j revision consistency checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.graph.rebuild_snapshot import (
    SourceRevision,
    SourceRevisionSnapshot,
    load_source_revision_snapshot,
)
from app.graph.rebuild_target import CANONICAL_COMPOSE_REBUILD_COMMAND
from app.graph.sync_shared import NEO4J_REBUILD_INSTRUCTION

NEO4J_UNAVAILABLE: str = "NEO4J_UNAVAILABLE"
NEO4J_REBUILD_REQUIRED: str = "NEO4J_REBUILD_REQUIRED"
REBUILD_REQUIRED_INSTRUCTION: str = (
    f"{NEO4J_REBUILD_INSTRUCTION} Command: {CANONICAL_COMPOSE_REBUILD_COMMAND}"
)

_CANDIDATE_REVISIONS_CYPHER: str = (
    "MATCH (c:Candidate) "
    "RETURN c.id AS id, c.source_updated_at AS source_updated_at "
    "ORDER BY id"
)
_JOB_REVISIONS_CYPHER: str = (
    "MATCH (j:Job) "
    "RETURN j.id AS id, j.source_updated_at AS source_updated_at "
    "ORDER BY id"
)


class _AsyncReadResult(Protocol):
    async def data(self) -> list[dict[str, Any]]: ...


class _AsyncReadSession(Protocol):
    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _AsyncReadResult: ...

    async def __aenter__(self) -> _AsyncReadSession: ...

    async def __aexit__(self, *args: object) -> None: ...


class AsyncGraphReadDriver(Protocol):
    """Minimal async Neo4j read surface used by revision consistency."""

    def session(self, **config: Any) -> _AsyncReadSession: ...


@dataclass(frozen=True, slots=True)
class GraphRevisionSnapshot:
    """Complete Neo4j Candidate/Job revision snapshot."""

    candidates: Mapping[str, datetime]
    jobs: Mapping[str, datetime]


@dataclass(frozen=True, slots=True)
class GraphConsistencyResult:
    """Stable result for a pre-match revision consistency check."""

    is_consistent: bool
    error_code: str | None
    message: str
    rebuild_instruction: str | None
    scorable_job_ids: frozenset[str]


def _ok(snapshot: SourceRevisionSnapshot) -> GraphConsistencyResult:
    return GraphConsistencyResult(
        is_consistent=True,
        error_code=None,
        message="SQLite and Neo4j Candidate/Job revisions are consistent.",
        rebuild_instruction=None,
        scorable_job_ids=frozenset(job.id for job in snapshot.jobs),
    )


def _unavailable() -> GraphConsistencyResult:
    return GraphConsistencyResult(
        is_consistent=False,
        error_code=NEO4J_UNAVAILABLE,
        message="Neo4j is unavailable for revision consistency check.",
        rebuild_instruction=None,
        scorable_job_ids=frozenset(),
    )


def _rebuild_required() -> GraphConsistencyResult:
    return GraphConsistencyResult(
        is_consistent=False,
        error_code=NEO4J_REBUILD_REQUIRED,
        message="Neo4j Candidate/Job revisions differ from SQLite.",
        rebuild_instruction=REBUILD_REQUIRED_INSTRUCTION,
        scorable_job_ids=frozenset(),
    )


def _normalize_utc_instant(value: object) -> datetime | None:
    if isinstance(value, datetime):
        stamp = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _source_revisions(
    rows: tuple[SourceRevision, ...],
) -> dict[str, datetime]:
    normalized: dict[str, datetime] = {}
    for row in rows:
        stamp = _normalize_utc_instant(row.updated_at)
        if stamp is None:
            continue
        normalized[row.id] = stamp
    return normalized


def _candidate_revisions(candidate: SourceRevision | None) -> dict[str, datetime]:
    if candidate is None:
        return {}
    stamp = _normalize_utc_instant(candidate.updated_at)
    if stamp is None:
        return {}
    return {candidate.id: stamp}


def _graph_revisions(rows: list[dict[str, Any]]) -> dict[str, datetime] | None:
    normalized: dict[str, datetime] = {}
    for row in rows:
        raw_id = row.get("id")
        stamp = _normalize_utc_instant(row.get("source_updated_at"))
        if not isinstance(raw_id, str) or raw_id.strip() == "" or stamp is None:
            return None
        normalized[raw_id] = stamp
    return normalized


async def _load_graph_revision_snapshot(
    driver: AsyncGraphReadDriver,
) -> GraphRevisionSnapshot:
    async with driver.session() as session:
        candidate_result = await session.run(_CANDIDATE_REVISIONS_CYPHER)
        candidate_revisions = _graph_revisions(await candidate_result.data())
        job_result = await session.run(_JOB_REVISIONS_CYPHER)
        job_revisions = _graph_revisions(await job_result.data())
    if candidate_revisions is None or job_revisions is None:
        return GraphRevisionSnapshot(candidates={}, jobs={})
    return GraphRevisionSnapshot(
        candidates=candidate_revisions,
        jobs=job_revisions,
    )


def _snapshots_match(
    sqlite: SourceRevisionSnapshot,
    graph: GraphRevisionSnapshot,
) -> bool:
    # ponytail: O(n) ID/revision comparison is intentional for the small local corpus; replace with a sync ledger only beyond portfolio scale.  # noqa: E501
    return (
        _candidate_revisions(sqlite.candidate) == graph.candidates
        and _source_revisions(sqlite.jobs) == graph.jobs
    )


async def check_graph_revision_consistency(
    session: Any,
    driver: AsyncGraphReadDriver,
) -> GraphConsistencyResult:
    """Compare SQLite source revisions with complete Neo4j revision sets."""
    sqlite_snapshot = await load_source_revision_snapshot(session)
    try:
        graph_snapshot = await _load_graph_revision_snapshot(driver)
    except Exception:
        return _unavailable()

    if not _snapshots_match(sqlite_snapshot, graph_snapshot):
        return _rebuild_required()
    return _ok(sqlite_snapshot)


__all__ = [
    "AsyncGraphReadDriver",
    "GraphConsistencyResult",
    "GraphRevisionSnapshot",
    "NEO4J_REBUILD_REQUIRED",
    "NEO4J_UNAVAILABLE",
    "REBUILD_REQUIRED_INSTRUCTION",
    "check_graph_revision_consistency",
]
