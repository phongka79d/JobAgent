"""Focused saved-Job list paging primitives (Plan 10 public API reads).

Owns newest-first ``(created_at, id)`` cursor pages over ``job_posts``. Callers
own the session and commit. No evaluation assembly, HTTP, providers, graph,
or presentation logic. Compact tool lists remain on ``repositories.jobs``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.jobs import (
    JOB_COMPACT_QUERY_LIMIT_MAX,
    JOB_COMPACT_QUERY_LIMIT_MIN,
    JobPost,
)
from app.repositories import jobs as jobs_repo


class SavedJobsRepositoryError(Exception):
    """Base error for saved-Job repository invariant violations."""


async def get_by_id(session: AsyncSession, job_id: str) -> JobPost | None:
    """Return the Job row by primary key, or ``None`` if missing.

    Delegates to the Job repository owner so ID lookup stays single-sourced.
    """
    return await jobs_repo.get_by_id(session, job_id)


async def list_jobs_before(
    session: AsyncSession,
    *,
    limit: int,
    before: tuple[datetime, str] | None = None,
) -> list[JobPost]:
    """Return up to *limit* jobs newest-first for saved-JD pagination.

    When *before* is ``(created_at, id)``, only rows lexicographically earlier
    than that pair are included. Ordering is ``created_at DESC, id DESC``.
    Callers request ``limit + 1`` to detect a next page. Does not finalize the
    caller's unit of work.
    """
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise SavedJobsRepositoryError("limit must be an int in 1..50")
    if limit < JOB_COMPACT_QUERY_LIMIT_MIN or limit > (
        JOB_COMPACT_QUERY_LIMIT_MAX + 1
    ):
        # Allow limit+1 from the service (51) for has_older detection only.
        if limit != JOB_COMPACT_QUERY_LIMIT_MAX + 1:
            raise SavedJobsRepositoryError(
                f"limit must be in {JOB_COMPACT_QUERY_LIMIT_MIN}.."
                f"{JOB_COMPACT_QUERY_LIMIT_MAX + 1}, got {limit!r}"
            )

    stmt = select(JobPost)
    if before is not None:
        before_created_at, before_id = before
        stmt = stmt.where(
            or_(
                JobPost.created_at < before_created_at,
                and_(
                    JobPost.created_at == before_created_at,
                    JobPost.id < before_id,
                ),
            )
        )
    stmt = stmt.order_by(JobPost.created_at.desc(), JobPost.id.desc()).limit(
        limit
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


__all__ = [
    "SavedJobsRepositoryError",
    "get_by_id",
    "list_jobs_before",
]
