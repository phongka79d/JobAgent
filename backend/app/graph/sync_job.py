"""Idempotent Job/Skill graph synchronization (Plan 5 §7.7, Master §8/§21).

After a processed scorable (``full|partial``) SQLite Job commit, projects one
Job identity into Neo4j:

* ``MERGE`` ``Job{id=<SQLite UUID>}`` with approved properties and the exact
  finite embedding
* Set ``source_updated_at`` from ``job_posts.updated_at``
* Replace only this Job's ``REQUIRES`` / ``PREFERS`` edges
* ``MERGE`` canonical Skill nodes with confidence/evidence
* Reuse shared seed Skill / ``RELATED_TO`` projection (no LLM-invented edges)

Unscorable/failed Jobs are never synced by callers. Exact duplicate return must
not call this function. Shared driver protocol, failure codes, timestamps,
result drain, and seed projection live in :mod:`app.graph.sync_shared`.

No SQLite sessions, provider/embedding calls, or raw JD text enter this module.
Callers inject an async Neo4j driver (real or fake). Failures raise
:class:`JobSyncError` with stable code ``NEO4J_SYNC_FAILED``; they must not
roll back or downgrade committed SQLite state.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.db.models.jobs import JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL
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
from app.schemas.embeddings import EmbeddingVectorError, validate_finite_vector
from app.schemas.jobs import JobPostExtraction, JobSkill
from app.services.skill_normalization import SkillNormalizer

# Scorable qualities eligible for Job graph projection (Master §8 / Plan 5 §7.7).
_SCORABLE_SYNC_QUALITIES: frozenset[str] = frozenset(
    {JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL}
)


class JobSyncError(Exception):
    """Raised when Job graph synchronization fails.

    Carries stable ``code`` (always :data:`NEO4J_SYNC_FAILED` for this owner)
    and developer rebuild guidance. Never embeds secrets or raw JD text.
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


def job_skill_param_row(skill: JobSkill) -> dict[str, Any]:
    """Parameter map for one Job skill edge (Skill node + rel props)."""
    return {
        "skill": skill_ref_node_props(skill.skill),
        "rel": {
            "confidence": float(skill.confidence),
            "evidence": list(skill.evidence),
        },
    }


def _locked_embedding_for_graph(embedding: Sequence[float]) -> list[float]:
    """Validate via the sole production embedding owner; sanitize failures."""
    # Shared owner requires a list; coerce plain sequences without logging values.
    if isinstance(embedding, list):
        candidate: Any = embedding
    elif isinstance(embedding, Sequence) and not isinstance(embedding, (str, bytes)):
        candidate = list(embedding)
    else:
        raise JobSyncError("Job embedding failed locked-vector validation")
    try:
        return validate_finite_vector(candidate)
    except EmbeddingVectorError as exc:
        # Map to graph failure contract; never surface vector/provider detail.
        raise JobSyncError("Job embedding failed locked-vector validation") from exc


