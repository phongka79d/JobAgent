"""Replay-safe projection of active scorable Jobs into Neo4j.

Outbox payloads remain identifier-only (``job_id``). Processing reloads the
current validated SQLite Job, embeds only active ``full|partial`` rows, and
``MERGE``s Job/Skill/JobFamily with owned ``REQUIRES``/``PREFERS``/``IN_FAMILY``
edges. Ignored/unscorable Jobs never enter Neo4j. Graph/embedding failure
preserves canonical Job state and leaves retryable outbox/sync failure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol
from uuid import UUID

from app.db.enums import GraphSyncStatus, JdQuality, ProcessingStatus, RecordStatus
from app.db.session import DatabaseSessionManager
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.job_posts import JobPostRecord, JobPostRepository
from app.schemas.job_post import JobPostExtraction, JobSkill
from app.services.embeddings import (
    JobEmbeddingError,
    JobEmbeddingErrorCode,
    JobEmbeddingResult,
)
from app.services.skill_normalization import provisional_canonical_key

# Matches ``JDIngestionService`` enqueue identity (Plan 5 §7.6 / Master §21).
JOB_UPSERT_OPERATION: Final[str] = "upsert_job"
DEFAULT_JOB_SYNC_BATCH_SIZE: Final[int] = 20

_SCORABLE_QUALITIES: Final[frozenset[str]] = frozenset(
    {
        JdQuality.FULL.value,
        JdQuality.PARTIAL.value,
    }
)

_PROJECT_JOB_CYPHER: Final[str] = """
MERGE (j:Job {id: $job_id})
SET j.title = $title,
    j.company = $company,
    j.location = $location,
    j.work_mode = $work_mode,
    j.seniority = $seniority,
    j.quality = $quality,
    j.embedding = $embedding
