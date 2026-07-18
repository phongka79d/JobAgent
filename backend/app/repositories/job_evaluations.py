"""Flush-only persistence for validated ``job_evaluations`` rows.

Owns insert-with-unique-race reload, exact-context and latest-stale reads, and
derived none|current|stale lookup. Callers own the session and commit. No
provider, filesystem, Neo4j, or matching work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.job_evaluations import JobEvaluation
from app.schemas.job_evaluations import (
    JobEvaluationLookup,
    JobEvaluationRecord,
    match_result_to_json,
    record_from_row,
    validate_match_result_payload,
)
from app.schemas.matching import MatchResult
from app.services.evaluation_context import (
    EvaluationCurrentness,
    derive_evaluation_currentness,
)


class JobEvaluationRepositoryError(Exception):
    """Base error for job evaluation repository invariant violations."""


def _require_nonempty(name: str, value: object) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise JobEvaluationRepositoryError(f"{name} must be a non-empty string")
    return value


def _as_record(row: JobEvaluation) -> JobEvaluationRecord:
    return record_from_row(
        id=row.id,
        job_id=row.job_id,
        active_attachment_id=row.active_attachment_id,
        evaluation_context_hash=row.evaluation_context_hash,
        job_revision=row.job_revision,
        profile_revision=row.profile_revision,
        preferences_revision=row.preferences_revision,
        cv_source_hash=row.cv_source_hash,
        matching_contract_version=row.matching_contract_version,
        result_json=row.result_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_by_id(
    session: AsyncSession,
    evaluation_id: str,
) -> JobEvaluation | None:
    """Return the evaluation with primary key *evaluation_id*, or ``None``."""
    return await session.get(JobEvaluation, evaluation_id)


async def get_by_job_context(
    session: AsyncSession,
    *,
    job_id: str,
    evaluation_context_hash: str,
) -> JobEvaluation | None:
    """Return the unique row for ``(job_id, evaluation_context_hash)``."""
    job_id = _require_nonempty("job_id", job_id)
    evaluation_context_hash = _require_nonempty(
        "evaluation_context_hash", evaluation_context_hash
    )
    result = await session.execute(
        select(JobEvaluation).where(
            JobEvaluation.job_id == job_id,
            JobEvaluation.evaluation_context_hash == evaluation_context_hash,
        )
    )
    return result.scalar_one_or_none()


async def get_latest_for_job(
    session: AsyncSession,
    job_id: str,
) -> JobEvaluation | None:
    """Return the newest evaluation for *job_id*, or ``None`` when empty."""
    job_id = _require_nonempty("job_id", job_id)
    result = await session.execute(
        select(JobEvaluation)
        .where(JobEvaluation.job_id == job_id)
        .order_by(
            JobEvaluation.created_at.desc(),
            JobEvaluation.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def count_for_job(session: AsyncSession, job_id: str) -> int:
    """Return how many evaluation rows exist for *job_id*."""
    job_id = _require_nonempty("job_id", job_id)
    result = await session.execute(
        select(func.count())
        .select_from(JobEvaluation)
        .where(JobEvaluation.job_id == job_id)
    )
    return int(result.scalar_one())


async def lookup_for_job(
    session: AsyncSession,
    *,
    job_id: str,
    current_context_hash: str,
) -> JobEvaluationLookup:
    """Derive none|current|stale and the relevant row without rewriting history.

    ``current`` returns the exact-hash row. ``stale`` returns the latest stored
    row. ``none`` returns no evaluation.
    """
    job_id = _require_nonempty("job_id", job_id)
    current_context_hash = _require_nonempty(
        "current_context_hash", current_context_hash
    )
    exact = await get_by_job_context(
        session,
        job_id=job_id,
        evaluation_context_hash=current_context_hash,
    )
    latest = await get_latest_for_job(session, job_id)
    has_any = latest is not None
    has_exact = exact is not None
    state: EvaluationCurrentness = derive_evaluation_currentness(
        has_any_row=has_any,
        has_exact_context_hash=has_exact,
    )
    row: JobEvaluation | None
    if state == "current":
        row = exact
    elif state == "stale":
        row = latest
    else:
        row = None
    return JobEvaluationLookup(
        job_id=job_id,
        currentness=state,
        evaluation=_as_record(row) if row is not None else None,
    )


async def insert_evaluation(
    session: AsyncSession,
    *,
    job_id: str,
    active_attachment_id: str,
    evaluation_context_hash: str,
    job_revision: datetime,
    profile_revision: datetime,
    preferences_revision: datetime,
    cv_source_hash: str,
    matching_contract_version: str,
    result: MatchResult | dict[str, Any],
) -> tuple[JobEvaluation, bool]:
    """Insert one validated evaluation or reload a concurrent unique winner.

    Validates *result* as a compact ``MatchResult``. On unique-key race for
    ``(job_id, evaluation_context_hash)``, reloads the committed row and returns
    ``(row, False)``. Does not finalize the caller's unit of work.
    """
    job_id = _require_nonempty("job_id", job_id)
    active_attachment_id = _require_nonempty(
        "active_attachment_id", active_attachment_id
    )
    evaluation_context_hash = _require_nonempty(
        "evaluation_context_hash", evaluation_context_hash
    )
    cv_source_hash = _require_nonempty("cv_source_hash", cv_source_hash)
    matching_contract_version = _require_nonempty(
        "matching_contract_version", matching_contract_version
    )
    validated = validate_match_result_payload(result)
    if validated.job_id != job_id:
        raise JobEvaluationRepositoryError(
            "MatchResult.job_id must equal the evaluation job_id"
        )

    existing = await get_by_job_context(
        session,
        job_id=job_id,
        evaluation_context_hash=evaluation_context_hash,
    )
    if existing is not None:
        return existing, False

    now = utc_now()
    row = JobEvaluation(
        job_id=job_id,
        active_attachment_id=active_attachment_id,
        evaluation_context_hash=evaluation_context_hash,
        job_revision=job_revision,
        profile_revision=profile_revision,
        preferences_revision=preferences_revision,
        cv_source_hash=cv_source_hash,
        matching_contract_version=matching_contract_version,
        result_json=match_result_to_json(validated),
        created_at=now,
        updated_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row, True
    except IntegrityError:
        winner = await get_by_job_context(
            session,
            job_id=job_id,
            evaluation_context_hash=evaluation_context_hash,
        )
        if winner is None:
            raise JobEvaluationRepositoryError(
                "unique (job_id, evaluation_context_hash) conflict "
                "but row not found on re-select"
            ) from None
        return winner, False


__all__ = [
    "JobEvaluationRepositoryError",
    "count_for_job",
    "get_by_id",
    "get_by_job_context",
    "get_latest_for_job",
    "insert_evaluation",
    "lookup_for_job",
]
