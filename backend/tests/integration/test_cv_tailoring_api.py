from __future__ import annotations

import hashlib
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.api.dependencies import CVTailoringDeps, get_cv_tailoring_deps
from app.core.ids import new_uuid
from app.db.models.attachments import Attachment
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import workspace_state as workspace_repo
from app.repositories.cv_tailoring import CVTailoringVersionWrite
from app.schemas.cv_tailoring import TailoringUserIssue, TailoringVersionMutationResponse
from app.schemas.sse import build_sse_event
from app.services.cv_tailoring import (
    TAILORING_ARTIFACT_UNAVAILABLE,
    TailoringError,
    TailoringLaunch,
)
from app.storage.cv_tailoring import TailoringArtifactStorage
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.db_migration import run_async, session_factory


def _content() -> dict[str, Any]:
    return {
        "header": {
            "full_name": "Synthetic Candidate",
            "location": None,
            "phone": None,
            "email": None,
            "github_url": None,
        },
        "sections": [
            {
                "id": "summary",
                "ordinal": 0,
                "heading": "Summary",
                "kind": "summary",
                "items": [],
            }
        ],
    }


class _RouteCoordinator:
    def __init__(self, *, profile_id: str, session_id: str) -> None:
        self.profile_id = profile_id
        self.session_id = session_id
        self.prepare_error: TailoringError | None = None
        self.manual_error: TailoringError | None = None
        self.initial_calls: list[dict[str, Any]] = []
        self.ai_calls: list[dict[str, Any]] = []
        self.stream_calls: list[str] = []
        self.manual_calls: list[dict[str, Any]] = []

    async def prepare_session(self, **kwargs: Any) -> TailoringLaunch:
        if self.prepare_error is not None:
            raise self.prepare_error
        self.initial_calls.append(kwargs)
        return TailoringLaunch(
            session_id=self.session_id,
            run_id=new_uuid(),
            profile_id=self.profile_id,
        )

    async def prepare_ai_version(self, **kwargs: Any) -> TailoringLaunch:
        self.ai_calls.append(kwargs)
        return TailoringLaunch(
            session_id=self.session_id,
            run_id=new_uuid(),
            profile_id=self.profile_id,
        )

    async def stream_initial_version(self, launch: TailoringLaunch):
        self.stream_calls.append(launch.run_id)
        yield build_sse_event(
            "run_started",
            launch.run_id,
            {"state": "running", "resumed": False},
        )
        yield build_sse_event(
            "run_completed", launch.run_id, {"state": "completed"}
        )

    async def create_manual_version(
        self, **kwargs: Any
    ) -> TailoringVersionMutationResponse:
        if self.manual_error is not None:
            raise self.manual_error
        self.manual_calls.append(kwargs)
        return TailoringVersionMutationResponse(
            outcome="version_created",
            session_id=self.session_id,
            version_id=new_uuid(),
            version_number=2,
            currentness="current",
        )


def test_cv_tailoring_router_exposes_exact_authorized_endpoint_shapes() -> None:
    from app.api.cv_tailoring import router
    from app.schemas.cv_tailoring import (
        TailoringDeleteResponse,
        TailoringVersionMutationResponse,
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
    ] is TailoringVersionMutationResponse
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