WITH j
OPTIONAL MATCH (j)-[old_req:REQUIRES]->(:Skill)
DELETE old_req
WITH j
OPTIONAL MATCH (j)-[old_pref:PREFERS]->(:Skill)
DELETE old_pref
WITH j
OPTIONAL MATCH (j)-[old_fam:IN_FAMILY]->(:JobFamily)
DELETE old_fam
WITH j
FOREACH (skill_data IN $required_skills |
  MERGE (skill:Skill {canonical_key: skill_data.canonical_key})
  SET skill.display_name = skill_data.display_name,
      skill.category = skill_data.category,
      skill.status = skill_data.status,
      skill.aliases = coalesce(skill.aliases, []) +
        [a IN skill_data.aliases WHERE NOT a IN coalesce(skill.aliases, [])]
  MERGE (j)-[rel:REQUIRES]->(skill)
  SET rel.confidence = skill_data.confidence,
      rel.evidence = skill_data.evidence
)
FOREACH (skill_data IN $preferred_skills |
  MERGE (skill:Skill {canonical_key: skill_data.canonical_key})
  SET skill.display_name = skill_data.display_name,
      skill.category = skill_data.category,
      skill.status = skill_data.status,
      skill.aliases = coalesce(skill.aliases, []) +
        [a IN skill_data.aliases WHERE NOT a IN coalesce(skill.aliases, [])]
  MERGE (j)-[rel:PREFERS]->(skill)
  SET rel.confidence = skill_data.confidence,
      rel.evidence = skill_data.evidence
)
FOREACH (family_data IN $job_families |
  MERGE (f:JobFamily {canonical_key: family_data.canonical_key})
  SET f.display_name = family_data.display_name
  MERGE (j)-[:IN_FAMILY]->(f)
)
""".strip()


class JobGraphClient(Protocol):
    """Parameter-bound graph operation required by this projector."""

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None: ...


class JobEmbeddingPort(Protocol):
    """Minimal embedding surface used at Job sync time."""

    def embed_job(self, job: JobPostExtraction) -> JobEmbeddingResult: ...


def _skill_parameters(skills: Sequence[JobSkill]) -> list[dict[str, object]]:
    return [
        {
            "canonical_key": item.skill.canonical_key,
            "display_name": item.skill.display_name,
            "aliases": list(item.skill.aliases),
            "category": item.skill.category,
            "status": item.skill.status.value
            if hasattr(item.skill.status, "value")
            else str(item.skill.status),
            "confidence": item.confidence,
            "evidence": list(item.evidence),
        }
        for item in skills
    ]


def _job_family_parameters(
    extraction: JobPostExtraction,
) -> list[dict[str, object]]:
    raw = extraction.job_family
    if raw is None:
        return []
    display = raw.strip()
    if not display:
        return []
    try:
        key = provisional_canonical_key(display)
    except ValueError:
        return []
    return [{"canonical_key": key, "display_name": display}]


def is_graph_eligible(record: JobPostRecord) -> bool:
    """True when a Job may enter Neo4j (active processed full|partial)."""
    return (
        record.processing_status == ProcessingStatus.PROCESSED.value
        and record.record_status == RecordStatus.ACTIVE.value
        and record.jd_quality in _SCORABLE_QUALITIES
        and record.extraction is not None
    )


def _parse_job_id(entity_id: str, payload: Mapping[str, Any]) -> UUID:
    if payload != {"job_id": entity_id}:
        raise ValueError("invalid job sync payload")
    return UUID(entity_id)


def _sanitize_failure_code(exc: BaseException) -> str:
    if isinstance(exc, JobEmbeddingError):
        return exc.code.value
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code and len(code) <= 64:
        cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in code)
        if cleaned:
            return cleaned[:64]
    return "job_projection_failed"


def _embedding_vector(result: JobEmbeddingResult) -> list[float]:
    if len(result.vectors) != 1:
        raise JobEmbeddingError(JobEmbeddingErrorCode.VECTOR_COUNT_MISMATCH)
    values = result.vectors[0].values
    if len(values) != 1536:
        raise JobEmbeddingError(JobEmbeddingErrorCode.DIMENSION_MISMATCH)
    return [float(v) for v in values]


def build_job_projection_parameters(
    *,
    job_id: UUID,
    extraction: JobPostExtraction,
    embedding: Sequence[float],
) -> dict[str, Any]:
    """Build parameter-bound Cypher inputs for one Job projection."""
    if len(embedding) != 1536:
        raise JobEmbeddingError(JobEmbeddingErrorCode.DIMENSION_MISMATCH)
    return {
        "job_id": str(job_id),
        "title": extraction.title,
        "company": extraction.company,
        "location": extraction.location,
        "work_mode": extraction.work_mode.value
        if hasattr(extraction.work_mode, "value")
        else str(extraction.work_mode),
        "seniority": extraction.seniority.value
        if hasattr(extraction.seniority, "value")
        else str(extraction.seniority),
        "quality": extraction.jd_quality.value
        if hasattr(extraction.jd_quality, "value")
        else str(extraction.jd_quality),
        "embedding": list(embedding),
        "required_skills": _skill_parameters(extraction.required_skills),
        "preferred_skills": _skill_parameters(extraction.preferred_skills),
        "job_families": _job_family_parameters(extraction),
    }


async def project_eligible_job(
    record: JobPostRecord,
    client: JobGraphClient,
    embedding_service: JobEmbeddingPort,
) -> dict[str, Any]:
    """Embed and MERGE one eligible Job. Does not mutate SQLite/outbox state.

    Used by online outbox processing and full rebuild so Cypher/parameter
    construction is not duplicated. Caller must pre-check eligibility.
    """
    if not is_graph_eligible(record):
        raise ValueError("job not graph eligible")
    extraction = record.extraction
    assert extraction is not None  # guarded by eligibility
    embed_result = embedding_service.embed_job(extraction)
    vector = _embedding_vector(embed_result)
    parameters = build_job_projection_parameters(
        job_id=record.id,
        extraction=extraction,
        embedding=vector,
    )
    if "RELATED_TO" in _PROJECT_JOB_CYPHER:
        raise RuntimeError("RELATED_TO forbidden")  # pragma: no cover
    await client.run_query(_PROJECT_JOB_CYPHER, parameters)
    return parameters


async def process_job_sync_outbox(
    database: DatabaseSessionManager,
    client: JobGraphClient,
    embedding_service: JobEmbeddingPort,
    *,
    limit: int = DEFAULT_JOB_SYNC_BATCH_SIZE,
) -> int:
    """Project one bounded Job outbox slice; never mutates canonical Job content.

    Reloads each Job by SQLite ID from an identifier-only payload, embeds only
    eligible active full/partial rows, and maps outbox success/failure to
    ``graph_sync_status`` in the same transaction as the outbox transition.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        limit = DEFAULT_JOB_SYNC_BATCH_SIZE

    processed = 0
    async with database.session_scope() as session:
        outbox = GraphOutboxRepository(session)
        jobs = JobPostRepository(session)
        await outbox.requeue_failed_by_operation(
            operation=JOB_UPSERT_OPERATION,
            limit=limit,
        )
        rows = await outbox.claim_pending(
            limit=limit,
            operation=JOB_UPSERT_OPERATION,
        )
        for row in rows:
            try:
                job_id = _parse_job_id(row.entity_id, row.payload)
                record = await jobs.get_by_id(job_id)
                if record is None:
                    raise ValueError("job missing")
                if not is_graph_eligible(record):
                    # Ineligible: never project; clear retryable pending work.
                    await jobs.set_graph_sync_status(
                        job_id,
                        status=GraphSyncStatus.NOT_REQUIRED,
                    )
                    await outbox.mark_synced(row.id)
                    processed += 1
                    continue

                await project_eligible_job(record, client, embedding_service)
            except Exception as exc:
                error_code = _sanitize_failure_code(exc)
                await outbox.mark_failed(row.id, error=error_code)
                # Best-effort Job sync status; missing/invalid job stays failed outbox.
                try:
                    job_id_for_status = UUID(row.entity_id)
                    current = await jobs.get_by_id(job_id_for_status)
                    if (
                        current is not None
                        and current.record_status == RecordStatus.ACTIVE.value
                        and current.processing_status
                        == ProcessingStatus.PROCESSED.value
                    ):
                        await jobs.set_graph_sync_status(
                            job_id_for_status,
                            status=GraphSyncStatus.FAILED,
                        )
                except Exception:
                    pass
            else:
                await outbox.mark_synced(row.id)
                await jobs.set_graph_sync_status(
                    job_id,
                    status=GraphSyncStatus.SYNCED,
                )
                processed += 1
    return processed


__all__ = [
    "DEFAULT_JOB_SYNC_BATCH_SIZE",
    "JOB_UPSERT_OPERATION",
    "JobEmbeddingPort",
    "JobGraphClient",
    "build_job_projection_parameters",
    "is_graph_eligible",
    "process_job_sync_outbox",
    "project_eligible_job",
]
