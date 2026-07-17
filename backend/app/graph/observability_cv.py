"""Active-CV branch projection for bounded graph observability (Plan 9 / 05B).

Owns fixed read-only Cypher and parsers for the single active CV branch
(``CV`` with ``PROJECTS_TO`` to Candidate), its sections, entries, and
allowlisted structural edges. Caps and ordering follow Master §14.1.
Never mutates the graph or accepts client Cypher.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from app.db.models.profiles import CANDIDATE_PROFILE_ID

# Master §14.1 hard caps for the active CV branch.
CAP_CV: int = 1
CAP_CV_SECTIONS: int = 20
CAP_CV_ENTRIES: int = 60

CV_EDGE_TYPES: frozenset[str] = frozenset(
    {"PROJECTS_TO", "HAS_SECTION", "HAS_ENTRY"}
)

CvGraphEdgeType = Literal["PROJECTS_TO", "HAS_SECTION", "HAS_ENTRY"]

_COUNT_ACTIVE_CV_CYPHER: str = (
    "MATCH (cv:CV)-[:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "RETURN count(cv) AS total"
)
_COUNT_ACTIVE_SECTIONS_CYPHER: str = (
    "MATCH (cv:CV)-[:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "MATCH (cv)-[:HAS_SECTION]->(sec:CVSection) "
    "RETURN count(sec) AS total"
)
_COUNT_ACTIVE_ENTRIES_CYPHER: str = (
    "MATCH (cv:CV)-[:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "MATCH (cv)-[:HAS_SECTION]->(sec:CVSection)-[:HAS_ENTRY]->(entry:CVEntry) "
    "RETURN count(entry) AS total"
)

_ACTIVE_CV_CYPHER: str = (
    "MATCH (cv:CV)-[:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "RETURN cv.id AS id, cv.original_name AS original_name, "
    "cv.extraction_version AS extraction_version, "
    "cv.source_updated_at AS revision "
    "ORDER BY cv.id ASC "
    f"LIMIT {CAP_CV}"
)
_ACTIVE_SECTIONS_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id})-[:HAS_SECTION]->(sec:CVSection) "
    "RETURN sec.id AS id, sec.heading AS heading, sec.kind AS kind, "
    "sec.ordinal AS ordinal, sec.entry_count AS entry_count "
    "ORDER BY sec.ordinal ASC, sec.id ASC "
    f"LIMIT {CAP_CV_SECTIONS}"
)
_ACTIVE_ENTRIES_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id})-[:HAS_SECTION]->(sec:CVSection)"
    "-[:HAS_ENTRY]->(entry:CVEntry) "
    "RETURN entry.id AS id, sec.id AS section_id, entry.ordinal AS ordinal, "
    "entry.title AS title, entry.subtitle AS subtitle, "
    "entry.date_text AS date_text, entry.preview AS preview, "
    "sec.ordinal AS section_ordinal "
    "ORDER BY sec.ordinal ASC, entry.ordinal ASC, entry.id ASC "
    f"LIMIT {CAP_CV_ENTRIES}"
)
_ACTIVE_CV_EDGES_CYPHER: str = (
    "MATCH (a)-[r:PROJECTS_TO|HAS_SECTION|HAS_ENTRY]->(b) "
    "WHERE ("
    "  (a:CV AND a.id IN $cv_ids) OR "
    "  (a:CVSection AND a.id IN $section_ids) OR "
    "  (a:CVEntry AND a.id IN $entry_ids) OR "
    "  (a:Candidate AND a.id IN $candidate_ids)"
    ") AND ("
    "  (b:CV AND b.id IN $cv_ids) OR "
    "  (b:CVSection AND b.id IN $section_ids) OR "
    "  (b:CVEntry AND b.id IN $entry_ids) OR "
    "  (b:Candidate AND b.id IN $candidate_ids)"
    ") "
    "RETURN "
    "CASE "
    "  WHEN 'Candidate' IN labels(a) THEN a.id "
    "  ELSE a.id "
    "END AS source_id, "
    "CASE "
    "  WHEN 'Candidate' IN labels(b) THEN b.id "
    "  ELSE b.id "
    "END AS target_id, "
    "type(r) AS type"
)

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


@dataclass(frozen=True, slots=True)
class ProjectedCv:
    id: str
    original_name: str
    extraction_version: str
    revision: str


@dataclass(frozen=True, slots=True)
class ProjectedCvSection:
    id: str
    heading: str
    kind: str
    ordinal: int
    entry_count: int


@dataclass(frozen=True, slots=True)
class ProjectedCvEntry:
    id: str
    section_id: str
    ordinal: int
    title: str | None
    subtitle: str | None
    date_text: str | None
    preview: str


@dataclass(frozen=True, slots=True)
class ProjectedCvEdge:
    source_id: str
    target_id: str
    type: CvGraphEdgeType


@dataclass(frozen=True, slots=True)
class ActiveCvBranchProjection:
    """Cap-aware active CV branch (nodes selected before structural edges)."""

    cv: ProjectedCv | None
    sections: tuple[ProjectedCvSection, ...]
    entries: tuple[ProjectedCvEntry, ...]
    edges: tuple[ProjectedCvEdge, ...]
    omitted_node_count: int
    omitted_edge_count: int
    nodes_truncated: bool
    edges_truncated: bool


class CvProjectionError(Exception):
    """Raised when the active-CV read projection cannot complete safely."""


def cv_cypher_statement_templates() -> Sequence[str]:
    """Fixed read-only CV Cypher templates for static review."""
    return (
        _COUNT_ACTIVE_CV_CYPHER,
        _COUNT_ACTIVE_SECTIONS_CYPHER,
        _COUNT_ACTIVE_ENTRIES_CYPHER,
        _ACTIVE_CV_CYPHER,
        _ACTIVE_SECTIONS_CYPHER,
        _ACTIVE_ENTRIES_CYPHER,
        _ACTIVE_CV_EDGES_CYPHER,
    )


def assert_cv_read_only_templates() -> None:
    """Raise AssertionError if any CV template embeds a write token."""
    for template in cv_cypher_statement_templates():
        padded = f" {' '.join(template.upper().split())} "
        for token in _WRITE_TOKENS:
            if token in padded:
                raise AssertionError(
                    f"observability CV Cypher must be read-only; found {token!r}"
                )


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text else None


async def _scalar_total(
    session: _AsyncReadSession,
    query: str,
    parameters: Mapping[str, Any],
) -> int:
    result = await session.run(query, parameters)
    rows = await result.data()
    if not rows:
        return 0
    return _as_nonneg_int(rows[0].get("total"))


def _parse_cv(row: Mapping[str, Any]) -> ProjectedCv | None:
    node_id = _require_str(row.get("id"))
    original_name = _require_str(row.get("original_name"))
    extraction_version = _require_str(row.get("extraction_version"))
    revision = _normalize_revision(row.get("revision"))
    if (
        node_id is None
        or original_name is None
        or extraction_version is None
        or revision is None
    ):
        return None
    return ProjectedCv(
        id=node_id,
        original_name=original_name,
        extraction_version=extraction_version,
        revision=revision,
    )


def _parse_section(row: Mapping[str, Any]) -> ProjectedCvSection | None:
    node_id = _require_str(row.get("id"))
    heading = _require_str(row.get("heading"))
    kind = _require_str(row.get("kind"))
    if node_id is None or heading is None or kind is None:
        return None
    return ProjectedCvSection(
        id=node_id,
        heading=heading,
        kind=kind,
        ordinal=_as_nonneg_int(row.get("ordinal")),
        entry_count=_as_nonneg_int(row.get("entry_count")),
    )


def _parse_entry(row: Mapping[str, Any]) -> ProjectedCvEntry | None:
    node_id = _require_str(row.get("id"))
    section_id = _require_str(row.get("section_id"))
    if node_id is None or section_id is None:
        return None
    preview = row.get("preview")
    preview_text = preview if isinstance(preview, str) else ""
    return ProjectedCvEntry(
        id=node_id,
        section_id=section_id,
        ordinal=_as_nonneg_int(row.get("ordinal")),
        title=_optional_str(row.get("title")),
        subtitle=_optional_str(row.get("subtitle")),
        date_text=_optional_str(row.get("date_text")),
        preview=preview_text,
    )


def _parse_cv_edge(row: Mapping[str, Any]) -> ProjectedCvEdge | None:
    source_id = _require_str(row.get("source_id"))
    target_id = _require_str(row.get("target_id"))
    raw_type = _require_str(row.get("type"))
    if source_id is None or target_id is None or raw_type is None:
        return None
    if raw_type not in CV_EDGE_TYPES:
        return None
    return ProjectedCvEdge(
        source_id=source_id,
        target_id=target_id,
        type=raw_type,  # type: ignore[arg-type]
    )


def _sort_cv_edges(edges: Sequence[ProjectedCvEdge]) -> list[ProjectedCvEdge]:
    return sorted(edges, key=lambda e: (e.type, e.source_id, e.target_id))


async def load_active_cv_branch(
    session: _AsyncReadSession,
    *,
    candidate_id: str = CANDIDATE_PROFILE_ID,
) -> ActiveCvBranchProjection:
    """Load the single active CV branch under Master caps/order.

    Uses an already-open read session (shared with Candidate/Job/Skill loads).
    Raises :class:`CvProjectionError` on driver/parse failure.
    """
    try:
        cand_params = {"candidate_id": candidate_id}
        total_cv = await _scalar_total(
            session, _COUNT_ACTIVE_CV_CYPHER, cand_params
        )
        total_sections = await _scalar_total(
            session, _COUNT_ACTIVE_SECTIONS_CYPHER, cand_params
        )
        total_entries = await _scalar_total(
            session, _COUNT_ACTIVE_ENTRIES_CYPHER, cand_params
        )

        cv_result = await session.run(_ACTIVE_CV_CYPHER, cand_params)
        cv_rows = await cv_result.data()
        cv: ProjectedCv | None = None
        for row in cv_rows:
            parsed = _parse_cv(row)
            if parsed is not None:
                cv = parsed
                break

        sections: list[ProjectedCvSection] = []
        entries: list[ProjectedCvEntry] = []
        if cv is not None:
            sec_result = await session.run(
                _ACTIVE_SECTIONS_CYPHER, {"cv_id": cv.id}
            )
            for row in await sec_result.data():
                parsed_sec = _parse_section(row)
                if parsed_sec is not None:
                    sections.append(parsed_sec)
            ent_result = await session.run(
                _ACTIVE_ENTRIES_CYPHER, {"cv_id": cv.id}
            )
            for row in await ent_result.data():
                parsed_ent = _parse_entry(row)
                if parsed_ent is not None:
                    entries.append(parsed_ent)

        cv_ids = [cv.id] if cv is not None else []
        section_ids = [s.id for s in sections]
        entry_ids = [e.id for e in entries]
        candidate_ids = [candidate_id] if cv is not None else []

        edge_result = await session.run(
            _ACTIVE_CV_EDGES_CYPHER,
            {
                "cv_ids": cv_ids,
                "section_ids": section_ids,
                "entry_ids": entry_ids,
                "candidate_ids": candidate_ids,
            },
        )
        edge_rows = await edge_result.data()
    except CvProjectionError:
        raise
    except Exception as exc:
        raise CvProjectionError("active CV branch projection failed") from exc

    raw_edges: list[ProjectedCvEdge] = []
    for row in edge_rows:
        parsed_edge = _parse_cv_edge(row)
        if parsed_edge is not None:
            raw_edges.append(parsed_edge)
    sorted_edges = _sort_cv_edges(raw_edges)

    selected_cv = 1 if cv is not None else 0
    omitted_nodes = (
        max(0, total_cv - selected_cv)
        + max(0, total_sections - len(sections))
        + max(0, total_entries - len(entries))
    )
    # Structural edges are not edge-capped here; the parent merges into CAP_EDGES.
    return ActiveCvBranchProjection(
        cv=cv,
        sections=tuple(sections),
        entries=tuple(entries),
        edges=tuple(sorted_edges),
        omitted_node_count=omitted_nodes,
        omitted_edge_count=0,
        nodes_truncated=omitted_nodes > 0,
        edges_truncated=False,
    )


# Fail import if a write token is ever introduced into fixed templates.
assert_cv_read_only_templates()

__all__ = [
    "CAP_CV",
    "CAP_CV_ENTRIES",
    "CAP_CV_SECTIONS",
    "CV_EDGE_TYPES",
    "ActiveCvBranchProjection",
    "CvGraphEdgeType",
    "CvProjectionError",
    "ProjectedCv",
    "ProjectedCvEdge",
    "ProjectedCvEntry",
    "ProjectedCvSection",
    "assert_cv_read_only_templates",
    "cv_cypher_statement_templates",
    "load_active_cv_branch",
]
