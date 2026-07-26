"""Flush-only persistence and atomic-CAS contracts for CV tailoring."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import Attachment
from app.db.models.cv_tailoring import CVTailoringVersion
from app.db.models.jobs import JobPost
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import jobs as jobs_repo
from app.repositories.cv_tailoring import (
    CVTailoringVersionWrite,
    TailoringParentConflict,
)
from sqlalchemy import func, select

from tests.support.db_migration import run_async, session_factory


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


async def _ready_profile(session) -> tuple[Profile, Attachment]:
    attachment = Attachment(
        file_hash=new_uuid().replace("-", "") * 2,
        original_name="synthetic.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=1,
        storage_path=f"{new_uuid()}.pdf",
        state="archived",
    )
    session.add(attachment)
    await session.flush()
    profile = Profile(
        attachment_id=attachment.id,
        display_name="Synthetic Candidate",
        profile_json={"summary": "Synthetic"},
        location=None,
        extraction_version="cv-document-v1",
        source_hash="source-revision-a",
        state="ready",
    )
    session.add(profile)
    await session.flush()
    return profile, attachment


def _version_write(*, parent_version_id: str | None = None) -> CVTailoringVersionWrite:
    return CVTailoringVersionWrite(
        id=new_uuid(),
        parent_version_id=parent_version_id,
        created_by="ai" if parent_version_id is None else "user",
        content_json={"header": {"full_name": "Synthetic Candidate"}, "sections": []},
        provenance_json={"targeted_section_ids": [], "facts": []},
        source_revision_json={"source_hash": "source-revision-a"},
        tex_relative_path=f"cv-tailoring/{new_uuid()}/resume.tex",
        pdf_relative_path=f"cv-tailoring/{new_uuid()}/resume.pdf",
        tex_sha256="a" * 64,
        pdf_sha256="b" * 64,
        page_count=1,
        page_warning=None,
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )


def test_session_starts_at_zero_and_versions_advance_only_by_exact_cas(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, attachment = await _ready_profile(session)
                row = await tailoring_repo.create_session(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment.id,
                    source_hash=profile.source_hash,
                    profile_updated_at=profile.updated_at,
                    job_id=None,
                    job_updated_at=None,
                    job_label_json=None,
                    instruction="Tailor for a synthetic role",
                    template_version="latex-cv-v1",
                )
                assert row.latest_version_number == 0
                assert row.state == "generating"
                await session.commit()
                session_id = row.id

            async with factory() as session:
                first = await tailoring_repo.create_version_cas(
                    session,
                    session_id=session_id,
                    expected_latest_version_number=0,
                    expected_parent_version_id=None,
                    version=_version_write(),
                )
                assert first.version_number == 1
                await session.commit()
                first_id = first.id

            async with factory() as session:
                second = await tailoring_repo.create_version_cas(
                    session,
                    session_id=session_id,
                    expected_latest_version_number=1,
                    expected_parent_version_id=first_id,
                    version=_version_write(parent_version_id=first_id),
                )
                assert second.version_number == 2
                await session.commit()

            async with factory() as session:
                stale_write = _version_write(parent_version_id=first_id)
                with pytest.raises(TailoringParentConflict):
                    await tailoring_repo.create_version_cas(
                        session,
                        session_id=session_id,
                        expected_latest_version_number=1,
                        expected_parent_version_id=first_id,
                        version=stale_write,
                    )
                await session.rollback()
                count = await session.scalar(
                    select(func.count()).select_from(CVTailoringVersion)
                )
                assert count == 2
        finally:
            await engine.dispose()

    run_async(_body())


def test_failed_to_deleting_clears_error_and_delete_is_retry_safe(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, attachment = await _ready_profile(session)
                row = await tailoring_repo.create_session(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment.id,
                    source_hash=profile.source_hash,
                    profile_updated_at=profile.updated_at,
                    job_id=None,
                    job_updated_at=None,
                    job_label_json=None,
                    instruction="Synthetic instruction",
                    template_version="latex-cv-v1",
                )
                await session.commit()
                session_id = row.id

            async with factory() as session:
                failed = await tailoring_repo.mark_session_failed(
                    session, session_id, error_code="TAILORING_COMPILE_FAILED"
                )
                assert failed.state == "failed"
                deleting = await tailoring_repo.mark_session_deleting(
                    session, session_id
                )
                assert deleting.state == "deleting"
                assert deleting.error_code is None
                assert await tailoring_repo.delete_session(session, session_id) is True
                assert await tailoring_repo.delete_session(session, session_id) is False
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_version_rows_have_no_repository_update_or_delete_surface() -> None:
    assert not hasattr(tailoring_repo, "update_version")
    assert not hasattr(tailoring_repo, "delete_version")


def test_version_write_rejects_nonpositive_pages_and_naive_time() -> None:
    valid = _version_write()
    with pytest.raises(ValueError, match="page_count"):
        replace(valid, page_count=0)
    with pytest.raises(ValueError, match="created_at"):
        replace(valid, created_at=datetime(2026, 7, 26))
    with pytest.raises(ValueError, match="created_by"):
        replace(valid, created_by="provider")


def test_job_delete_retains_snapshot_and_profile_delete_cascades_derivatives(
    db_path: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, attachment = await _ready_profile(session)
                job = await jobs_repo.create_text_job(
                    session,
                    raw_content="Synthetic JD",
                    raw_content_hash=new_uuid(),
                )
                row = await tailoring_repo.create_session(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment.id,
                    source_hash=profile.source_hash,
                    profile_updated_at=profile.updated_at,
                    job_id=job.id,
                    job_updated_at=job.updated_at,
                    job_label_json={"title": "Synthetic Role", "company": "Lab"},
                    instruction="",
                    template_version="latex-cv-v1",
                )
                first = await tailoring_repo.create_version_cas(
                    session,
                    session_id=row.id,
                    expected_latest_version_number=0,
                    expected_parent_version_id=None,
                    version=_version_write(),
                )
                await session.commit()
                profile_id = profile.id
                session_id = row.id
                version_id = first.id
                job_id = job.id

            async with factory() as session:
                job = await session.get(JobPost, job_id)
                assert job is not None
                await session.delete(job)
                await session.commit()

            async with factory() as session:
                retained = await tailoring_repo.get_session(session, session_id)
                assert retained is not None
                assert retained.job_id is None
                assert retained.job_updated_at is not None
                assert retained.job_label_json == {
                    "title": "Synthetic Role",
                    "company": "Lab",
                }
                version = await tailoring_repo.get_version(session, version_id)
                assert version is not None
                assert version.tex_relative_path.endswith("resume.tex")
                assert version.pdf_relative_path.endswith("resume.pdf")
                profile = await session.get(Profile, profile_id)
                assert profile is not None
                await session.delete(profile)
                await session.commit()

            async with factory() as session:
                assert await tailoring_repo.get_session(session, session_id) is None
                assert await tailoring_repo.get_version(session, version_id) is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_insert_trigger_rejects_session_without_job_or_instruction(
    db_path: Path,
) -> None:
    async def _body() -> None:
        from sqlalchemy.exc import IntegrityError

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile, attachment = await _ready_profile(session)
                with pytest.raises(IntegrityError, match="job or instruction"):
                    await tailoring_repo.create_session(
                        session,
                        profile_id=profile.id,
                        source_attachment_id=attachment.id,
                        source_hash=profile.source_hash,
                        profile_updated_at=profile.updated_at,
                        job_id=None,
                        job_updated_at=None,
                        job_label_json=None,
                        instruction="   ",
                        template_version="latex-cv-v1",
                    )
        finally:
            await engine.dispose()

    run_async(_body())
