from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import Attachment
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import cv_tailoring as tailoring_repo
from app.services.cv_tailoring import TailoringError
from app.services.cv_tailoring_deletion import (
    TAILORING_DELETE_FAILED,
    delete_tailoring_session,
)
from app.storage.cv_tailoring import TailoringArtifactStorage

from tests.support.db_migration import run_async, session_factory


def test_tailoring_deletion_has_one_retry_safe_public_surface() -> None:
    assert list(inspect.signature(delete_tailoring_session).parameters) == [
        "session_id",
        "session_factory",
        "sqlite_path",
        "storage",
    ]


class _FailOnceStorage(TailoringArtifactStorage):
    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir)
        self.calls = 0

    def delete_session(self, *, profile_id: str, session_id: str) -> bool:
        self.calls += 1
        if self.calls == 1:
            return False
        return super().delete_session(profile_id=profile_id, session_id=session_id)


def test_artifact_cleanup_failure_keeps_deleting_session_for_retry(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        storage = _FailOnceStorage(tmp_path / "files")
        try:
            async with factory() as session:
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
                owner = await tailoring_repo.create_session(
                    session,
                    profile_id=profile.id,
                    source_attachment_id=attachment.id,
                    source_hash=profile.source_hash,
                    profile_updated_at=profile.updated_at,
                    job_id=None,
                    job_updated_at=None,
                    job_label_json=None,
                    instruction="Synthetic tailoring",
                    template_version="latex-cv-v1",
                )
                await session.commit()
                session_id = owner.id

            with pytest.raises(TailoringError) as caught:
                await delete_tailoring_session(
                    session_id=session_id,
                    session_factory=factory,
                    sqlite_path=migrated_sqlite,
                    storage=storage,
                )
            assert caught.value.code == TAILORING_DELETE_FAILED
            async with factory() as session:
                retained = await tailoring_repo.get_session(session, session_id)
                assert retained is not None
                assert retained.state == "deleting"

            result = await delete_tailoring_session(
                session_id=session_id,
                session_factory=factory,
                sqlite_path=migrated_sqlite,
                storage=storage,
            )
            assert result.deleted_session_id == session_id
            async with factory() as session:
                assert await tailoring_repo.get_session(session, session_id) is None
        finally:
            await engine.dispose()

    run_async(_body())
