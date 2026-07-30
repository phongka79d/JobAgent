"""Synthetic cross-layer acceptance for fixed-template CV tailoring.

Only repository-authored synthetic data and local structured-provider/compiler
fakes are used.  The tests exercise production service, tool, persistence,
download, and deletion boundaries without adding test-only production seams.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from app.api.cv_tailoring import _download
from app.api.dependencies import CVTailoringDeps
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentActivity, AgentRun, ToolExecution
from app.db.models.cv_documents import CVDocument as CVDocumentRow
from app.db.models.job_evaluations import JobEvaluation
from app.db.models.jobs import JobPost
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.cv_tailoring import TailoredCVContent
from app.schemas.profile import CandidateProfile
from app.schemas.tools import ToolResult
from app.services.cv_document_projection import project_outline
from app.services.cv_tailoring import (
    TAILORING_PARENT_CONFLICT,
    TAILORING_SOURCE_STALE,
    TailoringCoordinator,
    TailoringError,
)
from app.services.cv_tailoring_compiler import TailoringCompileResult
from app.services.cv_tailoring_deletion import (
    TAILORING_DELETE_FAILED,
    delete_tailoring_session,
)
from app.services.job_deletion import delete_job
from app.services.pdf_extraction import PdfTextExtraction
from app.services.profile_approval import commit_approved_draft
from app.services.profile_deletion import ProfileDeletionError, delete_profile
from app.services.profile_drafts import propose_profile_from_cv
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.storage.cv_tailoring import TailoringArtifactStorage
from app.tools.cv_tailoring import build_create_tailored_cv_tool
from app.tools.registry import production_registry
from pypdf import PdfReader, PdfWriter
from sqlalchemy import func, select

from tests.fakes.graph_rebuild import FakeNeo4jDriver
from tests.integration.test_cv_tailoring_coordinator import (
    _Invoker,
    _patch_for_summary,
    _Settings,
)
from tests.integration.test_job_deletion import ExactJobFakeDriver
from tests.integration.test_profile_approval import _skills_fixture
from tests.support.db_migration import run_async, session_factory
from tests.unit.test_cv_tailoring_projection import _document, _profile
from tests.unit.test_profile_extraction import ContactDocumentInvoker


@dataclass(frozen=True, slots=True)
class _SourceSeed:
    profile_id: str
    attachment_id: str
    conversation_id: str
    document: Any
    profile: CandidateProfile


class _IdentityContactInvoker(ContactDocumentInvoker):
    """Reuse the contact fake while providing a grounded synthetic name."""

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
        if schema_name in {"batch", "consolidate"}:
            return result.model_copy(update={"full_name": "Synthetic Candidate"})
        return result


class _IdentityNoContactInvoker(_IdentityContactInvoker):
    """Document fake for an approved profile whose optional contacts are absent."""

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
        if schema_name == "batch":
            return result.model_copy(update={"contacts": []})
        return result


class _FailOnceStorage(TailoringArtifactStorage):
    def __init__(self, files_dir: Path) -> None:
        super().__init__(files_dir)
        self.calls = 0

    def delete_session(self, *, profile_id: str, session_id: str) -> bool:
        self.calls += 1
        return self.calls > 1 and super().delete_session(
            profile_id=profile_id,
            session_id=session_id,
        )


async def _pdf_compile(
    tex_source: str,
    *,
    staging_dir: Path,
    settings: Any,
) -> TailoringCompileResult:
    del settings
    logging.getLogger("app.services.cv_tailoring.acceptance").info(
        "synthetic compiler completed"
    )
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


def _synthetic_document(attachment_id: str) -> Any:
    document = _document().model_copy(update={"attachment_id": attachment_id})
    summary = document.sections[0]
    escaped = summary.entries[0].model_copy(
        update={"body": "Synthetic % & $ # _ source text"}
    )
    return document.model_copy(
        update={
            "sections": [
                summary.model_copy(update={"entries": [escaped]}),
                *document.sections[1:],
            ]
        }
    )


async def _seed_ready_source(
    factory: Any,
    files_dir: Path,
    *,
    github_url: str | None,
    active: bool,
    omit_contact_keys: bool = False,
) -> _SourceSeed:
    attachment_id = new_uuid()
    storage = AttachmentStorage(files_dir)
    source_bytes = f"%PDF-1.4 synthetic {attachment_id}".encode()
    relative = storage.write_bytes(attachment_id, source_bytes)
    document = _synthetic_document(attachment_id)
    profile_model = _profile().model_copy(update={"github_url": github_url})
    profile_json = profile_model.model_dump(mode="json")
    if omit_contact_keys:
        for key in ("phone", "email", "github_url"):
            profile_json.pop(key, None)

    async with factory() as session:
        attachment = Attachment(
            id=attachment_id,
            file_hash=hashlib.sha256(source_bytes).hexdigest(),
            original_name="synthetic.pdf",
            mime_type="application/pdf",
            size_bytes=len(source_bytes),
            page_count=1,
            storage_path=relative,
            state="active" if active else "archived",
        )
        session.add(attachment)
        profile = Profile(
            attachment_id=attachment.id,
            display_name="Synthetic Candidate",
            profile_json=profile_json,
            location=profile_model.location,
            extraction_version="cv-document-v1",
            source_hash="source-revision-a",
            state="ready",
        )
        session.add(profile)
        await session.flush()
        session.add(
            CVDocumentRow(
                attachment_id=attachment.id,
                document_json=document.model_dump(mode="json"),
                profile_json=profile_json,
                outline_json={"sections": project_outline(document)},
                extraction_version="cv-document-v1",
                source_hash="source-revision-a",
            )
        )
        await profiles_repo.upsert_profile_preferences(
            session,
            profile_id=profile.id,
            preferences_json={
                "target_roles": [],
                "preferred_locations": [],
                "acceptable_work_modes": [],
                "target_seniority": [],
            },
        )
        conversation = await conversations_repo.create_for_profile(
            session,
            profile_id=profile.id,
        )
        if active:
            await workspace_repo.set_active_profile_id(session, profile.id)
        await session.commit()
        return _SourceSeed(
            profile_id=profile.id,
            attachment_id=attachment.id,
            conversation_id=conversation.id,
            document=document,
            profile=profile_model,
        )


def _job_extraction(label: str) -> dict[str, Any]:
    return {
        "title": f"{label.title()} Engineer",
        "company": "Synthetic Civic Lab",
        "summary": "Build source-grounded public-service systems.",
        "responsibilities": ["Maintain synthetic services."],
        "required_skills": [],
        "preferred_skills": [],
        "seniority": "mid",
        "min_experience_years": 2.0,
        "max_experience_years": 4.0,
        "location": "Ha Noi",
        "work_mode": "hybrid",
        "extraction_confidence": 0.9,
    }


async def _seed_scorable_job(factory: Any, quality: str) -> str:
    async with factory() as session:
        row = await jobs_repo.create_text_job(
            session,
            raw_content=f"Synthetic {quality} JD",
            raw_content_hash=hashlib.sha256(quality.encode()).hexdigest(),
        )
        await jobs_repo.mark_processing(session, row.id)
        await jobs_repo.mark_processed(
            session,
            row.id,
            extraction_json=_job_extraction(quality),
            jd_quality=quality,
            embedding_json=[0.1, 0.2],
            embedding_model="synthetic-embedding",
            embedding_dimensions=2,
        )
        await session.commit()
        return row.id


async def _initial_version(
    coordinator: TailoringCoordinator,
    *,
    profile_id: str,
    job_id: str | None,
    instruction: str,
) -> tuple[str, Any]:
    launch = await coordinator.prepare_session(
        profile_id=profile_id,
        job_id=job_id,
        instruction=instruction,
        parent_run_id=None,
    )
    events = [event async for event in coordinator.stream_initial_version(launch)]
    assert events[-1].event == "run_completed"
    created = await coordinator.get_completed_version(launch)
    return launch.session_id, created


def _tool_result(raw: Any) -> ToolResult:
    if hasattr(raw, "content"):
        raw = raw.content
    if isinstance(raw, str):
        raw = json.loads(raw)
    return ToolResult.model_validate(raw)


async def _download_bytes(
    deps: CVTailoringDeps,
    *,
    version_id: str,
    kind: str,
) -> bytes:
    response = await _download(version_id, kind=kind, deps=deps)
    return b"".join([chunk async for chunk in response.body_iterator])


def test_reextract_review_save_profile_and_optional_contacts(
    migrated_sqlite: Path,
    tmp_path: Path,
) -> None:
    """Legacy nullable contacts become durable only after explicit approval."""

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        files_dir = tmp_path / "files"
        storage = AttachmentStorage(files_dir)
        normalizer = SkillNormalizer.from_path(_skills_fixture())
        try:
            owner = await _seed_ready_source(
                factory,
                files_dir,
                github_url=None,
                active=True,
                omit_contact_keys=True,
            )
            async with factory() as session:
                row = await session.get(Profile, owner.profile_id)
                assert row is not None
                legacy = CandidateProfile.model_validate(row.profile_json)
                assert legacy.phone is None
                assert legacy.email is None
                assert legacy.github_url is None

            text = (
                "Synthetic Candidate Python. Phone +1 (202) 555-0147. "
                "Email person@example.test and alternate@example.test. "
                "GitHub https://github.com/synthetic-user."
            )

            def extract_text(_source: object) -> PdfTextExtraction:
                return PdfTextExtraction(
                    page_count=1,
                    normal_text=text,
                    layout_text=text,
                    normal_is_meaningful=True,
                    layout_is_meaningful=True,
                )

            proposed = await propose_profile_from_cv(
                attachment_id=owner.attachment_id,
                target_profile_id=owner.profile_id,
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                invoker=_IdentityContactInvoker(),
                extract_text_fn=extract_text,
                reprocess=True,
            )
            assert proposed.tool_result.ok is True
            assert proposed.draft is not None
            assert (
                proposed.draft.candidate_profile.github_url
                == "https://github.com/synthetic-user"
            )
            async with factory() as session:
                unchanged = await session.get(Profile, owner.profile_id)
                assert unchanged is not None
                assert unchanged.profile_json.get("github_url") is None

            async def no_graph_sync() -> None:
                return None

            committed = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                expected_profile_id=owner.profile_id,
                sync_fn=no_graph_sync,
            )
            assert committed.ok is True
            async with factory() as session:
                saved = await session.get(Profile, owner.profile_id)
                assert saved is not None and saved.state == "ready"
                assert (
                    saved.profile_json["github_url"]
                    == "https://github.com/synthetic-user"
                )

            second = await _seed_ready_source(
                factory,
                files_dir,
                github_url=None,
                active=False,
            )
            second_proposed = await propose_profile_from_cv(
                attachment_id=second.attachment_id,
                target_profile_id=second.profile_id,
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                invoker=_IdentityNoContactInvoker(),
                extract_text_fn=extract_text,
                reprocess=True,
            )
            assert second_proposed.tool_result.ok is True
            assert second_proposed.draft is not None
            assert second_proposed.draft.candidate_profile.github_url is None
            second_committed = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=normalizer,
                expected_profile_id=second.profile_id,
                sync_fn=no_graph_sync,
            )
            assert second_committed.ok is True
            async with factory() as session:
                second_row = await session.get(Profile, second.profile_id)
                assert second_row is not None and second_row.state == "ready"
                absent = CandidateProfile.model_validate(second_row.profile_json)
                assert absent.github_url is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_cross_layer_tool_jobs_versions_staleness_deletion_and_privacy(
    migrated_sqlite: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exercise the complete synthetic acceptance matrix through real owners."""

    async def _body() -> None:
        format_reference = {"marker": "REFERENCE_ONLY_SENTINEL_7429"}
        marker = format_reference["marker"]
        caplog.set_level(logging.INFO, logger="app")
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        files_dir = tmp_path / "files"
        attachment_storage = AttachmentStorage(files_dir)
        storage = _FailOnceStorage(files_dir)
        try:
            source = await _seed_ready_source(
                factory,
                files_dir,
                github_url="https://github.com/synthetic-candidate",
                active=True,
            )
            full_job_id = await _seed_scorable_job(factory, "full")
            partial_job_id = await _seed_scorable_job(factory, "partial")
            invoker = _Invoker(_patch_for_summary(source.document, source.profile))
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=storage,
                settings=_Settings(),
                invoker=invoker,
                sqlite_path=migrated_sqlite,
                compiler=_pdf_compile,
            )
            deps = CVTailoringDeps(
                coordinator=coordinator,
                storage=storage,
                settings=cast(Any, object()),
                session_factory=factory,
            )

            async with factory() as session:
                profile = await session.get(Profile, source.profile_id)
                document = await session.get(CVDocumentRow, source.attachment_id)
                preferences = await profiles_repo.get_profile_preferences(
                    session,
                    source.profile_id,
                )
                jobs = (
                    (await session.execute(select(JobPost).order_by(JobPost.id.asc())))
                    .scalars()
                    .all()
                )
                profile_json_before = json.dumps(
                    profile.profile_json,
                    sort_keys=True,
                )
                document_json_before = json.dumps(
                    document.document_json,
                    sort_keys=True,
                )
                preferences_before = json.dumps(
                    preferences.preferences_json,
                    sort_keys=True,
                )
                jobs_before = {
                    row.id: json.dumps(row.extraction_json, sort_keys=True)
                    for row in jobs
                }
                evaluation_count_before = int(
                    await session.scalar(
                        select(func.count()).select_from(JobEvaluation)
                    )
                    or 0
                )
                user = await messages_repo.insert_message(
                    session,
                    conversation_id=source.conversation_id,
                    role="user",
                    content="Create a synthetic tailored CV",
                )
                chat_run = await runs_repo.create_run(
                    session,
                    user_message_id=user.id,
                )
                await session.commit()
                chat_run_id = chat_run.id

            monkeypatch.setattr(
                "app.services.tool_execution.get_session_factory",
                lambda: factory,
            )
            tool = build_create_tailored_cv_tool(coordinator=coordinator)
            raw_result = await tool.ainvoke(
                {
                    "type": "tool_call",
                    "id": "call-synthetic-tailor",
                    "name": tool.name,
                    "args": {
                        "instruction": "Prioritize the synthetic summary",
                        "state": {
                            "run_id": chat_run_id,
                            "profile_id": source.profile_id,
                            "selected_job_id": None,
                        },
                    },
                }
            )
            tool_result = _tool_result(raw_result)
            assert tool_result.ok is True and tool_result.data is not None
            instruction_session_id = str(tool_result.data["session_id"])
            first_version_id = str(tool_result.data["version_id"])

            async with factory() as session:
                await runs_repo.complete_run(session, chat_run_id)
                first = await tailoring_repo.get_version(
                    session,
                    first_version_id,
                )
                assert first is not None
                assert first.provenance_json["targeted_section_ids"] == ["summary"]
                assert first.provenance_json["facts"]
                first_content = TailoredCVContent.model_validate(first.content_json)
                await session.commit()

            later = await coordinator.prepare_ai_version(
                session_id=instruction_session_id,
                parent_version_id=first_version_id,
                instruction="Keep the selected section concise",
                target_section_ids=["summary"],
            )
            later_events = [
                event async for event in coordinator.stream_initial_version(later)
            ]
            assert later_events[-1].event == "run_completed"
            assert later_events[-1].payload.outcome == "no_change"

            changed_content = first_content.model_copy(
                update={
                    "sections": [
                        first_content.sections[0].model_copy(
                            update={
                                "items": [
                                    first_content.sections[0]
                                    .items[0]
                                    .model_copy(
                                        update={
                                            "body": first_content.sections[0]
                                            .items[0]
                                            .body.model_copy(
                                                update={
                                                    "text": (
                                                        "Synthetic source-supported "
                                                        "summary edit"
                                                    )
                                                }
                                            )
                                        }
                                    )
                                ]
                            }
                        ),
                        *first_content.sections[1:],
                    ]
                }
            )
            third = await coordinator.create_manual_version(
                session_id=instruction_session_id,
                parent_version_id=first_version_id,
                content=changed_content,
            )
            with pytest.raises(TailoringError) as conflict:
                await coordinator.create_manual_version(
                    session_id=instruction_session_id,
                    parent_version_id=first_version_id,
                    content=changed_content,
                )
            assert conflict.value.code == TAILORING_PARENT_CONFLICT

            full_session_id, full_created = await _initial_version(
                coordinator,
                profile_id=source.profile_id,
                job_id=full_job_id,
                instruction="",
            )
            partial_session_id, partial_created = await _initial_version(
                coordinator,
                profile_id=source.profile_id,
                job_id=partial_job_id,
                instruction="",
            )
            assert full_created.version_number == 1
            assert partial_created.version_number == 1

            async with factory() as session:
                chain = await tailoring_repo.list_versions(
                    session,
                    instruction_session_id,
                )
                assert [row.version_number for row in chain] == [1, 2]
                assert [row.created_by for row in chain] == ["ai", "user"]
                assert [row.parent_version_id for row in chain] == [
                    None,
                    chain[0].id,
                ]
                full_row = await tailoring_repo.get_version(
                    session,
                    full_created.version_id,
                )
                partial_row = await tailoring_repo.get_version(
                    session,
                    partial_created.version_id,
                )
                full_session = await tailoring_repo.get_session(
                    session, full_session_id
                )
                assert full_session is not None
                assert full_session.job_label_json is not None
                assert full_session.job_label_json["display_label"] == (
                    "Full Engineer · Synthetic Civic Lab"
                )
                assert full_row is not None and partial_row is not None
                full_content = TailoredCVContent.model_validate(full_row.content_json)
                partial_content = TailoredCVContent.model_validate(
                    partial_row.content_json
                )

            tex_before = await _download_bytes(
                deps,
                version_id=full_created.version_id,
                kind="source",
            )
            pdf_before = await _download_bytes(
                deps,
                version_id=full_created.version_id,
                kind="pdf",
            )

            async with factory() as session:
                owner = await tailoring_repo.get_session(
                    session,
                    instruction_session_id,
                )
                profile = await session.get(Profile, source.profile_id)
                assert owner is not None and profile is not None
                profile.updated_at = utc_now() + timedelta(seconds=5)
                await session.commit()
                captured_profile_revision = owner.profile_updated_at
            with pytest.raises(TailoringError) as stale_profile:
                await coordinator.create_manual_version(
                    session_id=instruction_session_id,
                    parent_version_id=third.version_id,
                    content=changed_content,
                )
            assert stale_profile.value.code == TAILORING_SOURCE_STALE
            assert await _download_bytes(
                deps,
                version_id=third.version_id,
                kind="source",
            )
            async with factory() as session:
                profile = await session.get(Profile, source.profile_id)
                assert profile is not None
                profile.updated_at = captured_profile_revision
                await session.commit()

            async with factory() as session:
                document = await session.get(CVDocumentRow, source.attachment_id)
                assert document is not None
                document.source_hash = "source-revision-stale"
                await session.commit()
            with pytest.raises(TailoringError) as stale_cv:
                await coordinator.create_manual_version(
                    session_id=partial_session_id,
                    parent_version_id=partial_created.version_id,
                    content=partial_content,
                )
            assert stale_cv.value.code == TAILORING_SOURCE_STALE
            assert await _download_bytes(
                deps,
                version_id=partial_created.version_id,
                kind="pdf",
            )
            async with factory() as session:
                document = await session.get(CVDocumentRow, source.attachment_id)
                assert document is not None
                document.source_hash = "source-revision-a"
                await session.commit()

            async with factory() as session:
                full_job = await session.get(JobPost, full_job_id)
                assert full_job is not None
                full_job.updated_at = utc_now() + timedelta(seconds=5)
                await session.commit()
            with pytest.raises(TailoringError) as stale_job:
                await coordinator.create_manual_version(
                    session_id=full_session_id,
                    parent_version_id=full_created.version_id,
                    content=full_content,
                )
            assert stale_job.value.code == TAILORING_SOURCE_STALE
            assert (
                await _download_bytes(
                    deps,
                    version_id=full_created.version_id,
                    kind="source",
                )
                == tex_before
            )

            async with factory() as session:
                profile = await session.get(Profile, source.profile_id)
                document = await session.get(CVDocumentRow, source.attachment_id)
                preferences = await profiles_repo.get_profile_preferences(
                    session,
                    source.profile_id,
                )
                jobs = (
                    (await session.execute(select(JobPost).order_by(JobPost.id.asc())))
                    .scalars()
                    .all()
                )
                assert json.dumps(profile.profile_json, sort_keys=True) == (
                    profile_json_before
                )
                assert json.dumps(document.document_json, sort_keys=True) == (
                    document_json_before
                )
                assert json.dumps(preferences.preferences_json, sort_keys=True) == (
                    preferences_before
                )
                assert {
                    row.id: json.dumps(row.extraction_json, sort_keys=True)
                    for row in jobs
                } == jobs_before
                assert (
                    int(
                        await session.scalar(
                            select(func.count()).select_from(JobEvaluation)
                        )
                        or 0
                    )
                    == evaluation_count_before
                )

            untouched_graph = FakeNeo4jDriver()
            assert untouched_graph.queries == []
            exact_job_graph = ExactJobFakeDriver(jobs={full_job_id})
            await delete_job(
                full_job_id,
                driver=exact_job_graph,
                session_factory=factory,
            )
            assert (
                await _download_bytes(
                    deps,
                    version_id=full_created.version_id,
                    kind="source",
                )
                == tex_before
            )
            assert (
                await _download_bytes(
                    deps,
                    version_id=full_created.version_id,
                    kind="pdf",
                )
                == pdf_before
            )

            with pytest.raises(TailoringError) as first_delete:
                await delete_tailoring_session(
                    session_id=partial_session_id,
                    session_factory=factory,
                    sqlite_path=migrated_sqlite,
                    storage=storage,
                )
            assert first_delete.value.code == TAILORING_DELETE_FAILED
            deleted = await delete_tailoring_session(
                session_id=partial_session_id,
                session_factory=factory,
                sqlite_path=migrated_sqlite,
                storage=storage,
            )
            assert deleted.deleted_session_id == partial_session_id

            tex_paths = list(storage.root.rglob("resume.tex"))
            pdf_paths = list(storage.root.rglob("resume.pdf"))
            assert tex_paths and pdf_paths
            tex_text = "\n".join(path.read_text(encoding="utf-8") for path in tex_paths)
            pdf_text = "\n".join(
                page.extract_text() or ""
                for path in pdf_paths
                for page in PdfReader(str(path)).pages
            )
            assert "\\documentclass[11pt]{article}" in tex_text
            assert "Synthetic \\% \\& \\$ \\# \\_ source text" in tex_text
            assert all(len(PdfReader(str(path)).pages) == 1 for path in pdf_paths)

            captured_prompts = "\n".join(
                str(getattr(message, "content", message))
                for messages in invoker.messages
                for message in messages
            )
            selection_prompt = "\n".join(
                str(getattr(message, "content", message))
                for message in invoker.messages[0]
            )
            selected_section_prompt = "\n".join(
                str(getattr(message, "content", message))
                for message in invoker.messages[1]
            )
            assert "Summary" in selection_prompt
            assert "Synthetic % & $ # _ source text" not in selection_prompt
            assert "Synthetic % & $ # _ source text" in selected_section_prompt
            assert "Volunteer mentor" not in selected_section_prompt
            assert "Volunteer mentor" not in captured_prompts
            assert marker not in captured_prompts
            assert marker not in tool_result.model_dump_json()
            async with factory() as session:
                tool_rows = (
                    (await session.execute(select(ToolExecution))).scalars().all()
                )
                activities = (
                    (await session.execute(select(AgentActivity))).scalars().all()
                )
                errors = (
                    (await session.execute(select(AgentRun.error_code))).scalars().all()
                )
                sqlite_json = json.dumps(
                    [
                        row.result_json
                        for row in tool_rows
                        if row.result_json is not None
                    ],
                    sort_keys=True,
                )
                assert marker not in sqlite_json
                assert marker not in str(activities)
                assert marker not in str(errors)
            assert marker not in tex_text
            assert marker not in pdf_text
            assert marker not in caplog.text
            assert any(
                record.name.startswith("app.services.cv_tailoring")
                for record in caplog.records
            )
            assert marker.encode() not in migrated_sqlite.read_bytes()

            expected_tools = [
                "propose_profile_from_cv",
                "propose_profile_update",
                "commit_profile_draft",
                "save_job",
                "query_jobs",
                "match_jobs",
                "read_active_cv",
                "create_tailored_cv",
            ]
            assert production_registry().tool_names() == expected_tools

            profile_artifact_root = storage.root / source.profile_id
            assert profile_artifact_root.is_dir()
            original_delete_session = TailoringArtifactStorage.delete_session
            cleanup_calls = 0

            def fail_first_profile_cleanup(
                instance: TailoringArtifactStorage,
                *,
                profile_id: str,
                session_id: str,
            ) -> bool:
                nonlocal cleanup_calls
                cleanup_calls += 1
                if cleanup_calls == 1:
                    return False
                return original_delete_session(
                    instance,
                    profile_id=profile_id,
                    session_id=session_id,
                )

            monkeypatch.setattr(
                TailoringArtifactStorage,
                "delete_session",
                fail_first_profile_cleanup,
            )
            with pytest.raises(ProfileDeletionError) as profile_delete_failed:
                await delete_profile(
                    profile_id=source.profile_id,
                    session_factory=factory,
                    storage=attachment_storage,
                    graph_driver=FakeNeo4jDriver(),
                    sqlite_path=migrated_sqlite,
                )
            assert profile_delete_failed.value.code == "PROFILE_DELETE_RETRYABLE"
            await delete_profile(
                profile_id=source.profile_id,
                session_factory=factory,
                storage=attachment_storage,
                graph_driver=FakeNeo4jDriver(),
                sqlite_path=migrated_sqlite,
            )
            assert cleanup_calls > 1
            assert not profile_artifact_root.exists()
            async with factory() as session:
                assert await session.get(Profile, source.profile_id) is None
                remaining = await tailoring_repo.list_sessions_for_profile(
                    session,
                    source.profile_id,
                )
                assert remaining == []
        finally:
            await engine.dispose()

    run_async(_body())
