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


# ---------------------------------------------------------------------------
# 02B: validated draft proposal from staged CV (fake provider)
# ---------------------------------------------------------------------------


def _cv_fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "cv" / name


def _skills_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"


def _fake_valid_extracted() -> Any:
    from app.services.profile_extraction import ExtractedCandidateProfile

    return ExtractedCandidateProfile.model_validate(
        {
            "summary": "Integration-test backend engineer.",
            "current_title": "Backend Engineer",
            "total_experience_years": 4.0,
            "skills": [
                {
                    "name": "Python",
                    "confidence": 0.91,
                    "proficiency": "advanced",
                    "years": 4.0,
                    "evidence": ["Python on backend"],
                }
            ],
            "experiences": [
                {
                    "title": "Engineer",
                    "company": "Co",
                    "start_date_text": "2020",
                    "end_date_text": "present",
                    "summary": "APIs",
                }
            ],
            "education": [
                {
                    "institution": "U",
                    "degree": "BSc",
                    "field": "CS",
                    "graduation_year": 2019,
                }
            ],
            "languages": [{"name": "English", "proficiency": "fluent"}],
            "extraction_confidence": 0.8,
        }
    )


class _ScriptedInvoker:
    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self.calls = 0

    def invoke_structured(
        self, messages: Any, *, is_repair: bool = False
    ) -> Any:
        del messages, is_repair
        self.calls += 1
        if not self._items:
            raise RuntimeError("script exhausted")
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def test_propose_from_cv_creates_validated_draft_and_replaces_prior(
    db_path: Path, tmp_path: Path
) -> None:
    """New staged CV → validated draft_json; prior unreferenced staged removed."""
    from app.core.ids import new_uuid
    from app.services.profile_drafts import propose_profile_from_cv
    from app.services.profile_extraction import build_draft_from_extracted
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    invoker = _ScriptedInvoker([_fake_valid_extracted()])
    pdf = _cv_fixture("digital_cv_01.pdf")
    old_draft = build_draft_from_extracted(
        _fake_valid_extracted(), normalizer
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = storage.write_bytes(old_id, pdf.read_bytes())
            new_rel = storage.write_bytes(new_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="int-old",
                    original_name="old.pdf",
                    size_bytes=10,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.create_staged(
                    session,
                    file_hash="int-new",
                    original_name="new.pdf",
                    size_bytes=10,
                    storage_path=new_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=old_draft.model_dump(mode="json"),
                    source_attachment_id=old_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=new_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["draft_id"] == PROFILE_DRAFT_ID
            assert invoker.calls == 1

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id == new_id
                # Full ProfileDraftPayload shape (not repository opaque MINIMAL_DRAFT).
                assert "candidate_profile" in draft.draft_json
                assert "job_preferences" in draft.draft_json
                assert draft.draft_json["job_preferences"]["target_roles"] == []
                assert await att_repo.get_by_id(session, old_id) is None
                # No active profile mutation.
                assert await prof_repo.get_active_profile(session) is None
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is not None
                assert prefs.preferences_json["target_roles"] == []
            assert not storage.exists(old_rel)
            assert storage.exists(new_rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_from_cv_no_text_marks_failed_retains_file(
    db_path: Path, tmp_path: Path
) -> None:
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_FAILED
    from app.services.pdf_extraction import NO_EXTRACTABLE_TEXT
    from app.services.profile_drafts import propose_profile_from_cv
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    invoker = _ScriptedInvoker([])
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    pdf = _cv_fixture("image_only_cv.pdf")

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="int-img",
                    original_name="img.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == NO_EXTRACTABLE_TEXT
            async with factory() as session:
                row = await att_repo.get_by_id(session, att_id)
                assert row is not None
                assert row.state == ATTACHMENT_STATE_FAILED
                assert row.failure_code == NO_EXTRACTABLE_TEXT
                assert await prof_repo.get_current_draft(session) is None
            assert storage.exists(rel)
            assert invoker.calls == 0
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# 02C: correction-preserving propose_profile_update
# ---------------------------------------------------------------------------


def _valid_profile_json() -> dict[str, Any]:
    return {
        "summary": "Backend engineer",
        "current_title": "Backend Engineer",
        "total_experience_years": 4.0,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": ["python3"],
                    "category": "language",
                },
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 4.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["Python backend work"],
            }
        ],
        "experiences": [
            {
                "title": "Engineer",
                "company": "Co",
                "start_date_text": "2020",
                "end_date_text": "present",
                "summary": "APIs",
            }
        ],
        "education": [
            {
                "institution": "U",
                "degree": "BSc",
                "field": "CS",
                "graduation_year": 2019,
            }
        ],
        "languages": [{"name": "English", "proficiency": "fluent"}],
        "extraction_confidence": 0.8,
    }


def _valid_draft_json(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate_profile": _valid_profile_json(),
        "job_preferences": {k: [] for k in JOB_PREFERENCE_KEYS},
    }
    base.update(overrides)
    return base


def test_propose_update_current_draft_profile_and_skills(
    db_path: Path,
) -> None:
    """Current-draft update: profile field + skill correction; draft-only write."""
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session, file_hash="upd-draft", storage_path="upd-draft.pdf"
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=_valid_draft_json(),
                    source_attachment_id=att_id,
                )
                await session.commit()
                saved_att = att_id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                profile_changes={"current_title": "Senior Backend Engineer"},
                skill_corrections=[
                    {
                        "name": "Python",
                        "excluded": True,
                        "evidence": ["User asked to exclude Python"],
                    }
                ],
            )
            assert result.tool_result.ok is True
            assert result.base_kind == "current_draft"
            assert result.source_attachment_id == saved_att
            assert result.draft is not None
            assert result.draft.candidate_profile.current_title == (
                "Senior Backend Engineer"
            )
            py = next(
                s
                for s in result.draft.candidate_profile.skills
                if s.skill.canonical_key == "python"
            )
            assert py.excluded is True
            assert py.source == "user_correction"

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id == saved_att
                assert (
                    draft.draft_json["candidate_profile"]["current_title"]
                    == "Senior Backend Engineer"
                )
                skills = draft.draft_json["candidate_profile"]["skills"]
                assert skills[0]["excluded"] is True
                assert skills[0]["source"] == "user_correction"
                # Active singletons untouched.
                assert await prof_repo.get_active_profile(session) is None
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is not None
                assert prefs.preferences_json["target_roles"] == []
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_active_context_copy(
    db_path: Path,
) -> None:
    """No draft: copy approved profile/preferences into a new current draft."""
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session, file_hash="upd-active", storage_path="upd-active.pdf"
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_valid_profile_json(),
                )
                await session.commit()
                saved_att = att_id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                profile_changes={"summary": "Corrected summary from chat"},
            )
            assert result.tool_result.ok is True
            assert result.base_kind == "active_context"
            assert result.source_attachment_id is None
            assert result.draft is not None
            assert result.draft.candidate_profile.summary == (
                "Corrected summary from chat"
            )

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id is None
                assert (
                    draft.draft_json["candidate_profile"]["summary"]
                    == "Corrected summary from chat"
                )
                # Active profile unchanged.
                active = await prof_repo.get_active_profile(session)
                assert active is not None
                assert active.profile_json["summary"] == "Backend engineer"
                assert active.active_attachment_id == saved_att
                row = await att_repo.get_by_id(session, saved_att)
                assert row is not None
                assert row.state == ATTACHMENT_STATE_ACTIVE
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_preference_only_null_source(
    db_path: Path,
) -> None:
    """Preference-only update from active context uses null source attachment."""
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _staged_attachment(
                    session, file_hash="upd-pref", storage_path="upd-pref.pdf"
                )
                await att_repo.mark_active(session, att_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_valid_profile_json(),
                )
                await session.commit()

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                preference_changes={
                    "target_roles": ["Platform Engineer"],
                    "preferred_locations": ["Berlin"],
                    "acceptable_work_modes": ["remote"],
                    "target_seniority": ["senior"],
                },
            )
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["preference_only"] is True
            assert result.source_attachment_id is None
            assert result.draft is not None
            assert result.draft.job_preferences.target_roles == [
                "Platform Engineer"
            ]
            # Profile facts unchanged from active copy.
            assert result.draft.candidate_profile.summary == "Backend engineer"

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id is None
                assert draft.draft_json["job_preferences"]["target_roles"] == [
                    "Platform Engineer"
                ]
                # Active preferences still empty until approval.
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is not None
                assert prefs.preferences_json["target_roles"] == []
                active = await prof_repo.get_active_profile(session)
                assert active is not None
                assert active.profile_json["summary"] == "Backend engineer"
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_exclusions_survive_repeated_updates(
    db_path: Path,
) -> None:
    """Excluded user_correction skills remain after a later unrelated update."""
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=_valid_draft_json(),
                    source_attachment_id=None,
                )
                await session.commit()

            first = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                skill_corrections=[
                    {
                        "name": "Python",
                        "excluded": True,
                        "evidence": ["exclude python"],
                    }
                ],
            )
            assert first.tool_result.ok is True

            second = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                profile_changes={"current_title": "Staff Engineer"},
            )
            assert second.tool_result.ok is True
            assert second.draft is not None
            py = next(
                s
                for s in second.draft.candidate_profile.skills
                if s.skill.canonical_key == "python"
            )
            assert py.excluded is True
            assert py.source == "user_correction"
            assert second.draft.candidate_profile.current_title == "Staff Engineer"

            # Explicit re-include is allowed.
            third = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                skill_corrections=[
                    {
                        "name": "Python",
                        "excluded": False,
                        "evidence": ["user re-added python"],
                    }
                ],
            )
            assert third.tool_result.ok is True
            assert third.draft is not None
            py2 = next(
                s
                for s in third.draft.candidate_profile.skills
                if s.skill.canonical_key == "python"
            )
            assert py2.excluded is False
            assert py2.source == "user_correction"
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_invalid_payload_leaves_prior_unchanged(
    db_path: Path,
) -> None:
    """Invalid/partial changes fail without mutating draft or active truth."""
    from app.services.profile_drafts import (
        ERROR_INVALID_PROFILE_UPDATE,
        propose_profile_update,
    )
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())
    prior = _valid_draft_json()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=prior,
                    source_attachment_id=None,
                )
                await session.commit()

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                profile_changes={"extraction_confidence": 2.5},  # out of [0,1]
            )
            assert result.tool_result.ok is False
            assert result.tool_result.code == ERROR_INVALID_PROFILE_UPDATE

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.draft_json == prior
                assert await prof_repo.get_active_profile(session) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_empty_and_no_context_fail(
    db_path: Path,
) -> None:
    from app.services.profile_drafts import (
        ERROR_EMPTY_UPDATE,
        ERROR_NO_PROFILE_CONTEXT,
        propose_profile_update,
    )
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            empty = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
            )
            assert empty.tool_result.ok is False
            assert empty.tool_result.code == ERROR_EMPTY_UPDATE

            missing = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                profile_changes={"summary": "x"},
            )
            assert missing.tool_result.ok is False
            assert missing.tool_result.code == ERROR_NO_PROFILE_CONTEXT
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_tool_compact_and_no_preference_tool() -> None:
    """Tool factory returns compact ToolResult; no separate preference tool."""
    import inspect

    from app.tools import profile as profile_tools
    from app.tools.registry import production_registry

    src = inspect.getsource(profile_tools)
    assert "PROPOSE_PROFILE_UPDATE_NAME" in src
    assert "propose_profile_update" in src
    assert "build_propose_profile_update_tool" in src
    # Single update tool covers preferences — no standalone preference tool.
    assert "propose_preferences" not in src
    assert "update_preferences" not in src
    assert "preference_tool" not in src
    assert production_registry().is_empty()
    names = production_registry().tool_names()
    assert "propose_profile_update" not in names
