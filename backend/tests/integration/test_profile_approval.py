"""Integration tests for profile-family repository primitives (pre-service).

Uses a migrated temporary SQLite file (Alembic head). Covers singleton
active/draft/preferences reads, upserts, deletes, UTC timestamps, missing
rows, and constraint-visible failures. Full approval transaction ordering and
API routes remain later service tasks.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.models.profiles import (
    JOB_PREFERENCE_KEYS,
    PROFILE_DRAFT_ID,
    Profile,
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
    """Compatibility upsert creates one durable selected profile and reuses it."""

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
                created_id = created.id
                assert created_id != "active"
                assert created.active_attachment_id == att_id
                assert created.profile_json["full_name"] == "Test User"
                assert created.updated_at.tzinfo is not None
                await session.commit()

            async with factory() as session:
                found = await prof_repo.get_active_profile(session)
                assert found is not None
                assert found.id == created_id

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
                assert updated.id == created_id
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
                        text("SELECT COUNT(*) FROM profiles")
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


def test_compatibility_upsert_never_promotes_selected_pending_profile(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_id = await _staged_attachment(session)
                pending = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="pending.pdf",
                )
                from app.repositories import workspace_state as workspace_repo

                await workspace_repo.set_active_profile_id(session, pending.id)
                with pytest.raises(ProfileRepositoryError):
                    await prof_repo.upsert_active_profile(
                        session,
                        active_attachment_id=attachment_id,
                        profile_json=MINIMAL_PROFILE,
                    )
                selected = await prof_repo.get_active_profile(session)
                assert selected is not None
                assert selected.id == pending.id
                assert selected.state == "pending"
                assert selected.profile_json is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_profile_fk_and_attachment_uniqueness_visible(db_path: Path) -> None:
    """Missing attachment FK and duplicate attachment ownership are rejected."""

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
                await prof_repo.create_profile(
                    session,
                    attachment_id=att_id,
                    display_name="First",
                    profile_json=MINIMAL_PROFILE,
                    location=None,
                    extraction_version="test-v1",
                    source_hash="source-1",
                )
                with pytest.raises(IntegrityError):
                    await prof_repo.create_profile(
                        session,
                        attachment_id=att_id,
                        display_name="Duplicate",
                        profile_json=MINIMAL_PROFILE,
                        location=None,
                        extraction_version="test-v1",
                        source_hash="source-2",
                    )
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
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                draft_id = draft.id
                assert draft_id != PROFILE_DRAFT_ID
                assert draft.source_attachment_id == att_id
                assert draft.draft_json["profile"]["full_name"] == "Test User"
                await session.commit()

            async with factory() as session:
                found = await prof_repo.get_current_draft(session)
                assert found is not None
                assert found.id == draft_id

                # Preference-only style: clear source attachment.
                updated = await prof_repo.upsert_current_draft(
                    session,
                    draft_json={**MINIMAL_DRAFT, "note": "ignored-by-shape"},
                    source_attachment_id=None,
                )
                assert updated.id == draft_id
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
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
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


def test_job_preferences_are_profile_owned_and_upserted(db_path: Path) -> None:
    """Preferences are absent without a profile and keyed to the selected row."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is None
                att_id = await _staged_attachment(
                    session, file_hash="prefs", storage_path="prefs.pdf"
                )
                await att_repo.mark_active(session, att_id)
                profile = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=MINIMAL_PROFILE,
                )
                await session.commit()

            async with factory() as session:
                past = datetime(2020, 1, 1, tzinfo=UTC)
                new_doc = {
                    **EMPTY_PREFS,
                    "target_roles": ["Backend Engineer"],
                }
                updated = await prof_repo.upsert_job_preferences(
                    session, preferences_json=new_doc
                )
                assert updated.profile_id == profile.id
                assert updated.preferences_json["target_roles"] == [
                    "Backend Engineer"
                ]
                updated.updated_at = past
                await session.flush()
                updated = await prof_repo.upsert_job_preferences(
                    session, preferences_json=new_doc
                )
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
                        text("SELECT COUNT(*) FROM profile_preferences")
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
    assert "create_pending_profile" in src
    assert "get_selected_ready_profile" in src
    # No JSON shape validation / Pydantic imports in repository.
    assert "parse_candidate_profile" not in src
    assert "parse_job_preferences" not in src
    assert "parse_profile_draft" not in src
    assert "BaseModel" not in src


def test_profile_restrict_blocks_active_attachment_delete(
    db_path: Path,
) -> None:
    """Active attachment delete is rejected; profile pointer remains intact.

    Repository ownership blocks ``active`` before row removal (Batch04).
    FK RESTRICT on ``candidate_profile.active_attachment_id`` remains the
    database backstop if a raw DELETE bypassed the repository guard.
    """
    from app.repositories.attachments import AttachmentRepositoryError

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
                with pytest.raises(AttachmentRepositoryError):
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
                row_id = row.id
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
                assert row2.id == row_id
                assert isinstance(row2, Profile)
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


