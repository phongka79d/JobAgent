"""SQLite-to-fake-graph Candidate synchronization integration tests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from app.db.enums import OutboxStatus
from app.db.session import create_session_manager
from app.graph.candidate_sync import (
    CANDIDATE_SYNC_OPERATION,
    process_candidate_sync_outbox,
    rebuild_candidate_projection,
)
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile


class StatefulCandidateGraph:
    """Minimal semantic fake for Candidate/Skill MERGE and edge replacement."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.candidates: set[str] = set()
        self.skills: dict[str, dict[str, object]] = {}
        self.edges: set[tuple[str, str]] = set()

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        if self.fail:
            raise RuntimeError("neo4j unavailable")
        assert "RELATED_TO" not in query
        params = dict(parameters or {})
        candidate_id = str(params["candidate_id"])
        self.candidates.add(candidate_id)
        self.edges = {edge for edge in self.edges if edge[0] != candidate_id}
        for skill in params["skills"]:
            canonical_key = str(skill["canonical_key"])
            self.skills[canonical_key] = dict(skill)
            self.edges.add((candidate_id, canonical_key))


def _profile(*keys: str) -> CandidateProfile:
    skills = []
    for key in keys:
        excluded = key.startswith("excluded:")
        canonical_key = key.removeprefix("excluded:")
        skills.append(
            {
                "skill": {
                    "canonical_key": canonical_key,
                    "display_name": "CI/CD" if canonical_key == "ci_cd" else canonical_key,
                    "aliases": ["CI/CD"] if canonical_key == "ci_cd" else [],
                    "category": None,
                    "status": "provisional" if canonical_key == "zig" else "verified",
                    "confidence": 0.8,
                    "evidence": [],
                },
                "proficiency": "intermediate",
                "years": None,
                "source": "cv",
                "excluded": excluded,
                "evidence": [],
            }
        )
    return CandidateProfile.model_validate(
        {
            "summary": "Engineer.",
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": skills,
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.8,
        }
    )


@pytest.mark.asyncio
async def test_successive_approvals_replay_to_exact_current_graph(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "candidate-integration.db")
    await db.create_all()
    graph = StatefulCandidateGraph()
    try:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile("python", "obsolete"))
        assert await process_candidate_sync_outbox(db, graph) == 1

        async with db.session_scope() as session:
            await ProfileRepository(session).replace(
                _profile("python", "ci_cd", "zig", "excluded:obsolete")
            )
            row = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert row is not None and row.status == OutboxStatus.PENDING.value
        assert await process_candidate_sync_outbox(db, graph) == 1
        assert await rebuild_candidate_projection(db, graph) == 1

        assert graph.candidates == {"1"}
        assert graph.edges == {("1", "python"), ("1", "ci_cd"), ("1", "zig")}
        assert graph.skills["ci_cd"]["aliases"] == ["CI/CD"]
        assert graph.skills["zig"]["status"] == "provisional"
        async with db.session_scope() as session:
            row = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert row is not None and row.status == OutboxStatus.SYNCED.value
            assert row.payload == {"candidate_id": "1"}
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_graph_failure_preserves_sqlite_and_rollback_does_not_enqueue(
    tmp_path: Path,
) -> None:
    db = create_session_manager(tmp_path / "candidate-failure.db")
    await db.create_all()
    try:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile("python"))
        assert await process_candidate_sync_outbox(db, StatefulCandidateGraph(fail=True)) == 0

        session = db.session_factory()
        try:
            await ProfileRepository(session).replace(_profile("zig"))
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            approved = await ProfileRepository(session).get()
            row = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert approved is not None
            assert [item.skill.canonical_key for item in approved.profile.skills] == ["python"]
            assert row is not None and row.status == OutboxStatus.FAILED.value

        healthy = StatefulCandidateGraph()
        assert await process_candidate_sync_outbox(db, healthy) == 1
        assert healthy.edges == {("1", "python")}
    finally:
        await db.dispose()
