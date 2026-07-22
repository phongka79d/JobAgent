"""Idempotent Candidate/Skill graph synchronization (Plan 4 §7.7, Master §8/§21).

After SQLite profile commit, projects the approved Candidate Profile into Neo4j:

* ``MERGE`` ``Candidate{id:'active'}`` with ``source_updated_at`` from SQLite
  ``candidate_profile.updated_at``
* Rebuild only this Candidate's ``HAS_SKILL`` edges from non-excluded skills
* ``MERGE`` canonical ``Skill`` nodes (display name, aliases, category)
* Idempotently load seed ``RELATED_TO{weight, source}`` via shared seed projection

Shared driver protocol, failure codes, timestamp/result helpers, and seed
Skill/``RELATED_TO`` projection live in :mod:`app.graph.sync_shared`. This
module owns only Candidate/HAS_SKILL domain Cypher.

Neo4j is a derived index, never the profile source of truth. Runtime values are
bound as Cypher parameters only. Raw CV text never enters this module.

Callers inject an async Neo4j driver (real or fake). Failures raise
:class:`CandidateSyncError` with stable code ``NEO4J_SYNC_FAILED``; they must
not roll back committed SQLite state.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph.sync_shared import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    consume_result,
    iso_utc,
    project_seed_skills_and_related,
    related_to_param_rows,
    seed_skill_param_rows,
    shared_seed_cypher_templates,
    skill_ref_node_props,
)
from app.schemas.profile import CandidateProfile, CandidateSkill
from app.services.skill_normalization import SkillNormalizer


class CandidateSyncError(Exception):
    """Raised when Candidate graph synchronization fails.

    Carries stable ``code`` (always :data:`NEO4J_SYNC_FAILED` for this owner)
    and developer rebuild guidance. Never embeds secrets or raw CV text.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = NEO4J_SYNC_FAILED,
        rebuild_instruction: str = NEO4J_REBUILD_INSTRUCTION,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.rebuild_instruction = rebuild_instruction
        self.message = message


def candidate_skill_param_row(skill: CandidateSkill) -> dict[str, Any]:
    """Exact Skill/HAS_SKILL parameter row shared by sync and integrity reads."""
    return {
        "skill": skill_ref_node_props(skill.skill),
        "rel": {
            "confidence": float(skill.confidence),
            "years": skill.years,
            "proficiency": skill.proficiency,
            "evidence": list(skill.evidence),
        },
    }


def non_excluded_skills(profile: CandidateProfile) -> list[CandidateSkill]:
    """Return skills that belong in Neo4j (exclusions stay SQLite-only)."""
    return [s for s in profile.skills if not s.excluded]


async def sync_candidate(
    driver: AsyncGraphDriver,
    *,
    profile: CandidateProfile,
    source_updated_at: datetime,
    normalizer: SkillNormalizer,
) -> None:
    """Project *profile* onto the singleton Candidate graph identity.

    Parameterized, idempotent Cypher only. Raises :class:`CandidateSyncError`
    on any driver/session failure without mutating SQLite.
    """
    if not isinstance(source_updated_at, datetime):
        raise CandidateSyncError(
            "source_updated_at must be a datetime from candidate_profile.updated_at"
        )

    skills = non_excluded_skills(profile)
    skill_rows = [candidate_skill_param_row(skill) for skill in skills]
    related = related_to_param_rows(normalizer)
    seed_skills = seed_skill_param_rows(normalizer)

    params: dict[str, Any] = {
        # Singleton identity from the SQLite profile model owner (Master §8.1).
        "candidate_id": CANDIDATE_PROFILE_ID,
        "source_updated_at": iso_utc(source_updated_at),
        "skills": skill_rows,
    }

    merge_candidate = (
        "MERGE (c:Candidate {id: $candidate_id}) "
        "SET c.source_updated_at = $source_updated_at "
        "RETURN c.id AS id"
    )
    clear_has_skill = (
        "MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->() "
        "DELETE r"
    )
    merge_has_skills = (
        "UNWIND $skills AS row "
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key}) "
        "SET s.display_name = row.skill.display_name, "
        "    s.aliases = row.skill.aliases, "
        "    s.category = row.skill.category "
        "WITH s, row "
        "MATCH (c:Candidate {id: $candidate_id}) "
        "MERGE (c)-[r:HAS_SKILL]->(s) "
        "SET r.confidence = row.rel.confidence, "
        "    r.years = row.rel.years, "
        "    r.proficiency = row.rel.proficiency, "
        "    r.evidence = row.rel.evidence"
    )

    try:
        async with driver.session() as session:
            result = await session.run(merge_candidate, params)
            await consume_result(result)
            result = await session.run(clear_has_skill, params)
            await consume_result(result)
            if skill_rows:
                result = await session.run(merge_has_skills, params)
                await consume_result(result)
            await project_seed_skills_and_related(
                session,
                seed_skills=seed_skills,
                related=related,
            )
    except CandidateSyncError:
        raise
    except Exception as exc:
        raise CandidateSyncError(
            "Candidate/Skill Neo4j synchronization failed"
        ) from exc


def cypher_statement_templates() -> Sequence[str]:
    """Return fixed Cypher templates for static review (no runtime values)."""
    return (
        "MERGE (c:Candidate {id: $candidate_id})",
        "MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->()",
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key})",
        "MERGE (c)-[r:HAS_SKILL]->(s)",
        *shared_seed_cypher_templates(),
    )


__all__ = [
    "AsyncGraphDriver",
    "CandidateSyncError",
    "NEO4J_REBUILD_INSTRUCTION",
    "NEO4J_SYNC_FAILED",
    "cypher_statement_templates",
    "non_excluded_skills",
    "sync_candidate",
]
