"""Validated singleton Job Preferences repository tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from app.db.base import SINGLETON_PK
from app.db.models.profile import JobPreferences as JobPreferencesRow
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.preferences import (
    PreferencesRepository,
    PreferencesValidationError,
)
from app.schemas.preferences import JobPreferences
from sqlalchemy import func, select


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "preferences.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _prefs(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target_roles": ["Backend"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_get_missing_returns_none(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            assert await repo.get() is None


@pytest.mark.asyncio
async def test_replace_singleton_round_trip(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            prefs = JobPreferences.model_validate(_prefs())
            saved = await repo.replace(prefs)
            assert saved.target_roles == ["Backend"]
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.model_dump(mode="json") == prefs.model_dump(mode="json")
            count = (
                await session.execute(
                    select(func.count()).select_from(JobPreferencesRow)
                )
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_replace_overwrites_same_row(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            await repo.replace(
                JobPreferences.model_validate(_prefs(target_roles=["A"]))
            )
            await repo.replace(
                JobPreferences.model_validate(_prefs(target_roles=["B"]))
            )
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.target_roles == ["B"]
            count = (
                await session.execute(
                    select(func.count()).select_from(JobPreferencesRow)
                )
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_invalid_stored_json_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            session.add(
                JobPreferencesRow(
                    id=SINGLETON_PK,
                    preferences_json={
                        "roles": ["legacy"],
                        "acceptable_work_modes": ["anywhere"],
                    },
                )
            )
            await session.flush()
            repo = PreferencesRepository(session)
            with pytest.raises(PreferencesValidationError):
                await repo.get()


@pytest.mark.asyncio
async def test_omitted_preferences_means_no_write(tmp_path: Path) -> None:
    """Preservation is achieved by not calling replace (draft omit path)."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            original = JobPreferences.model_validate(
                _prefs(target_roles=["KeepMe"])
            )
            await repo.replace(original)
            # Simulate commit that omits preferences: profile path only — no
            # preferences replace call.
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.target_roles == ["KeepMe"]
            assert loaded.model_dump(mode="json") == original.model_dump(mode="json")


@pytest.mark.asyncio
async def test_delete_idempotent(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            assert await repo.delete() is False
            await repo.replace(JobPreferences.model_validate(_prefs()))
            assert await repo.delete() is True
            assert await repo.get() is None
            assert await repo.delete() is False


@pytest.mark.asyncio
async def test_invalid_write_does_not_overwrite(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = PreferencesRepository(session)
            await repo.replace(
                JobPreferences.model_validate(_prefs(target_roles=["Stable"]))
            )
            with pytest.raises(PreferencesValidationError):
                await repo.replace(
                    {"acceptable_work_modes": ["spaceship"]}  # type: ignore[arg-type]
                )
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.target_roles == ["Stable"]
