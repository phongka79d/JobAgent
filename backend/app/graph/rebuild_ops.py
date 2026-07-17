"""Graph clear, label-scoped counts, and projection helpers for rebuild.

Owns destructive JobAgent label clears and exact endpoint-scoped relationship
counts. Does not open SQLite, call ShopAIKey, or own the public CLI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.graph.sync_shared import AsyncGraphDriver, consume_result

# Label-scoped clear only — never an unrestricted all-node DETACH DELETE.
# CV owned nodes first so relationships to Candidate are removed with the CV.
CLEAR_CV_ENTRY_CYPHER: str = "MATCH (e:CVEntry) DETACH DELETE e"
CLEAR_CV_SECTION_CYPHER: str = "MATCH (s:CVSection) DETACH DELETE s"
CLEAR_CV_CYPHER: str = "MATCH (cv:CV) DETACH DELETE cv"
CLEAR_CANDIDATE_CYPHER: str = "MATCH (c:Candidate) DETACH DELETE c"
CLEAR_JOB_CYPHER: str = "MATCH (j:Job) DETACH DELETE j"
CLEAR_SKILL_CYPHER: str = "MATCH (s:Skill) DETACH DELETE s"

CLEAR_STATEMENTS: tuple[str, ...] = (
    CLEAR_CV_ENTRY_CYPHER,
    CLEAR_CV_SECTION_CYPHER,
    CLEAR_CV_CYPHER,
    CLEAR_CANDIDATE_CYPHER,
    CLEAR_JOB_CYPHER,
    CLEAR_SKILL_CYPHER,
)

COUNT_ORDER: tuple[str, ...] = (
    "CV",
    "CVSection",
    "CVEntry",
    "Candidate",
    "Job",
    "Skill",
    "PROJECTS_TO",
    "HAS_SECTION",
    "HAS_ENTRY",
    "HAS_SKILL",
    "REQUIRES",
    "PREFERS",
    "RELATED_TO",
)

# Exact JobAgent endpoint labels only — unrelated same-type edges are excluded.
COUNT_CYPHER: Mapping[str, str] = {
    "CV": "MATCH (cv:CV) RETURN count(cv) AS n",
    "CVSection": "MATCH (s:CVSection) RETURN count(s) AS n",
    "CVEntry": "MATCH (e:CVEntry) RETURN count(e) AS n",
    "Candidate": "MATCH (c:Candidate) RETURN count(c) AS n",
    "Job": "MATCH (j:Job) RETURN count(j) AS n",
    "Skill": "MATCH (s:Skill) RETURN count(s) AS n",
    "PROJECTS_TO": (
        "MATCH (:CV)-[r:PROJECTS_TO]->(:Candidate) RETURN count(r) AS n"
    ),
    "HAS_SECTION": (
        "MATCH (:CV)-[r:HAS_SECTION]->(:CVSection) RETURN count(r) AS n"
    ),
    "HAS_ENTRY": (
        "MATCH (:CVSection)-[r:HAS_ENTRY]->(:CVEntry) RETURN count(r) AS n"
    ),
    "HAS_SKILL": (
        "MATCH (:Candidate)-[r:HAS_SKILL]->(:Skill) RETURN count(r) AS n"
    ),
    "REQUIRES": "MATCH (:Job)-[r:REQUIRES]->(:Skill) RETURN count(r) AS n",
    "PREFERS": "MATCH (:Job)-[r:PREFERS]->(:Skill) RETURN count(r) AS n",
    "RELATED_TO": (
        "MATCH (:Skill)-[r:RELATED_TO]->(:Skill) RETURN count(r) AS n"
    ),
}


@dataclass(frozen=True, slots=True)
class RebuildCounts:
    """Printed entity and relationship totals after a successful rebuild."""

    CV: int
    CVSection: int
    CVEntry: int
    Candidate: int
    Job: int
    Skill: int
    PROJECTS_TO: int
    HAS_SECTION: int
    HAS_ENTRY: int
    HAS_SKILL: int
    REQUIRES: int
    PREFERS: int
    RELATED_TO: int

    def as_mapping(self) -> dict[str, int]:
        return {
            "CV": self.CV,
            "CVSection": self.CVSection,
            "CVEntry": self.CVEntry,
            "Candidate": self.Candidate,
            "Job": self.Job,
            "Skill": self.Skill,
            "PROJECTS_TO": self.PROJECTS_TO,
            "HAS_SECTION": self.HAS_SECTION,
            "HAS_ENTRY": self.HAS_ENTRY,
            "HAS_SKILL": self.HAS_SKILL,
            "REQUIRES": self.REQUIRES,
            "PREFERS": self.PREFERS,
            "RELATED_TO": self.RELATED_TO,
        }


async def clear_jobagent_graph(driver: AsyncGraphDriver) -> None:
    """Delete only JobAgent-owned labels (CV branch, Candidate, Job, Skill)."""
    async with driver.session() as session:
        for statement in CLEAR_STATEMENTS:
            result = await session.run(statement)
            await consume_result(result)


async def scalar_count(result: Any) -> int:
    """Extract a single integer count from a Neo4j async result."""
    if result is None:
        return 0
    single = getattr(result, "single", None)
    if callable(single):
        record = await single()
        if record is None:
            return 0
        if isinstance(record, Mapping):
            return int(record.get("n", 0))
        try:
            return int(record["n"])
        except Exception:
            return int(record[0])
    data = getattr(result, "data", None)
    if callable(data):
        rows = await data()
        if not rows:
            return 0
        first = rows[0]
        if isinstance(first, Mapping):
            return int(first.get("n", 0))
        return int(first)
    return 0


async def count_graph(driver: AsyncGraphDriver) -> RebuildCounts:
    """Return authoritative post-rebuild entity/relationship counts."""
    values: dict[str, int] = {}
    async with driver.session() as session:
        for key in COUNT_ORDER:
            result = await session.run(COUNT_CYPHER[key])
            values[key] = await scalar_count(result)
    return RebuildCounts(
        CV=values["CV"],
        CVSection=values["CVSection"],
        CVEntry=values["CVEntry"],
        Candidate=values["Candidate"],
        Job=values["Job"],
        Skill=values["Skill"],
        PROJECTS_TO=values["PROJECTS_TO"],
        HAS_SECTION=values["HAS_SECTION"],
        HAS_ENTRY=values["HAS_ENTRY"],
        HAS_SKILL=values["HAS_SKILL"],
        REQUIRES=values["REQUIRES"],
        PREFERS=values["PREFERS"],
        RELATED_TO=values["RELATED_TO"],
    )


__all__ = [
    "CLEAR_CANDIDATE_CYPHER",
    "CLEAR_CV_CYPHER",
    "CLEAR_CV_ENTRY_CYPHER",
    "CLEAR_CV_SECTION_CYPHER",
    "CLEAR_JOB_CYPHER",
    "CLEAR_SKILL_CYPHER",
    "CLEAR_STATEMENTS",
    "COUNT_CYPHER",
    "COUNT_ORDER",
    "RebuildCounts",
    "clear_jobagent_graph",
    "count_graph",
    "scalar_count",
]
