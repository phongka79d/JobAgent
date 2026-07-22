"""Allowlisted read-only Neo4j projection for Plan 8/9 observability graph.

Owns fixed MATCH/RETURN Cypher for Candidate/Job/Skill nodes and shared
edge loading. Active CV branch projection lives in
:mod:`app.graph.observability_cv`. Applies Master node/edge caps and ordering.
Never mutates the graph, accepts client Cypher, or opens write sessions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.graph.observability_cv import (
    CAP_CV,
    CAP_CV_ENTRIES,
    CAP_CV_SECTIONS,
    CV_EDGE_TYPES,
    ActiveCvBranchProjection,
    CvProjectionError,
    ProjectedCv,
    ProjectedCvEntry,
    ProjectedCvSection,
    assert_cv_read_only_templates,
    cv_cypher_statement_templates,
    load_active_cv_branch,
)

# Master / Plan 8/9 hard caps (apply after ordered selection).
CAP_CANDIDATES: int = 1
CAP_JOBS: int = 20
CAP_SKILLS: int = 40
CAP_EDGES: int = 100

ALLOWLISTED_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "HAS_SKILL",
        "REQUIRES",
        "PREFERS",
        "RELATED_TO",
        "PROJECTS_TO",
        "HAS_SECTION",
        "HAS_ENTRY",
    }
)

GraphEdgeType = Literal[
    "HAS_SKILL",
    "REQUIRES",
    "PREFERS",
    "RELATED_TO",
    "PROJECTS_TO",
    "HAS_SECTION",
    "HAS_ENTRY",
]

# Fixed read-only Cypher — unique RETURN shapes for test fakes and review.
_COUNT_CANDIDATES_CYPHER: str = (
    "MATCH (c:Candidate) RETURN count(c) AS total"
)
_COUNT_JOBS_CYPHER: str = "MATCH (j:Job) RETURN count(j) AS total"
_COUNT_SKILLS_CYPHER: str = "MATCH (s:Skill) RETURN count(s) AS total"

_CANDIDATES_CYPHER: str = (
    "MATCH (c:Candidate) "
    "RETURN c.id AS id, c.source_updated_at AS revision "
    "ORDER BY c.id ASC "
    f"LIMIT {CAP_CANDIDATES}"
)
_JOBS_CYPHER: str = (
    "MATCH (j:Job) "
    "RETURN j.id AS id, j.title AS title, j.company AS company, "
    "j.source_updated_at AS revision "
    "ORDER BY j.id ASC "
    f"LIMIT {CAP_JOBS}"
)
_SKILLS_CYPHER: str = (
    "MATCH (s:Skill) "
    "RETURN s.canonical_key AS canonical_name, "
    "s.canonical_key AS canonical_key, s.display_name AS display_name, "
    "s.category AS category "
    "ORDER BY s.canonical_key ASC "
    f"LIMIT {CAP_SKILLS}"
)
# Edges among already-selected Candidate/Job/Skill node IDs only.
_EDGES_CYPHER: str = (
    "MATCH (a)-[r:HAS_SKILL|REQUIRES|PREFERS|RELATED_TO]->(b) "
    "WHERE ("
    "  (a:Candidate AND a.id IN $candidate_ids) OR "
    "  (a:Job AND a.id IN $job_ids) OR "
    "  (a:Skill AND a.canonical_key IN $skill_keys)"
    ") AND ("
    "  (b:Candidate AND b.id IN $candidate_ids) OR "
    "  (b:Job AND b.id IN $job_ids) OR "
    "  (b:Skill AND b.canonical_key IN $skill_keys)"
    ") "
    "RETURN "
    "CASE WHEN 'Skill' IN labels(a) THEN a.canonical_key ELSE a.id END "
    "AS source_id, "
    "CASE WHEN 'Skill' IN labels(b) THEN b.canonical_key ELSE b.id END "
    "AS target_id, "
    "type(r) AS type"
)

# Write-token guard for static review of this module's templates.
_WRITE_TOKENS: tuple[str, ...] = (
    " MERGE ",
    " CREATE ",
    " DELETE ",
    " DETACH ",
    " SET ",
    " REMOVE ",
    " DROP ",
    " FOREACH ",
    " CALL {",
    " LOAD CSV ",
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


class AsyncGraphObservabilityDriver(Protocol):
    """Minimal async Neo4j read surface for the observability projection."""

    def session(self, **config: Any) -> _AsyncReadSession: ...


@dataclass(frozen=True, slots=True)
class ProjectedCandidate:
    id: str
    revision: str


@dataclass(frozen=True, slots=True)
class ProjectedJob:
    id: str
    title: str
    company: str
    revision: str


@dataclass(frozen=True, slots=True)
class ProjectedSkill:
    canonical_name: str
    canonical_key: str | None = None
    display_name: str | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectedEdge:
    source_id: str
    target_id: str
    type: GraphEdgeType


@dataclass(frozen=True, slots=True)
class BoundedGraphProjection:
    """Cap-aware allowlisted snapshot payload (nodes selected before edges)."""

    cv: ProjectedCv | None
    sections: tuple[ProjectedCvSection, ...]
    entries: tuple[ProjectedCvEntry, ...]
    candidate: ProjectedCandidate | None
    jobs: tuple[ProjectedJob, ...]
    skills: tuple[ProjectedSkill, ...]
    edges: tuple[ProjectedEdge, ...]
    nodes_truncated: bool
    edges_truncated: bool
    omitted_node_count: int
    omitted_edge_count: int


class GraphProjectionError(Exception):
    """Raised when the read-only projection cannot be completed safely."""


def cypher_statement_templates() -> Sequence[str]:
    """Fixed read-only Cypher templates for static review (no runtime values)."""
    return (
        _COUNT_CANDIDATES_CYPHER,
        _COUNT_JOBS_CYPHER,
        _COUNT_SKILLS_CYPHER,
        _CANDIDATES_CYPHER,
        _JOBS_CYPHER,
        _SKILLS_CYPHER,
        _EDGES_CYPHER,
        *cv_cypher_statement_templates(),
    )


def assert_read_only_templates() -> None:
    """Raise AssertionError if any template embeds a write/mutation token."""
    for template in cypher_statement_templates():
        padded = f" {' '.join(template.upper().split())} "
        for token in _WRITE_TOKENS:
            if token in padded:
                raise AssertionError(
                    f"observability graph Cypher must be read-only; found {token!r}"
                )
    assert_cv_read_only_templates()


def _normalize_revision(value: object) -> str | None:
    if isinstance(value, datetime):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        else:
            stamp = stamp.astimezone(UTC)
        return stamp.isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return None


def _require_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text else None


def _as_nonneg_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


async def _scalar_total(session: _AsyncReadSession, query: str) -> int:
    result = await session.run(query)
    rows = await result.data()
    if not rows:
        return 0
    return _as_nonneg_int(rows[0].get("total"))


def _parse_candidate(row: Mapping[str, Any]) -> ProjectedCandidate | None:
    node_id = _require_str(row.get("id"))
    revision = _normalize_revision(row.get("revision"))
    if node_id is None or revision is None:
        return None
    return ProjectedCandidate(id=node_id, revision=revision)


def _parse_job(row: Mapping[str, Any]) -> ProjectedJob | None:
    node_id = _require_str(row.get("id"))
    revision = _normalize_revision(row.get("revision"))
    if node_id is None or revision is None:
        return None
    title = _require_str(row.get("title")) or ""
    company = _require_str(row.get("company")) or ""
    return ProjectedJob(
        id=node_id,
        title=title,
        company=company,
        revision=revision,
    )


def _parse_skill(row: Mapping[str, Any]) -> ProjectedSkill | None:
    name = _require_str(row.get("canonical_name"))
    if name is None:
        return None
    return ProjectedSkill(
        canonical_name=name,
        canonical_key=_require_str(row.get("canonical_key")) or name,
        display_name=_require_str(row.get("display_name")) or name,
        category=_require_str(row.get("category")),
    )


def _parse_edge(row: Mapping[str, Any]) -> ProjectedEdge | None:
    source_id = _require_str(row.get("source_id"))
    target_id = _require_str(row.get("target_id"))
    raw_type = _require_str(row.get("type"))
    if source_id is None or target_id is None or raw_type is None:
        return None
    if raw_type not in ALLOWLISTED_EDGE_TYPES:
        return None
    return ProjectedEdge(
        source_id=source_id,
        target_id=target_id,
        type=raw_type,  # type: ignore[arg-type]
    )


def _sort_edges(edges: Sequence[ProjectedEdge]) -> list[ProjectedEdge]:
    return sorted(edges, key=lambda e: (e.type, e.source_id, e.target_id))


async def load_bounded_graph_projection(
    driver: AsyncGraphObservabilityDriver,
) -> BoundedGraphProjection:
    """Load one allowlisted, cap-aware active-CV + Candidate/Job/Skill snapshot.

    Selects nodes first (ordered + capped), then only allowlisted edges whose
    endpoints are among the selected nodes. Edges are sorted by
    ``(type, source_id, target_id)`` and capped at :data:`CAP_EDGES`.
    Raises :class:`GraphProjectionError` on driver/parse failure.
    """
    try:
        async with driver.session() as session:
            total_candidates = await _scalar_total(session, _COUNT_CANDIDATES_CYPHER)
            total_jobs = await _scalar_total(session, _COUNT_JOBS_CYPHER)
            total_skills = await _scalar_total(session, _COUNT_SKILLS_CYPHER)

            cand_result = await session.run(_CANDIDATES_CYPHER)
            cand_rows = await cand_result.data()
            job_result = await session.run(_JOBS_CYPHER)
            job_rows = await job_result.data()
            skill_result = await session.run(_SKILLS_CYPHER)
            skill_rows = await skill_result.data()

            candidates: list[ProjectedCandidate] = []
            for row in cand_rows:
                parsed = _parse_candidate(row)
                if parsed is not None:
                    candidates.append(parsed)
            candidate = candidates[0] if candidates else None

            jobs: list[ProjectedJob] = []
            for row in job_rows:
                parsed_job = _parse_job(row)
                if parsed_job is not None:
                    jobs.append(parsed_job)

            skills: list[ProjectedSkill] = []
            for row in skill_rows:
                parsed_skill = _parse_skill(row)
                if parsed_skill is not None:
                    skills.append(parsed_skill)

            candidate_ids = [candidate.id] if candidate is not None else []
            job_ids = [j.id for j in jobs]
            skill_keys = [s.canonical_name for s in skills]

            edge_result = await session.run(
                _EDGES_CYPHER,
                {
                    "candidate_ids": candidate_ids,
                    "job_ids": job_ids,
                    "skill_keys": skill_keys,
                },
            )
            edge_rows = await edge_result.data()

            try:
                cv_branch: ActiveCvBranchProjection = await load_active_cv_branch(
                    session
                )
            except CvProjectionError as exc:
                raise GraphProjectionError(str(exc)) from exc
    except GraphProjectionError:
        raise
    except Exception as exc:
        raise GraphProjectionError(
            "bounded graph projection failed"
        ) from exc

    raw_edges: list[ProjectedEdge] = []
    for row in edge_rows:
        parsed_edge = _parse_edge(row)
        if parsed_edge is not None:
            raw_edges.append(parsed_edge)
    for cv_edge in cv_branch.edges:
        if cv_edge.type in ALLOWLISTED_EDGE_TYPES:
            raw_edges.append(
                ProjectedEdge(
                    source_id=cv_edge.source_id,
                    target_id=cv_edge.target_id,
                    type=cv_edge.type,
                )
            )
    sorted_edges = _sort_edges(raw_edges)
    total_edges = len(sorted_edges)
    edges = sorted_edges[:CAP_EDGES]
    omitted_edges = max(0, total_edges - len(edges))

    selected_candidates = 1 if candidate is not None else 0
    omitted_nodes = (
        max(0, total_candidates - selected_candidates)
        + max(0, total_jobs - len(jobs))
        + max(0, total_skills - len(skills))
        + cv_branch.omitted_node_count
    )
    nodes_truncated = omitted_nodes > 0
    edges_truncated = omitted_edges > 0

    return BoundedGraphProjection(
        cv=cv_branch.cv,
        sections=cv_branch.sections,
        entries=cv_branch.entries,
        candidate=candidate,
        jobs=tuple(jobs),
        skills=tuple(skills),
        edges=tuple(edges),
        nodes_truncated=nodes_truncated,
        edges_truncated=edges_truncated,
        omitted_node_count=omitted_nodes,
        omitted_edge_count=omitted_edges,
    )


# Fail import if a write token is ever introduced into fixed templates.
assert_read_only_templates()

__all__ = [
    "ALLOWLISTED_EDGE_TYPES",
    "CAP_CANDIDATES",
    "CAP_CV",
    "CAP_CV_ENTRIES",
    "CAP_CV_SECTIONS",
    "CAP_EDGES",
    "CAP_JOBS",
    "CAP_SKILLS",
    "CV_EDGE_TYPES",
    "AsyncGraphObservabilityDriver",
    "BoundedGraphProjection",
    "GraphEdgeType",
    "GraphProjectionError",
    "ProjectedCandidate",
    "ProjectedCv",
    "ProjectedCvEntry",
    "ProjectedCvSection",
    "ProjectedEdge",
    "ProjectedJob",
    "ProjectedSkill",
    "assert_read_only_templates",
    "cypher_statement_templates",
    "load_bounded_graph_projection",
]