def test_job_backed_session_persists_shared_display_label(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    from app.api.cv_tailoring import router
    from app.db.models.cv_documents import CVDocument as CVDocumentRow
    from app.repositories import jobs as jobs_repo
    from app.services.cv_tailoring import TailoringCoordinator
    from app.services.cv_tailoring_projection import project_outline
    from app.services.job_display import derive_saved_job_display_label
    from tests.support.graph_rebuild import extraction_payload
    from tests.unit.test_cv_tailoring_projection import _document, _profile

    async def _seed_and_prepare() -> tuple[CVTailoringDeps, str, str, Any]:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        storage = TailoringArtifactStorage(tmp_path / "job-backed-files")
        async with factory() as session:
            attachment = Attachment(
                file_hash="c" * 64,
                original_name="job-backed.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                page_count=1,
                storage_path=f"{new_uuid()}.pdf",
                state="active",
            )
            session.add(attachment)
            await session.flush()
            profile_model = _profile()
            document = _document().model_copy(
                update={"attachment_id": attachment.id}
            )
            profile = Profile(
                attachment_id=attachment.id,
                display_name="Synthetic Candidate",
                profile_json=profile_model.model_dump(mode="json"),
                location=profile_model.location,
                extraction_version="cv-document-v1",
                source_hash="source-revision-a",
                state="ready",
            )
            session.add(profile)
            session.add(
                CVDocumentRow(
                    attachment_id=attachment.id,
                    document_json=document.model_dump(mode="json"),
                    profile_json=profile_model.model_dump(mode="json"),
                    outline_json={"sections": project_outline(document)},
                    extraction_version="cv-document-v1",
                    source_hash="source-revision-a",
                )
            )
            await session.flush()
            await workspace_repo.set_active_profile_id(session, profile.id)

            job = await jobs_repo.create_text_job(
                session,
                raw_content="Synthetic Role at Lab.",
                raw_content_hash="job-backed-label-hash",
            )
            await jobs_repo.mark_processing(session, job.id)
            extraction = extraction_payload()
            extraction.update(
                {
                    "title": "Synthetic Role",
                    "company": "Lab",
                    "summary": "Build trusted systems.",
                }
            )
            processed = await jobs_repo.mark_processed(
                session,
                job.id,
                extraction_json=extraction,
                jd_quality="full",
                embedding_json=[0.01 + (index * 1e-6) for index in range(1536)],
                embedding_model="text-embedding-3-small",
                embedding_dimensions=1536,
            )
            expected_label = derive_saved_job_display_label(
                title=extraction["title"],
                company=extraction["company"],
                summary=extraction["summary"],
                saved_at=processed.created_at,
            )
            await session.commit()

        coordinator = TailoringCoordinator(
            session_factory=factory,
            storage=storage,
            settings=SimpleNamespace(CV_TAILOR_MAX_INSTRUCTION_CHARS=4_000),
            sqlite_path=migrated_sqlite,
        )
        launch = await coordinator.prepare_session(
            profile_id=profile.id,
            job_id=job.id,
            instruction="",
            parent_run_id=None,
        )
        async with factory() as session:
            persisted = await tailoring_repo.get_session(session, launch.session_id)
            assert persisted is not None
            assert persisted.job_label_json == {
                "title": "Synthetic Role",
                "company": "Lab",
                "display_label": expected_label,
            }
        return (
            CVTailoringDeps(
                coordinator=coordinator,
                storage=storage,
                settings=SimpleNamespace(SQLITE_PATH=migrated_sqlite),
                session_factory=factory,
            ),
            launch.session_id,
            expected_label,
            engine,
        )

    deps, session_id, expected_label, engine = run_async(_seed_and_prepare())
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_cv_tailoring_deps] = lambda: deps
    try:
        with TestClient(app) as client:
            response = client.get("/api/cv-tailoring/sessions")
            assert response.status_code == 200
            item = response.json()["items"][0]
            assert item["id"] == session_id
            assert item["job_label"]["display_label"] == expected_label
    finally:
        run_async(engine.dispose())


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


