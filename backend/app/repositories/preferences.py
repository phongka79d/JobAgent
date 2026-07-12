"""Validated singleton Job Preferences repository (caller-owned transactions).

Opaque ``preferences_json`` is validated at this boundary. Optional preferences
are absent when no row exists; callers that omit preference changes simply do
not call ``replace``. Methods flush only and never commit or roll back.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SINGLETON_PK
from app.db.models.profile import JobPreferences as JobPreferencesRow
from app.schemas.preferences import JobPreferences


class PreferencesRepositoryError(Exception):
    """Preference persistence failed without disclosing raw JSON payloads."""


class PreferencesValidationError(PreferencesRepositoryError):
    """Stored or inbound preferences JSON failed Pydantic validation."""


class PreferencesNotFoundError(PreferencesRepositoryError):
    """Required singleton preferences row is missing."""


def _validate_preferences_document(data: Any) -> JobPreferences:
    """Parse opaque JSON into domain preferences; never return unvalidated data."""
    if not isinstance(data, dict):
        raise PreferencesValidationError("invalid preferences document")
    try:
        return JobPreferences.model_validate(data)
    except ValidationError as exc:
        raise PreferencesValidationError("invalid preferences document") from exc


def _preferences_to_storage(preferences: JobPreferences) -> dict[str, Any]:
    return preferences.model_dump(mode="json")


class PreferencesRepository:
    """Singleton load/replace for explicit Job Preferences."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> JobPreferences | None:
        """Load the singleton preferences, or ``None`` when no row exists.

        Invalid stored JSON raises ``PreferencesValidationError`` and never
        surfaces as an approved domain object.
        """
        row = await self._session.get(JobPreferencesRow, SINGLETON_PK)
        if row is None:
            return None
        return _validate_preferences_document(row.preferences_json)

    async def replace(self, preferences: JobPreferences) -> JobPreferences:
        """Create or overwrite the singleton preferences. Does not commit.

        Preference *preservation* is achieved by not calling this method when
        a draft omits preference changes.
        """
        if not isinstance(preferences, JobPreferences):
            preferences = _validate_preferences_document(preferences)

        storage = _preferences_to_storage(preferences)
        validated = _validate_preferences_document(storage)

        row = await self._session.get(JobPreferencesRow, SINGLETON_PK)
        if row is None:
            row = JobPreferencesRow(
                id=SINGLETON_PK,
                preferences_json=storage,
            )
            self._session.add(row)
        else:
            row.preferences_json = storage

        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise PreferencesRepositoryError(
                "preferences write failed"
            ) from integrity_error

        return validated

    async def delete(self) -> bool:
        """Delete the singleton preferences row. Idempotent: False if missing."""
        row = await self._session.get(JobPreferencesRow, SINGLETON_PK)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
