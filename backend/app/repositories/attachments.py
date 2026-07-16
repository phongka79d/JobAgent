"""Attachment retrieval and allowed state-transition primitives.

Owns focused reads/mutations for the ``attachments`` table only: exact
file-hash lookup, staged insert, and the approved transitions
``staged → active``, ``staged → failed``, and ``failed → staged`` (same-file
retry). Callers own the async session and commit; this module never opens a
session, commits/rolls back, or touches the filesystem, providers, or graph.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.repositories import attachment_text_chunks as chunk_repo

# Approved transitions only (Master §6.2 attachments):
# staged → active | failed
# failed → staged  (explicit same-file retry)
# active → archived  (approved replacement; never restore to active)
# archived is terminal (immutable history).
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ATTACHMENT_STATE_STAGED: frozenset(
        {ATTACHMENT_STATE_ACTIVE, ATTACHMENT_STATE_FAILED}
    ),
    ATTACHMENT_STATE_FAILED: frozenset({ATTACHMENT_STATE_STAGED}),
    ATTACHMENT_STATE_ACTIVE: frozenset({ATTACHMENT_STATE_ARCHIVED}),
    ATTACHMENT_STATE_ARCHIVED: frozenset(),
}


class AttachmentRepositoryError(Exception):
    """Base error for attachment repository invariant violations."""


class AttachmentNotFoundError(AttachmentRepositoryError):
    """Raised when the requested attachment primary key does not exist."""


class InvalidAttachmentTransitionError(AttachmentRepositoryError):
    """Raised when a state transition is skipped, backward, or terminal."""


async def get_by_id(
    session: AsyncSession,
    attachment_id: str,
) -> Attachment | None:
    """Return the attachment with primary key *attachment_id*, or ``None``."""
    return await session.get(Attachment, attachment_id)


async def get_by_file_hash(
    session: AsyncSession,
    file_hash: str,
) -> Attachment | None:
    """Return the row with exact *file_hash*, or ``None`` if missing.

    Hash uniqueness is enforced by ``uq_attachments__file_hash``. Does not
    finalize the caller's unit of work.
    """
    stmt = select(Attachment).where(Attachment.file_hash == file_hash)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active(session: AsyncSession) -> Attachment | None:
    """Return the single ``active`` attachment, or ``None`` if none exists.

    Partial unique index ``uq_attachments__single_active`` guarantees at most
    one active row. Does not finalize the caller's unit of work.
    """
    stmt = select(Attachment).where(Attachment.state == ATTACHMENT_STATE_ACTIVE)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_staged(
    session: AsyncSession,
    *,
    file_hash: str,
    original_name: str,
    size_bytes: int,
    storage_path: str,
    page_count: int | None = None,
    mime_type: str = ATTACHMENT_MIME_TYPE_PDF,
    attachment_id: str | None = None,
) -> Attachment:
    """Insert one ``staged`` attachment row with optional *page_count*.

    When *attachment_id* is provided it is used as the primary key so callers
    can finalize a UUID-derived storage path before insert. Does not validate
    business rules beyond what the ORM/CHECK constraints enforce at flush.
    Does not finalize the caller's unit of work.
    """
    if not isinstance(file_hash, str) or file_hash.strip() == "":
        raise AttachmentRepositoryError("file_hash must be a non-empty string")
    if not isinstance(original_name, str) or original_name.strip() == "":
        raise AttachmentRepositoryError(
            "original_name must be a non-empty string"
        )
    if not isinstance(storage_path, str) or storage_path.strip() == "":
        raise AttachmentRepositoryError(
            "storage_path must be a non-empty string"
        )
    if size_bytes <= 0:
        raise AttachmentRepositoryError("size_bytes must be > 0")
    if page_count is not None and page_count <= 0:
        raise AttachmentRepositoryError("page_count must be > 0 when set")
    if attachment_id is not None and (
        not isinstance(attachment_id, str) or attachment_id.strip() == ""
    ):
        raise AttachmentRepositoryError(
            "attachment_id must be a non-empty string when set"
        )

    if attachment_id is not None:
        row = Attachment(
            id=attachment_id,
            file_hash=file_hash,
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            page_count=page_count,
            storage_path=storage_path,
            state=ATTACHMENT_STATE_STAGED,
            failure_code=None,
        )
    else:
        row = Attachment(
            file_hash=file_hash,
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            page_count=page_count,
            storage_path=storage_path,
            state=ATTACHMENT_STATE_STAGED,
            failure_code=None,
        )
    session.add(row)
    await session.flush()
    return row


async def mark_active(
    session: AsyncSession,
    attachment_id: str,
    *,
    page_count: int | None = None,
) -> Attachment:
    """Transition ``staged → active`` with required non-null page count.

    When *page_count* is provided it is written on the row; otherwise the
    existing ``page_count`` must already be non-null. Clears any failure code.
    """
    if page_count is not None and page_count <= 0:
        raise AttachmentRepositoryError("page_count must be > 0 when set")
    return await _transition(
        session,
        attachment_id,
        to_state=ATTACHMENT_STATE_ACTIVE,
        page_count=page_count,
        failure_code=None,
    )


async def mark_failed(
    session: AsyncSession,
    attachment_id: str,
    *,
    failure_code: str,
) -> Attachment:
    """Transition ``staged → failed`` with a non-empty *failure_code*."""
    if not isinstance(failure_code, str) or failure_code.strip() == "":
        raise AttachmentRepositoryError(
            "failure_code must be a non-empty string for failed attachments"
        )
    return await _transition(
        session,
        attachment_id,
        to_state=ATTACHMENT_STATE_FAILED,
        page_count=None,
        failure_code=failure_code,
    )


async def retry_as_staged(
    session: AsyncSession,
    attachment_id: str,
) -> Attachment:
    """Transition ``failed → staged`` and clear ``failure_code`` (retry)."""
    return await _transition(
        session,
        attachment_id,
        to_state=ATTACHMENT_STATE_STAGED,
        page_count=None,
        failure_code=None,
    )


async def mark_archived(
    session: AsyncSession,
    attachment_id: str,
) -> Attachment:
    """Transition ``active → archived`` (immutable retained history).

    Clears no page_count; failure_code remains null. Archived rows cannot
    transition back to active. Does not finalize the caller's unit of work
    or touch storage/chunks.
    """
    return await _transition(
        session,
        attachment_id,
        to_state=ATTACHMENT_STATE_ARCHIVED,
        page_count=None,
        failure_code=None,
    )


async def delete(session: AsyncSession, attachment_id: str) -> None:
    """Delete the attachment row by primary key after a successful flush.

    Removes child ``attachment_text_chunks`` first (FK RESTRICT). Callers
    must ensure other FK safety (e.g. profile already repointed). Raises
    :class:`AttachmentNotFoundError` when the row is missing. Does not
    finalize the caller's unit of work or delete filesystem bytes.
    """
    row = await session.get(Attachment, attachment_id)
    if row is None:
        raise AttachmentNotFoundError(
            f"attachment {attachment_id!r} not found"
        )
    if row.state == ATTACHMENT_STATE_ARCHIVED:
        raise AttachmentRepositoryError(
            "archived attachments are immutable history and cannot be deleted"
        )
    await chunk_repo.delete_for_attachment(session, attachment_id)
    await session.delete(row)
    await session.flush()


async def _transition(
    session: AsyncSession,
    attachment_id: str,
    *,
    to_state: str,
    page_count: int | None,
    failure_code: str | None,
) -> Attachment:
    """Apply one allowed attachment state transition with field coupling.

    Does not finalize the caller's unit of work. On invalid transition the
    in-memory row is left unchanged (no field writes before the check).
    """
    row = await session.get(Attachment, attachment_id)
    if row is None:
        raise AttachmentNotFoundError(
            f"attachment {attachment_id!r} not found"
        )

    from_state = row.state
    allowed = _ALLOWED_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise InvalidAttachmentTransitionError(
            f"transition {from_state!r} → {to_state!r} is not allowed"
        )

    now = utc_now()

    if to_state == ATTACHMENT_STATE_ACTIVE:
        effective_pages = page_count if page_count is not None else row.page_count
        if effective_pages is None or effective_pages <= 0:
            raise AttachmentRepositoryError(
                "active attachment requires page_count > 0"
            )
        row.page_count = effective_pages
        row.failure_code = None
    elif to_state == ATTACHMENT_STATE_FAILED:
        row.failure_code = failure_code
    elif to_state == ATTACHMENT_STATE_STAGED:
        # Explicit retry: clear failure; leave page_count as-is.
        row.failure_code = None
    elif to_state == ATTACHMENT_STATE_ARCHIVED:
        # Immutable history: keep page_count/metadata; no failure_code.
        row.failure_code = None
    else:
        raise InvalidAttachmentTransitionError(
            f"unsupported target state {to_state!r}"
        )

    row.state = to_state
    row.updated_at = now
    await session.flush()
    return row
