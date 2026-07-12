"""Injectable fake Neo4j driver/session for graph unit tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

RecordProvider = Callable[[str, Mapping[str, Any]], list[dict[str, Any]]]


@dataclass
class RecordedQuery:
    query: str
    parameters: Mapping[str, Any]


class FakeResult:
    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self._records = list(records) if records is not None else []

    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return list(self._records)


class FakeSession:
    def __init__(self, driver: FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        return None

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> FakeResult:
        params = dict(parameters) if parameters is not None else {}
        self._driver.queries.append(RecordedQuery(query=query, parameters=params))
        if self._driver.run_error is not None:
            raise self._driver.run_error
        if self._driver.run_started is not None:
            self._driver.run_started.set()
        if self._driver.run_gate is not None:
            await self._driver.run_gate.wait()
        if self._driver.run_delay_seconds > 0:
            await asyncio.sleep(self._driver.run_delay_seconds)
        self._driver.apply_write(query, params)
        records: list[dict[str, Any]] = []
        if self._driver.record_provider is not None:
            records = list(self._driver.record_provider(query, params))
        else:
            records = self._driver.default_records(query, params)
        return FakeResult(records)


@dataclass
class FakeDriver:
    """In-memory driver that records queries and can simulate failures.

    Close semantics: ``closed`` is set only after a successful close. A
    ``close_error`` or cancelled wait on ``close_gate`` must not pre-mark the
    resource closed, so ownership tests can observe abandoned-vs-owned state.

    When ``track_graph`` is True (default), Job/Candidate MERGE writes update an
    in-memory subgraph so rebuild ``fetch_records`` parity checks can observe
    IDs and counts without a live Neo4j instance.
    """

    queries: list[RecordedQuery] = field(default_factory=list)
    verify_calls: int = 0
    close_calls: int = 0
    run_error: BaseException | None = None
    verify_error: BaseException | None = None
    close_error: BaseException | None = None
    verify_delay_seconds: float = 0.0
    run_delay_seconds: float = 0.0
    closed: bool = False
    track_graph: bool = True
    record_provider: RecordProvider | None = None
    # Event gates for deterministic concurrency (set before client ops).
    verify_started: asyncio.Event | None = None
    verify_gate: asyncio.Event | None = None
    run_started: asyncio.Event | None = None
    run_gate: asyncio.Event | None = None
    close_started: asyncio.Event | None = None
    close_gate: asyncio.Event | None = None
    # Tracked subgraph (rebuild parity / semantic checks).
    job_ids: set[str] = field(default_factory=set)
    skill_keys: set[str] = field(default_factory=set)
    family_keys: set[str] = field(default_factory=set)
    requires_count: int = 0
    prefers_count: int = 0
    in_family_count: int = 0
    candidate_ids: set[str] = field(default_factory=set)
    has_skill_count: int = 0
    # Per-job edge counts for stale-edge replacement on re-MERGE.
    _job_requires: dict[str, int] = field(default_factory=dict)
    _job_prefers: dict[str, int] = field(default_factory=dict)
    _job_families: dict[str, int] = field(default_factory=dict)
    _candidate_skills: dict[str, int] = field(default_factory=dict)

    def session(self, **kwargs: Any) -> FakeSession:
        return FakeSession(self)

    async def verify_connectivity(self, **kwargs: Any) -> None:
        self.verify_calls += 1
        if self.verify_started is not None:
            self.verify_started.set()
        if self.verify_gate is not None:
            await self.verify_gate.wait()
        if self.verify_delay_seconds > 0:
            await asyncio.sleep(self.verify_delay_seconds)
        if self.verify_error is not None:
            raise self.verify_error

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_started is not None:
            self.close_started.set()
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_error is not None:
            # Do not mark closed before a failed cleanup — ownership tests rely
            # on ``closed`` reflecting successful resource release only.
            raise self.close_error
        self.closed = True

    def apply_write(self, query: str, params: Mapping[str, Any]) -> None:
        """Update tracked subgraph from known JobAgent write patterns."""
        if not self.track_graph:
            return
        # Label-scoped clear statements.
        if "DETACH DELETE" in query:
            if ":Candidate" in query:
                self.candidate_ids.clear()
                self.has_skill_count = 0
                self._candidate_skills.clear()
            if ":Job" in query:
                self.job_ids.clear()
                self.requires_count = 0
                self.prefers_count = 0
                self.in_family_count = 0
                self._job_requires.clear()
                self._job_prefers.clear()
                self._job_families.clear()
            if ":Skill" in query:
                self.skill_keys.clear()
            if ":JobFamily" in query:
                self.family_keys.clear()
            return

        if "MERGE (j:Job" in query and "job_id" in params:
            job_id = str(params["job_id"])
            self.job_ids.add(job_id)
            # Replace owned edge counts for this job.
            prev_req = self._job_requires.pop(job_id, 0)
            prev_pref = self._job_prefers.pop(job_id, 0)
            prev_fam = self._job_families.pop(job_id, 0)
            self.requires_count = max(0, self.requires_count - prev_req)
            self.prefers_count = max(0, self.prefers_count - prev_pref)
            self.in_family_count = max(0, self.in_family_count - prev_fam)

            req_skills = list(params.get("required_skills") or [])
            pref_skills = list(params.get("preferred_skills") or [])
            families = list(params.get("job_families") or [])
            for skill in req_skills:
                key = str(skill.get("canonical_key", ""))
                if key:
                    self.skill_keys.add(key)
            for skill in pref_skills:
                key = str(skill.get("canonical_key", ""))
                if key:
                    self.skill_keys.add(key)
            for family in families:
                key = str(family.get("canonical_key", ""))
                if key:
                    self.family_keys.add(key)
            self._job_requires[job_id] = len(req_skills)
            self._job_prefers[job_id] = len(pref_skills)
            self._job_families[job_id] = len(families)
            self.requires_count += len(req_skills)
            self.prefers_count += len(pref_skills)
            self.in_family_count += len(families)
            return

        if "MERGE (c:Candidate" in query and "candidate_id" in params:
            cand_id = str(params["candidate_id"])
            self.candidate_ids.add(cand_id)
            prev = self._candidate_skills.pop(cand_id, 0)
            self.has_skill_count = max(0, self.has_skill_count - prev)
            skills = list(params.get("skills") or [])
            for skill in skills:
                key = str(skill.get("canonical_key", ""))
                if key:
                    self.skill_keys.add(key)
            self._candidate_skills[cand_id] = len(skills)
            self.has_skill_count += len(skills)

    def default_records(
        self,
        query: str,
        params: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Answer common rebuild parity read queries from tracked state."""
        del params  # parameter-bound; static aggregates ignore values
        if not self.track_graph:
            return []
        if "collect(j.id)" in query and "Job" in query:
            return [{"job_ids": sorted(self.job_ids)}]
        if "count(s) AS skill_count" in query or (
            "Skill" in query and "skill_count" in query
        ):
            return [{"skill_count": len(self.skill_keys)}]
        if "JobFamily" in query and "family_count" in query:
            return [{"family_count": len(self.family_keys)}]
        if "REQUIRES" in query and "requires_count" in query:
            return [{"requires_count": self.requires_count}]
        if "PREFERS" in query and "prefers_count" in query:
            return [{"prefers_count": self.prefers_count}]
        if "IN_FAMILY" in query and "in_family_count" in query:
            return [{"in_family_count": self.in_family_count}]
        if "Candidate" in query and "candidate_count" in query:
            return [{"candidate_count": len(self.candidate_ids)}]
        if "HAS_SKILL" in query and "has_skill_count" in query:
            return [{"has_skill_count": self.has_skill_count}]
        return []
