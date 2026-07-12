"""Candidate outbox projection tests using the fake Neo4j driver."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from app.db.enums import OutboxStatus
from app.db.session import DatabaseSessionManager, create_session_manager
from app.graph.candidate_sync import (
    CANDIDATE_SYNC_OPERATION,
    process_candidate_sync_outbox,
    rebuild_candidate_projection,
)
from app.graph.client import Neo4jClient
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from tests.graph.fakes import FakeDriver


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "candidate-sync.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _profile() -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "summary": "Backend engineer.",
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": [
                {
                    "skill": {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": ["Py"],
                        "category": "language",
                        "status": "verified",
                        "confidence": 0.9,
                        "evidence": ["Python service"],
                    },
                    "proficiency": "advanced",
                    "years": None,
                    "source": "cv",
                    "excluded": False,
                    "evidence": ["Python service"],
                },
                {
                    "skill": {
                        "canonical_key": "provisional:unknown-tool",
                        "display_name": "Unknown Tool",
                        "aliases": [],
                        "category": None,
                        "status": "provisional",
                        "confidence": 0.4,
                        "evidence": [],
                    },
                    "proficiency": "beginner",
                    "years": None,
                    "source": "cv",
                    "excluded": True,
                    "evidence": [],
                },
            ],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.7,
        }
    )


@pytest.mark.asyncio
async def test_projects_candidate_skills_idempotently_without_private_payloads(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile())

        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        processed = await process_candidate_sync_outbox(db, client, limit=10)
        assert processed == 1

        async with db.session_scope() as session:
            from app.repositories.graph_outbox import GraphOutboxRepository

            rows = await GraphOutboxRepository(session).claim_pending(limit=10)
            assert rows == []

        assert len(driver.queries) == 1
        recorded = driver.queries[0]
        assert "MERGE (c:Candidate {id: $candidate_id})" in recorded.query
        assert "MERGE (c)-[relationship:HAS_SKILL]->(skill)" in recorded.query
        assert "RELATED_TO" not in recorded.query
        assert recorded.parameters["candidate_id"] == "1"
        assert recorded.parameters["skills"] == [
            {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["Py"],
                "category": "language",
                "status": "verified",
                "proficiency": "advanced",
                "years": None,
            }
        ]

        async with db.session_scope() as session:
            from app.repositories.graph_outbox import GraphOutboxRepository

            row = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert row is not None
            assert row.status == OutboxStatus.SYNCED.value
            assert row.payload == {"candidate_id": "1"}


@pytest.mark.asyncio
async def test_failed_projection_remains_replayable(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile())

        failed_client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: FakeDriver(run_error=RuntimeError("down")),
        )
        assert await process_candidate_sync_outbox(db, failed_client, limit=10) == 0

        healthy = FakeDriver()
        healthy_client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: healthy,
        )
        assert await process_candidate_sync_outbox(db, healthy_client, limit=10) == 1


@pytest.mark.asyncio
async def test_legitimate_slash_alias_is_projected_not_treated_as_path(
    tmp_path: Path,
) -> None:
    data = _profile().model_dump(mode="json")
    data["skills"][0]["skill"].update(
        canonical_key="ci_cd",
        display_name="CI/CD",
        aliases=["CI/CD", "continuous integration"],
    )
    profile = CandidateProfile.model_validate(data)
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(profile)

        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_candidate_sync_outbox(db, client) == 1
        skill = driver.queries[0].parameters["skills"][0]
        assert skill["display_name"] == "CI/CD"
        assert skill["aliases"] == ["CI/CD", "continuous integration"]


@pytest.mark.asyncio
async def test_candidate_rebuild_requeues_synced_singleton(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            await ProfileRepository(session).replace(_profile())

        driver = FakeDriver()
        client = Neo4jClient(
            uri="bolt://test.invalid",
            user="neo4j",
            password="password",
            driver_factory=lambda: driver,
        )
        assert await process_candidate_sync_outbox(db, client) == 1
        assert await rebuild_candidate_projection(db, client) == 1
        assert len(driver.queries) == 2
