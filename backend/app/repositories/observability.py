"""Cross-table read projections for observability APIs (Plan 8).

Owns attachment, chunk, and agent-run list queries with ``limit + 1``
newest-first (or ascending-ordinal for chunks) pagination primitives.
Callers own the async session and commit. Never mutates rows, opens a
session, touches the filesystem, or calls providers/Neo4j.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachment_text_chunks import AttachmentTextChunk
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentRun, ToolExecution


class ObservabilityRepositoryError(Exception):
    """Base error for observability repository invariant violations."""


async def list_attachments_before(
    session: AsyncSession,
    *,
    limit: int,
    before: tuple[datetime, str] | None = None,
) -> list[Attachment]:
    """Return up to *limit* attachments newest-first for history pagination.

    When *before* is ``(created_at, id)``, only rows lexicographically earlier
    than that pair are included. Ordering is ``created_at DESC, id DESC``.
    Does not finalize the caller's unit of work.
    """
    if limit < 1:
        raise ObservabilityRepositoryError("limit must be >= 1")

    stmt = select(Attachment)
    if before is not None:
        before_created_at, before_id = before
        stmt = stmt.where(
            or_(
                Attachment.created_at < before_created_at,
                and_(
                    Attachment.created_at == before_created_at,
                    Attachment.id < before_id,
                ),
            )
        )
    stmt = stmt.order_by(
        Attachment.created_at.desc(), Attachment.id.desc()
    ).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> Attachment | None:
    """Return the attachment by primary key, or ``None`` if missing."""
    return await session.get(Attachment, attachment_id)


async def list_chunks_after(
    session: AsyncSession,
    attachment_id: str,
    *,
    limit: int,
    after: tuple[datetime, int] | None = None,
) -> list[AttachmentTextChunk]:
    """Return up to *limit* chunks in ascending ordinal (source) order.

    When *after* is ``(created_at, ordinal)``, only rows lexicographically
    greater than that pair are included. Callers request ``limit + 1`` to
    detect a next page. Does not finalize the caller's unit of work.
    """
    if limit < 1:
        raise ObservabilityRepositoryError("limit must be >= 1")
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise ObservabilityRepositoryError(
            "attachment_id must be a non-empty string"
        )

    conditions = [AttachmentTextChunk.attachment_id == attachment_id]
    if after is not None:
        after_created_at, after_ordinal = after
        conditions.append(
            or_(
                AttachmentTextChunk.created_at > after_created_at,
                and_(
                    AttachmentTextChunk.created_at == after_created_at,
                    AttachmentTextChunk.ordinal > after_ordinal,
                ),
            )
        )

    stmt = (
        select(AttachmentTextChunk)
        .where(*conditions)
        .order_by(
            AttachmentTextChunk.ordinal.asc(),
            AttachmentTextChunk.created_at.asc(),
            AttachmentTextChunk.id.asc(),
        )
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_chunks_for_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> int:
    """Return the number of chunk rows for *attachment_id*."""
    stmt = select(AttachmentTextChunk.id).where(
        AttachmentTextChunk.attachment_id == attachment_id
    )
    result = await session.execute(stmt)
    return len(list(result.scalars().all()))


async def get_chunk_by_ordinal(
    session: AsyncSession,
    attachment_id: str,
    ordinal: int,
) -> AttachmentTextChunk | None:
    """Return one chunk by attachment + ordinal, or ``None``."""
    stmt = select(AttachmentTextChunk).where(
        AttachmentTextChunk.attachment_id == attachment_id,
        AttachmentTextChunk.ordinal == ordinal,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_runs_before(
    session: AsyncSession,
    *,
    limit: int,
    before: tuple[datetime, str] | None = None,
) -> list[AgentRun]:
    """Return up to *limit* agent runs newest-first for history pagination.

    When *before* is ``(created_at, id)``, only rows lexicographically earlier
    than that pair are included. Ordering is ``created_at DESC, id DESC``.
    Does not finalize the caller's unit of work.
    """
    if limit < 1:
        raise ObservabilityRepositoryError("limit must be >= 1")

    stmt = select(AgentRun)
    if before is not None:
        before_created_at, before_id = before
        stmt = stmt.where(
            or_(
                AgentRun.created_at < before_created_at,
                and_(
                    AgentRun.created_at == before_created_at,
                    AgentRun.id < before_id,
                ),
            )
        )
    stmt = stmt.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(
        limit
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_tool_executions_for_run_ids(
    session: AsyncSession,
    run_ids: list[str],
) -> list[ToolExecution]:
    """Return tool executions for *run_ids*, ordered by ``(created_at, id)``."""
    if not run_ids:
        return []
    stmt = (
        select(ToolExecution)
        .where(ToolExecution.run_id.in_(list(run_ids)))
        .order_by(ToolExecution.created_at.asc(), ToolExecution.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


__all__ = [
    "ObservabilityRepositoryError",
    "count_chunks_for_attachment",
    "get_attachment",
    "get_chunk_by_ordinal",
    "list_attachments_before",
    "list_chunks_after",
    "list_runs_before",
    "list_tool_executions_for_run_ids",
]
