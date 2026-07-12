"""Replay-safe projection of the approved Candidate singleton into Neo4j."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.db.base import SINGLETON_PK
from app.db.session import DatabaseSessionManager
from app.repositories.graph_outbox import (
    CANDIDATE_SYNC_OPERATION,
    GraphOutboxRepository,
)
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile

DEFAULT_CANDIDATE_SYNC_BATCH_SIZE = 20


class CandidateGraphClient(Protocol):
    """The parameter-bound graph operation required by this projector."""

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None: ...

_PROJECT_CANDIDATE_CYPHER = """
MERGE (c:Candidate {id: $candidate_id})
SET c.current_title = $current_title,
    c.total_experience_years = $total_experience_years
WITH c
OPTIONAL MATCH (c)-[existing:HAS_SKILL]->(:Skill)
DELETE existing
WITH c, $skills AS skills
UNWIND skills AS skill_data
MERGE (skill:Skill {canonical_key: skill_data.canonical_key})
SET skill.display_name = skill_data.display_name,
    skill.aliases = skill_data.aliases,
    skill.category = skill_data.category,
    skill.status = skill_data.status
MERGE (c)-[relationship:HAS_SKILL]->(skill)
SET relationship.proficiency = skill_data.proficiency,
    relationship.years = skill_data.years
""".strip()


def _active_skill_parameters(profile: CandidateProfile) -> list[dict[str, object]]:
    return [
        {
            "canonical_key": candidate_skill.skill.canonical_key,
            "display_name": candidate_skill.skill.display_name,
            "aliases": candidate_skill.skill.aliases,
            "category": candidate_skill.skill.category,
            "status": candidate_skill.skill.status.value,
            "proficiency": candidate_skill.proficiency.value,
            "years": candidate_skill.years,
        }
        for candidate_skill in profile.skills
        if not candidate_skill.excluded
    ]


async def process_candidate_sync_outbox(
    database: DatabaseSessionManager,
    client: CandidateGraphClient,
    *,
    limit: int = DEFAULT_CANDIDATE_SYNC_BATCH_SIZE,
) -> int:
    """Project one bounded candidate outbox slice without mutating SQLite source data."""
    processed = 0
    async with database.session_scope() as session:
        outbox = GraphOutboxRepository(session)
        await outbox.requeue_failed_by_operation(
            operation=CANDIDATE_SYNC_OPERATION,
            limit=limit,
        )
        rows = await outbox.claim_pending(
            limit=limit,
            operation=CANDIDATE_SYNC_OPERATION,
        )
        for row in rows:
            try:
                if row.entity_id != str(SINGLETON_PK) or row.payload != {
                    "candidate_id": str(SINGLETON_PK)
                }:
                    raise ValueError("invalid candidate sync payload")
                approved = await ProfileRepository(session).get()
                if approved is None:
                    raise ValueError("approved candidate missing")
                await client.run_query(
                    _PROJECT_CANDIDATE_CYPHER,
                    {
                        "candidate_id": str(SINGLETON_PK),
                        "current_title": approved.profile.current_title,
                        "total_experience_years": approved.profile.total_experience_years,
                        "skills": _active_skill_parameters(approved.profile),
                    },
                )
            except Exception:
                await outbox.mark_failed(row.id, error="candidate_projection_failed")
            else:
                await outbox.mark_synced(row.id)
                processed += 1
    return processed


async def rebuild_candidate_projection(
    database: DatabaseSessionManager,
    client: CandidateGraphClient,
) -> int:
    """Requeue the canonical singleton and project its current approved state.

    The enqueue commits before graph processing starts, so graph failure cannot
    roll back or otherwise mutate the approved SQLite profile.
    """
    async with database.session_scope() as session:
        approved = await ProfileRepository(session).get()
        if approved is None:
            return 0
        await GraphOutboxRepository(session).enqueue(
            operation=CANDIDATE_SYNC_OPERATION,
            entity_id=str(SINGLETON_PK),
            payload={"candidate_id": str(SINGLETON_PK)},
            requeue_existing=True,
        )
    return await process_candidate_sync_outbox(database, client, limit=1)


__all__ = [
    "CANDIDATE_SYNC_OPERATION",
    "CandidateGraphClient",
    "DEFAULT_CANDIDATE_SYNC_BATCH_SIZE",
    "process_candidate_sync_outbox",
    "rebuild_candidate_projection",
]