def _fake_valid_profile() -> Any:
    from app.schemas.profile import parse_candidate_profile
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())
    return parse_candidate_profile(
        {
            "summary": "Integration-test backend engineer.",
            "current_title": "Backend Engineer",
            "total_experience_years": 4.0,
            "skills": [
                {
                    "skill": normalizer.normalize_name("Python").model_dump(
                        mode="json"
                    ),
                    "confidence": 0.91,
                    "proficiency": "advanced",
                    "years": 4.0,
                    "source": "cv",
                    "excluded": False,
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


class _CoveringDocumentInvoker:
    """Document-first invoker covering ordinals found in prompts."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke_structured(
        self,
        messages: Any,
        *,
        schema_name: str,
        is_repair: bool = False,
    ) -> Any:
        del is_repair
        from app.services.cv_document_extraction import (
            ExtractedBatchDocument,
            ExtractedConsolidation,
            ExtractedEntryFragment,
            ExtractedSectionFragment,
        )

        self.calls += 1
        joined = "\n".join(
            getattr(m, "content", "")
            for m in list(messages)
            if isinstance(getattr(m, "content", None), str)
        )
        if schema_name == "candidate_skills":
            entry_match = re.search(
                r'"entry_id":"([^"]+)"[^}]*Python',
                joined,
                re.DOTALL,
            )
            assert entry_match is not None
            return {
                "assertions": [
                    {
                        "name": "Python",
                        "confidence": 0.9,
                        "proficiency": "advanced",
                        "years": None,
                        "evidence": ["Python"],
                        "source_entry_ids": [entry_match.group(1)],
                    }
                ]
            }
        ordinals = sorted(
            {int(m) for m in re.findall(r"\[ordinal=(\d+)\]", joined)}
        ) or [0]
        first = ordinals[0]
        sections = [
            ExtractedSectionFragment(
                heading="Summary",
                kind="summary",
                entries=[
                    ExtractedEntryFragment(
                        title="Backend Engineer",
                        subtitle=None,
                        date_text=None,
                        location=None,
                        body="Integration-test backend engineer.",
                        bullets=[],
                        attributes=[],
                        source_chunk_ordinals=[first],
                    )
                ],
                source_chunk_ordinals=[first],
            ),
            ExtractedSectionFragment(
                heading="Skills",
                kind="skills",
                entries=[
                    ExtractedEntryFragment(
                        title=None,
                        subtitle=None,
                        date_text=None,
                        location=None,
                        body="Python",
                        bullets=["Python"],
                        attributes=[],
                        source_chunk_ordinals=ordinals,
                    )
                ],
                source_chunk_ordinals=ordinals,
            ),
        ]
        if schema_name == "batch":
            return ExtractedBatchDocument(
                contacts=[],
                detected_languages=["en"],
                sections=sections,
                extraction_warnings=[],
                extraction_confidence=0.8,
            )
        return ExtractedConsolidation(
            detected_languages=["en"],
            sections=sections,
            extraction_warnings=[],
            extraction_confidence=0.8,
        )


def test_propose_from_cv_creates_validated_draft_and_replaces_prior(
    db_path: Path, tmp_path: Path
) -> None:
    """New staged CV → validated draft pair + chunks; prior staged removed."""
    from app.core.ids import new_uuid
    from app.repositories import attachment_text_chunks as chunk_repo
    from app.repositories import cv_documents as cv_doc_repo
    from app.services.profile_drafts import propose_profile_from_cv
    from app.services.profile_extraction import build_draft_from_candidate_profile
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    invoker = _CoveringDocumentInvoker()
    pdf = _cv_fixture("digital_cv_01.pdf")
    old_draft = build_draft_from_candidate_profile(_fake_valid_profile())

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
                pending = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=new_id,
                    display_name="new.pdf",
                )
                pending_id = pending.id
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=old_draft.model_dump(mode="json"),
                    source_attachment_id=old_id,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=old_id,
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=new_id,
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
                target_profile_id=pending_id,
            )
            assert result.tool_result.ok is True
            assert result.tool_result.data is not None
            assert result.tool_result.data["draft_id"] == PROFILE_DRAFT_ID
            assert result.tool_result.data["source_hash"]
            assert invoker.calls >= 1

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id == new_id
                assert draft.target_profile_id == pending_id
                # Full ProfileDraftPayload shape (not repository opaque MINIMAL_DRAFT).
                assert "candidate_profile" in draft.draft_json
                assert "job_preferences" in draft.draft_json
                assert draft.draft_json["job_preferences"]["target_roles"] == []
                doc_draft = await cv_doc_repo.get_draft(session, new_id)
                assert doc_draft is not None
                assert doc_draft.source_hash == result.tool_result.data["source_hash"]
                assert doc_draft.document_json["attachment_id"] == new_id
                assert await chunk_repo.count_for_attachment(session, new_id) > 0
                assert await att_repo.get_by_id(session, old_id) is None
                # No active profile mutation.
                assert await prof_repo.get_active_profile(session) is None
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is None
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
    from app.repositories import attachment_text_chunks as chunk_repo
    from app.repositories import cv_documents as cv_doc_repo
    from app.services.pdf_extraction import NO_EXTRACTABLE_TEXT
    from app.services.profile_drafts import propose_profile_from_cv
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    invoker = _CoveringDocumentInvoker()
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
                owner = await prof_repo.create_pending_profile(
                    session, attachment_id=att_id, display_name="img.pdf"
                )
                await session.commit()

            result = await propose_profile_from_cv(
                attachment_id=att_id,
                target_profile_id=owner.id,
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
                assert await cv_doc_repo.get_draft(session, att_id) is None
                assert await chunk_repo.count_for_attachment(session, att_id) == 0
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
                owner = await prof_repo.create_pending_profile(
                    session, attachment_id=att_id, display_name="upd-draft.pdf"
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=_valid_draft_json(),
                    source_attachment_id=att_id,
                    target_profile_id=owner.id,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()
                saved_att = att_id
                owner_id = owner.id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=owner_id,
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
                # Approved rows remain absent while only a draft exists.
                assert await prof_repo.get_active_profile(session) is None
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_propose_update_rejects_current_draft_owned_by_another_profile(
    db_path: Path,
) -> None:
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer

    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                other_attachment_id = await _staged_attachment(
                    session,
                    file_hash="upd-other-owner",
                    storage_path="upd-other-owner.pdf",
                )
                await att_repo.mark_active(session, other_attachment_id)
                await att_repo.mark_archived(session, other_attachment_id)
                expected_owner = await prof_repo.create_profile(
                    session,
                    attachment_id=other_attachment_id,
                    display_name="Other owner",
                    profile_json=_valid_profile_json(),
                    location=None,
                    extraction_version="existing-v1",
                    source_hash="other-owner-source",
                )
                draft_attachment_id = await _staged_attachment(
                    session,
                    file_hash="upd-draft-owner",
                    storage_path="upd-draft-owner.pdf",
                )
                draft_owner = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=draft_attachment_id,
                    display_name="Draft owner",
                )
                original = _valid_draft_json()
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=original,
                    source_attachment_id=draft_attachment_id,
                    target_profile_id=draft_owner.id,
                )
                await session.commit()

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=expected_owner.id,
                profile_changes={"summary": "must not cross profile ownership"},
            )

            assert result.tool_result.ok is False
            assert result.tool_result.code == "PROFILE_INCONSISTENT"
            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.target_profile_id == draft_owner.id
                assert draft.draft_json == original
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
                approved_profile = _valid_profile_json()
                approved_profile.update(
                    {
                        "phone": "+1 (202) 555-0147",
                        "email": "approved@example.test",
                        "github_url": "https://github.com/approved-user",
                    }
                )
                profile = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=approved_profile,
                )
                await session.commit()
                saved_att = att_id
                owner_id = profile.id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=owner_id,
                profile_changes={
                    "summary": "Corrected summary from chat",
                    "phone": "+1 303 555 0199",
                    "email": "DRAFT@Example.TEST",
                    "github_url": "https://www.github.com/draft-user/",
                },
            )
            assert result.tool_result.ok is True
            assert result.base_kind == "active_context"
            assert result.source_attachment_id is None
            assert result.draft is not None
            assert result.draft.candidate_profile.summary == (
                "Corrected summary from chat"
            )
            assert result.draft.candidate_profile.phone == "+13035550199"
            assert result.draft.candidate_profile.email == "draft@example.test"
            assert (
                result.draft.candidate_profile.github_url
                == "https://github.com/draft-user"
            )

            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id is None
                assert draft.target_profile_id == owner_id
                assert (
                    draft.draft_json["candidate_profile"]["summary"]
                    == "Corrected summary from chat"
                )
                # Active profile unchanged.
                active = await prof_repo.get_active_profile(session)
                assert active is not None
                assert active.profile_json["summary"] == "Backend engineer"
                assert active.profile_json["phone"] == "+1 (202) 555-0147"
                assert active.profile_json["email"] == "approved@example.test"
                assert (
                    active.profile_json["github_url"]
                    == "https://github.com/approved-user"
                )
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
                profile = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=_valid_profile_json(),
                )
                await session.commit()
                owner_id = profile.id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=owner_id,
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
                # Preferences remain absent until approval creates them.
                prefs = await prof_repo.get_job_preferences(session)
                assert prefs is None
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
                att_id = await _staged_attachment(
                    session, file_hash="upd-repeat", storage_path="upd-repeat.pdf"
                )
                owner = await prof_repo.create_pending_profile(
                    session, attachment_id=att_id, display_name="upd-repeat.pdf"
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=_valid_draft_json(),
                    source_attachment_id=None,
                    target_profile_id=owner.id,
                )
                await session.commit()
                owner_id = owner.id

            first = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=owner_id,
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
                expected_profile_id=owner_id,
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
                expected_profile_id=owner_id,
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
                att_id = await _staged_attachment(
                    session, file_hash="upd-invalid", storage_path="upd-invalid.pdf"
                )
                owner = await prof_repo.create_pending_profile(
                    session, attachment_id=att_id, display_name="upd-invalid.pdf"
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=prior,
                    source_attachment_id=None,
                    target_profile_id=owner.id,
                )
                await session.commit()
                owner_id = owner.id

            result = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=owner_id,
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
    from app.core.ids import new_uuid
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
                expected_profile_id=new_uuid(),
            )
            assert empty.tool_result.ok is False
            assert empty.tool_result.code == ERROR_EMPTY_UPDATE

            missing = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=new_uuid(),
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
    names = production_registry().tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
    assert "propose_profile_update" in names

# ---------------------------------------------------------------------------
# 03A: constraint-safe approval transaction + post-commit sync
# ---------------------------------------------------------------------------


class _RecordingSyncDriver:
    """Minimal async driver stand-in; records whether sync ran."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.runs = 0
        self.queries: list[str] = []

    def session(self, **config: object) -> _RecordingSession:
        del config
        return _RecordingSession(self)


class _RecordingSession:
    def __init__(self, driver: _RecordingSyncDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def run(
        self, query: str, parameters: object = None, **kwargs: object
    ) -> _EmptyResult:
        del parameters, kwargs
        self._driver.runs += 1
        self._driver.queries.append(query)
        if self._driver.fail:
            raise OSError("neo4j fail")
        return _EmptyResult()


class _EmptyResult:
    async def consume(self) -> None:
        return None


def _approval_valid_profile_json(
    *, exclude_python: bool = False
) -> dict[str, Any]:
    skills: list[dict[str, Any]] = [
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
            "source": "cv" if not exclude_python else "user_correction",
            "excluded": exclude_python,
            "evidence": ["Python backend"],
        },
        {
            "skill": {
                "canonical_key": "fastapi",
                "display_name": "FastAPI",
                "aliases": ["fast api"],
                "category": "framework",
            },
            "confidence": 0.85,
            "proficiency": "advanced",
            "years": 3.0,
            "source": "cv",
            "excluded": False,
            "evidence": ["FastAPI services"],
        },
    ]
    return {
        "summary": "Backend engineer",
        "current_title": "Backend Engineer",
        "total_experience_years": 4.0,
        "skills": skills,
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


def _approval_draft_json(
    *,
    prefs: dict[str, Any] | None = None,
    exclude_python: bool = False,
) -> dict[str, Any]:
    from app.db.models.profiles import JOB_PREFERENCE_KEYS

    return {
        "candidate_profile": _approval_valid_profile_json(
            exclude_python=exclude_python
        ),
        "job_preferences": prefs
        if prefs is not None
        else {k: [] for k in JOB_PREFERENCE_KEYS},
    }


def _write_pdf(storage: Any, attachment_id: str) -> str:
    # Minimal non-empty PDF-ish bytes; storage only cares about presence.
    return storage.write_bytes(attachment_id, b"%PDF-1.4 approval-test\n%%EOF\n")


async def _seed_cv_document_draft(
    session: Any,
    *,
    attachment_id: str,
    profile_json: dict[str, Any] | None = None,
    chunk_text: str = "approval coupling chunk text",
) -> str:
    """Seed document draft + matching chunks for CV-backed approval preflight."""
    from app.repositories import attachment_text_chunks as chunk_repo
    from app.repositories import cv_documents as cv_doc_repo
    from app.repositories.attachment_text_chunks import build_chunk_write
    from app.services.profile_extraction import (
        CanonicalChunk,
        compute_canonical_source_hash,
    )

    chunks = (CanonicalChunk(ordinal=0, text=chunk_text),)
    source_hash = compute_canonical_source_hash(chunks)
    profile = (
        profile_json
        if profile_json is not None
        else _approval_valid_profile_json()
    )
    await cv_doc_repo.upsert_draft(
        session,
        attachment_id=attachment_id,
        document_json={
            "attachment_id": attachment_id,
            "detected_languages": ["en"],
            "sections": [],
            "extraction_warnings": [],
            "extraction_confidence": 0.8,
        },
        profile_json=profile,
        outline_json={"sections": []},
        extraction_version="test-v1",
        source_hash=source_hash,
    )
    await chunk_repo.replace_for_attachment(
        session,
        attachment_id,
        [build_chunk_write(0, chunk_text)],
    )
    return source_hash


async def _seed_pending_profile_draft_owner(
    session: Any,
    *,
    attachment_id: str,
    draft_json: dict[str, Any],
    select_workspace: bool = True,
) -> tuple[str, str]:
    from app.repositories import conversations as conversations_repo
    from app.repositories import workspace_state as workspace_repo

    pending = await prof_repo.create_pending_profile(
        session,
        attachment_id=attachment_id,
        display_name="cv.pdf",
    )
    conversation = await conversations_repo.create_bootstrap_for_profile(
        session, profile_id=pending.id
    )
    if select_workspace:
        await workspace_repo.set_active_profile_id(session, pending.id)
    await prof_repo.upsert_current_draft(
        session,
        draft_json=draft_json,
        source_attachment_id=attachment_id,
        target_profile_id=pending.id,
    )
    return pending.id, conversation.id


async def _seed_ready_profile_conversation(
    session: Any,
    *,
    attachment_id: str,
) -> tuple[str, str]:
    from app.repositories import conversations as conversations_repo

    await att_repo.mark_active(session, attachment_id)
    profile = await prof_repo.upsert_active_profile(
        session,
        active_attachment_id=attachment_id,
        profile_json=_approval_valid_profile_json(),
    )
    await prof_repo.upsert_job_preferences(
        session,
        preferences_json={key: [] for key in JOB_PREFERENCE_KEYS},
    )
    conversation = await conversations_repo.create_for_profile(
        session, profile_id=profile.id
    )
    return profile.id, conversation.id


def test_first_approval_promotes_pending_profile_and_preserves_bootstrap_chat(
    db_path: Path, tmp_path: Path
) -> None:
    """One extraction feeds approval; approval adds no provider work."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.repositories import conversations as conversations_repo
    from app.repositories import workspace_state as workspace_repo
    from app.services.profile_approval import commit_approved_draft
    from app.services.profile_drafts import (
        propose_profile_from_cv,
        propose_profile_update,
    )
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()
    pdf = _cv_fixture("digital_cv_01.pdf")

    class _IdentityDocumentInvoker(_CoveringDocumentInvoker):
        def invoke_structured(
            self,
            messages: Any,
            *,
            schema_name: str,
            is_repair: bool = False,
        ) -> Any:
            result = super().invoke_structured(
                messages,
                schema_name=schema_name,
                is_repair=is_repair,
            )
            if hasattr(result, "model_copy"):
                return result.model_copy(update={"full_name": "Ava Synthetic"})
            return result

    invoker = _IdentityDocumentInvoker()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            prefs = {
                "target_roles": ["Backend Engineer"],
                "preferred_locations": ["Berlin"],
                "acceptable_work_modes": ["remote"],
                "target_seniority": ["senior"],
            }
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="first-appr",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                pending = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=att_id,
                    display_name="cv.pdf",
                )
                bootstrap = await conversations_repo.create_bootstrap_for_profile(
                    session, profile_id=pending.id
                )
                await workspace_repo.set_active_profile_id(session, pending.id)
                pending_id = pending.id
                conversation_id = bootstrap.id
                await session.commit()

            proposed = await propose_profile_from_cv(
                attachment_id=att_id,
                target_profile_id=pending_id,
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                invoker=invoker,
            )
            assert proposed.tool_result.ok is True
            assert invoker.calls > 0
            provider_calls_after_extraction = invoker.calls
            corrected = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=pending_id,
                preference_changes=prefs,
            )
            assert corrected.tool_result.ok is True

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=pending_id,
            )
            assert result.ok is True
            assert result.sqlite_committed is True
            assert result.sync_ok is True
            assert result.cleanup_ok is True
            assert result.active_attachment_id == att_id
            assert result.previous_attachment_id is None
            assert result.preferences_updated is True
            assert result.profile_id == pending_id
            assert result.conversation_id == conversation_id
            assert result.code is None
            assert invoker.calls == provider_calls_after_extraction
            assert driver.runs >= 1
            joined = "\n".join(driver.queries)
            assert "MERGE (c:Candidate {profile_id: $profile_id})" in joined
            assert "MERGE (cv:CV {id: $cv_id})" in joined
            assert "PROJECTS_TO" in joined

            async with factory() as session:
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.id == pending_id
                assert profile.state == "ready"
                assert profile.display_name == "Ava Synthetic"
                assert profile.active_attachment_id == att_id
                assert await prof_repo.get_current_draft(session) is None
                att = await att_repo.get_by_id(session, att_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE
                jp = await prof_repo.get_job_preferences(session)
                assert jp is not None
                assert jp.preferences_json["target_roles"] == ["Backend Engineer"]
                assert int(
                    (
                        await session.execute(
                            text("SELECT COUNT(*) FROM attachments")
                        )
                    ).scalar_one()
                ) == 1
                assert int(
                    (
                        await session.execute(text("SELECT COUNT(*) FROM profiles"))
                    ).scalar_one()
                ) == 1
                assert int(
                    (
                        await session.execute(
                            text("SELECT COUNT(*) FROM conversations")
                        )
                    ).scalar_one()
                ) == 1
            assert storage.exists(rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_approved_profile_persists_across_engine_restart(
    db_path: Path, tmp_path: Path
) -> None:
    """Restart persistence: approved profile, prefs, active CV survive reopen.

    Simulates process stop by disposing the engine, then reopening the same
    SQLite file and FILES_DIR path. User corrections in approved JSON remain.
    """
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.repositories import conversations as conversations_repo
    from app.repositories import workspace_state as workspace_repo
    from app.services.profile_approval import commit_approved_draft
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    files_dir = tmp_path / "files"
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()
    prefs = {
        "target_roles": ["Platform Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["senior"],
    }

    async def _approve() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="restart-appr",
                    original_name="cv-restart.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                pending = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=att_id,
                    display_name="cv-restart.pdf",
                )
                await conversations_repo.create_bootstrap_for_profile(
                    session, profile_id=pending.id
                )
                await workspace_repo.set_active_profile_id(session, pending.id)
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json=_approval_draft_json(
                        prefs=prefs, exclude_python=True
                    ),
                    source_attachment_id=att_id,
                    target_profile_id=pending.id,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=pending.id,
            )
            assert result.ok is True
            assert result.sqlite_committed is True
            assert result.active_attachment_id == att_id
            return att_id, pending.id
        finally:
            await engine.dispose()

    att_id, profile_id = run_async(_approve())
    assert storage.exists(att_id)

    async def _reopen_and_assert() -> None:
        # Fresh engine on the same durable path (no remigration).
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.id == profile_id
                assert profile.active_attachment_id == att_id
                assert profile.profile_json["summary"] == "Backend engineer"
                skills = profile.profile_json["skills"]
                py = next(
                    s
                    for s in skills
                    if s["skill"]["canonical_key"] == "python"
                )
                assert py["excluded"] is True
                assert py["source"] == "user_correction"

                att = await att_repo.get_by_id(session, att_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE
                assert att.original_name == "cv-restart.pdf"
                active = await att_repo.get_active(session)
                assert active is not None
                assert active.id == att_id

                jp = await prof_repo.get_job_preferences(session)
                assert jp is not None
                assert jp.preferences_json["target_roles"] == [
                    "Platform Engineer"
                ]
                assert await prof_repo.get_current_draft(session) is None

                n = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM attachments")
                    )
                ).scalar_one()
                assert int(n) == 1
        finally:
            await engine.dispose()

    run_async(_reopen_and_assert())
    # File bytes remain under the original FILES_DIR after engine restart.
    assert storage.exists(att_id)
    assert (files_dir / att_id).is_file()


def test_replacement_archives_old_attachment_and_retains_file(
    db_path: Path, tmp_path: Path
) -> None:
    """Replacement: old attachment archived, PDF retained, one active."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import (
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
    )
    from app.repositories import attachment_text_chunks as chunk_repo
    from app.repositories.attachment_text_chunks import build_chunk_write
    from app.services.profile_approval import commit_approved_draft
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = _write_pdf(storage, old_id)
            new_rel = _write_pdf(storage, new_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="old-appr",
                    original_name="old.pdf",
                    size_bytes=40,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.mark_active(session, old_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=old_id,
                    profile_json=_approval_valid_profile_json(),
                )
                # Chunks on the soon-to-be-archived active CV must be retained.
                await chunk_repo.replace_for_attachment(
                    session,
                    old_id,
                    [build_chunk_write(0, "retained archived chunk text")],
                )
                await att_repo.create_staged(
                    session,
                    file_hash="new-appr",
                    original_name="new.pdf",
                    size_bytes=40,
                    storage_path=new_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                pending_id, _conversation_id = await _seed_pending_profile_draft_owner(
                    session,
                    attachment_id=new_id,
                    draft_json=_approval_draft_json(),
                    select_workspace=False,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=new_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=pending_id,
            )
            assert result.ok is True
            assert result.sqlite_committed is True
            assert result.previous_attachment_id == old_id
            assert result.active_attachment_id == new_id
            assert result.cleanup_ok is True
            assert result.data.get("previous_attachment_archived") is True

            async with factory() as session:
                old_att = await att_repo.get_by_id(session, old_id)
                assert old_att is not None
                assert old_att.state == ATTACHMENT_STATE_ARCHIVED
                # No restore path: archived cannot become active.
                from app.repositories.attachments import (
                    InvalidAttachmentTransitionError,
                )

                try:
                    await att_repo.mark_active(session, old_id)
                    raise AssertionError("archived must not restore to active")
                except InvalidAttachmentTransitionError:
                    pass
                new_att = await att_repo.get_by_id(session, new_id)
                assert new_att is not None
                assert new_att.state == ATTACHMENT_STATE_ACTIVE
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == new_id
                assert await prof_repo.get_current_draft(session) is None
                active_n = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM attachments "
                            "WHERE state = 'active'"
                        )
                    )
                ).scalar_one()
                assert int(active_n) == 1
                archived_chunks = await chunk_repo.list_for_attachment(
                    session, old_id
                )
                assert len(archived_chunks) == 1
                assert archived_chunks[0].text == "retained archived chunk text"
            assert storage.exists(old_rel)
            assert storage.exists(new_rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_preflight_missing_file_leaves_prior_truth(
    db_path: Path, tmp_path: Path
) -> None:
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.services.profile_approval import (
        ERROR_ATTACHMENT_FILE_MISSING,
        commit_approved_draft,
    )
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = _write_pdf(storage, old_id)
            # Row points at a path that was never written.
            missing_rel = new_id  # uuid path without file
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="old-miss",
                    original_name="old.pdf",
                    size_bytes=40,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.mark_active(session, old_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=old_id,
                    profile_json=_approval_valid_profile_json(),
                )
                await att_repo.create_staged(
                    session,
                    file_hash="new-miss",
                    original_name="new.pdf",
                    size_bytes=40,
                    storage_path=missing_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                pending_id, _conversation_id = await _seed_pending_profile_draft_owner(
                    session,
                    attachment_id=new_id,
                    draft_json=_approval_draft_json(),
                    select_workspace=False,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=new_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=pending_id,
            )
            assert result.ok is False
            assert result.sqlite_committed is False
            assert result.code == ERROR_ATTACHMENT_FILE_MISSING
            assert driver.runs == 0

            async with factory() as session:
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == old_id
                old = await att_repo.get_by_id(session, old_id)
                assert old is not None
                assert old.state == ATTACHMENT_STATE_ACTIVE
                new = await att_repo.get_by_id(session, new_id)
                assert new is not None
                assert new.state == "staged"
                assert await prof_repo.get_current_draft(session) is not None
            assert storage.exists(old_rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_transaction_failpoint_rolls_back_preserves_staged(
    db_path: Path, tmp_path: Path
) -> None:
    """before_commit failpoint: prior active intact; new stays staged; no Neo4j."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.services.profile_approval import (
        ERROR_APPROVAL_TRANSACTION_FAILED,
        commit_approved_draft,
    )
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = _write_pdf(storage, old_id)
            new_rel = _write_pdf(storage, new_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="fp-old",
                    original_name="old.pdf",
                    size_bytes=40,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.mark_active(session, old_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=old_id,
                    profile_json=_approval_valid_profile_json(),
                )
                await att_repo.create_staged(
                    session,
                    file_hash="fp-new",
                    original_name="new.pdf",
                    size_bytes=40,
                    storage_path=new_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                pending_id, _conversation_id = await _seed_pending_profile_draft_owner(
                    session,
                    attachment_id=new_id,
                    draft_json=_approval_draft_json(),
                    select_workspace=False,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=new_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                failpoint="before_commit",
                expected_profile_id=pending_id,
            )
            assert result.ok is False
            assert result.sqlite_committed is False
            assert result.code == ERROR_APPROVAL_TRANSACTION_FAILED
            assert driver.runs == 0

            async with factory() as session:
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == old_id
                old = await att_repo.get_by_id(session, old_id)
                assert old is not None
                assert old.state == ATTACHMENT_STATE_ACTIVE
                new = await att_repo.get_by_id(session, new_id)
                assert new is not None
                assert new.state == "staged"
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.source_attachment_id == new_id
            assert storage.exists(old_rel)
            assert storage.exists(new_rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_sync_failure_after_commit_keeps_sqlite_truth(
    db_path: Path, tmp_path: Path
) -> None:
    """Neo4j failure returns NEO4J_SYNC_FAILED; SQLite remains committed."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.graph.sync_candidate import NEO4J_SYNC_FAILED
    from app.services.profile_approval import commit_approved_draft
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver(fail=True)

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="sync-fail",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                pending_id, _conversation_id = await _seed_pending_profile_draft_owner(
                    session,
                    attachment_id=att_id,
                    draft_json=_approval_draft_json(exclude_python=True),
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=pending_id,
            )
            assert result.ok is False
            assert result.sqlite_committed is True
            assert result.sync_ok is False
            assert result.code == NEO4J_SYNC_FAILED
            assert "rebuild" in (result.summary or "").lower() or (
                "rebuild_instruction" in result.data
            )
            assert result.data.get("sqlite_committed") is True

            async with factory() as session:
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == att_id
                # Exclusion preserved in SQLite approved JSON.
                skills = profile.profile_json["skills"]
                py = next(
                    s for s in skills if s["skill"]["canonical_key"] == "python"
                )
                assert py["excluded"] is True
                assert await prof_repo.get_current_draft(session) is None
                att = await att_repo.get_by_id(session, att_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE
        finally:
            await engine.dispose()

    run_async(_body())


def test_cleanup_failure_reported_sqlite_valid(
    db_path: Path, tmp_path: Path
) -> None:
    """Cleanup failpoint: committed SQLite ok; cleanup_ok False; sync may pass."""
    from app.core.ids import new_uuid
    from app.services.profile_approval import commit_approved_draft
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            old_id = new_uuid()
            new_id = new_uuid()
            old_rel = _write_pdf(storage, old_id)
            new_rel = _write_pdf(storage, new_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="cl-old",
                    original_name="old.pdf",
                    size_bytes=40,
                    storage_path=old_rel,
                    page_count=1,
                    attachment_id=old_id,
                )
                await att_repo.mark_active(session, old_id)
                await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=old_id,
                    profile_json=_approval_valid_profile_json(),
                )
                await att_repo.create_staged(
                    session,
                    file_hash="cl-new",
                    original_name="new.pdf",
                    size_bytes=40,
                    storage_path=new_rel,
                    page_count=1,
                    attachment_id=new_id,
                )
                pending_id, _conversation_id = await _seed_pending_profile_draft_owner(
                    session,
                    attachment_id=new_id,
                    draft_json=_approval_draft_json(),
                    select_workspace=False,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=new_id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                failpoint="cleanup",
                expected_profile_id=pending_id,
            )
            assert result.sqlite_committed is True
            assert result.cleanup_ok is False
            assert result.sync_ok is True
            assert result.ok is True  # sync ok; cleanup failpoint is reported
            assert result.active_attachment_id == new_id

            async with factory() as session:
                from app.db.models.attachments import ATTACHMENT_STATE_ARCHIVED

                old = await att_repo.get_by_id(session, old_id)
                assert old is not None
                assert old.state == ATTACHMENT_STATE_ARCHIVED
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == new_id
            # Retained archive PDF always kept (no previous-file cleanup).
            assert storage.exists(old_rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_preference_only_approval_keeps_attachment(
    db_path: Path, tmp_path: Path
) -> None:
    """Draft without source CV updates profile/prefs; attachment unchanged."""
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.repositories import attachment_text_chunks as chunk_repo
    from app.repositories.attachment_text_chunks import build_chunk_write
    from app.services.profile_approval import commit_approved_draft
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            prefs = {
                "target_roles": ["Platform Engineer"],
                "preferred_locations": [],
                "acceptable_work_modes": ["remote"],
                "target_seniority": ["mid"],
            }
            grounded_profile = _approval_valid_profile_json()
            grounded_profile["full_name"] = "Ada Lovelace"
            grounded_profile["location"] = "Hanoi"
            corrected_profile = dict(grounded_profile)
            corrected_profile["summary"] = "Corrected backend profile"
            corrected_profile["location"] = "Atlantis"
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="pref-only",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.mark_active(session, att_id)
                ready = await prof_repo.upsert_active_profile(
                    session,
                    active_attachment_id=att_id,
                    profile_json=grounded_profile,
                )
                await chunk_repo.replace_for_attachment(
                    session,
                    att_id,
                    [
                        build_chunk_write(
                            0,
                            "Ada Lovelace is a backend engineer based in Hanoi.",
                        )
                    ],
                )
                await prof_repo.upsert_current_draft(
                    session,
                    draft_json={
                        "candidate_profile": corrected_profile,
                        "job_preferences": prefs,
                    },
                    source_attachment_id=None,
                    target_profile_id=ready.id,
                )
                await session.commit()

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=ready.id,
            )
            assert result.ok is True
            assert result.sqlite_committed is True
            assert result.active_attachment_id == att_id
            assert result.previous_attachment_id is None
            assert result.preferences_updated is True

            async with factory() as session:
                att = await att_repo.get_by_id(session, att_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE
                jp = await prof_repo.get_job_preferences(session)
                assert jp is not None
                assert jp.preferences_json["target_roles"] == [
                    "Platform Engineer"
                ]
                profile = await prof_repo.get_profile(session, ready.id)
                assert profile is not None
                assert profile.profile_json["summary"] == (
                    "Corrected backend profile"
                )
                assert profile.profile_json["full_name"] == "Ada Lovelace"
                assert profile.profile_json["location"] is None
                assert await prof_repo.get_current_draft(session) is None
            assert storage.exists(rel)
        finally:
            await engine.dispose()

    run_async(_body())


def test_missing_draft_preflight_no_neo4j(
    db_path: Path, tmp_path: Path
) -> None:
    from app.core.ids import new_uuid
    from app.services.profile_approval import (
        ERROR_DRAFT_NOT_FOUND,
        commit_approved_draft,
    )
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
                expected_profile_id=new_uuid(),
            )
            assert result.ok is False
            assert result.code == ERROR_DRAFT_NOT_FOUND
            assert result.sqlite_committed is False
            assert driver.runs == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_approval_module_boundaries_static() -> None:
    """No open transaction spans filesystem/Neo4j; stable codes reviewable."""
    import inspect

    from app.services import profile_approval as appr

    src = inspect.getsource(appr)
    assert "NEO4J_SYNC_FAILED" in src
    assert "commit" in src
    assert "rollback" in src
    assert "mark_archived" in src
    # Replacement retains archived CV; no previous-file cleanup path.
    assert "storage.delete" not in src
    assert "sqlite_committed" in src
    # No raw CV extraction in approval.
    assert "extract_text" not in src
    assert "raw_cv" not in src
    assert "PdfReader" not in src

# ---------------------------------------------------------------------------
# 03B: interrupt-guarded commit_profile_draft full path
# ---------------------------------------------------------------------------


def test_commit_profile_draft_missing_draft_fails_before_interrupt(
    db_path: Path, tmp_path: Path
) -> None:
    """Missing draft terminalizes failed with no interrupt/side effects."""
    from app.agent.graph import build_agent_graph
    from app.core.ids import new_uuid
    from app.db.models.chat import (
        AGENT_RUN_STATE_COMPLETED,
        TOOL_EXECUTION_STATUS_FAILED,
    )
    from app.repositories import agent_runs as runs_repo
    from app.repositories import tool_executions as tool_repo
    from app.services.chat_turns import stream_chat_turn
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        ERROR_DRAFT_NOT_FOUND,
        build_commit_profile_draft_tool,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel
    from tests.support.db_migration import run_async

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    side_effects: list[str] = []

    async def _fake_commit(**kwargs: object) -> object:
        side_effects.append("commit")
        raise AssertionError("commit must not run without draft")

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="missing-draft-owner",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                _profile_id, conversation_id = (
                    await _seed_ready_profile_conversation(
                        session, attachment_id=att_id
                    )
                )
                await session.commit()

            tool = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                commit_fn=_fake_commit,  # type: ignore[arg-type]
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-commit-missing",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Could not commit: no draft."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = []
            async for event in stream_chat_turn(
                conversation_id=conversation_id,
                message="please commit my profile draft",
                graph_bundle=bundle,
                session_factory=factory,
                sqlite_path=db_path,
            ):
                events.append(event)
            names = [e.event for e in events]
            assert "approval_required" not in names
            assert "run_completed" in names
            assert side_effects == []

            run_id = events[0].run_id
            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_FAILED
                assert tools[0].error_code == ERROR_DRAFT_NOT_FOUND
                assert tools[0].tool_call_id == "call-commit-missing"
        finally:
            await engine.dispose()

    run_async(_body())


def test_commit_profile_draft_rejects_cross_profile_owner_before_interrupt(
    db_path: Path, tmp_path: Path
) -> None:
    from app.agent.graph import build_agent_graph
    from app.core.ids import new_uuid
    from app.db.models.chat import TOOL_EXECUTION_STATUS_FAILED
    from app.repositories import tool_executions as tool_repo
    from app.services.chat_turns import stream_chat_turn
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        build_commit_profile_draft_tool,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    commits: list[str] = []

    async def _fake_commit(**kwargs: object) -> object:
        commits.append("commit")
        raise AssertionError("cross-profile commit must not run")

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            pending_attachment_id = new_uuid()
            active_attachment_id = new_uuid()
            pending_rel = _write_pdf(storage, pending_attachment_id)
            active_rel = _write_pdf(storage, active_attachment_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="cross-profile-draft",
                    original_name="draft.pdf",
                    size_bytes=40,
                    storage_path=pending_rel,
                    page_count=1,
                    attachment_id=pending_attachment_id,
                )
                draft_owner, _conversation_id = (
                    await _seed_pending_profile_draft_owner(
                        session,
                        attachment_id=pending_attachment_id,
                        draft_json=_approval_draft_json(),
                        select_workspace=False,
                    )
                )
                await att_repo.create_staged(
                    session,
                    file_hash="cross-profile-run",
                    original_name="active.pdf",
                    size_bytes=40,
                    storage_path=active_rel,
                    page_count=1,
                    attachment_id=active_attachment_id,
                )
                run_owner, conversation_id = (
                    await _seed_ready_profile_conversation(
                        session,
                        attachment_id=active_attachment_id,
                    )
                )
                await session.commit()

            tool = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                commit_fn=_fake_commit,  # type: ignore[arg-type]
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-cross-profile-commit",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="The draft belongs to another profile."),
                ]
            )
            bundle = build_agent_graph(model=model, registry=ToolRegistry([tool]))
            events = [
                event
                async for event in stream_chat_turn(
                    conversation_id=conversation_id,
                    message="save that draft",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]

            assert "approval_required" not in [event.event for event in events]
            assert commits == []
            run_id = events[0].run_id
            async with factory() as session:
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.target_profile_id == draft_owner
                assert run_owner != draft_owner
                rows = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(rows) == 1
                assert rows[0].status == TOOL_EXECUTION_STATUS_FAILED
                assert rows[0].error_code == "PROFILE_INCONSISTENT"
        finally:
            await engine.dispose()

    run_async(_body())


def test_commit_profile_draft_request_changes_preserves_draft(
    db_path: Path, tmp_path: Path
) -> None:
    """request_changes: one running row, draft kept, checkpoint cleaned, new turn ok."""
    from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
    from app.agent.graph import build_agent_graph
    from app.core.ids import new_uuid
    from app.db.models.chat import (
        AGENT_RUN_STATE_COMPLETED,
        AGENT_RUN_STATE_INTERRUPTED,
        TOOL_EXECUTION_STATUS_COMPLETED,
        TOOL_EXECUTION_STATUS_RUNNING,
    )
    from app.repositories import agent_runs as runs_repo
    from app.repositories import tool_executions as tool_repo
    from app.services.chat_turns import stream_chat_turn, stream_resume
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        PROFILE_COMMIT_ACTIONS,
        PROFILE_COMMIT_KIND,
        build_commit_profile_draft_tool,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel
    from tests.support.db_migration import run_async

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    commits: list[str] = []

    async def _fake_commit(**kwargs: object) -> object:
        commits.append("save")
        raise AssertionError("save_profile must not run on request_changes")

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="req-changes",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                _pending_id, conversation_id = (
                    await _seed_pending_profile_draft_owner(
                        session,
                        attachment_id=att_id,
                        draft_json=_approval_draft_json(),
                    )
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()

            correction = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=_pending_id,
                profile_changes={
                    "phone": "+1 (202) 555-0147",
                    "email": "CORRECTED@Example.TEST",
                    "github_url": "https://www.github.com/corrected-user/",
                },
            )
            assert correction.tool_result.ok is True
            assert correction.draft is not None
            assert correction.draft.candidate_profile.phone == "+12025550147"

            tool = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                commit_fn=_fake_commit,  # type: ignore[arg-type]
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-commit-rc",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Waiting for approval."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = [e async for e in stream_chat_turn(
                conversation_id=conversation_id,
                message="commit draft please",
                graph_bundle=bundle,
                session_factory=factory,
                sqlite_path=db_path,
            )]
            names = [e.event for e in events]
            assert names[-1] == "approval_required"
            assert "run_completed" not in names
            approval = events[-1]
            assert approval.payload.kind == PROFILE_COMMIT_KIND
            assert list(approval.payload.allowed_actions) == list(
                PROFILE_COMMIT_ACTIONS
            )
            run_id = approval.run_id

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                proj = run.pending_approval_json
                assert proj is not None
                assert proj["kind"] == PROFILE_COMMIT_KIND
                assert proj["draft_id"] == PROFILE_DRAFT_ID
                assert proj["allowed_actions"] == list(PROFILE_COMMIT_ACTIONS)
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_RUNNING
                assert tools[0].result_json is None
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is True

            # Resume on new request boundary with fresh tool/model instances.
            tool2 = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                commit_fn=_fake_commit,  # type: ignore[arg-type]
            )
            model2 = FakeChatModel(
                responses=[AIMessage(content="Understood; send your changes.")]
            )
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )
            resume_events = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="request_changes",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            rnames = [e.event for e in resume_events]
            assert "run_completed" in rnames
            assert "approval_required" not in rnames
            assert commits == []

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                assert run.pending_approval_json is None
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tools[0].tool_call_id == "call-commit-rc"
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("committed") is False
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.target_profile_id == _pending_id
                assert (
                    draft.draft_json["candidate_profile"]["phone"]
                    == "+12025550147"
                )
                assert (
                    draft.draft_json["candidate_profile"]["email"]
                    == "corrected@example.test"
                )
                assert (
                    draft.draft_json["candidate_profile"]["github_url"]
                    == "https://github.com/corrected-user"
                )
                draft_json_after = draft.draft_json

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is False

            # Exact identity replay: no second side effect / row.
            replay = await execute_tool_replay(
                factory=factory,
                run_id=run_id,
                tool_call_id="call-commit-rc",
            )
            assert replay is not None
            assert replay.ok is True
            assert replay.data is not None
            assert replay.data.get("committed") is False
            assert commits == []

            # Terminal re-entry / rapid repeated request_changes: no commit, draft
            # unchanged, one stored ToolResult identity.
            boom_model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-should-not-run",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            )
            boom_bundle = build_agent_graph(
                model=boom_model,
                registry=ToolRegistry([tool2]),
            )
            noop = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="request_changes",
                    graph_bundle=boom_bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert [e.event for e in noop] == ["run_started", "run_completed"]
            assert boom_model.invoke_count == 0
            assert commits == []

            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].tool_call_id == "call-commit-rc"
                draft = await prof_repo.get_current_draft(session)
                assert draft is not None
                assert draft.draft_json == draft_json_after
        finally:
            await engine.dispose()

    run_async(_body())


async def execute_tool_replay(
    *,
    factory: object,
    run_id: str,
    tool_call_id: str,
) -> Any:
    from app.services.tool_execution import get_replay_result

    return await get_replay_result(
        run_id=run_id,
        tool_call_id=tool_call_id,
        session_factory=factory,  # type: ignore[arg-type]
    )


def test_commit_profile_draft_save_profile_commits_and_sync_failure_truthful(
    db_path: Path, tmp_path: Path
) -> None:
    """save_profile uses (03A); Neo4j fail after commit is truthful ToolResult."""
    from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
    from app.agent.graph import build_agent_graph
    from app.core.ids import new_uuid
    from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE
    from app.db.models.chat import (
        AGENT_RUN_STATE_COMPLETED,
        AGENT_RUN_STATE_INTERRUPTED,
        TOOL_EXECUTION_STATUS_FAILED,
        TOOL_EXECUTION_STATUS_RUNNING,
    )
    from app.graph.sync_candidate import NEO4J_SYNC_FAILED
    from app.repositories import agent_runs as runs_repo
    from app.repositories import tool_executions as tool_repo
    from app.services.chat_turns import stream_chat_turn, stream_resume
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        build_commit_profile_draft_tool,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel
    from tests.support.db_migration import run_async

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="save-sync-fail",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                _pending_id, conversation_id = (
                    await _seed_pending_profile_draft_owner(
                        session,
                        attachment_id=att_id,
                        draft_json=_approval_draft_json(),
                    )
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()

            driver = _RecordingSyncDriver(fail=True)
            tool = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-commit-save",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Awaiting save."),
                ]
            )
            bundle = build_agent_graph(
                model=model,
                registry=ToolRegistry([tool]),
            )
            events = [
                e
                async for e in stream_chat_turn(
                    conversation_id=conversation_id,
                    message="save my profile",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert events[-1].event == "approval_required"
            run_id = events[-1].run_id

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_INTERRUPTED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert tools[0].status == TOOL_EXECUTION_STATUS_RUNNING
                selected = await prof_repo.get_active_profile(session)
                assert selected is not None
                assert selected.id == _pending_id
                assert selected.state == "pending"
                assert await prof_repo.get_selected_ready_profile(session) is None

            tool2 = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
            )
            model2 = FakeChatModel(
                responses=[
                    AIMessage(
                        content="Profile saved in SQLite; graph sync failed."
                    )
                ]
            )
            bundle2 = build_agent_graph(
                model=model2,
                registry=ToolRegistry([tool2]),
            )
            resume_events = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="save_profile",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert "run_completed" in [e.event for e in resume_events]

            async with factory() as session:
                run = await runs_repo.get_run(session, run_id)
                assert run is not None
                assert run.state == AGENT_RUN_STATE_COMPLETED
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_FAILED
                assert tools[0].error_code == NEO4J_SYNC_FAILED
                assert tools[0].tool_call_id == "call-commit-save"
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is False
                assert stored.data is not None
                assert stored.data.get("sqlite_committed") is True
                assert stored.data.get("committed") is True
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.active_attachment_id == att_id
                assert await prof_repo.get_current_draft(session) is None
                att = await att_repo.get_by_id(session, att_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE

            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, run_id) is False

            # Replay never repeats SQLite/file/Neo4j side effects.
            runs_before = driver.runs
            replay = await execute_tool_replay(
                factory=factory,
                run_id=run_id,
                tool_call_id="call-commit-save",
            )
            assert replay is not None
            assert replay.ok is False
            assert replay.code == NEO4J_SYNC_FAILED
            assert driver.runs == runs_before
        finally:
            await engine.dispose()

    run_async(_body())


def test_commit_profile_draft_save_profile_success_and_terminal_noop(
    db_path: Path, tmp_path: Path
) -> None:
    """save_profile success completes tool; terminal resume is no-op stream."""
    from app.agent.graph import build_agent_graph
    from app.core.ids import new_uuid
    from app.db.models.chat import (
        TOOL_EXECUTION_STATUS_COMPLETED,
    )
    from app.repositories import tool_executions as tool_repo
    from app.services.chat_turns import stream_chat_turn, stream_resume
    from app.services.profile_drafts import propose_profile_update
    from app.services.skill_normalization import SkillNormalizer
    from app.storage.attachments import AttachmentStorage
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        build_commit_profile_draft_tool,
    )
    from app.tools.registry import ToolRegistry
    from langchain_core.messages import AIMessage

    from tests.fakes.fake_chat_model import FakeChatModel
    from tests.support.db_migration import run_async

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    driver = _RecordingSyncDriver()

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = _write_pdf(storage, att_id)
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="save-ok",
                    original_name="cv.pdf",
                    size_bytes=40,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                _pending_id, conversation_id = (
                    await _seed_pending_profile_draft_owner(
                        session,
                        attachment_id=att_id,
                        draft_json=_approval_draft_json(
                            prefs={
                                "target_roles": ["Backend"],
                                "preferred_locations": [],
                                "acceptable_work_modes": ["remote"],
                                "target_seniority": [],
                            }
                        ),
                    )
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=att_id,
                )
                await session.commit()

            correction = await propose_profile_update(
                session_factory=factory,
                normalizer=normalizer,
                expected_profile_id=_pending_id,
                profile_changes={
                    "phone": "+84 900 000 001",
                    "email": "SAVED@Example.TEST",
                    "github_url": "https://www.github.com/saved-user/",
                },
            )
            assert correction.tool_result.ok is True
            assert correction.draft is not None
            assert correction.draft.candidate_profile.phone == "+84900000001"
            assert correction.draft.candidate_profile.email == "saved@example.test"
            assert (
                correction.draft.candidate_profile.github_url
                == "https://github.com/saved-user"
            )

            tool = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
            )
            model = FakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": COMMIT_PROFILE_DRAFT_NAME,
                                "args": {"draft_id": "current"},
                                "id": "call-commit-ok",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="Awaiting."),
                ]
            )
            bundle = build_agent_graph(
                model=model, registry=ToolRegistry([tool])
            )
            events = [
                e
                async for e in stream_chat_turn(
                    conversation_id=conversation_id,
                    message="approve profile",
                    graph_bundle=bundle,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            run_id = events[-1].run_id

            tool2 = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                driver=driver,  # type: ignore[arg-type]
            )
            model2 = FakeChatModel(
                responses=[AIMessage(content="Profile saved successfully.")]
            )
            bundle2 = build_agent_graph(
                model=model2, registry=ToolRegistry([tool2])
            )
            resume_events = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="save_profile",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            assert resume_events[-1].event == "run_completed"
            # One accepted save drives a non-zero Cypher batch (merge/clear/skills).
            graph_queries_after_save = driver.runs
            assert graph_queries_after_save >= 1

            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                assert tools[0].tool_call_id == "call-commit-ok"
                stored = tool_repo.load_stored_result(tools[0])
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("committed") is True
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.profile_json["phone"] == "+84900000001"
                assert profile.profile_json["email"] == "saved@example.test"
                assert (
                    profile.profile_json["github_url"]
                    == "https://github.com/saved-user"
                )
                profile_updated = profile.updated_at
                assert await prof_repo.get_current_draft(session) is None

            # Same-identity ToolResult replay: no second SQLite/graph work.
            replay = await execute_tool_replay(
                factory=factory,
                run_id=run_id,
                tool_call_id="call-commit-ok",
            )
            assert replay is not None
            assert replay.ok is True
            assert replay.data is not None
            assert replay.data.get("committed") is True
            assert driver.runs == graph_queries_after_save

            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                profile = await prof_repo.get_active_profile(session)
                assert profile is not None
                assert profile.updated_at == profile_updated
                assert await prof_repo.get_current_draft(session) is None

            # Terminal no-op resume / rapid repeated save_profile.
            noop = [
                e
                async for e in stream_resume(
                    run_id=run_id,
                    action="save_profile",
                    graph_bundle=bundle2,
                    session_factory=factory,
                    sqlite_path=db_path,
                )
            ]
            noop_names = [e.event for e in noop]
            assert noop_names == ["run_started", "run_completed"]
            assert "text_delta" not in noop_names
            assert "approval_required" not in noop_names
            assert driver.runs == graph_queries_after_save

            async with factory() as session:
                tools = await tool_repo.list_for_run_ids(session, [run_id])
                assert len(tools) == 1
                assert tools[0].tool_call_id == "call-commit-ok"
        finally:
            await engine.dispose()

    run_async(_body())


def test_production_registry_exactly_seven_tools_static() -> None:
    """Production registry is seven tools; no synthetic helpers."""
    from app.tools.active_cv import READ_ACTIVE_CV_NAME
    from app.tools.jobs import QUERY_JOBS_NAME, SAVE_JOB_NAME
    from app.tools.matching import MATCH_JOBS_NAME
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        PROPOSE_PROFILE_FROM_CV_NAME,
        PROPOSE_PROFILE_UPDATE_NAME,
    )
    from app.tools.registry import production_registry

    names = production_registry().tool_names()
    assert names == [
        PROPOSE_PROFILE_FROM_CV_NAME,
        PROPOSE_PROFILE_UPDATE_NAME,
        COMMIT_PROFILE_DRAFT_NAME,
        SAVE_JOB_NAME,
        QUERY_JOBS_NAME,
        MATCH_JOBS_NAME,
        READ_ACTIVE_CV_NAME,
    ]
    assert "synthetic_interrupt" not in names

    reg_src = (
        Path(__file__).resolve().parents[2] / "app" / "tools" / "registry.py"
    ).read_text(encoding="utf-8")
    assert "build_synthetic" not in reg_src
    assert "build_production_job_tools" in reg_src
    assert "build_production_match_tools" in reg_src
    assert "build_production_active_cv_tools" in reg_src
    profile_src = (
        Path(__file__).resolve().parents[2] / "app" / "tools" / "profile.py"
    ).read_text(encoding="utf-8")
    assert "interrupt(" in profile_src
    assert "allow_running_reentry" in profile_src
    assert "execute_tool" in profile_src
    assert "InjectedToolCallId" in profile_src
    assert "InjectedState" in profile_src
    assert "save_profile" in profile_src
    assert "request_changes" in profile_src
    # Every production profile tool factory routes through the one executor.
    for factory_name in (
        "build_propose_profile_from_cv_tool",
        "build_propose_profile_update_tool",
        "build_commit_profile_draft_tool",
    ):
        fn = getattr(
            __import__("app.tools.profile", fromlist=[factory_name]),
            factory_name,
        )
        src = inspect.getsource(fn)
        assert "execute_tool" in src
        assert "InjectedToolCallId" in src
        assert "InjectedState" in src
    jobs_src = (
        Path(__file__).resolve().parents[2] / "app" / "tools" / "jobs.py"
    ).read_text(encoding="utf-8")
    assert "execute_tool" in jobs_src
    for factory_name in ("build_save_job_tool", "build_query_jobs_tool"):
        fn = getattr(
            __import__("app.tools.jobs", fromlist=[factory_name]),
            factory_name,
        )
        src = inspect.getsource(fn)
        assert "execute_tool" in src
        assert "InjectedToolCallId" in src
        assert "InjectedState" in src
    matching_src = (
        Path(__file__).resolve().parents[2] / "app" / "tools" / "matching.py"
    ).read_text(encoding="utf-8")
    assert "execute_tool" in matching_src
    match_fn = __import__(
        "app.tools.matching", fromlist=["build_match_jobs_tool"]
    ).build_match_jobs_tool
    match_src = inspect.getsource(match_fn)
    assert "execute_tool" in match_src
    assert "InjectedToolCallId" in match_src
    assert "InjectedState" in match_src


