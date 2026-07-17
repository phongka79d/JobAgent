"""Unit tests for bounded Neo4j observability graph projection (Plan 8/9).

Covers allowlisted Cypher (no mutation tokens), node/edge caps and order,
active CV branch caps, truncation metadata, and service status assembly for
ready/stale/unavailable and no-active-profile. Uses in-process fakes only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from app.graph.consistency import (
    NEO4J_REBUILD_REQUIRED,
    NEO4J_UNAVAILABLE,
    REBUILD_REQUIRED_INSTRUCTION,
)
from app.graph.observability import (
    ALLOWLISTED_EDGE_TYPES,
    CAP_CV_ENTRIES,
    CAP_CV_SECTIONS,
    CAP_EDGES,
    CAP_JOBS,
    CAP_SKILLS,
    BoundedGraphProjection,
    ProjectedCandidate,
    ProjectedCv,
    ProjectedCvEntry,
    ProjectedCvSection,
    ProjectedEdge,
    ProjectedJob,
    ProjectedSkill,
    assert_read_only_templates,
    cypher_statement_templates,
    load_bounded_graph_projection,
)
from app.schemas.observability import GraphSnapshot
from app.services.observability import (
    ERROR_NO_ACTIVE_PROFILE,
    _empty_graph_snapshot,
    _ready_graph_snapshot,
)

# ---------------------------------------------------------------------------
# Focused read fake (test-local; not a production registration)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, driver: GraphObservabilityFake) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        del kwargs
        self._driver.queries.append(query)
        params = dict(parameters) if parameters is not None else {}
        self._driver.parameters.append(params)
        upper = f" {' '.join(query.upper().split())} "
        for token in (
            " MERGE ",
            " CREATE ",
            " DELETE ",
            " DETACH ",
            " SET ",
            " REMOVE ",
            " DROP ",
        ):
            if token in upper:
                self._driver.write_queries.append(query)
                raise AssertionError(f"write Cypher is not allowed: {query}")
        if self._driver.fail_on_run:
            raise OSError("simulated neo4j read failure")
        return _FakeResult(self._driver.resolve(query, params))


class GraphObservabilityFake:
    """In-memory allowlisted graph answering fixed observability queries."""

    def __init__(
        self,
        *,
        candidates: Sequence[Mapping[str, Any]] | None = None,
        jobs: Sequence[Mapping[str, Any]] | None = None,
        skills: Sequence[Mapping[str, Any]] | None = None,
        edges: Sequence[Mapping[str, Any]] | None = None,
        cvs: Sequence[Mapping[str, Any]] | None = None,
        sections: Sequence[Mapping[str, Any]] | None = None,
        entries: Sequence[Mapping[str, Any]] | None = None,
        fail_on_run: bool = False,
    ) -> None:
        self.candidates = [dict(r) for r in (candidates or ())]
        self.jobs = [dict(r) for r in (jobs or ())]
        self.skills = [dict(r) for r in (skills or ())]
        self.edges = [dict(r) for r in (edges or ())]
        self.cvs = [dict(r) for r in (cvs or ())]
        self.sections = [dict(r) for r in (sections or ())]
        self.entries = [dict(r) for r in (entries or ())]
        self.fail_on_run = fail_on_run
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.write_queries: list[str] = []
        self.session_enter = 0
        self.session_exit = 0

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)

    def resolve(
        self, query: str, params: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        # Active CV branch counts / nodes / edges (observability_cv).
        if "count(cv) AS total" in query and "PROJECTS_TO" in query:
            return [{"total": len(self.cvs)}]
        if "count(sec) AS total" in query:
            return [{"total": len(self.sections)}]
        if "count(entry) AS total" in query:
            return [{"total": len(self.entries)}]
        if "cv.original_name AS original_name" in query:
            ordered = sorted(self.cvs, key=lambda r: str(r.get("id", "")))
            return ordered[:1]
        if "sec.heading AS heading" in query:
            ordered = sorted(
                self.sections,
                key=lambda r: (int(r.get("ordinal", 0)), str(r.get("id", ""))),
            )
            return ordered[:CAP_CV_SECTIONS]
        if "entry.preview AS preview" in query:
            ordered = sorted(
                self.entries,
                key=lambda r: (
                    int(r.get("section_ordinal", 0)),
                    int(r.get("ordinal", 0)),
                    str(r.get("id", "")),
                ),
            )
            return ordered[:CAP_CV_ENTRIES]
        if "PROJECTS_TO|HAS_SECTION|HAS_ENTRY" in query:
            allowed = (
                set(params.get("cv_ids") or [])
                | set(params.get("section_ids") or [])
                | set(params.get("entry_ids") or [])
                | set(params.get("candidate_ids") or [])
            )
            out_cv: list[dict[str, Any]] = []
            for edge in self.edges:
                src = edge.get("source_id")
                tgt = edge.get("target_id")
                etype = edge.get("type")
                if (
                    src in allowed
                    and tgt in allowed
                    and etype in {"PROJECTS_TO", "HAS_SECTION", "HAS_ENTRY"}
                ):
                    out_cv.append(
                        {
                            "source_id": src,
                            "target_id": tgt,
                            "type": etype,
                        }
                    )
            return out_cv
        if "count(c) AS total" in query:
            return [{"total": len(self.candidates)}]
        if "count(j) AS total" in query:
            return [{"total": len(self.jobs)}]
        if "count(s) AS total" in query:
            return [{"total": len(self.skills)}]
        if "c.source_updated_at AS revision" in query:
            ordered = sorted(self.candidates, key=lambda r: str(r.get("id", "")))
            return ordered[:1]
        if "j.title AS title" in query:
            ordered = sorted(self.jobs, key=lambda r: str(r.get("id", "")))
            return ordered[:CAP_JOBS]
        if "s.canonical_key AS canonical_name" in query:
            ordered = sorted(
                self.skills, key=lambda r: str(r.get("canonical_name", ""))
            )
            return ordered[:CAP_SKILLS]
        if "HAS_SKILL|REQUIRES|PREFERS|RELATED_TO" in query:
            cand_ids = set(params.get("candidate_ids") or [])
            job_ids = set(params.get("job_ids") or [])
            skill_keys = set(params.get("skill_keys") or [])
            allowed = cand_ids | job_ids | skill_keys
            out: list[dict[str, Any]] = []
            for edge in self.edges:
                src = edge.get("source_id")
                tgt = edge.get("target_id")
                etype = edge.get("type")
                if (
                    src in allowed
                    and tgt in allowed
                    and etype in ALLOWLISTED_EDGE_TYPES
                    and etype
                    in {"HAS_SKILL", "REQUIRES", "PREFERS", "RELATED_TO"}
                ):
                    out.append(
                        {
                            "source_id": src,
                            "target_id": tgt,
                            "type": etype,
                        }
                    )
            return out
        raise AssertionError(f"unscripted observability query: {query}")


REV = "2024-07-01T12:00:00Z"


def _cand(node_id: str = "active", revision: str = REV) -> dict[str, Any]:
    return {"id": node_id, "revision": revision}


def _job(node_id: str, title: str = "Role", company: str = "Co") -> dict[str, Any]:
    return {
        "id": node_id,
        "title": title,
        "company": company,
        "revision": REV,
    }


def _skill(name: str) -> dict[str, Any]:
    return {"canonical_name": name}


def _edge(src: str, tgt: str, etype: str) -> dict[str, Any]:
    return {"source_id": src, "target_id": tgt, "type": etype}


# ---------------------------------------------------------------------------
# Cypher / allowlist static checks
# ---------------------------------------------------------------------------


def test_templates_are_read_only() -> None:
    assert_read_only_templates()
    joined = " ".join(cypher_statement_templates()).upper()
    padded = f" {' '.join(joined.split())} "
    for bad in (
        " MERGE ",
        " CREATE ",
        " DELETE ",
        " DETACH ",
        " SET ",
        " REMOVE ",
        " DROP ",
    ):
        assert bad not in padded


def test_edge_type_allowlist_exact() -> None:
    assert ALLOWLISTED_EDGE_TYPES == frozenset(
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


# ---------------------------------------------------------------------------
# Projection caps / order / truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_projection_orders_and_caps_nodes_and_edges() -> None:
    jobs = [_job(f"job-{i:02d}") for i in range(25, 0, -1)]  # reverse insert
    skills = [_skill(f"skill-{i:02d}") for i in range(50, 0, -1)]
    # Edges: more than CAP_EDGES between selected endpoints.
    selected_job_ids = sorted(j["id"] for j in jobs)[:CAP_JOBS]
    selected_skills = sorted(s["canonical_name"] for s in skills)[:CAP_SKILLS]
    edges: list[dict[str, Any]] = []
    # HAS_SKILL from candidate to skills
    for s in selected_skills:
        edges.append(_edge("active", s, "HAS_SKILL"))
    # REQUIRES / PREFERS mix
    for jid in selected_job_ids:
        for s in selected_skills[:5]:
            edges.append(_edge(jid, s, "REQUIRES"))
            edges.append(_edge(jid, s, "PREFERS"))
    # RELATED_TO between skills
    for i in range(len(selected_skills) - 1):
        edges.append(
            _edge(selected_skills[i], selected_skills[i + 1], "RELATED_TO")
        )
    # Disallowed type and endpoints outside selection must be dropped.
    edges.append(_edge("active", "outsider", "HAS_SKILL"))
    edges.append(_edge("active", selected_skills[0], "OWNS"))

    assert len(edges) > CAP_EDGES

    fake = GraphObservabilityFake(
        candidates=[_cand()],
        jobs=jobs,
        skills=skills,
        edges=edges,
    )
    projection = await load_bounded_graph_projection(fake)

    assert projection.candidate is not None
    assert projection.candidate.id == "active"
    assert len(projection.jobs) == CAP_JOBS
    assert [j.id for j in projection.jobs] == sorted(j.id for j in projection.jobs)
    assert len(projection.skills) == CAP_SKILLS
    assert [s.canonical_name for s in projection.skills] == sorted(
        s.canonical_name for s in projection.skills
    )
    assert len(projection.edges) == CAP_EDGES
    assert projection.nodes_truncated is True
    assert projection.edges_truncated is True
    # 5 omitted jobs + 10 omitted skills (+ 0 candidates)
    assert projection.omitted_node_count == 5 + 10
    assert projection.omitted_edge_count > 0
    edge_keys = [(e.type, e.source_id, e.target_id) for e in projection.edges]
    assert edge_keys == sorted(edge_keys)
    for edge in projection.edges:
        assert edge.type in ALLOWLISTED_EDGE_TYPES
    assert fake.write_queries == []
    assert fake.session_enter == fake.session_exit == 1


@pytest.mark.asyncio
async def test_projection_empty_graph() -> None:
    fake = GraphObservabilityFake()
    projection = await load_bounded_graph_projection(fake)
    assert projection.candidate is None
    assert projection.jobs == ()
    assert projection.skills == ()
    assert projection.edges == ()
    assert projection.nodes_truncated is False
    assert projection.edges_truncated is False
    assert projection.omitted_node_count == 0
    assert projection.omitted_edge_count == 0


@pytest.mark.asyncio
async def test_projection_driver_failure_raises() -> None:
    fake = GraphObservabilityFake(fail_on_run=True)
    with pytest.raises(Exception):
        await load_bounded_graph_projection(fake)


@pytest.mark.asyncio
async def test_projection_ignores_edges_outside_selected_nodes() -> None:
    fake = GraphObservabilityFake(
        candidates=[_cand()],
        jobs=[_job("job-a"), _job("job-b")],
        skills=[_skill("python"), _skill("rust")],
        edges=[
            _edge("active", "python", "HAS_SKILL"),
            _edge("job-a", "rust", "REQUIRES"),
            # job-z not selected → dropped
            _edge("job-z", "python", "REQUIRES"),
            # skill not selected → dropped
            _edge("active", "golang", "HAS_SKILL"),
        ],
    )
    projection = await load_bounded_graph_projection(fake)
    pairs = {(e.source_id, e.target_id, e.type) for e in projection.edges}
    assert pairs == {
        ("active", "python", "HAS_SKILL"),
        ("job-a", "rust", "REQUIRES"),
    }


# ---------------------------------------------------------------------------
# Service assembly helpers (status vocabulary)
# ---------------------------------------------------------------------------


def test_empty_snapshot_statuses() -> None:
    ready = _empty_graph_snapshot(
        status="ready",
        code=ERROR_NO_ACTIVE_PROFILE,
        summary="No active candidate profile is available for graph inspection.",
    )
    assert ready.status == "ready"
    assert ready.code == ERROR_NO_ACTIVE_PROFILE
    assert ready.candidate is None
    assert ready.jobs == []
    assert ready.edges == []
    assert ready.nodes_truncated is False
    assert ready.rebuild_instruction is None
    GraphSnapshot.model_validate(ready.model_dump(mode="json"))

    stale = _empty_graph_snapshot(
        status="stale",
        code=NEO4J_REBUILD_REQUIRED,
        summary="stale",
        rebuild_instruction=REBUILD_REQUIRED_INSTRUCTION,
    )
    assert stale.status == "stale"
    assert stale.code == NEO4J_REBUILD_REQUIRED
    assert stale.rebuild_instruction is not None
    assert "rebuild" in stale.rebuild_instruction.lower()

    unavailable = _empty_graph_snapshot(
        status="unavailable",
        code=NEO4J_UNAVAILABLE,
        summary="down",
    )
    assert unavailable.status == "unavailable"
    assert unavailable.code == NEO4J_UNAVAILABLE


def test_ready_snapshot_maps_projection() -> None:
    att = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    projection = BoundedGraphProjection(
        cv=ProjectedCv(
            id=att,
            original_name="cv.pdf",
            extraction_version="cv-document-v1",
            revision=REV,
        ),
        sections=(
            ProjectedCvSection(
                id=f"{att}:s0",
                heading="Experience",
                kind="experience",
                ordinal=0,
                entry_count=1,
            ),
        ),
        entries=(
            ProjectedCvEntry(
                id=f"{att}:s0:e0",
                section_id=f"{att}:s0",
                ordinal=0,
                title="Engineer",
                subtitle="Acme",
                date_text="2020",
                preview="Built APIs",
            ),
        ),
        candidate=ProjectedCandidate(id="active", revision=REV),
        jobs=(
            ProjectedJob(
                id="j1", title="SRE", company="Acme", revision=REV
            ),
        ),
        skills=(ProjectedSkill(canonical_name="python"),),
        edges=(
            ProjectedEdge(
                source_id="active", target_id="python", type="HAS_SKILL"
            ),
            ProjectedEdge(
                source_id=att, target_id="active", type="PROJECTS_TO"
            ),
        ),
        nodes_truncated=False,
        edges_truncated=False,
        omitted_node_count=0,
        omitted_edge_count=0,
    )
    snap = _ready_graph_snapshot(projection)
    assert snap.status == "ready"
    assert snap.code is None
    assert snap.cv is not None
    assert snap.cv.id == att
    assert len(snap.sections) == 1
    assert len(snap.entries) == 1
    assert snap.candidate is not None
    assert snap.candidate.id == "active"
    assert len(snap.jobs) == 1
    assert snap.jobs[0].title == "SRE"
    assert snap.skills[0].canonical_name == "python"
    assert any(e.type == "HAS_SKILL" for e in snap.edges)
    # Forbid extras via schema
    body = snap.model_dump(mode="json")
    assert "embedding" not in body
    assert "body" not in str(body)
    GraphSnapshot.model_validate(body)


@pytest.mark.asyncio
async def test_revision_datetime_normalized_in_projection() -> None:
    """load path accepts datetime revisions via fake rows."""
    stamp = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
    fake = GraphObservabilityFake(
        candidates=[{"id": "active", "revision": stamp}],
        jobs=[
            {
                "id": "j1",
                "title": "T",
                "company": "C",
                "revision": stamp,
            }
        ],
    )
    projection = await load_bounded_graph_projection(fake)
    assert projection.candidate is not None
    assert "2024-07-01" in projection.candidate.revision
    assert projection.jobs[0].revision.endswith("Z") or "+" in projection.jobs[
        0
    ].revision


@pytest.mark.asyncio
async def test_active_cv_branch_caps_order_and_allowlist() -> None:
    att = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    sections = [
        {
            "id": f"{att}:s{i:02d}",
            "heading": f"H{i:02d}",
            "kind": "other",
            "ordinal": i,
            "entry_count": 1,
        }
        for i in range(25)
    ]
    entries = [
        {
            "id": f"{att}:s{i:02d}:e0",
            "section_id": f"{att}:s{i:02d}",
            "ordinal": 0,
            "title": f"T{i:02d}",
            "subtitle": None,
            "date_text": None,
            "preview": "p",
            "section_ordinal": i,
        }
        for i in range(70)
    ]
    edges = [
        {"source_id": att, "target_id": "active", "type": "PROJECTS_TO"},
    ]
    for sec in sections[:CAP_CV_SECTIONS]:
        edges.append(
            {
                "source_id": att,
                "target_id": sec["id"],
                "type": "HAS_SECTION",
            }
        )
    for ent in entries[:CAP_CV_ENTRIES]:
        edges.append(
            {
                "source_id": ent["section_id"],
                "target_id": ent["id"],
                "type": "HAS_ENTRY",
            }
        )
    # Disallowed structural type must be dropped.
    edges.append({"source_id": att, "target_id": "active", "type": "OWNS"})

    fake = GraphObservabilityFake(
        candidates=[_cand()],
        cvs=[
            {
                "id": att,
                "original_name": "cv.pdf",
                "extraction_version": "cv-document-v1",
                "revision": REV,
            }
        ],
        sections=sections,
        entries=entries,
        edges=edges,
    )
    projection = await load_bounded_graph_projection(fake)
    assert projection.cv is not None
    assert projection.cv.id == att
    assert len(projection.sections) == CAP_CV_SECTIONS
    assert [s.ordinal for s in projection.sections] == list(
        range(CAP_CV_SECTIONS)
    )
    assert len(projection.entries) == CAP_CV_ENTRIES
    assert projection.nodes_truncated is True
    assert all(
        e.type in ALLOWLISTED_EDGE_TYPES for e in projection.edges
    )
    assert any(e.type == "PROJECTS_TO" for e in projection.edges)
    assert not any(e.type == "OWNS" for e in projection.edges)
    raw = str(projection)
    assert "body" not in raw
