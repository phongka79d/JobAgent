"""Validated pending profile-draft repository (caller-owned transactions).

Draft rows hold a validated ``ProfileDraftDocument`` only. Create/update of a
pending draft never mutates the approved profile or preferences singletons.
Methods flush only and never commit or roll back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import new_uuid
from app.db.enums import ProfileDraftState
from app.db.models.profile import ProfileDraft as ProfileDraftRow
from app.schemas.profile_draft import ProfileDraftDocument


class ProfileDraftRepositoryError(Exception):
    """Draft persistence failed without disclosing raw JSON payloads."""


class ProfileDraftValidationError(ProfileDraftRepositoryError):
    """Stored or inbound draft JSON failed Pydantic validation."""


class ProfileDraftNotFoundError(ProfileDraftRepositoryError):
    """No draft exists for the requested identity."""


class ProfileDraftStateError(ProfileDraftRepositoryError):
    """Requested draft operation is not allowed for the current state."""


@dataclass(frozen=True, slots=True)
class ProfileDraftRecord:
    """Validated draft document plus row identity and source attachment."""

    id: UUID
    source_attachment_id: UUID
    document: ProfileDraftDocument
    state: str


def _validate_draft_document(data: Any) -> ProfileDraftDocument:
    """Parse opaque JSON into a domain draft; never return unvalidated data."""
    if not isinstance(data, dict):
        raise ProfileDraftValidationError("invalid draft document")
    try:
        return ProfileDraftDocument.from_storage_dict(data)
    except ValidationError as exc:
        raise ProfileDraftValidationError("invalid draft document") from exc
    except ValueError as exc:
        # from_storage_dict / model validators may raise ValueError
        raise ProfileDraftValidationError("invalid draft document") from exc


class ProfileDraftRepository:
    """Pending draft create/load/update/delete with state checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        document: ProfileDraftDocument,
        *,
        source_attachment_id: UUID,
        draft_id: UUID | None = None,
    ) -> ProfileDraftRecord:
        """Insert a pending draft. Does not modify approved singletons."""
        if not isinstance(document, ProfileDraftDocument):
            document = _validate_draft_document(document)
        # Normalize via storage form (omit-vs-replace preferences).
        storage = document.to_storage_dict()
        validated = _validate_draft_document(storage)

        row_id = draft_id if draft_id is not None else new_uuid()
        row = ProfileDraftRow(
            id=row_id,
            source_attachment_id=source_attachment_id,
            draft_json=storage,
            state=ProfileDraftState.PENDING.value,
        )
        self._session.add(row)

        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise ProfileDraftRepositoryError("draft write failed") from integrity_error

        return ProfileDraftRecord(
            id=row.id,
            source_attachment_id=row.source_attachment_id,
            document=validated,
            state=row.state,
        )

    async def get(self, draft_id: UUID) -> ProfileDraftRecord | None:
        """Load one draft by id with validated document, or ``None``."""
        row = await self._session.get(ProfileDraftRow, draft_id)
        if row is None:
            return None
        document = _validate_draft_document(row.draft_json)
        return ProfileDraftRecord(
            id=row.id,
            source_attachment_id=row.source_attachment_id,
            document=document,
            state=row.state,
        )

    async def get_pending(self) -> ProfileDraftRecord | None:
        """Return the most recently created pending draft, if any."""
        result = await self._session.execute(
            select(ProfileDraftRow)
            .where(ProfileDraftRow.state == ProfileDraftState.PENDING.value)
            .order_by(
                ProfileDraftRow.created_at.desc(),
                ProfileDraftRow.id.desc(),
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        document = _validate_draft_document(row.draft_json)
        return ProfileDraftRecord(
            id=row.id,
            source_attachment_id=row.source_attachment_id,
            document=document,
            state=row.state,
        )

    async def update(
        self,
        draft_id: UUID,
        document: ProfileDraftDocument,
        *,
        source_attachment_id: UUID | None = None,
        retain_source_attachment: bool = True,
    ) -> ProfileDraftRecord:
        """Update the same pending draft (same-draft correction). Does not commit.

        Active-context corrections may retain ``source_attachment_id`` (default)
        so the current active CV remains the draft source without promotion.
        """
        row = await self._session.get(ProfileDraftRow, draft_id)
        if row is None:
            raise ProfileDraftNotFoundError("draft not found")
        if row.state != ProfileDraftState.PENDING.value:
            raise ProfileDraftStateError("draft is not pending")

        if not isinstance(document, ProfileDraftDocument):
            document = _validate_draft_document(document)
        storage = document.to_storage_dict()
        validated = _validate_draft_document(storage)

        row.draft_json = storage
        if not retain_source_attachment:
            if source_attachment_id is None:
                raise ProfileDraftRepositoryError("source_attachment_id required")
            row.source_attachment_id = source_attachment_id
        elif source_attachment_id is not None:
            # Explicit new source while still retaining control is allowed when
            # callers pass a replacement id with retain_source_attachment=False.
            # When retain is True, ignore the argument to preserve attachment.
            pass

        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise ProfileDraftRepositoryError("draft write failed") from integrity_error

        return ProfileDraftRecord(
            id=row.id,
            source_attachment_id=row.source_attachment_id,
            document=validated,
            state=row.state,
        )

    async def discard(self, draft_id: UUID) -> ProfileDraftRecord:
        """Mark a pending draft discarded without deleting the row."""
        row = await self._session.get(ProfileDraftRow, draft_id)
        if row is None:
            raise ProfileDraftNotFoundError("draft not found")
        if row.state != ProfileDraftState.PENDING.value:
            raise ProfileDraftStateError("draft is not pending")
        row.state = ProfileDraftState.DISCARDED.value
        await self._session.flush()
        document = _validate_draft_document(row.draft_json)
        return ProfileDraftRecord(
            id=row.id,
            source_attachment_id=row.source_attachment_id,
            document=document,
            state=row.state,
        )

    async def delete(self, draft_id: UUID) -> bool:
        """Delete a draft row by id. Idempotent: False if missing."""
        row = await self._session.get(ProfileDraftRow, draft_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    def is_pending(self, record: ProfileDraftRecord) -> bool:
        """State check helper for callers (pure)."""
        return record.state == ProfileDraftState.PENDING.value