def test_five_production_tools_durable_status_and_proposal_replay(
    db_path: Path, tmp_path: Path
) -> None:
    """All five tools create one durable execution + ordered tool_status path.

    Proposal-tool same-identity replay must not re-extract, re-call the
    provider, or mutate the draft a second time.
    """
    import json

    from app.core.ids import new_uuid
    from app.db.models.chat import (
        CHAT_MESSAGE_ROLE_USER,
        TOOL_EXECUTION_STATUS_COMPLETED,
    )
    from app.repositories import agent_runs as runs_repo
    from app.repositories import chat_messages as messages_repo
    from app.repositories import conversations as conversations_repo
    from app.repositories import tool_executions as tool_repo
    from app.repositories import workspace_state as workspace_repo
    from app.schemas.tools import ToolResult
    from app.services.skill_normalization import SkillNormalizer
    from app.services.tool_execution import tool_status_publication_scope
    from app.storage.attachments import AttachmentStorage
    from app.tools.jobs import (
        QUERY_JOBS_NAME,
        SAVE_JOB_NAME,
        build_query_jobs_tool,
        build_save_job_tool,
    )
    from app.tools.profile import (
        COMMIT_PROFILE_DRAFT_NAME,
        PROPOSE_PROFILE_FROM_CV_NAME,
        PROPOSE_PROFILE_UPDATE_NAME,
        build_commit_profile_draft_tool,
        build_propose_profile_from_cv_tool,
        build_propose_profile_update_tool,
    )

    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    normalizer = SkillNormalizer.from_path(_skills_fixture())
    invoker = _CoveringDocumentInvoker()
    pdf = _cv_fixture("digital_cv_01.pdf")
    owner_profile_id = ""
    owner_attachment_id = ""

    async def _ainvoke(
        tool_fn: Any,
        *,
        run_id: str,
        tool_call_id: str,
        args: dict[str, Any],
    ) -> ToolResult:
        raw = await tool_fn.ainvoke(
            {
                "type": "tool_call",
                "id": tool_call_id,
                "name": tool_fn.name,
                "args": {
                    **args,
                    "state": {
                        "run_id": run_id,
                        "profile_id": owner_profile_id,
                        "attachment_ids": [owner_attachment_id],
                    },
                },
            }
        )
        if isinstance(raw, str):
            payload = json.loads(raw)
        elif hasattr(raw, "content"):
            content = raw.content
            payload = (
                json.loads(content) if isinstance(content, str) else content
            )
        else:
            payload = raw
        return ToolResult.model_validate(payload)

    async def _body() -> None:
        nonlocal owner_profile_id, owner_attachment_id
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            rel = storage.write_bytes(att_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="five-tool-cv",
                    original_name="cv.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=att_id,
                )
                pending = await prof_repo.create_pending_profile(
                    session,
                    attachment_id=att_id,
                    display_name="cv.pdf",
                )
                conversation = await conversations_repo.create_bootstrap_for_profile(
                    session, profile_id=pending.id
                )
                await workspace_repo.set_active_profile_id(session, pending.id)
                user = await messages_repo.insert_message(
                    session,
                    conversation_id=conversation.id,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="five-tool durable status",
                    source_attachment_id=att_id,
                )
                run = await runs_repo.create_run(
                    session,
                    user_message_id=user.id,
                    source_attachment_id=att_id,
                )
                owner_profile_id = pending.id
                owner_attachment_id = att_id
                await session.commit()
                run_id = run.id

            propose_cv = build_propose_profile_from_cv_tool(
                session_factory=factory,
                storage=storage,
                invoker=invoker,
                normalizer=normalizer,
            )
            propose_upd = build_propose_profile_update_tool(
                session_factory=factory,
                normalizer=normalizer,
            )
            commit_fn = build_commit_profile_draft_tool(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
            )
            save_fn = build_save_job_tool(
                session_factory=factory,
                normalizer=normalizer,
            )
            query_fn = build_query_jobs_tool(session_factory=factory)

            # LLM-visible schemas stay public-only (injected identity hidden).
            from langchain_core.utils.function_calling import (
                convert_to_openai_tool,
            )

            cv_props = set(
                (
                    convert_to_openai_tool(propose_cv)
                    .get("function", {})
                    .get("parameters", {})
                    .get("properties")
                    or {}
                ).keys()
            )
            assert cv_props == {"attachment_id", "reprocess"}
            upd_props = set(
                (
                    convert_to_openai_tool(propose_upd)
                    .get("function", {})
                    .get("parameters", {})
                    .get("properties")
                    or {}
                ).keys()
            )
            assert "tool_call_id" not in upd_props
            assert "state" not in upd_props
            assert "run_id" not in upd_props
            assert upd_props <= {
                "profile_changes",
                "preference_changes",
                "skill_corrections",
            }

            pubs: list[Any] = []
            with tool_status_publication_scope(pubs.append):
                first_cv = await _ainvoke(
                    propose_cv,
                    run_id=run_id,
                    tool_call_id="call_five_propose_cv",
                    args={"attachment_id": att_id},
                )
            assert first_cv.ok is True
            assert invoker.calls >= 1
            calls_after_first = invoker.calls
            assert [p.status for p in pubs] == [
                "pending",
                "running",
                "completed",
            ]
            assert all(p.tool_name == PROPOSE_PROFILE_FROM_CV_NAME for p in pubs)
            exec_id_cv = pubs[0].tool_execution_id
            assert all(p.tool_execution_id == exec_id_cv for p in pubs)
            assert all(p.tool_call_id == "call_five_propose_cv" for p in pubs)
            assert pubs[-1].duration_ms is not None
            assert pubs[-1].summary

            async with factory() as session:
                draft_before = await prof_repo.get_current_draft(session)
                assert draft_before is not None
                draft_json_before = json.dumps(
                    draft_before.draft_json, sort_keys=True
                )
                draft_updated_before = draft_before.updated_at

            pubs.clear()
            with tool_status_publication_scope(pubs.append):
                replay_cv = await _ainvoke(
                    propose_cv,
                    run_id=run_id,
                    tool_call_id="call_five_propose_cv",
                    args={"attachment_id": att_id},
                )
            assert replay_cv.model_dump(mode="json") == first_cv.model_dump(
                mode="json"
            )
            # Durable replay must not re-extract or re-call the document invoker.
            assert invoker.calls == calls_after_first
            assert [p.status for p in pubs] == ["completed"]
            assert pubs[0].tool_execution_id == exec_id_cv

            async with factory() as session:
                draft_after = await prof_repo.get_current_draft(session)
                assert draft_after is not None
                assert (
                    json.dumps(draft_after.draft_json, sort_keys=True)
                    == draft_json_before
                )
                assert draft_after.updated_at == draft_updated_before

            pubs.clear()
            with tool_status_publication_scope(pubs.append):
                first_upd = await _ainvoke(
                    propose_upd,
                    run_id=run_id,
                    tool_call_id="call_five_propose_upd",
                    args={
                        "profile_changes": {
                            "summary": "Corrected summary once."
                        }
                    },
                )
            assert first_upd.ok is True
            assert [p.status for p in pubs] == [
                "pending",
                "running",
                "completed",
            ]
            assert all(p.tool_name == PROPOSE_PROFILE_UPDATE_NAME for p in pubs)
            exec_id_upd = pubs[0].tool_execution_id

            async with factory() as session:
                draft_mid = await prof_repo.get_current_draft(session)
                assert draft_mid is not None
                mid_json = json.dumps(draft_mid.draft_json, sort_keys=True)
                mid_updated = draft_mid.updated_at
                summary = draft_mid.draft_json["candidate_profile"]["summary"]
                assert summary == "Corrected summary once."

            pubs.clear()
            with tool_status_publication_scope(pubs.append):
                replay_upd = await _ainvoke(
                    propose_upd,
                    run_id=run_id,
                    tool_call_id="call_five_propose_upd",
                    args={
                        "profile_changes": {
                            "summary": "Would mutate if re-invoked"
                        }
                    },
                )
            assert replay_upd.model_dump(mode="json") == first_upd.model_dump(
                mode="json"
            )
            assert [p.status for p in pubs] == ["completed"]
            assert pubs[0].tool_execution_id == exec_id_upd

            async with factory() as session:
                draft_final = await prof_repo.get_current_draft(session)
                assert draft_final is not None
                assert (
                    json.dumps(draft_final.draft_json, sort_keys=True)
                    == mid_json
                )
                assert draft_final.updated_at == mid_updated
                assert (
                    draft_final.draft_json["candidate_profile"]["summary"]
                    == "Corrected summary once."
                )

            # query_jobs is a full durable path without Job side-effect fakes.
            pubs.clear()
            with tool_status_publication_scope(pubs.append):
                q = await _ainvoke(
                    query_fn,
                    run_id=run_id,
                    tool_call_id="call_five_query",
                    args={},
                )
            assert q.ok is True
            assert [p.status for p in pubs] == [
                "pending",
                "running",
                "completed",
            ]
            assert all(p.tool_name == QUERY_JOBS_NAME for p in pubs)

            # Remaining registered tools share the same execute_tool owner.
            assert commit_fn.name == COMMIT_PROFILE_DRAFT_NAME
            assert save_fn.name == SAVE_JOB_NAME
            assert "execute_tool" in inspect.getsource(
                build_commit_profile_draft_tool
            )
            assert "execute_tool" in inspect.getsource(build_save_job_tool)

            async with factory() as session:
                rows = await tool_repo.list_for_run_ids(session, [run_id])
                by_call = {r.tool_call_id: r for r in rows}
                for call_id, tool_name in (
                    ("call_five_propose_cv", PROPOSE_PROFILE_FROM_CV_NAME),
                    ("call_five_propose_upd", PROPOSE_PROFILE_UPDATE_NAME),
                    ("call_five_query", QUERY_JOBS_NAME),
                ):
                    row = by_call[call_id]
                    assert row.tool_name == tool_name
                    assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
                    assert row.duration_ms is not None
                    assert row.result_json is not None
                # Exactly one durable row per proposal identity (replay reuse).
                assert (
                    sum(
                        1
                        for r in rows
                        if r.tool_call_id == "call_five_propose_cv"
                    )
                    == 1
                )
                assert (
                    sum(
                        1
                        for r in rows
                        if r.tool_call_id == "call_five_propose_upd"
                    )
                    == 1
                )
                # Compact arguments summaries only (IDs / keys, never bodies).
                cv_args = by_call["call_five_propose_cv"].arguments_summary_json
                assert cv_args == {
                    "attachment_id": att_id,
                    "reprocess": False,
                }
                upd_args = by_call[
                    "call_five_propose_upd"
                ].arguments_summary_json
                assert upd_args is not None
                assert upd_args.get("profile_change_keys") == ["summary"]
                assert "Corrected summary" not in json.dumps(upd_args)
                assert "%PDF" not in json.dumps(
                    first_cv.model_dump(mode="json")
                )
        finally:
            await engine.dispose()

    run_async(_body())
