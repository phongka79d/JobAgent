"""Idempotent Candidate/Skill graph synchronization (Plan 4 §7.7, Master §8/§21).

After SQLite profile commit, projects the approved Candidate Profile into Neo4j:

* ``MERGE`` ``Candidate{id:'active'}`` with ``source_updated_at`` from SQLite
  ``candidate_profile.updated_at``
* Rebuild only this Candidate's ``HAS_SKILL`` edges from non-excluded skills
* ``MERGE`` canonical ``Skill`` nodes (display name, aliases, category)
* Idempotently load seed ``RELATED_TO{weight, source}`` from the taxonomy

Neo4j is a derived index, never the profile source of truth. Runtime values are
bound as Cypher parameters only. Raw CV text never enters this module.

Callers inject an async Neo4j driver (real or fake). Failures raise
:class:`CandidateSyncError` with stable code ``NEO4J_SYNC_FAILED``; they must
not roll back committed SQLite state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.schemas.profile import CandidateProfile, CandidateSkill
from app.services.skill_normalization import SkillNormalizer

# Stable failure code for post-commit derived-sync failures (Master §20/§21).
NEO4J_SYNC_FAILED: str = "NEO4J_SYNC_FAILED"

# Local rebuild guidance returned with NEO4J_SYNC_FAILED (developer-facing).
NEO4J_REBUILD_INSTRUCTION: str = (
    "Restore Neo4j connectivity and run the local graph rebuild command to "
    "reproject Candidate/Skill data from SQLite."
)

_CANDIDATE_ID: str = CANDIDATE_PROFILE_ID  # "active"


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


class _AsyncResult(Protocol):
    async def consume(self) -> Any: ...


class _AsyncSession(Protocol):
    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _AsyncResult: ...

    async def __aenter__(self) -> _AsyncSession: ...

    async def __aexit__(self, *args: object) -> None: ...


class AsyncGraphDriver(Protocol):
    """Minimal async Neo4j driver surface used by this module."""

    def session(self, **config: Any) -> _AsyncSession: ...


def _iso_utc(value: datetime) -> str:
    """Serialize a timezone-aware (or naive-as-UTC) datetime for Neo4j properties."""
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _skill_props(skill: CandidateSkill) -> dict[str, Any]:
    """Parameter map for one Skill node (no raw CV body)."""
    ref = skill.skill
    return {
        "canonical_key": ref.canonical_key,
        "display_name": ref.display_name,
        "aliases": list(ref.aliases),
        "category": ref.category,
    }


def _has_skill_props(skill: CandidateSkill) -> dict[str, Any]:
    """Parameter map for one HAS_SKILL relationship."""
    return {
        "confidence": float(skill.confidence),
        "years": skill.years,
        "proficiency": skill.proficiency,
        "evidence": list(skill.evidence),
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
    skill_rows: list[dict[str, Any]] = [
        {
            "skill": _skill_props(s),
            "rel": _has_skill_props(s),
        }
        for s in skills
    ]
    related: list[dict[str, Any]] = [
        {
            "from_key": edge.from_key,
            "to_key": edge.to_key,
            "weight": float(edge.weight),
            "source": edge.source,
        }
        for edge in normalizer.approved_relationships()
    ]
    # Seed Skill metadata for RELATED_TO endpoints (and any seed keys).
    seed_skill_rows: list[dict[str, Any]] = []
    for seed in normalizer.taxonomy.skills:
        seed_skill_rows.append(
            {
                "canonical_key": seed.canonical_key,
                "display_name": seed.display_name,
                "aliases": list(seed.aliases),
                "category": seed.category,
            }
        )

    params: dict[str, Any] = {
        "candidate_id": _CANDIDATE_ID,
        "source_updated_at": _iso_utc(source_updated_at),
        "skills": skill_rows,
        "related": related,
        "seed_skills": seed_skill_rows,
    }

    # Single session / write sequence so a partial failure is one exception.
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
    merge_seed_skills = (
        "UNWIND $seed_skills AS row "
        "MERGE (s:Skill {canonical_key: row.canonical_key}) "
        "SET s.display_name = row.display_name, "
        "    s.aliases = row.aliases, "
        "    s.category = row.category"
    )
    merge_related = (
        "UNWIND $related AS edge "
        "MATCH (a:Skill {canonical_key: edge.from_key}) "
        "MATCH (b:Skill {canonical_key: edge.to_key}) "
        "MERGE (a)-[r:RELATED_TO]->(b) "
        "SET r.weight = edge.weight, r.source = edge.source"
    )

    try:
        async with driver.session() as session:
            result = await session.run(merge_candidate, params)
            await _consume(result)
            result = await session.run(clear_has_skill, params)
            await _consume(result)
            if skill_rows:
                result = await session.run(merge_has_skills, params)
                await _consume(result)
            if seed_skill_rows:
                result = await session.run(merge_seed_skills, params)
                await _consume(result)
            if related:
                result = await session.run(merge_related, params)
                await _consume(result)
    except CandidateSyncError:
        raise
    except Exception as exc:
        raise CandidateSyncError(
            "Candidate/Skill Neo4j synchronization failed"
        ) from exc


async def _consume(result: Any) -> None:
    """Drain an async result when the driver provides ``consume``/``data``."""
    if result is None:
        return
    consume = getattr(result, "consume", None)
    if callable(consume):
        await consume()
        return
    data = getattr(result, "data", None)
    if callable(data):
        await data()


def cypher_statement_templates() -> Sequence[str]:
    """Return fixed Cypher templates for static review (no runtime values)."""
    return (
        "MERGE (c:Candidate {id: $candidate_id})",
        "MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->()",
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key})",
        "MERGE (c)-[r:HAS_SKILL]->(s)",
        "MERGE (a)-[r:RELATED_TO]->(b)",
    )
