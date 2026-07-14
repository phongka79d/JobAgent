"""Read-only SQLite snapshot and stored-embedding preflight for rebuild.

Owns the only approved graph-package SQLite reads: optional Candidate profile
and every processed ``full|partial`` Job with locked embedding validation.
Never mutates SQLite, opens ShopAIKey, or issues Neo4j statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.graph.rebuild_target import RebuildError
from app.repositories import profiles as profile_repo
from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    EmbeddingVectorError,
    require_locked_embedding_contract,
    validate_finite_vector,
)
from app.schemas.jobs import JobPostExtraction, parse_job_post_extraction
from app.schemas.profile import CandidateProfile, parse_candidate_profile

CONFIGURATION_RESTORATION_GUIDANCE: str = (
    "Stored embedding model, dimensions, or vector length does not match the "
    f"locked contract ({LOCKED_EMBEDDING_MODEL}, "
    f"{LOCKED_EMBEDDING_DIMENSIONS} finite floats). Restore the original "
    "EMBEDDING_MODEL and EMBEDDING_DIMENSIONS configuration and re-run rebuild. "
    "Rebuild does not call the embedding provider or re-embed Jobs."
)

_SCORABLE_QUALITIES: frozenset[str] = frozenset(
    {JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL}
)


@dataclass(frozen=True, slots=True)
class ScorableJobRow:
    """In-memory scorable Job projection (detached from SQLite session)."""

    job_id: str
    extraction: JobPostExtraction
    jd_quality: str
    embedding: list[float]
    source_updated_at: Any


def validate_stored_embedding(
    *,
    job_id: str,
    embedding_model: str | None,
    embedding_dimensions: int | None,
    embedding_json: Any,
    expected_model: str,
    expected_dimensions: int,
) -> list[float]:
    """Validate one stored embedding; raise RebuildError with restore guidance."""
    if embedding_model != expected_model:
        raise RebuildError(
            f"Job {job_id}: embedding_model mismatch. "
            f"{CONFIGURATION_RESTORATION_GUIDANCE}",
            code="EMBEDDING_CONFIG_MISMATCH",
        )
    if embedding_dimensions != expected_dimensions:
        raise RebuildError(
            f"Job {job_id}: embedding_dimensions mismatch. "
            f"{CONFIGURATION_RESTORATION_GUIDANCE}",
            code="EMBEDDING_CONFIG_MISMATCH",
        )
    try:
        require_locked_embedding_contract(
            model=expected_model,
            dimensions=expected_dimensions,
        )
        return validate_finite_vector(embedding_json)
    except EmbeddingVectorError as exc:
        raise RebuildError(
            f"Job {job_id}: stored embedding failed locked-vector validation. "
            f"{CONFIGURATION_RESTORATION_GUIDANCE}",
            code="EMBEDDING_CONFIG_MISMATCH",
        ) from exc


async def load_rebuild_inputs(
    session: AsyncSession,
    *,
    expected_model: str,
    expected_dimensions: int,
) -> tuple[CandidateProfile | None, Any | None, list[ScorableJobRow]]:
    """Read Candidate (optional) and all scorable Jobs; preflight embeddings.

    Read-only: no flush/commit of mutations. Preflight runs before any graph
    clear so mismatch never issues a destructive Cypher statement.
    """
    profile_row = await profile_repo.get_active_profile(session)
    profile: CandidateProfile | None = None
    profile_updated_at: Any | None = None
    if profile_row is not None:
        try:
            profile = parse_candidate_profile(profile_row.profile_json)
        except Exception as exc:
            raise RebuildError(
                "Active Candidate profile_json failed validation; fix SQLite "
                "profile data before rebuild.",
                code="CANDIDATE_INVALID",
            ) from exc
        profile_updated_at = profile_row.updated_at

    stmt = (
        select(JobPost)
        .where(JobPost.processing_status == JOB_PROCESSING_STATUS_PROCESSED)
        .where(JobPost.jd_quality.in_(tuple(_SCORABLE_QUALITIES)))
        .order_by(JobPost.created_at.asc(), JobPost.id.asc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    scorable: list[ScorableJobRow] = []
    for row in rows:
        vector = validate_stored_embedding(
            job_id=row.id,
            embedding_model=row.embedding_model,
            embedding_dimensions=row.embedding_dimensions,
            embedding_json=row.embedding_json,
            expected_model=expected_model,
            expected_dimensions=expected_dimensions,
        )
        try:
            extraction = parse_job_post_extraction(row.extraction_json)
        except Exception as exc:
            raise RebuildError(
                f"Job {row.id}: extraction_json failed validation; fix SQLite "
                "Job data before rebuild.",
                code="JOB_INVALID",
            ) from exc
        quality = row.jd_quality
        if quality is None or quality not in _SCORABLE_QUALITIES:
            continue
        scorable.append(
            ScorableJobRow(
                job_id=row.id,
                extraction=extraction,
                jd_quality=quality,
                embedding=vector,
                source_updated_at=row.updated_at,
            )
        )
    return profile, profile_updated_at, scorable


__all__ = [
    "CONFIGURATION_RESTORATION_GUIDANCE",
    "ScorableJobRow",
    "load_rebuild_inputs",
    "validate_stored_embedding",
]
