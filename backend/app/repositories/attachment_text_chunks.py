"""Persistence primitives for ``attachment_text_chunks``.

Owns insert/replace/list/get/delete-for-attachment only. Callers own the
async session and commit. Never opens a session, calls providers, or
touches the filesystem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachment_text_chunks import (
    CHUNK_PREVIEW_MAX_CHARS,
    AttachmentTextChunk,
)


class AttachmentTextChunkRepositoryError(Exception):
    """Base error for attachment text-chunk repository invariant violations."""


@dataclass(frozen=True, slots=True)
class ChunkWrite:
    """One canonical chunk ready for persistence (pre-validated)."""

    ordinal: int
    text: str
    preview: str
    char_count: int
    token_estimate: int


def preview_for_text(text: str, *, max_chars: int = CHUNK_PREVIEW_MAX_CHARS) -> str:
    """Bounded preview of *text* (exact prefix; no ellipsis mutation)."""
    if max_chars < 0:
        raise AttachmentTextChunkRepositoryError("max_chars must be >= 0")
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def token_estimate_for_chars(char_count: int) -> int:
    """Deterministic local estimate: ``ceil(char_count / 4)``."""
    if char_count < 0:
        raise AttachmentTextChunkRepositoryError("char_count must be >= 0")
    return int(ceil(char_count / 4))


def build_chunk_write(ordinal: int, text: str) -> ChunkWrite:
    """Build a validated write row from ordinal and nonempty *text*."""
    if ordinal < 0:
        raise AttachmentTextChunkRepositoryError("ordinal must be >= 0")
    if not isinstance(text, str) or text == "":
        raise AttachmentTextChunkRepositoryError(
            "chunk text must be a nonempty string"
        )
    char_count = len(text)
    return ChunkWrite(
        ordinal=ordinal,
        text=text,
        preview=preview_for_text(text),
        char_count=char_count,
        token_estimate=token_estimate_for_chars(char_count),
    )


async def list_for_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> list[AttachmentTextChunk]:
    """Return chunks for *attachment_id* in ascending ordinal order."""
    stmt = (
        select(AttachmentTextChunk)
        .where(AttachmentTextChunk.attachment_id == attachment_id)
        .order_by(AttachmentTextChunk.ordinal.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_attachment_ordinal(
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


async def count_for_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> int:
    """Return the number of chunk rows for *attachment_id*."""
    rows = await list_for_attachment(session, attachment_id)
    return len(rows)


async def delete_for_attachment(
    session: AsyncSession,
    attachment_id: str,
) -> int:
    """Delete all chunk rows for *attachment_id*. Returns rows removed.

    Required before application-level attachment deletion (FK RESTRICT).
    Does not finalize the caller's unit of work.
    """
    existing = await list_for_attachment(session, attachment_id)
    count = len(existing)
    if count:
        stmt = delete(AttachmentTextChunk).where(
            AttachmentTextChunk.attachment_id == attachment_id
        )
        await session.execute(stmt)
        await session.flush()
    return count


async def replace_for_attachment(
    session: AsyncSession,
    attachment_id: str,
    chunks: Sequence[ChunkWrite],
) -> list[AttachmentTextChunk]:
    """Replace all chunks for *attachment_id* with *chunks* (atomic in session).

    Empty *chunks* clears existing rows and writes nothing (caller uses this
    only when intentionally wiping; successful extraction always passes
    nonempty ascending ordinals). Does not finalize the caller's unit of work.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        raise AttachmentTextChunkRepositoryError(
            "attachment_id must be a non-empty string"
        )

    seen: set[int] = set()
    ordered = sorted(chunks, key=lambda c: c.ordinal)
    for i, chunk in enumerate(ordered):
        if chunk.ordinal in seen:
            raise AttachmentTextChunkRepositoryError(
                f"duplicate ordinal {chunk.ordinal}"
            )
        seen.add(chunk.ordinal)
        if chunk.ordinal != i:
            raise AttachmentTextChunkRepositoryError(
                "chunk ordinals must be contiguous ascending from 0"
            )
        if chunk.char_count <= 0 or chunk.text == "":
            raise AttachmentTextChunkRepositoryError(
                "chunk text/char_count must be nonempty"
            )
        if chunk.char_count != len(chunk.text):
            raise AttachmentTextChunkRepositoryError(
                "char_count must equal len(text)"
            )
        if chunk.token_estimate != token_estimate_for_chars(chunk.char_count):
            raise AttachmentTextChunkRepositoryError(
                "token_estimate must equal ceil(char_count / 4)"
            )
        if chunk.preview != preview_for_text(chunk.text):
            raise AttachmentTextChunkRepositoryError(
                "preview must match bounded text prefix"
            )

    await delete_for_attachment(session, attachment_id)

    rows: list[AttachmentTextChunk] = []
    for chunk in ordered:
        row = AttachmentTextChunk(
            attachment_id=attachment_id,
            ordinal=chunk.ordinal,
            text=chunk.text,
            preview=chunk.preview,
            char_count=chunk.char_count,
            token_estimate=chunk.token_estimate,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows
