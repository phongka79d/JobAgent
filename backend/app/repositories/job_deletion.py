"""Narrow SQLite Job deletion primitive (Plan 10 complete Job deletion).

Flush-only: deletes one ``job_posts`` row so ``job_evaluations`` cascade in the
same short transaction owned by the caller. No graph, HTTP, or orchestration.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job_evaluations import JobEvaluation
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import JobNotFoundError, JobRepositoryError


async def count_evaluations_for_job(
    session: AsyncSession,
    job_id: str,
) -> int:
    """Return the number of evaluation rows for *job_id*."""
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobRepositoryError("job_id must be a non-empty string")
    result = await session.execute(
        select(func.count())
        .select_from(JobEvaluation)
        .where(JobEvaluation.job_id == job_id.strip())
    )
    return int(result.scalar_one())


async def delete_job_row(session: AsyncSession, job_id: str) -> None:
    """Delete the SQLite Job row; evaluations CASCADE with the Job FK.

    Raises :class:`JobNotFoundError` when the Job is already absent. Graph
    absence must be confirmed by the coordinator before calling this primitive.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobRepositoryError("job_id must be a non-empty string")
    await jobs_repo.delete_by_id(session, job_id.strip())


__all__ = [
    "JobNotFoundError",
    "JobRepositoryError",
    "count_evaluations_for_job",
    "delete_job_row",
]