async def sync_job(
    driver: AsyncGraphDriver,
    *,
    job_id: str,
    extraction: JobPostExtraction,
    jd_quality: str,
    embedding: Sequence[float],
    source_updated_at: datetime,
    normalizer: SkillNormalizer,
) -> None:
    """Project one scorable Job onto Neo4j using parameterized idempotent Cypher.

    Raises :class:`JobSyncError` on validation or driver failure without
    mutating SQLite. Non-scorable qualities never open a graph session.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobSyncError("job_id must be the non-empty SQLite Job UUID")
    if not isinstance(source_updated_at, datetime):
        raise JobSyncError(
            "source_updated_at must be a datetime from job_posts.updated_at"
        )
    if not isinstance(extraction, JobPostExtraction):
        raise JobSyncError("extraction must be a validated JobPostExtraction")
    if not isinstance(jd_quality, str) or jd_quality.strip() == "":
        raise JobSyncError("jd_quality must be the authoritative quality string")
    # Gate before any driver session or Cypher: only full|partial are scorable.
    if jd_quality not in _SCORABLE_SYNC_QUALITIES:
        raise JobSyncError(
            "Only processed full|partial Jobs may be synchronized to Neo4j"
        )

    vector = _locked_embedding_for_graph(embedding)
    requires = [job_skill_param_row(skill) for skill in extraction.required_skills]
    prefers = [job_skill_param_row(skill) for skill in extraction.preferred_skills]
    seed_skills = seed_skill_param_rows(normalizer)
    related = related_to_param_rows(normalizer)

    params: dict[str, Any] = {
        "job_id": job_id,
        "title": extraction.title,
        "company": extraction.company,
        "location": extraction.location,
        "work_mode": extraction.work_mode,
        "seniority": extraction.seniority,
        "quality": jd_quality,
        "embedding": vector,
        "source_updated_at": iso_utc(source_updated_at),
        "requires": requires,
        "prefers": prefers,
    }

    merge_job = (
        "MERGE (j:Job {id: $job_id}) "
        "SET j.title = $title, "
        "    j.company = $company, "
        "    j.location = $location, "
        "    j.work_mode = $work_mode, "
        "    j.seniority = $seniority, "
        "    j.quality = $quality, "
        "    j.embedding = $embedding, "
        "    j.source_updated_at = $source_updated_at "
        "RETURN j.id AS id"
    )
    # Clear only this Job's skill edges (not other Jobs).
    clear_job_skill_rels = (
        "MATCH (j:Job {id: $job_id})-[r:REQUIRES|PREFERS]->() "
        "DELETE r"
    )
    merge_requires = (
        "UNWIND $requires AS row "
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key}) "
        "SET s.display_name = row.skill.display_name, "
        "    s.aliases = row.skill.aliases, "
        "    s.category = row.skill.category "
        "WITH s, row "
        "MATCH (j:Job {id: $job_id}) "
        "MERGE (j)-[r:REQUIRES]->(s) "
        "SET r.confidence = row.rel.confidence, "
        "    r.evidence = row.rel.evidence"
    )
    merge_prefers = (
        "UNWIND $prefers AS row "
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key}) "
        "SET s.display_name = row.skill.display_name, "
        "    s.aliases = row.skill.aliases, "
        "    s.category = row.skill.category "
        "WITH s, row "
        "MATCH (j:Job {id: $job_id}) "
        "MERGE (j)-[r:PREFERS]->(s) "
        "SET r.confidence = row.rel.confidence, "
        "    r.evidence = row.rel.evidence"
    )

    try:
        async with driver.session() as session:
            result = await session.run(merge_job, params)
            await consume_result(result)
            result = await session.run(clear_job_skill_rels, params)
            await consume_result(result)
            if requires:
                result = await session.run(merge_requires, params)
                await consume_result(result)
            if prefers:
                result = await session.run(merge_prefers, params)
                await consume_result(result)
            await project_seed_skills_and_related(
                session,
                seed_skills=seed_skills,
                related=related,
            )
    except JobSyncError:
        raise
    except Exception as exc:
        raise JobSyncError("Job/Skill Neo4j synchronization failed") from exc


def cypher_statement_templates() -> Sequence[str]:
    """Return fixed Cypher templates for static review (no runtime values)."""
    return (
        "MERGE (j:Job {id: $job_id})",
        "MATCH (j:Job {id: $job_id})-[r:REQUIRES|PREFERS]->()",
        "MERGE (s:Skill {canonical_key: row.skill.canonical_key})",
        "MERGE (j)-[r:REQUIRES]->(s)",
        "MERGE (j)-[r:PREFERS]->(s)",
        *shared_seed_cypher_templates(),
    )


__all__ = [
    "AsyncGraphDriver",
    "JobSyncError",
    "NEO4J_REBUILD_INSTRUCTION",
    "NEO4J_SYNC_FAILED",
    "cypher_statement_templates",
    "sync_job",
]
