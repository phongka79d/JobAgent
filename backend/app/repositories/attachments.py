"""Attachment metadata repository (staged/active state mechanics only).

Persists rows in the ``attachments`` table. Callers own the ``AsyncSession``
transaction: this module never commits or rolls back implicitly. Content-policy
(MIME, magic bytes, page limits) and profile-replacement decisions belong to
Plan 4; this repository accepts already-validated metadata and service-generated
storage paths.

Service paths use the authoritative canonical grammar from
``attachment_storage_paths`` (``staged/<uuid>`` / ``active/<uuid>`` with leaf
exactly matching ``str(attachment_id)``).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AttachmentState
from app.db.models.attachments import Attachment
from app.services.attachment_storage_errors import InvalidStoragePathError
from app.services.attachment_storage_paths import (
    require_canonical_service_path as _require_canonical_service_path,
)


class AttachmentRepositoryError(Exception):
    """Metadata operation failed without disclosing storage absolute paths."""


class AttachmentNotFoundError(AttachmentRepositoryError):
    """No attachment row exists for the requested identity."""


class AttachmentStateError(AttachmentRepositoryError):
    """Requested staged/active transition is not allowed."""


class AttachmentDuplicateError(AttachmentRepositoryError):
    """Unique id or file_hash conflict; caller must roll back the failed unit."""

    def __init__(self, kind: str = "unknown") -> None:
        self.kind = kind
        super().__init__(f"duplicate attachment ({kind})")


@dataclass(frozen=True, slots=True)
class StagedAttachmentInput:
    """Validated metadata required to insert a staged attachment row."""

    id: UUID
    file_hash: str
    original_name: str
    mime_type: str
    size_bytes: int
    storage_path: str
    page_count: int | None = None


def require_canonical_service_path(
    storage_path: str,
    attachment_id: UUID,
    *,
    expected_area: str,
) -> str:
    """Repository-facing wrapper around the shared canonical path validator."""
    try:
        return _require_canonical_service_path(
            storage_path,
            attachment_id,
            expected_area=expected_area,
        )
    except InvalidStoragePathError as exc:
        msg = str(exc)
        if "path identity mismatch" in msg:
            raise AttachmentRepositoryError("path identity mismatch") from None
        raise AttachmentRepositoryError("invalid storage path") from None


def _map_integrity_error(exc: IntegrityError) -> AttachmentDuplicateError:
    """Translate SQLAlchemy integrity failures without leaking SQL/params."""
    raw = str(getattr(exc, "orig", "") or "").lower()
    if "file_hash" in raw:
        return AttachmentDuplicateError("hash")
    if "attachments.id" in raw or raw.endswith(".id"):
        return AttachmentDuplicateError("id")
    if "primary key" in raw:
        return AttachmentDuplicateError("id")
    return AttachmentDuplicateError("unknown")


class AttachmentRepository:
    """Narrow attachment metadata operations on a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_staged(self, payload: StagedAttachmentInput) -> Attachment:
        """Insert a staged attachment. Does not commit.

        On unique conflicts raises ``AttachmentDuplicateError`` after a failed
        flush. The session is left unusable for further work until the *caller*
        rolls back; this method never commits or rolls back.
        """
        storage_path = require_canonical_service_path(
            payload.storage_path,
            payload.id,
            expected_area="staged",
        )
        if payload.size_bytes < 0:
            raise AttachmentRepositoryError("invalid size")
        if not payload.file_hash or not payload.original_name or not payload.mime_type:
            raise AttachmentRepositoryError("invalid metadata")

        row = Attachment(
            id=payload.id,
            file_hash=payload.file_hash,
            original_name=payload.original_name,
            mime_type=payload.mime_type,
            size_bytes=payload.size_bytes,
            page_count=payload.page_count,
            storage_path=storage_path,
            state=AttachmentState.STAGED.value,
        )
        self._session.add(row)
        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise _map_integrity_error(integrity_error)
        return row

    async def get_by_id(self, attachment_id: UUID) -> Attachment | None:
        """Load one attachment by primary key, or None."""
        return await self._session.get(Attachment, attachment_id)

    async def get_by_hash(self, file_hash: str) -> Attachment | None:
        """Load one attachment by unique file hash, or None.

        Lookup only — duplicate-detection policy remains Plan 4.
        """
        result = await self._session.execute(
            select(Attachment).where(Attachment.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    async def mark_active(
        self,
        attachment_id: UUID,
        *,
        storage_path: str,
    ) -> Attachment:
        """Transition staged -> active and record the active service path.

        Does not commit. Rejects missing rows, non-staged states, and paths
        whose UUID leaf does not match ``attachment_id``.
        """
        active_path = require_canonical_service_path(
            storage_path,
            attachment_id,
            expected_area="active",
        )

        row = await self.get_by_id(attachment_id)
        if row is None:
            raise AttachmentNotFoundError("attachment not found")
        if row.state != AttachmentState.STAGED.value:
            raise AttachmentStateError("invalid state transition")

        row.state = AttachmentState.ACTIVE.value
        row.storage_path = active_path
        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise _map_integrity_error(integrity_error)
        return row

    async def delete(self, attachment_id: UUID) -> bool:
        """Delete attachment metadata by id. Idempotent: False if missing.

        Does not commit. Does not touch filesystem bytes.
        """
        row = await self.get_by_id(attachment_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
