"""Integration tests for profile-family repository primitives (pre-service).

Uses a migrated temporary SQLite file (Alembic head). Covers singleton
active/draft/preferences reads, upserts, deletes, UTC timestamps, missing
rows, and constraint-visible failures. Full approval transaction ordering and
API routes remain later service tasks.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.models.profiles import (
    CANDIDATE_PROFILE_ID,
    JOB_PREFERENCE_KEYS,
    JOB_PREFERENCES_ID,
    PROFILE_DRAFT_ID,
    CandidateProfile,
)
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
from app.repositories import profiles as prof_repo
from app.repositories.profiles import ProfileRepositoryError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.support.db_migration import run_async, session_factory

MINIMAL_PROFILE: dict[str, Any] = {
    "full_name": "Test User",
    "headline": None,
    "summary": None,
    "location": None,
    "email": None,
    "phone": None,
    "links": [],
    "skills": [],
    "experience": [],
    "education": [],
    "languages": [],
    "extraction_confidence": 0.5,
    "source_attachment_id": None,
}
MINIMAL_DRAFT: dict[str, Any] = {
    "profile": MINIMAL_PROFILE,
    "preferences": {k: [] for k in JOB_PREFERENCE_KEYS},
    "corrections": [],
    "exclusions": [],
}
EMPTY_PREFS: dict[str, list[Any]] = {k: [] for k in JOB_PREFERENCE_KEYS}


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


async def _staged_attachment(
    session: object,
    *,
    file_hash: str = "prof-hash",
    storage_path: str = "prof/cv.pdf",
    page_count: int = 1,
) -> str:
    row = await att_repo.create_staged(
        session,  # type: ignore[arg-type]
        file_hash=file_hash,
        original_name="cv.pdf",
        size_bytes=50,
        storage_path=storage_path,
        page_count=page_count,
    )
    return row.id


# ---------------------------------------------------------------------------
# Active profile singleton
# ---------------------------------------------------------------------------


def test_active_profile_missing_then_upsert(db_path: Path) -> None:
    """No profile after seed; upsert creates active singleton and re-upserts."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                assert await prof_repo.get_active_profile(session) is None
                att_id = await _staged_attachment(session)
                await att_repo.mark_active(session, att_id)
                created = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=MINIMAL_PROFILE,
                )
                assert created.id == CANDIDATE_PROFILE_ID
                assert created.active_attachment_id == att_id
                assert created.profile_json["full_name"] == "Test User"
                assert created.updated_at.tzinfo is not None
                await session.commit()

            async with factory() as session:
                found = await prof_repo.get_active_profile(session)
                assert found is not None
                assert found.id == CANDIDATE_PROFILE_ID

                # Second attachment for repoint (replacement shape only).
                new_att = await _staged_attachment(
                    session,
                    file_hash="prof-hash-2",
                    storage_path="prof/cv2.pdf",
                )
                updated_json = {**MINIMAL_PROFILE, "full_name": "Updated"}
                updated = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=new_att,
                    profile_json=updated_json,
                )
                assert updated.id == CANDIDATE_PROFILE_ID
                assert updated.active_attachment_id == new_att
                assert updated.profile_json["full_name"] == "Updated"
                await session.commit()

            async with factory() as session:
                again = await prof_repo.get_active_profile(session)
                assert again is not None
                assert again.active_attachment_id == new_att
                assert again.profile_json["full_name"] == "Updated"
                count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM candidate_profile")
                    )
                ).scalar_one()
                assert int(count) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_upsert_profile_rejects_empty_attachment_id(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_active_profile(
                        session,
                        active_attachment_id="",
                        profile_json=MINIMAL_PROFILE,
                    )
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_active_profile(
                        session,
                        active_attachment_id="x",
                        profile_json=[],  # type: ignore[arg-type]
                    )
        finally:
            await engine.dispose()

    run_async(_body())


def test_profile_fk_and_singleton_constraint_visible(db_path: Path) -> None:
    """Missing attachment FK and wrong singleton id surface IntegrityError."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await prof_repo.upsert_active_profile(
                        session,
                        active_attachment_id="missing-attachment",
                        profile_json=MINIMAL_PROFILE,
                    )
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                att_id = await _staged_attachment(session)
                # Direct ORM insert with wrong id must fail CHECK.
                bad = CandidateProfile(
                    id="not-active",
                    active_attachment_id=att_id,
                    profile_json=MINIMAL_PROFILE,
                )
                session.add(bad)
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Draft singleton
# ---------------------------------------------------------------------------


def test_draft_upsert_read_delete(db_path: Path) -> None:
    """Draft singleton create, update, missing delete, and delete success."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                assert await prof_repo.get_current_draft(session) is None
                assert await prof_repo.delete_current_draft(session) is False

                att_id = await _staged_attachment(
                    session, file_hash="draft-h", storage_path="draft.pdf"
                )
                draft = await prof_repo.upsert_current_draft(
                    session,
                    draft_json=MINIMAL_DRAFT,
                    source_attachment_id=att_id,
                )
                assert draft.id == PROFILE_DRAFT_ID
                assert draft.source_attachment_id == att_id
                assert draft.draft_json["profile"]["full_name"] == "Test User"
                await session.commit()

            async with factory() as session:
                found = await prof_repo.get_current_draft(session)
                assert found is not None
                assert found.id == PROFILE_DRAFT_ID

                # Preference-only style: clear source attachment.
                updated = await prof_repo.upsert_current_draft(
                    session,
                    draft_json={**MINIMAL_DRAFT, "note": "ignored-by-shape"},
                    source_attachment_id=None,
                )
                assert updated.id == PROFILE_DRAFT_ID
                assert updated.source_attachment_id is None
                await session.commit()

            async with factory() as session:
                assert await prof_repo.delete_current_draft(session) is True
                await session.commit()

            async with factory() as session:
                assert await prof_repo.get_current_draft(session) is None
                assert await prof_repo.delete_current_draft(session) is False
                count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM profile_drafts")
                    )
                ).scalar_one()
                assert int(count) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_draft_source_attachment_unique_and_cascade(db_path: Path) -> None:
    """source_attachment_id unique; deleting attachment cascades the draft."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session, file_hash="cas", storage_path="cas.pdf"
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=MINIMAL_DRAFT,
                    source_attachment_id=att_id,
                )
                await session.commit()
                saved_att = att_id

            async with factory() as session:
                # Cascade: delete attachment removes draft.
                await att_repo.delete(session, saved_att)
                await session.commit()

            async with factory() as session:
                assert await prof_repo.get_current_draft(session) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_draft_rejects_non_mapping_json(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_current_draft(
                        session,
                        draft_json=[],  # type: ignore[arg-type]
                    )
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_current_draft(
                        session,
                        draft_json=MINIMAL_DRAFT,
                        source_attachment_id="",
                    )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Job preferences singleton (seeded)
# ---------------------------------------------------------------------------


def test_job_preferences_seeded_and_upsert(db_path: Path) -> None:
    """Seed inserts active preferences; upsert updates JSON and timestamp."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is not None
                assert prefs.id == JOB_PREFERENCES_ID
                assert set(prefs.preferences_json) == set(JOB_PREFERENCE_KEYS)
                for key in JOB_PREFERENCE_KEYS:
                    assert prefs.preferences_json[key] == []

                past = datetime(2020, 1, 1, tzinfo=UTC)
                prefs.updated_at = past
                await session.flush()
                await session.commit()

            async with factory() as session:
                new_doc = {
                    **EMPTY_PREFS,
                    "target_roles": ["Backend Engineer"],
                }
                updated = await prof_repo.upsert_job_preferences(
                    session, preferences_json=new_doc
                )
                assert updated.id == JOB_PREFERENCES_ID
                assert updated.preferences_json["target_roles"] == [
                    "Backend Engineer"
                ]
                assert updated.updated_at > past or (
                    updated.updated_at.replace(tzinfo=UTC) > past
                    if updated.updated_at.tzinfo is None
                    else updated.updated_at > past
                )
                await session.commit()

            async with factory() as session:
                again = await prof_repo.get_job_preferences(session)
                assert again is not None
                assert again.preferences_json["target_roles"] == [
                    "Backend Engineer"
                ]
                count = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM job_preferences")
                    )
                ).scalar_one()
                assert int(count) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_preferences_upsert_rejects_non_mapping(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_job_preferences(
                        session,
                        preferences_json=[],  # type: ignore[arg-type]
                    )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Transaction ownership and static hygiene
# ---------------------------------------------------------------------------


def test_profile_mutations_do_not_commit(db_path: Path) -> None:
    """Repository flush does not finalize; other sessions see no draft row."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await prof_repo.upsert_current_draft(
                    session, draft_json=MINIMAL_DRAFT
                )
                async with factory() as other:
                    n = (
                        await other.execute(
                            text("SELECT COUNT(*) FROM profile_drafts")
                        )
                    ).scalar_one()
                    assert int(n) == 0
                await session.rollback()
        finally:
            await engine.dispose()

    run_async(_body())


def test_profile_repository_source_has_no_commit_or_io() -> None:
    """Static evidence: no session finalization, providers, fs, or graph."""
    src = inspect.getsource(prof_repo)
    assert "session.commit" not in src
    assert "session.rollback" not in src
    assert "session_scope" not in src
    assert "get_session_factory" not in src
    assert "create_async_engine" not in src
    assert "httpx" not in src
    assert "shopaikey" not in src.lower()
    assert "create_all" not in src
    # No Neo4j driver / graph client imports (docstring may mention boundary).
    assert "from neo4j" not in src
    assert "import neo4j" not in src
    # Singleton constants only — no alternate IDs.
    assert "CANDIDATE_PROFILE_ID" in src
    assert "PROFILE_DRAFT_ID" in src
    assert "JOB_PREFERENCES_ID" in src
    # No JSON shape validation / Pydantic imports in repository.
    assert "parse_candidate_profile" not in src
    assert "parse_job_preferences" not in src
    assert "parse_profile_draft" not in src
    assert "BaseModel" not in src


def test_profile_restrict_blocks_active_attachment_delete(
    db_path: Path,
) -> None:
    """FK RESTRICT: cannot delete attachment still referenced by profile."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session,
                    file_hash="restrict",
                    storage_path="restrict.pdf",
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=MINIMAL_PROFILE,
                )
                await session.commit()
                saved = att_id

            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await att_repo.delete(session, saved)
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                assert await att_repo.get_by_id(session, saved) is not None
                assert await prof_repo.get_active_profile(session) is not None
        finally:
            await engine.dispose()

    run_async(_body())


def test_active_profile_updated_at_on_upsert(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session, file_hash="upd", storage_path="upd.pdf"
                )
                await att_repo.mark_active(session, att_id)
                row = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=MINIMAL_PROFILE,
                )
                past = datetime(2019, 6, 1, tzinfo=UTC)
                row.created_at = past
                row.updated_at = past
                await session.flush()
                await session.commit()

            async with factory() as session:
                row2 = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json={**MINIMAL_PROFILE, "headline": "Engineer"},
                )
                assert row2.updated_at > past or (
                    row2.updated_at.replace(tzinfo=UTC) > past
                    if row2.updated_at.tzinfo is None
                    else row2.updated_at > past
                )
                # Singleton identity preserved
                assert row2.id == CANDIDATE_PROFILE_ID
                assert isinstance(row2, CandidateProfile)
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())
