"""Shared low-level Job embedding and post-commit projection mechanics."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.db.models.jobs import JOB_PROCESSING_STATUS_PROCESSED, JobPost
from app.graph.sync_job import (
    NEO4J_REBUILD_INSTRUCTION,
    NEO4J_SYNC_FAILED,
    AsyncGraphDriver,
    JobSyncError,
    sync_job,
)
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    validate_finite_vector,
)
from app.schemas.jobs import JobPostExtraction
from app.services.embedding_text import build_job_embedding_text_v1
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)
JobSyncFn = Callable[[], Awaitable[None]]


class EmbeddingClient(Protocol):
    """Minimal fake-testable embedding surface."""

    def embed_text(self, text: str) -> list[float]:
        """Return one locked finite embedding vector."""
        ...


def embed_job_extraction(
    extraction: JobPostExtraction,
    embedding_client: EmbeddingClient,
) -> tuple[list[float], str, int]:
    """Build and validate the locked Job embedding contract."""
    text = build_job_embedding_text_v1(extraction)
    vector = embedding_client.embed_text(text)
    validated = validate_finite_vector(vector)
    return validated, LOCKED_EMBEDDING_MODEL, LOCKED_EMBEDDING_DIMENSIONS


@dataclass(frozen=True, slots=True)
class JobSyncResult:
    attempted: bool
    ok: bool
    code: str | None
    rebuild_instruction: str | None


async def sync_persisted_job(
    row: JobPost,
    *,
    normalizer: SkillNormalizer,
    graph_driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
    log_context: str,
) -> JobSyncResult:
    """Sync one committed scorable Job row without opening a DB transaction."""
    if (
        row.processing_status != JOB_PROCESSING_STATUS_PROCESSED
        or row.jd_quality not in {"full", "partial"}
    ):
        return JobSyncResult(False, True, None, None)
    if graph_driver is None and job_sync_fn is None:
        return JobSyncResult(False, True, None, None)
    if row.extraction_json is None or row.embedding_json is None:
        return JobSyncResult(
            True,
            False,
            NEO4J_SYNC_FAILED,
            NEO4J_REBUILD_INSTRUCTION,
        )

    extraction = JobPostExtraction.model_validate(row.extraction_json)

    async def default_sync() -> None:
        if graph_driver is None:
            raise JobSyncError("Neo4j driver not configured for Job sync")
        await sync_job(
            graph_driver,
            job_id=row.id,
            extraction=extraction,
            jd_quality=str(row.jd_quality),
            embedding=list(row.embedding_json or []),
            source_updated_at=row.updated_at,
            normalizer=normalizer,
        )

    try:
        await (job_sync_fn or default_sync)()
    except JobSyncError as exc:
        logger.info(
            "%s neo4j sync failed job_id=%s code=%s",
            log_context,
            row.id,
            exc.code,
        )
        return JobSyncResult(True, False, exc.code, exc.rebuild_instruction)
    except Exception:
        logger.info("%s neo4j sync failed job_id=%s", log_context, row.id)
        return JobSyncResult(True, False, NEO4J_SYNC_FAILED, NEO4J_REBUILD_INSTRUCTION)
    return JobSyncResult(True, True, None, None)


__all__ = [
    "EmbeddingClient",
    "JobSyncFn",
    "JobSyncResult",
    "embed_job_extraction",
    "sync_persisted_job",
]
