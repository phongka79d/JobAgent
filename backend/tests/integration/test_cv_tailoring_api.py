from __future__ import annotations

import hashlib
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import Attachment
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import workspace_state as workspace_repo
from app.repositories.cv_tailoring import CVTailoringVersionWrite
from app.services.cv_tailoring import TAILORING_ARTIFACT_UNAVAILABLE, TailoringError
from app.storage.cv_tailoring import TailoringArtifactStorage

from tests.support.db_migration import run_async, session_factory


def test_cv_tailoring_router_exposes_exact_authorized_endpoint_shapes() -> None:
    from app.api.cv_tailoring import router
    from app.schemas.cv_tailoring import (
        TailoringDeleteResponse,
        TailoringVersionCreateResponse,
    )

    shapes = {(route.path, frozenset(route.methods or ())) for route in router.routes}
    assert shapes == {
        ("/cv-tailoring/sessions", frozenset({"POST"})),
        ("/cv-tailoring/sessions", frozenset({"GET"})),
        ("/cv-tailoring/sessions/{session_id}", frozenset({"GET"})),
        (
            "/cv-tailoring/sessions/{session_id}/ai-versions",
            frozenset({"POST"}),
        ),
        (
            "/cv-tailoring/sessions/{session_id}/manual-versions",
            frozenset({"POST"}),
        ),
        ("/cv-tailoring/versions/{version_id}/source", frozenset({"GET"})),
        ("/cv-tailoring/versions/{version_id}/pdf", frozenset({"GET"})),
        ("/cv-tailoring/sessions/{session_id}", frozenset({"DELETE"})),
    }
    response_models = {
        (route.path, next(iter(route.methods or ()))): route.response_model
        for route in router.routes
    }
    assert response_models[
        ("/cv-tailoring/sessions/{session_id}/manual-versions", "POST")
    ] is TailoringVersionCreateResponse
    assert response_models[
        ("/cv-tailoring/sessions/{session_id}", "DELETE")
    ] is TailoringDeleteResponse


def test_main_app_registers_tailoring_routes_and_exposes_session_header() -> None:
    from app.main import create_app
    from app.schemas.cv_tailoring import CV_TAILORING_SESSION_HEADER

    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/api/cv-tailoring/sessions" in paths
    cors = next(
        item for item in app.user_middleware if item.cls.__name__ == "CORSMiddleware"
    )
    assert CV_TAILORING_SESSION_HEADER in cors.kwargs["expose_headers"]


def test_artifact_hashing_uses_bounded_streaming_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.cv_tailoring import _sha256_file

    artifact = tmp_path / "resume.pdf"
    payload = b"x" * (64 * 1024 + 17)
    artifact.write_bytes(payload)

    def reject_unbounded_read(_self: Path) -> bytes:
        raise AssertionError("read_bytes must not be used for artifact hashing")

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)
    assert _sha256_file(artifact) == hashlib.sha256(payload).hexdigest()


def test_tailoring_routes_use_one_injected_dependency_seam() -> None:
    from app.api.cv_tailoring import router
    from app.api.dependencies import CVTailoringDeps

    assert [item.name for item in fields(CVTailoringDeps)] == [
        "coordinator",
        "storage",
        "settings",
        "session_factory",
    ]
    endpoint_sources = "\n".join(
        inspect.getsource(route.endpoint) for route in router.routes
    )
    assert "get_session_factory" not in endpoint_sources


def test_source_download_verifies_hash_and_returns_safe_exact_headers(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    from app.api.cv_tailoring import _download
    from app.api.dependencies import CVTailoringDeps

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        storage = TailoringArtifactStorage(tmp_path / "files")
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
                await workspace_repo.set_active_profile_id(session, profile.id)
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
                await session.flush()
                version_id = new_uuid()
                staging = storage.create_staging_dir(version_id=version_id)
                tex_bytes = b"synthetic source"
                pdf_bytes = b"%PDF-1.4 synthetic"
                (staging / "resume.tex").write_bytes(tex_bytes)
                (staging / "resume.pdf").write_bytes(pdf_bytes)
                paths = storage.promote(
                    profile_id=profile.id,
                    session_id=owner.id,
                    version_id=version_id,
                    staged_tex=staging / "resume.tex",
                    staged_pdf=staging / "resume.pdf",
                )
                version = await tailoring_repo.create_version_cas(
                    session,
                    session_id=owner.id,
                    expected_latest_version_number=0,
                    expected_parent_version_id=None,
                    version=CVTailoringVersionWrite(
                        id=version_id,
                        parent_version_id=None,
                        created_by="ai",
                        content_json={"header": {}, "sections": []},
                        provenance_json={"targeted_section_ids": [], "facts": []},
                        source_revision_json={"source_hash": profile.source_hash},
                        tex_relative_path=paths.tex_relative_path,
                        pdf_relative_path=paths.pdf_relative_path,
                        tex_sha256=hashlib.sha256(tex_bytes).hexdigest(),
                        pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
                        page_count=1,
                        page_warning=None,
                        created_at=datetime(2026, 7, 26, tzinfo=UTC),
                    ),
                )
                await session.commit()

            deps = CVTailoringDeps(
                coordinator=cast(Any, object()),
                storage=storage,
                settings=cast(Any, object()),
                session_factory=factory,
            )
            response = await _download(version.id, kind="source", deps=deps)
            body = b"".join([chunk async for chunk in response.body_iterator])
            assert body == tex_bytes
            assert response.media_type == "text/x-tex; charset=utf-8"
            assert response.headers["content-length"] == str(len(tex_bytes))
            assert response.headers["content-disposition"] == (
                'attachment; filename="resume-v1.tex"'
            )
            assert response.headers["x-content-type-options"] == "nosniff"

            storage.resolve_artifact(
                relative_path=paths.tex_relative_path
            ).write_bytes(b"corrupt")
            with pytest.raises(TailoringError) as caught:
                await _download(version.id, kind="source", deps=deps)
            assert caught.value.code == TAILORING_ARTIFACT_UNAVAILABLE
        finally:
            await engine.dispose()

    run_async(_body())