def test_direct_routes_enforce_transport_ownership_and_artifact_contracts(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    from app.api.cv_tailoring import router
    from app.schemas.cv_tailoring import CV_TAILORING_SESSION_HEADER

    async def _seed() -> tuple[
        CVTailoringDeps,
        _RouteCoordinator,
        str,
        str,
        str,
        Any,
    ]:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        storage = TailoringArtifactStorage(tmp_path / "route-files")
        async with factory() as session:
            attachment = Attachment(
                file_hash="a" * 64,
                original_name="active.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                page_count=1,
                storage_path=f"{new_uuid()}.pdf",
                state="active",
            )
            session.add(attachment)
            await session.flush()
            profile = Profile(
                attachment_id=attachment.id,
                display_name="Synthetic Candidate",
                profile_json={"full_name": "Synthetic Candidate"},
                location=None,
                extraction_version="cv-document-v1",
                source_hash="source-active",
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
            tex_bytes = b"synthetic tex"
            pdf_bytes = b"%PDF-1.4 synthetic route"
            (staging / "resume.tex").write_bytes(tex_bytes)
            (staging / "resume.pdf").write_bytes(pdf_bytes)
            paths = storage.promote(
                profile_id=profile.id,
                session_id=owner.id,
                version_id=version_id,
                staged_tex=staging / "resume.tex",
                staged_pdf=staging / "resume.pdf",
            )
            await tailoring_repo.create_version_cas(
                session,
                session_id=owner.id,
                expected_latest_version_number=0,
                expected_parent_version_id=None,
                version=CVTailoringVersionWrite(
                    id=version_id,
                    parent_version_id=None,
                    created_by="ai",
                    content_json=_content(),
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

            other_attachment = Attachment(
                file_hash="b" * 64,
                original_name="other.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                page_count=1,
                storage_path=f"{new_uuid()}.pdf",
                state="archived",
            )
            session.add(other_attachment)
            await session.flush()
            other_profile = Profile(
                attachment_id=other_attachment.id,
                display_name="Other Candidate",
                profile_json={"full_name": "Other Candidate"},
                location=None,
                extraction_version="cv-document-v1",
                source_hash="source-other",
                state="ready",
            )
            session.add(other_profile)
            await session.flush()
            other_owner = await tailoring_repo.create_session(
                session,
                profile_id=other_profile.id,
                source_attachment_id=other_attachment.id,
                source_hash=other_profile.source_hash,
                profile_updated_at=other_profile.updated_at,
                job_id=None,
                job_updated_at=None,
                job_label_json=None,
                instruction="Other tailoring",
                template_version="latex-cv-v1",
            )
            await session.commit()

        coordinator = _RouteCoordinator(
            profile_id=profile.id, session_id=owner.id
        )
        deps = CVTailoringDeps(
            coordinator=cast(Any, coordinator),
            storage=storage,
            settings=cast(Any, SimpleNamespace(SQLITE_PATH=migrated_sqlite)),
            session_factory=factory,
        )
        return deps, coordinator, owner.id, other_owner.id, version_id, engine

    deps, coordinator, owner_id, other_owner_id, version_id, engine = run_async(
        _seed()
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_cv_tailoring_deps] = lambda: deps
    try:
        with TestClient(app) as client:
            malformed = client.post(
                "/api/cv-tailoring/sessions",
                json={"job_id": None, "instruction": "Tailor", "raw_jd": "no"},
            )
            assert malformed.status_code == 422
            assert coordinator.initial_calls == []

            created = client.post(
                "/api/cv-tailoring/sessions",
                json={"job_id": None, "instruction": "Tailor"},
            )
            assert created.status_code == 200
            assert created.headers[CV_TAILORING_SESSION_HEADER] == owner_id
            assert created.text.index("event: run_started") < created.text.index(
                "event: run_completed"
            )

            coordinator.prepare_error = TailoringError(
                "JOB_NOT_SCORABLE", "Selected Job is not scorable"
            )
            rejected = client.post(
                "/api/cv-tailoring/sessions",
                json={"job_id": None, "instruction": "Tailor"},
            )
            assert rejected.status_code == 409
            assert rejected.json()["detail"]["code"] == "JOB_NOT_SCORABLE"
            coordinator.prepare_error = None

            listed = client.get("/api/cv-tailoring/sessions")
            assert listed.status_code == 200
            assert [item["id"] for item in listed.json()["items"]] == [owner_id]

            detail = client.get(f"/api/cv-tailoring/sessions/{owner_id}")
            assert detail.status_code == 200
            assert detail.json()["selected_version"]["id"] == version_id
            assert detail.json()["content"] == _content()
            assert client.get(
                f"/api/cv-tailoring/sessions/{other_owner_id}"
            ).status_code == 404
            assert client.get(
                "/api/cv-tailoring/sessions/not-a-uuid"
            ).status_code == 422

            retried = client.post(
                f"/api/cv-tailoring/sessions/{owner_id}/ai-versions",
                json={
                    "parent_version_id": None,
                    "instruction": "",
                    "target_section_ids": [],
                },
            )
            assert retried.status_code == 200
            assert coordinator.ai_calls[-1] == {
                "session_id": owner_id,
                "parent_version_id": None,
                "instruction": "",
                "target_section_ids": [],
            }

            manual = client.post(
                f"/api/cv-tailoring/sessions/{owner_id}/manual-versions",
                json={"parent_version_id": version_id, "content": _content()},
            )
            assert manual.status_code == 200
            assert manual.json()["outcome"] == "version_created"
            assert manual.json()["session_id"] == owner_id
            assert coordinator.manual_calls[-1]["parent_version_id"] == version_id

            coordinator.manual_error = TailoringError(
                "TAILORING_GROUNDING_FAILED",
                "Tailored content is not source-supported",
                user_issues=(TailoringUserIssue(section_id="summary", section_heading="Summary", item_index=None, field="section", reason="required_source_missing"),),
            )
            rejected_manual = client.post(
                f"/api/cv-tailoring/sessions/{owner_id}/manual-versions",
                json={"parent_version_id": version_id, "content": _content()},
            )
            assert rejected_manual.status_code == 422
            assert rejected_manual.json()["detail"]["issues"] == [{"section_id": "summary", "section_heading": "Summary", "item_index": None, "field": "section", "reason": "required_source_missing"}]
            assert "provider" not in rejected_manual.text
            coordinator.manual_error = None

            streams_before_reads = list(coordinator.stream_calls)
            source = client.get(
                f"/api/cv-tailoring/versions/{version_id}/source"
            )
            assert source.status_code == 200
            assert source.content == b"synthetic tex"
            assert source.headers["content-type"] == "text/x-tex; charset=utf-8"
            assert source.headers["content-disposition"] == (
                'attachment; filename="resume-v1.tex"'
            )
            assert source.headers["content-length"] == str(len(source.content))
            assert source.headers["x-content-type-options"] == "nosniff"
            pdf = client.get(f"/api/cv-tailoring/versions/{version_id}/pdf")
            assert pdf.status_code == 200
            assert pdf.content == b"%PDF-1.4 synthetic route"
            assert pdf.headers["content-type"] == "application/pdf"
            assert pdf.headers["content-disposition"] == (
                'inline; filename="resume-v1.pdf"'
            )
            assert pdf.headers["content-length"] == str(len(pdf.content))
            assert pdf.headers["x-content-type-options"] == "nosniff"
            assert coordinator.stream_calls == streams_before_reads

            deleted = client.delete(f"/api/cv-tailoring/sessions/{owner_id}")
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted_session_id": owner_id}
            assert client.get(
                f"/api/cv-tailoring/versions/{version_id}/pdf"
            ).status_code == 404
    finally:
        run_async(engine.dispose())
