"""Graph-first / SQLite-second complete Job deletion coordinator (Plan 10).

Owns ordering only:

1. Reject unknown SQLite Job IDs with ``JOB_NOT_FOUND`` (no mutation).
2. Idempotently delete exact ``(:Job {id: $job_id})`` in Neo4j and confirm
   absence (missing graph node is success).
3. On any graph failure, leave SQLite Job + evaluations untouched and return
   retry guidance.
4. After graph absence is confirmed, delete the SQLite Job so evaluations
   cascade in one short transaction.

Preserves Skills, seed ``RELATED_TO``, Candidate/CV branches, and unrelated
Jobs. Repeated complete deletion returns ``JOB_NOT_FOUND`` without graph work.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session_factory, session_scope
from app.graph.delete_job import (
    JobGraphDeleteError,
    delete_job_node,
    job_node_absent,
)
from app.graph.sync_shared import AsyncGraphDriver
from app.repositories import job_deletion as job_del_repo
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import JobNotFoundError

logger = logging.getLogger(__name__)

ERROR_JOB_NOT_FOUND: str = "JOB_NOT_FOUND"
ERROR_JOB_DELETE_GRAPH_FAILED: str = "JOB_DELETE_GRAPH_FAILED"

JOB_NOT_FOUND_MESSAGE: str = "The requested Job was not found."
JOB_DELETE_RETRY_SUMMARY: str = (
    "Exact Job graph deletion failed; SQLite Job and evaluations were "
    "preserved. Restore Neo4j connectivity and retry DELETE."
)

GraphDeleteFn = Callable[[AsyncGraphDriver, str], Awaitable[None]]
GraphAbsentFn = Callable[[AsyncGraphDriver, str], Awaitable[bool]]


class JobDeleteError(Exception):
    """Stable-coded Job deletion failure for HTTP mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class JobDeleteResult:
    """Successful complete deletion (SQLite Job + graph node absent)."""

    job_id: str


async def delete_job(
    job_id: str,
    *,
    driver: AsyncGraphDriver,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    graph_delete_fn: GraphDeleteFn | None = None,
    graph_absent_fn: GraphAbsentFn | None = None,
) -> JobDeleteResult:
    """Delete one Job completely: exact graph first, SQLite second.

    Raises :class:`JobDeleteError` with a stable code. Graph failures never
    remove SQLite state. Returns only after the Job row and exact graph node
    are both gone.
    """
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobDeleteError(
            ERROR_JOB_NOT_FOUND,
            JOB_NOT_FOUND_MESSAGE,
        )
    jid = job_id.strip()
    factory = session_factory or get_session_factory()
    graph_fn = graph_delete_fn or delete_job_node
    absent_fn = graph_absent_fn or job_node_absent

    # 1. SQLite existence gate — unknown ID never mutates graph or SQLite.
    async with session_scope(factory) as session:
        existing = await jobs_repo.get_by_id(session, jid)
        if existing is None:
            raise JobDeleteError(
                ERROR_JOB_NOT_FOUND,
                JOB_NOT_FOUND_MESSAGE,
            )

    # 2. Exact graph delete + absence confirmation (idempotent missing node).
    try:
        await graph_fn(driver, jid)
        still_present = not await absent_fn(driver, jid)
        if still_present:
            raise JobDeleteError(
                ERROR_JOB_DELETE_GRAPH_FAILED,
                JOB_DELETE_RETRY_SUMMARY,
            )
    except JobDeleteError:
        raise
    except JobGraphDeleteError as exc:
        logger.warning(
            "Job graph delete failed job_id=%s code=%s",
            jid,
            exc.code,
        )
        raise JobDeleteError(
            ERROR_JOB_DELETE_GRAPH_FAILED,
            JOB_DELETE_RETRY_SUMMARY,
        ) from exc
    except Exception as exc:
        logger.exception("Job graph delete unexpected failure job_id=%s", jid)
        raise JobDeleteError(
            ERROR_JOB_DELETE_GRAPH_FAILED,
            JOB_DELETE_RETRY_SUMMARY,
        ) from exc

    # 3. SQLite Job + evaluations cascade only after graph absence confirmed.
    try:
        async with session_scope(factory) as session:
            await job_del_repo.delete_job_row(session, jid)
            remaining = await job_del_repo.count_evaluations_for_job(session, jid)
            if remaining != 0:
                raise JobDeleteError(
                    ERROR_JOB_DELETE_GRAPH_FAILED,
                    JOB_DELETE_RETRY_SUMMARY,
                )
    except JobDeleteError:
        raise
    except JobNotFoundError as exc:
        # Concurrent removal still yields complete absence — treat as success.
        logger.info("Job already absent during SQLite finalize job_id=%s", jid)
        del exc
    except Exception as exc:
        logger.exception("Job SQLite finalize failed job_id=%s", jid)
        raise JobDeleteError(
            ERROR_JOB_DELETE_GRAPH_FAILED,
            JOB_DELETE_RETRY_SUMMARY,
        ) from exc

    # Confirm SQLite absence before success.
    async with session_scope(factory) as session:
        gone = await jobs_repo.get_by_id(session, jid)
        if gone is not None:
            raise JobDeleteError(
                ERROR_JOB_DELETE_GRAPH_FAILED,
                JOB_DELETE_RETRY_SUMMARY,
            )

    return JobDeleteResult(job_id=jid)


__all__ = [
    "ERROR_JOB_DELETE_GRAPH_FAILED",
    "ERROR_JOB_NOT_FOUND",
    "JOB_DELETE_RETRY_SUMMARY",
    "JOB_NOT_FOUND_MESSAGE",
    "JobDeleteError",
    "JobDeleteResult",
    "delete_job",
]
