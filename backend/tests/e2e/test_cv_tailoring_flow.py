"""Synthetic acceptance flow for the bounded CV-tailoring coordinator.

This test deliberately uses only local structured fakes and synthetic source
models.  The format-reference marker is test-only: it is never accepted by a
coordinator entry point or passed to an invoker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentActivity, ToolExecution
from app.db.models.cv_documents import CVDocument as CVDocumentRow
from app.db.models.cv_tailoring import CVTailoringVersion
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import cv_tailoring as tailoring_repo
from app.schemas.cv_tailoring import TailoredCVContent
from app.services.cv_document_projection import project_outline
from app.services.cv_tailoring import (
    TAILORING_PARENT_CONFLICT,
    TAILORING_SOURCE_STALE,
    TailoringCoordinator,
    TailoringError,
)
from app.services.cv_tailoring_compiler import TailoringCompileResult
from app.services.cv_tailoring_projection import project_tailoring_baseline
from app.storage.cv_tailoring import TailoringArtifactStorage
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from tests.integration.test_cv_tailoring_coordinator import (
    _Invoker,
    _Settings,
    _patch_for_summary,
)
from tests.support.db_migration import run_async, session_factory
from tests.unit.test_cv_tailoring_projection import _document, _profile


async def _pdf_compile(
    tex_source: str, *, staging_dir: Path, settings: Any
) -> TailoringCompileResult:
    """A local compiler fake that writes a real one-page PDF, never a log."""
    del settings
    tex_path = staging_dir / "resume.tex"
    pdf_path = staging_dir / "resume.pdf"
    tex_path.write_text(tex_source, encoding="utf-8", newline="\n")
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as stream:
        writer.write(stream)
    return TailoringCompileResult(
        tex_path=tex_path,
        pdf_path=pdf_path,
        tex_sha256=hashlib.sha256(tex_path.read_bytes()).hexdigest(),
        pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        page_count=1,
        page_warning=None,
    )


class _FailOnceStorage(TailoringArtifactStorage):
    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir)
        self.calls = 0

    def delete_session(self, *, profile_id: str, session_id: str) -> bool:
        self.calls += 1
        return self.calls > 1 and super().delete_session(
            profile_id=profile_id, session_id=session_id
        )


async def _seed_ready_source(factory) -> tuple[str, Any, Any]:
    document = _document()
    summary = document.sections[0]
    document = document.model_copy(
        update={
            "sections": [
                summary.model_copy(
                    update={
                        "entries": [
                            summary.entries[0].model_copy(
                                update={"body": "Synthetic % & $ source text"}
                            )
                        ]
                    }
                ),
                *document.sections[1:],
            ]
        }
    )
    profile_model = _profile().model_copy(
        update={"github_url": "https://github.com/synthetic-candidate"}
    )
    async with factory() as session:
        attachment = Attachment(
            file_hash="a" * 64,
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
        await session.commit()
        return profile.id, document, profile_model


def test_synthetic_tailoring_acceptance_chain_privacy_and_recovery(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    """Exercise immutable versions, stale/CAS safety, artifacts, and cleanup."""

    async def _body() -> None:
        format_reference = {"marker": "REFERENCE_ONLY_SENTINEL_7429"}
        marker = format_reference["marker"]
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        storage = _FailOnceStorage(tmp_path / "files")
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            legacy = _profile().model_copy(
                update={"phone": None, "email": None, "github_url": None}
            )
            legacy_header = project_tailoring_baseline(
                document, profile=legacy, source_hash="source-revision-a"
            ).content.header
            assert legacy_header.phone is legacy_header.email is legacy_header.github_url is None

            invoker = _Invoker(_patch_for_summary(document, profile_model))
            compiler_log_capture: list[str] = []

            async def compile_with_sanitized_capture(
                tex_source: str, *, staging_dir: Path, settings: Any
            ) -> TailoringCompileResult:
                compiler_log_capture.append("synthetic compiler completed")
                return await _pdf_compile(
                    tex_source, staging_dir=staging_dir, settings=settings
                )

            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=storage,
                settings=_Settings(),
                invoker=invoker,
                sqlite_path=migrated_sqlite,
                compiler=compile_with_sanitized_capture,
            )
            initial = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Prioritize the synthetic role summary",
                parent_run_id=None,
            )
            initial_events = [
                event async for event in coordinator.stream_initial_version(initial)
            ]
            assert initial_events[-1].event == "run_completed"
            first = await coordinator.get_completed_version(initial)

            async with factory() as session:
                first_row = await tailoring_repo.get_version(session, first.version_id)
                profile = await session.get(Profile, profile_id)
                source = await session.scalar(
                    select(CVDocumentRow).where(CVDocumentRow.attachment_id == profile.attachment_id)
                )
                assert first_row is not None and profile is not None and source is not None
                profile_json_before = json.dumps(profile.profile_json, sort_keys=True)
                document_json_before = json.dumps(source.document_json, sort_keys=True)

            later = await coordinator.prepare_ai_version(
                session_id=initial.session_id,
                parent_version_id=first.version_id,
                instruction="Keep only the selected section concise",
                target_section_ids=["summary"],
            )
            assert [
                event async for event in coordinator.stream_initial_version(later)
            ][-1].event == "run_completed"
            second = await coordinator.get_completed_version(later)
            async with factory() as session:
                second_row = await tailoring_repo.get_version(session, second.version_id)
                assert second_row is not None
                second_content = TailoredCVContent.model_validate(second_row.content_json)

            third = await coordinator.create_manual_version(
                session_id=initial.session_id,
                parent_version_id=second.version_id,
                content=second_content,
            )
            assert third.version_number == 3
            with pytest.raises(TailoringError) as conflict:
                await coordinator.create_manual_version(
                    session_id=initial.session_id,
                    parent_version_id=first.version_id,
                    content=second_content,
                )
            assert conflict.value.code == TAILORING_PARENT_CONFLICT

            async with factory() as session:
                versions = await tailoring_repo.list_versions(session, initial.session_id)
                assert [version.version_number for version in versions] == [1, 2, 3]
                assert [version.created_by for version in versions] == ["ai", "ai", "user"]
                assert [version.parent_version_id for version in versions] == [
                    None,
                    versions[0].id,
                    versions[1].id,
                ]
                profile = await session.get(Profile, profile_id)
                source = await session.scalar(
                    select(CVDocumentRow).where(CVDocumentRow.attachment_id == profile.attachment_id)
                )
                assert json.dumps(profile.profile_json, sort_keys=True) == profile_json_before
                assert json.dumps(source.document_json, sort_keys=True) == document_json_before
                profile.updated_at = utc_now().replace(microsecond=0)
                await session.commit()

            with pytest.raises(TailoringError) as stale:
                await coordinator.create_manual_version(
                    session_id=initial.session_id,
                    parent_version_id=third.version_id,
                    content=second_content,
                )
            assert stale.value.code == TAILORING_SOURCE_STALE

            tex_path = storage.resolve_artifact(relative_path=versions[-1].tex_relative_path)
            pdf_path = storage.resolve_artifact(relative_path=versions[-1].pdf_relative_path)
            tex = tex_path.read_text(encoding="utf-8")
            assert "\\documentclass[11pt]{article}" in tex
            assert "GitHub: synthetic-candidate" in tex
            assert "Synthetic \\% \\& \\$ source text" in tex
            assert PdfReader(str(pdf_path)).pages and versions[-1].page_count == 1

            captured = "\n".join(
                str(getattr(message, "content", message))
                for messages in invoker.messages
                for message in messages
            )
            assert "Volunteer mentor" not in captured
            assert marker not in captured
            serialized_events = "\n".join(str(event.payload) for event in initial_events)
            pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
            assert marker not in (
                serialized_events
                + tex
                + pdf_text
                + "\n".join(compiler_log_capture)
                + migrated_sqlite.read_bytes().decode("latin-1")
            )
            async with factory() as session:
                activities = (await session.execute(select(AgentActivity))).scalars().all()
                tool_results = (await session.execute(select(ToolExecution))).scalars().all()
                assert marker not in str(activities)
                assert marker not in str(tool_results)

            from app.services.cv_tailoring_deletion import (
                TAILORING_DELETE_FAILED,
                delete_tailoring_session,
            )

            with pytest.raises(TailoringError) as deletion:
                await delete_tailoring_session(
                    session_id=initial.session_id,
                    session_factory=factory,
                    sqlite_path=migrated_sqlite,
                    storage=storage,
                )
            assert deletion.value.code == TAILORING_DELETE_FAILED
            result = await delete_tailoring_session(
                session_id=initial.session_id,
                session_factory=factory,
                sqlite_path=migrated_sqlite,
                storage=storage,
            )
            assert result.deleted_session_id == initial.session_id
            assert not tex_path.exists() and not pdf_path.exists()
        finally:
            await engine.dispose()

    run_async(_body())
