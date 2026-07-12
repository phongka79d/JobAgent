"""Validated profile draft repository: pending create/update/delete tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from app.db.base import SINGLETON_PK
from app.db.models.attachments import Attachment
from app.db.models.profile import (
    CandidateProfile as CandidateProfileRow,
)
from app.db.models.profile import (
    JobPreferences as JobPreferencesRow,
)
from app.db.models.profile import (
    ProfileDraft as ProfileDraftRow,
)
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import (
    ProfileDraftNotFoundError,
    ProfileDraftRepository,
    ProfileDraftStateError,
    ProfileDraftValidationError,
)
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "profile_drafts.db")
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


def _prefs(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "target_roles": ["Backend"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }
    data.update(overrides)
    return data


def _draft_doc(
    *,
    summary: str = "Backend engineer.",
    with_preferences: bool = False,
) -> ProfileDraftDocument:
    profile = CandidateProfile.model_validate(_minimal_profile(summary=summary))
    prefs = (
        JobPreferences.model_validate(_prefs()) if with_preferences else None
    )
    approval = build_approval_summary(profile, preferences=prefs)
    if with_preferences:
        return ProfileDraftDocument(
            profile=profile,
            preferences=prefs,
            approval_summary=approval,
        )
    return ProfileDraftDocument(profile=profile, approval_summary=approval)


async def _add_attachment(session: AsyncSession) -> Attachment:
    att_id = uuid4()
    att = Attachment(
        id=att_id,
        file_hash=uuid4().hex,
        original_name="cv.pdf",
        mime_type="application/pdf",
        size_bytes=12,
        storage_path=f"staged/{att_id}",
        state="staged",
    )
    session.add(att)
    await session.flush()
    return att


@pytest.mark.asyncio
async def test_create_and_load_pending_draft(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(summary="From CV."),
                source_attachment_id=att.id,
            )
            assert created.state == "pending"
            assert created.source_attachment_id == att.id
            assert created.document.profile.summary == "From CV."
            assert created.document.replaces_preferences() is False

            loaded = await repo.get(created.id)
            assert loaded is not None
            assert loaded.id == created.id
            assert "preferences" not in loaded.document.to_storage_dict()


@pytest.mark.asyncio
async def test_create_with_preference_replacement_serializes(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(with_preferences=True),
                source_attachment_id=att.id,
            )
            assert created.document.replaces_preferences() is True
            stored = created.document.to_storage_dict()
            assert "preferences" in stored
            reloaded = await repo.get(created.id)
            assert reloaded is not None
            assert reloaded.document.replaces_preferences() is True


@pytest.mark.asyncio
async def test_same_draft_correction_updates_same_row(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(summary="Initial."),
                source_attachment_id=att.id,
            )
            updated = await repo.update(
                created.id,
                _draft_doc(summary="Corrected once."),
            )
            assert updated.id == created.id
            assert updated.source_attachment_id == att.id
            assert updated.document.profile.summary == "Corrected once."

            count = (
                await session.execute(
                    select(func.count()).select_from(ProfileDraftRow)
                )
            ).scalar_one()
            assert count == 1

            pending = await repo.get_pending()
            assert pending is not None
            assert pending.id == created.id
            assert pending.document.profile.summary == "Corrected once."


@pytest.mark.asyncio
async def test_active_context_retains_source_attachment(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(),
                source_attachment_id=att.id,
            )
            other = await _add_attachment(session)
            # retain_source_attachment=True (default) ignores new id argument path
            updated = await repo.update(
                created.id,
                _draft_doc(summary="Active context edit."),
                source_attachment_id=other.id,
                retain_source_attachment=True,
            )
            assert updated.source_attachment_id == att.id


@pytest.mark.asyncio
async def test_draft_create_does_not_modify_approved_singletons(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            profiles = ProfileRepository(session)
            prefs = PreferencesRepository(session)
            approved_profile = CandidateProfile.model_validate(
                _minimal_profile(summary="Approved stays.")
            )
            approved_prefs = JobPreferences.model_validate(
                _prefs(target_roles=["KeepRole"])
            )
            await profiles.replace(
                approved_profile,
                active_attachment_id=att.id,
            )
            await prefs.replace(approved_prefs)

            before_profile = (
                await session.get(CandidateProfileRow, SINGLETON_PK)
            )
            before_prefs = await session.get(JobPreferencesRow, SINGLETON_PK)
            assert before_profile is not None
            assert before_prefs is not None
            profile_bytes = dict(before_profile.profile_json)
            prefs_bytes = dict(before_prefs.preferences_json)

            drafts = ProfileDraftRepository(session)
            await drafts.create(
                _draft_doc(summary="Draft only.", with_preferences=True),
                source_attachment_id=att.id,
            )
            await drafts.update(
                (await drafts.get_pending()).id,  # type: ignore[union-attr]
                _draft_doc(summary="Draft corrected."),
            )

            after_profile = await session.get(CandidateProfileRow, SINGLETON_PK)
            after_prefs = await session.get(JobPreferencesRow, SINGLETON_PK)
            assert after_profile is not None
            assert after_prefs is not None
            assert after_profile.profile_json == profile_bytes
            assert after_prefs.preferences_json == prefs_bytes


@pytest.mark.asyncio
async def test_invalid_draft_json_rejected_on_read(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            draft_id = uuid4()
            session.add(
                ProfileDraftRow(
                    id=draft_id,
                    source_attachment_id=att.id,
                    draft_json={"garbage": True},
                    state="pending",
                )
            )
            await session.flush()
            repo = ProfileDraftRepository(session)
            with pytest.raises(ProfileDraftValidationError):
                await repo.get(draft_id)


@pytest.mark.asyncio
async def test_invalid_write_leaves_prior_draft_on_rollback(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(summary="Stable draft."),
                source_attachment_id=att.id,
            )

        session = db.session_factory()
        try:
            repo = ProfileDraftRepository(session)
            with pytest.raises(ProfileDraftValidationError):
                await repo.update(
                    created.id,
                    {"profile": {"bad": True}},  # type: ignore[arg-type]
                )
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = ProfileDraftRepository(session)
            loaded = await repo.get(created.id)
            assert loaded is not None
            assert loaded.document.profile.summary == "Stable draft."


@pytest.mark.asyncio
async def test_discard_and_delete(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            att = await _add_attachment(session)
            repo = ProfileDraftRepository(session)
            created = await repo.create(
                _draft_doc(),
                source_attachment_id=att.id,
            )
            discarded = await repo.discard(created.id)
            assert discarded.state == "discarded"
            with pytest.raises(ProfileDraftStateError):
                await repo.update(created.id, _draft_doc(summary="Nope."))
            assert await repo.delete(created.id) is True
            assert await repo.get(created.id) is None
            assert await repo.delete(created.id) is False


@pytest.mark.asyncio
async def test_update_missing_raises(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = ProfileDraftRepository(session)
            with pytest.raises(ProfileDraftNotFoundError):
                await repo.update(uuid4(), _draft_doc())
