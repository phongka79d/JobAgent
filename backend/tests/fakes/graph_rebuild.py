"""Reusable fake Neo4j async driver for provider-free rebuild tests (Plan 5 / 03D).

Records Cypher, tracks label-scoped state for counts, and preserves unrelated
foreign same-type relationships. Never imported by production registration.
"""

from __future__ import annotations

import re
from typing import Any


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows if rows is not None else []

    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return list(self._rows)

    async def single(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, driver: FakeNeo4jDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        del kwargs
        if self._driver.fail_on_run:
            raise OSError("simulated neo4j write failure")
        self._driver.queries.append(query)
        params = dict(parameters) if parameters is not None else {}
        self._driver.parameters.append(params)
        self._driver._apply(query, params)
        return _FakeResult(self._driver._count_rows(query))


class FakeNeo4jDriver:
    """Async-driver stand-in: Cypher capture + simple label/rel bookkeeping."""

    def __init__(self, *, fail_on_run: bool = False) -> None:
        self.fail_on_run = fail_on_run
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.session_enter = 0
        self.session_exit = 0
        # Unrelated label that must survive label-scoped clear.
        self.other_nodes: set[str] = set()
        # Unrelated same-type relationships (non JobAgent endpoints).
        self.foreign_has_skill = 0
        self.foreign_requires = 0
        self.foreign_prefers = 0
        self.foreign_related_to = 0
        self.candidates: set[str] = set()
        self.jobs: set[str] = set()
        self.skills: set[str] = set()
        self.has_skill = 0
        self.requires = 0
        self.prefers = 0
        self.related_to = 0
        self.schema_statements = 0

    def seed_unrelated(self, node_id: str = "keep-me") -> None:
        self.other_nodes.add(node_id)

    def seed_unrelated_same_type_relationships(self) -> None:
        """Foreign nodes using JobAgent relationship types (must not inflate)."""
        self.foreign_has_skill = 7
        self.foreign_requires = 5
        self.foreign_prefers = 3
        self.foreign_related_to = 9

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)

    def _apply(self, query: str, params: dict[str, Any]) -> None:
        q = " ".join(query.split())
        if "DETACH DELETE" in q and "Candidate" in q and "MATCH (c:Candidate)" in q:
            self.candidates.clear()
            self.has_skill = 0
            return
        if "DETACH DELETE" in q and "Job" in q and "MATCH (j:Job)" in q:
            self.jobs.clear()
            self.requires = 0
            self.prefers = 0
            return
        if "DETACH DELETE" in q and "Skill" in q and "MATCH (s:Skill)" in q:
            self.skills.clear()
            self.has_skill = 0
            self.requires = 0
            self.prefers = 0
            self.related_to = 0
            return
        if q.startswith("CREATE CONSTRAINT") or q.startswith("CREATE VECTOR INDEX"):
            self.schema_statements += 1
            return
        if "MERGE (c:Candidate" in q:
            self.candidates.add(str(params.get("candidate_id", "active")))
            return
        if "MERGE (j:Job" in q:
            self.jobs.add(str(params.get("job_id", "")))
            return
        if "DELETE r" in q and "HAS_SKILL" in q:
            self.has_skill = 0
            return
        if "DELETE r" in q and "REQUIRES|PREFERS" in q:
            return
        if "HAS_SKILL" in q and "UNWIND $skills" in q:
            skills = params.get("skills") or []
            self.has_skill = len(skills)
            for row in skills:
                key = row.get("skill", {}).get("canonical_key")
                if key:
                    self.skills.add(str(key))
            return
        if "MERGE (j)-[r:REQUIRES]->(s)" in q or (
            "REQUIRES" in q and "UNWIND $requires" in q
        ):
            requires = params.get("requires") or []
            self.requires += len(requires)
            for row in requires:
                key = row.get("skill", {}).get("canonical_key")
                if key:
                    self.skills.add(str(key))
            return
        if "MERGE (j)-[r:PREFERS]->(s)" in q or (
            "PREFERS" in q and "UNWIND $prefers" in q
        ):
            prefers = params.get("prefers") or []
            self.prefers += len(prefers)
            for row in prefers:
                key = row.get("skill", {}).get("canonical_key")
                if key:
                    self.skills.add(str(key))
            return
        if "seed_skills" in params:
            for row in params.get("seed_skills") or []:
                key = row.get("canonical_key")
                if key:
                    self.skills.add(str(key))
            return
        if "related" in params and "RELATED_TO" in q:
            self.related_to = len(params.get("related") or [])
            return

    def _count_rows(self, query: str) -> list[dict[str, Any]]:
        q = query
        if "count" not in q.lower() or "DETACH" in q:
            return []
        # Endpoint-scoped relationship counts only.
        if "HAS_SKILL" in q and "Candidate" in q and "Skill" in q and "RETURN" in q:
            return [{"n": self.has_skill}]
        if "REQUIRES" in q and "Job" in q and "Skill" in q and "RETURN" in q:
            return [{"n": self.requires}]
        if "PREFERS" in q and "Job" in q and "Skill" in q and "RETURN" in q:
            return [{"n": self.prefers}]
        if "RELATED_TO" in q and "Skill" in q and "RETURN" in q:
            return [{"n": self.related_to}]
        # Reject legacy global MATCH ()-[r:TYPE]->() style if issued.
        if re.search(r"MATCH\s*\(\s*\)-\[r:", q):
            return [{"n": -1}]
        if ":Candidate" in q and "RETURN" in q:
            return [{"n": len(self.candidates)}]
        if ":Job" in q and "RETURN" in q and "embedding" not in q.lower():
            return [{"n": len(self.jobs)}]
        if ":Skill" in q and "RETURN" in q:
            return [{"n": len(self.skills)}]
        return [{"n": 0}]
