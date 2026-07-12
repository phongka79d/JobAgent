"""Validated singleton Candidate Profile repository (caller-owned transactions).

Opaque ``profile_json`` is validated at this boundary with the authoritative
Pydantic ``CandidateProfile`` contract. No historical snapshots: create/replace
always targets the singleton row (``SINGLETON_PK``). Methods flush only and
never commit or roll back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SINGLETON_PK
from app.db.models.profile import CandidateProfile as CandidateProfileRow
from app.repositories.graph_outbox import (
    CANDIDATE_SYNC_OPERATION,
    GraphOutboxRepository,
)
from app.schemas.candidate import CandidateProfile


class ProfileRepositoryError(Exception):
    """Profile persistence failed without disclosing raw JSON payloads."""


class ProfileValidationError(ProfileRepositoryError):
    """Stored or inbound profile JSON failed Pydantic validation."""


class ProfileNotFoundError(ProfileRepositoryError):
    """Required singleton profile row is missing."""


@dataclass(frozen=True, slots=True)
class ApprovedProfileRecord:
    """Validated approved profile plus singleton metadata (no storage paths)."""

    profile: CandidateProfile
    active_attachment_id: UUID | None
    embedding_model: str | None = None


def _validate_profile_document(data: Any) -> CandidateProfile:
    """Parse opaque JSON into a domain profile; never return unvalidated data."""
    if not isinstance(data, dict):
        raise ProfileValidationError("invalid profile document")
    try:
        return CandidateProfile.model_validate(data)
    except ValidationError as exc:
        raise ProfileValidationError("invalid profile document") from exc


def _profile_to_storage(profile: CandidateProfile) -> dict[str, Any]:
    return profile.model_dump(mode="json")


class ProfileRepository:
    """Singleton load/replace for the approved Candidate Profile."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> ApprovedProfileRecord | None:
        """Load the singleton profile, or ``None`` when no row exists.

        Invalid stored JSON raises ``ProfileValidationError`` and never
        surfaces as an approved domain object.
        """
        row = await self._session.get(CandidateProfileRow, SINGLETON_PK)
        if row is None:
            return None
        profile = _validate_profile_document(row.profile_json)
        return ApprovedProfileRecord(
            profile=profile,
            active_attachment_id=row.active_attachment_id,
            embedding_model=row.embedding_model,
        )

    async def replace(
        self,
        profile: CandidateProfile,
        *,
        active_attachment_id: UUID | None = None,
        retain_active_attachment: bool = False,
        embedding_model: str | None = None,
        retain_embedding_model: bool = False,
    ) -> ApprovedProfileRecord:
        """Create or overwrite the singleton approved profile. Does not commit.

        When ``retain_active_attachment`` is true (active-context corrections),
        the existing ``active_attachment_id`` is preserved and the
        ``active_attachment_id`` argument is ignored if a row already exists.
        """
        if not isinstance(profile, CandidateProfile):
            # Re-validate if callers pass a dict-like object by mistake.
            profile = _validate_profile_document(profile)

        # Round-trip through storage form so write path matches read path.
        storage = _profile_to_storage(profile)
        validated = _validate_profile_document(storage)

        row = await self._session.get(CandidateProfileRow, SINGLETON_PK)
        if row is None:
            if retain_active_attachment:
                # No prior attachment to retain on first insert.
                attachment_id = active_attachment_id
            else:
                attachment_id = active_attachment_id
            embed = embedding_model
            row = CandidateProfileRow(
                id=SINGLETON_PK,
                profile_json=storage,
                active_attachment_id=attachment_id,
                embedding_model=embed,
            )
            self._session.add(row)
        else:
            if retain_active_attachment:
                attachment_id = row.active_attachment_id
            else:
                attachment_id = active_attachment_id
            if retain_embedding_model:
                embed = row.embedding_model
            else:
                embed = embedding_model
            row.profile_json = storage
            row.active_attachment_id = attachment_id
            row.embedding_model = embed

        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise ProfileRepositoryError("profile write failed") from integrity_error

        await GraphOutboxRepository(self._session).enqueue(
            operation=CANDIDATE_SYNC_OPERATION,
            entity_id=str(SINGLETON_PK),
            payload={"candidate_id": str(SINGLETON_PK)},
            requeue_existing=True,
        )

        return ApprovedProfileRecord(
            profile=validated,
            active_attachment_id=row.active_attachment_id,
            embedding_model=row.embedding_model,
        )
