"""Validated singleton Candidate Profile repository tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.db.base import SINGLETON_PK
from app.db.models.attachments import Attachment
from app.db.models.profile import CandidateProfile as CandidateProfileRow
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.profiles import (
    ProfileRepository,
    ProfileRepositoryError,
    ProfileValidationError,
)
from app.schemas.candidate import CandidateProfile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "profiles.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _minimal_profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Backend engineer.",
        "current_title": "Engineer",
        "total_experience_years": None,
        "skills": [],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.7,
    }
    data.update(overrides)
    return data


async def _add_attachment(session: AsyncSession) -> Attachment:
    att = Attachment(
        id=uuid4(),
        file_hash=uuid4().hex,
        original_name="cv.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        storage_path=f"active/{uuid4()}",
        state="active",
    )
    # Fix path leaf to match id for realism
    att.storage_path = f"active/{att.id}"
    session.add(att)
    await session.flush()
    return att


@pytest.mark.asyncio
async def test_get_missing_returns_none(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ProfileRepository(session)
            assert await repo.get() is None


@pytest.mark.asyncio
async def test_replace_creates_singleton_and_reload(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileRepository(session)
            profile = CandidateProfile.model_validate(_minimal_profile())
            record = await repo.replace(
                profile,
                active_attachment_id=att.id,
            )
            assert record.profile.summary == "Backend engineer."
            assert record.active_attachment_id == att.id

            again = await repo.get()
            assert again is not None
            assert again.profile.summary == "Backend engineer."
            assert again.active_attachment_id == att.id

            count = (
                await session.execute(
                    select(func.count()).select_from(CandidateProfileRow)
                )
            ).scalar_one()
            assert count == 1
            assert again.profile.model_dump(mode="json") == profile.model_dump(
                mode="json"
            )


@pytest.mark.asyncio
async def test_replace_overwrites_same_singleton_no_history(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ProfileRepository(session)
            first = CandidateProfile.model_validate(
                _minimal_profile(summary="First version.")
            )
            await repo.replace(first)
            second = CandidateProfile.model_validate(
                _minimal_profile(summary="Second version.")
            )
            record = await repo.replace(second)
            assert record.profile.summary == "Second version."
            count = (
                await session.execute(
                    select(func.count()).select_from(CandidateProfileRow)
                )
            ).scalar_one()
            assert count == 1
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.profile.summary == "Second version."


@pytest.mark.asyncio
async def test_invalid_stored_json_never_returns_domain_object(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            session.add(
                CandidateProfileRow(
                    id=SINGLETON_PK,
                    profile_json={"headline": "not a valid profile", "cv_text": "X"},
                )
            )
            await session.flush()
            repo = ProfileRepository(session)
            with pytest.raises(ProfileValidationError, match="invalid profile"):
                await repo.get()


@pytest.mark.asyncio
async def test_invalid_write_rejected_before_partial_change(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ProfileRepository(session)
            good = CandidateProfile.model_validate(
                _minimal_profile(summary="Good profile.")
            )
            await repo.replace(good)
            # Forge invalid by going through validation path with bad dict.
            with pytest.raises(ProfileValidationError):
                await repo.replace({"not": "a profile"})  # type: ignore[arg-type]

            loaded = await repo.get()
            assert loaded is not None
            assert loaded.profile.summary == "Good profile."


@pytest.mark.asyncio
async def test_retain_active_attachment_on_replace(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileRepository(session)
            await repo.replace(
                CandidateProfile.model_validate(_minimal_profile()),
                active_attachment_id=att.id,
            )
            updated = await repo.replace(
                CandidateProfile.model_validate(
                    _minimal_profile(summary="Corrected summary.")
                ),
                retain_active_attachment=True,
                active_attachment_id=None,
            )
            assert updated.active_attachment_id == att.id
            assert updated.profile.summary == "Corrected summary."


@pytest.mark.asyncio
async def test_failed_write_rollback_leaves_prior_state(tmp_path: Path) -> None:
    """Caller-owned rollback after repository error leaves prior singleton."""
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ProfileRepository(session)
            await repo.replace(
                CandidateProfile.model_validate(
                    _minimal_profile(summary="Committed.")
                )
            )

        session = db.session_factory()
        try:
            repo = ProfileRepository(session)
            # Point active_attachment_id at a non-existent FK to force IntegrityError
            # on flush; caller must roll back.
            missing = uuid4()
            with pytest.raises(ProfileRepositoryError):
                await repo.replace(
                    CandidateProfile.model_validate(
                        _minimal_profile(summary="Should not stick.")
                    ),
                    active_attachment_id=missing,
                )
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = ProfileRepository(session)
            loaded = await repo.get()
            assert loaded is not None
            assert loaded.profile.summary == "Committed."
