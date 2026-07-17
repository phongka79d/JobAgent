"""Read-only SQLite snapshot and stored-embedding preflight for rebuild.

Owns the only approved graph-package SQLite reads: optional Candidate profile,
every processed ``full|partial`` Job with locked embedding validation, and
every retained approved CV document (plus legacy active metadata when no
document row exists). Never mutates SQLite, opens ShopAIKey, or issues Neo4j
statements.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachments import Attachment
from app.db.models.cv_documents import CVDocument
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.graph.rebuild_target import RebuildError
from app.repositories import profiles as profile_repo
from app.schemas.cv_document import CVDocument as CVDocumentModel
from app.schemas.cv_document import parse_cv_document
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


@dataclass(frozen=True, slots=True)
class ScorableJobFacts:
    """SQLite-authoritative facts required after vector retrieval."""

    job_id: str
    extraction: JobPostExtraction
    jd_quality: str
    source_url: str | None


@dataclass(frozen=True, slots=True)
class SourceRevision:
    """Read-only source revision for Candidate/Job parity checks."""

    id: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SourceRevisionSnapshot:
    """Active Candidate and complete scorable Job revision set from SQLite."""

    candidate: SourceRevision | None
    jobs: tuple[SourceRevision, ...]


@dataclass(frozen=True, slots=True)
class ApprovedCvRebuildRow:
    """One approved retained CV document ready for provider-free graph rebuild."""

    attachment_id: str
    document: CVDocumentModel
    original_name: str
    extraction_version: str
    source_hash: str
    source_updated_at: datetime
    is_active: bool


@dataclass(frozen=True, slots=True)
class LegacyActiveCvRow:
    """Active attachment without ``cv_documents`` (pre-Phase-9 / reprocess-required)."""

    attachment_id: str
    original_name: str
    source_updated_at: datetime


@dataclass(frozen=True, slots=True)
class ActiveCvConsistencyFacts:
    """SQLite facts used by observability active-CV staleness checks."""

    active_attachment_id: str | None
    source_hash: str | None
    document_updated_at: datetime | None
    has_document: bool


def _scorable_jobs_stmt() -> Any:
    return (
        select(JobPost)
        .where(JobPost.processing_status == JOB_PROCESSING_STATUS_PROCESSED)
        .where(JobPost.jd_quality.in_(tuple(_SCORABLE_QUALITIES)))
        .order_by(JobPost.created_at.asc(), JobPost.id.asc())
    )


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


async def load_source_revision_snapshot(
    session: AsyncSession,
) -> SourceRevisionSnapshot:
    """Read active Candidate and all scorable Job ID/revisions from SQLite."""
    profile_row = await profile_repo.get_active_profile(session)
    candidate = (
        SourceRevision(profile_row.id, profile_row.updated_at)
        if profile_row is not None
        else None
    )

    result = await session.execute(_scorable_jobs_stmt())
    jobs = tuple(
        SourceRevision(row.id, row.updated_at) for row in result.scalars().all()
    )
    return SourceRevisionSnapshot(candidate=candidate, jobs=jobs)


async def load_active_cv_consistency_facts(
    session: AsyncSession,
) -> ActiveCvConsistencyFacts:
    """Load active attachment ID and approved document hash/revision for staleness."""
    profile_row = await profile_repo.get_active_profile(session)
    if profile_row is None:
        return ActiveCvConsistencyFacts(
            active_attachment_id=None,
            source_hash=None,
            document_updated_at=None,
            has_document=False,
        )
    active_id = profile_row.active_attachment_id
    doc_row = await session.get(CVDocument, active_id)
    if doc_row is None:
        return ActiveCvConsistencyFacts(
            active_attachment_id=active_id,
            source_hash=None,
            document_updated_at=None,
            has_document=False,
        )
    return ActiveCvConsistencyFacts(
        active_attachment_id=active_id,
        source_hash=doc_row.source_hash,
        document_updated_at=doc_row.updated_at,
        has_document=True,
    )


async def load_approved_cv_rebuild_rows(
    session: AsyncSession,
    *,
    active_attachment_id: str | None,
) -> tuple[list[ApprovedCvRebuildRow], LegacyActiveCvRow | None]:
    """Load every approved CV document and optional legacy active metadata.

    Read-only. Invalid document_json fails the rebuild preflight before clear.
    """
    stmt = (
        select(CVDocument, Attachment)
        .join(Attachment, Attachment.id == CVDocument.attachment_id)
        .order_by(CVDocument.attachment_id.asc())
    )
    result = await session.execute(stmt)
    pairs = list(result.all())

    approved: list[ApprovedCvRebuildRow] = []
    seen_ids: set[str] = set()
    for doc_row, attachment in pairs:
        try:
            document = parse_cv_document(doc_row.document_json)
        except ValidationError as exc:
            raise RebuildError(
                f"CV {doc_row.attachment_id}: document_json failed validation; "
                "fix SQLite cv_documents before rebuild.",
                code="CV_INVALID",
            ) from exc
        attachment_id = str(doc_row.attachment_id)
        seen_ids.add(attachment_id)
        approved.append(
            ApprovedCvRebuildRow(
                attachment_id=attachment_id,
                document=document,
                original_name=attachment.original_name,
                extraction_version=doc_row.extraction_version,
                source_hash=doc_row.source_hash,
                source_updated_at=doc_row.updated_at,
                is_active=(
                    active_attachment_id is not None
                    and attachment_id == active_attachment_id
                ),
            )
        )

    legacy: LegacyActiveCvRow | None = None
    if (
        active_attachment_id is not None
        and active_attachment_id not in seen_ids
    ):
        attachment = await session.get(Attachment, active_attachment_id)
        if attachment is None:
            raise RebuildError(
                "Active attachment missing for legacy CV rebuild metadata.",
                code="CV_ACTIVE_MISSING",
            )
        legacy = LegacyActiveCvRow(
            attachment_id=active_attachment_id,
            original_name=attachment.original_name,
            source_updated_at=attachment.updated_at,
        )
    return approved, legacy


async def load_scorable_job_facts(
    session: AsyncSession,
    job_ids: Iterable[str],
) -> dict[str, ScorableJobFacts]:
    """Bulk-read current scorable Job facts by ID from SQLite."""
    requested = frozenset(job_ids)
    if not requested:
        return {}

    result = await session.execute(
        _scorable_jobs_stmt().where(JobPost.id.in_(tuple(requested)))
    )
    facts: dict[str, ScorableJobFacts] = {}
    for row in result.scalars().all():
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
        facts[row.id] = ScorableJobFacts(
            job_id=row.id,
            extraction=extraction,
            jd_quality=quality,
            source_url=row.source_url,
        )
    return facts


async def load_rebuild_inputs(
    session: AsyncSession,
    *,
    expected_model: str,
    expected_dimensions: int,
) -> tuple[
    CandidateProfile | None,
    Any | None,
    list[ScorableJobRow],
    list[ApprovedCvRebuildRow],
    LegacyActiveCvRow | None,
]:
    """Read Candidate, scorable Jobs, approved CVs; preflight embeddings.

    Read-only: no flush/commit of mutations. Preflight runs before any graph
    clear so mismatch never issues a destructive Cypher statement.
    """
    profile_row = await profile_repo.get_active_profile(session)
    profile: CandidateProfile | None = None
    profile_updated_at: Any | None = None
    active_attachment_id: str | None = None
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
        active_attachment_id = profile_row.active_attachment_id

    result = await session.execute(_scorable_jobs_stmt())
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

    approved_cvs, legacy_active = await load_approved_cv_rebuild_rows(
        session,
        active_attachment_id=active_attachment_id,
    )
    return profile, profile_updated_at, scorable, approved_cvs, legacy_active


__all__ = [
    "CONFIGURATION_RESTORATION_GUIDANCE",
    "ActiveCvConsistencyFacts",
    "ApprovedCvRebuildRow",
    "LegacyActiveCvRow",
    "ScorableJobFacts",
    "ScorableJobRow",
    "SourceRevision",
    "SourceRevisionSnapshot",
    "load_active_cv_consistency_facts",
    "load_approved_cv_rebuild_rows",
    "load_rebuild_inputs",
    "load_scorable_job_facts",
    "load_source_revision_snapshot",
    "validate_stored_embedding",
]
