"""Shared Neo4j projection primitives for Candidate and Job sync.

Owns only genuinely shared graph-sync building blocks so ``sync_candidate``,
``sync_job``, and later rebuild can reuse one driver protocol, failure contract,
timestamp serialization, result drain, and seed Skill/``RELATED_TO`` projection
without requiring an active Candidate or duplicating Cypher/business logic.

Domain relationship rebuild (HAS_SKILL / REQUIRES / PREFERS) stays in each
domain owner. Fixed DDL stays in ``constraints.py``. No SQLite sessions,
provider calls, or raw document bodies enter this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from app.schemas.skills import SkillRef
from app.services.skill_normalization import SkillNormalizer

# Stable failure code for post-commit derived-sync failures (Master §20/§21).
NEO4J_SYNC_FAILED: str = "NEO4J_SYNC_FAILED"

# Local rebuild guidance returned with NEO4J_SYNC_FAILED (developer-facing).
NEO4J_REBUILD_INSTRUCTION: str = (
    "Restore Neo4j connectivity and run the local graph rebuild command to "
    "reproject Candidate/Job/Skill data from SQLite."
)

# Fixed Cypher templates for seed Skill / RELATED_TO projection (parameters only).
MERGE_SEED_SKILLS_CYPHER: str = (
    "UNWIND $seed_skills AS row "
    "MERGE (s:Skill {canonical_key: row.canonical_key}) "
    "SET s.display_name = row.display_name, "
    "    s.aliases = row.aliases, "
    "    s.category = row.category"
)

MERGE_RELATED_TO_CYPHER: str = (
    "UNWIND $related AS edge "
    "MATCH (a:Skill {canonical_key: edge.from_key}) "
    "MATCH (b:Skill {canonical_key: edge.to_key}) "
    "MERGE (a)-[r:RELATED_TO]->(b) "
    "SET r.weight = edge.weight, r.source = edge.source"
)


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
    """Minimal async Neo4j driver surface used by graph sync owners."""

    def session(self, **config: Any) -> _AsyncSession: ...


def iso_utc(value: datetime) -> str:
    """Serialize a timezone-aware (or naive-as-UTC) datetime for Neo4j properties."""
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


async def consume_result(result: Any) -> None:
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


def skill_ref_node_props(ref: SkillRef) -> dict[str, Any]:
    """Parameter map for one canonical Skill node (identity + seed metadata)."""
    return {
        "canonical_key": ref.canonical_key,
        "display_name": ref.display_name,
        "aliases": list(ref.aliases),
        "category": ref.category,
    }


def seed_skill_param_rows(normalizer: SkillNormalizer) -> list[dict[str, Any]]:
    """Approved seed Skill node property rows for MERGE projection."""
    rows: list[dict[str, Any]] = []
    for seed in normalizer.taxonomy.skills:
        rows.append(
            {
                "canonical_key": seed.canonical_key,
                "display_name": seed.display_name,
                "aliases": list(seed.aliases),
                "category": seed.category,
            }
        )
    return rows


def related_to_param_rows(normalizer: SkillNormalizer) -> list[dict[str, Any]]:
    """Approved seed RELATED_TO edges only (no LLM-invented relationships)."""
    return [
        {
            "from_key": edge.from_key,
            "to_key": edge.to_key,
            "weight": float(edge.weight),
            "source": edge.source,
        }
        for edge in normalizer.approved_relationships()
    ]


async def project_seed_skills_and_related(
    session: _AsyncSession,
    *,
    seed_skills: Sequence[Mapping[str, Any]],
    related: Sequence[Mapping[str, Any]],
) -> None:
    """Idempotently MERGE seed Skill nodes and approved RELATED_TO edges.

    Safe when no Candidate exists: only Skill/RELATED_TO graph data is touched.
    """
    if seed_skills:
        result = await session.run(
            MERGE_SEED_SKILLS_CYPHER,
            {"seed_skills": list(seed_skills)},
        )
        await consume_result(result)
    if related:
        result = await session.run(
            MERGE_RELATED_TO_CYPHER,
            {"related": list(related)},
        )
        await consume_result(result)


def shared_seed_cypher_templates() -> Sequence[str]:
    """Fixed seed Skill / RELATED_TO templates for static review."""
    return (
        "MERGE (s:Skill {canonical_key: row.canonical_key})",
        "MERGE (a)-[r:RELATED_TO]->(b)",
    )


__all__ = [
    "AsyncGraphDriver",
    "MERGE_RELATED_TO_CYPHER",
    "MERGE_SEED_SKILLS_CYPHER",
    "NEO4J_REBUILD_INSTRUCTION",
    "NEO4J_SYNC_FAILED",
    "consume_result",
    "iso_utc",
    "project_seed_skills_and_related",
    "related_to_param_rows",
    "seed_skill_param_rows",
    "shared_seed_cypher_templates",
    "skill_ref_node_props",
]
