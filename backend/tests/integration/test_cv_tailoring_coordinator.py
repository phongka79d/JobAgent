from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachments import Attachment
from app.db.models.chat import AgentRun
from app.db.models.cv_documents import CVDocument as CVDocumentRow
from app.db.models.cv_tailoring import CVTailoringSession, CVTailoringVersion
from app.db.models.profiles import Profile
from app.db.session import build_async_engine
from app.schemas.cv_tailoring import (
    TailoredItemPatch,
    TailoredPatchSet,
    TailoredSectionPatch,
)
from app.services.cv_document_projection import project_outline
from app.services.cv_tailoring_compiler import (
    TailoringCompileError,
    TailoringCompileResult,
)
from app.services.cv_tailoring_projection import project_tailoring_baseline
from app.storage.cv_tailoring import TailoringArtifactStorage
from sqlalchemy import select

from tests.support.db_migration import run_async, session_factory
from tests.unit.test_cv_tailoring_projection import _document, _profile


class _Settings:
    CV_TAILOR_MAX_INSTRUCTION_CHARS = 4_000
    CV_TAILOR_MAX_SECTIONS = 20
    CV_TAILOR_MAX_ITEMS_PER_SECTION = 30
    CV_TAILOR_MAX_TEX_CHARS = 100_000
    CV_TAILOR_COMPILE_TIMEOUT_SECONDS = 15
    CV_TAILOR_MAX_PDF_MB = 5


class _Invoker:
    def __init__(self, patch: TailoredPatchSet) -> None:
        self.patch = patch
        self.messages: list[Sequence[Any]] = []

    def select_sections(self, messages: Sequence[Any]):
        from app.agent.tailoring_graph import TailoringSectionSelection

        self.messages.append(messages)
        return TailoringSectionSelection(section_ids=["summary"])

    def rewrite_sections(
        self, messages: Sequence[Any], *, is_repair: bool
    ) -> TailoredPatchSet:
        del is_repair
        self.messages.append(messages)
        return self.patch.model_copy(deep=True)

    def supports(
        self, *, output_text: str, cited_evidence: Sequence[str]
    ) -> bool:
        del output_text, cited_evidence
        return True


async def _fake_compile(
    tex_source: str, *, staging_dir: Path, settings: Any
) -> TailoringCompileResult:
    del settings
    tex_path = staging_dir / "resume.tex"
    pdf_path = staging_dir / "resume.pdf"
    tex_path.write_text(tex_source, encoding="utf-8", newline="\n")
    pdf_path.write_bytes(b"%PDF-1.4\nsynthetic\n%%EOF\n")
    return TailoringCompileResult(
        tex_path=tex_path,
        pdf_path=pdf_path,
        tex_sha256=hashlib.sha256(tex_path.read_bytes()).hexdigest(),
        pdf_sha256=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        page_count=1,
        page_warning=None,
    )


async def _failing_compile(
    tex_source: str, *, staging_dir: Path, settings: Any
) -> TailoringCompileResult:
    del tex_source, settings
    (staging_dir / "resume.log").write_text("private compiler detail")
    raise TailoringCompileError


def _patch_for_summary(document, profile) -> TailoredPatchSet:
    baseline = project_tailoring_baseline(
        document, profile=profile, source_hash="source-revision-a"
    )
    section = baseline.content.sections[0]
    return TailoredPatchSet(
        sections=[
            TailoredSectionPatch(
                section_id=section.id,
                items=[
                    TailoredItemPatch(
                        source_entry_id=item.source_entry_id,
                        title=item.title,
                        subtitle=item.subtitle,
                        date_text=item.date_text,
                        location=item.location,
                        body=item.body,
                        bullets=item.bullets,
                        attributes=item.attributes,
                    )
                    for item in section.items
                ],
            )
        ]
    )


async def _seed_ready_source(factory):
    profile_model = _profile()
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
        document_model = _document().model_copy(
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
                document_json=document_model.model_dump(mode="json"),
                profile_json=profile_model.model_dump(mode="json"),
                outline_json={"sections": project_outline(document_model)},
                extraction_version="cv-document-v1",
                source_hash="source-revision-a",
            )
        )
        await session.commit()
        return profile.id, document_model, profile_model


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    return migrated_sqlite


def test_initial_generation_persists_terminal_run_version_and_artifacts(
    db_path: Path, tmp_path: Path
) -> None:
    async def _body() -> None:
        from app.services.cv_tailoring import TailoringCoordinator

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            profile_id, document, profile = await _seed_ready_source(factory)
            invoker = _Invoker(_patch_for_summary(document, profile))
            storage = TailoringArtifactStorage(tmp_path / "files")
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=storage,
                settings=_Settings(),
                invoker=invoker,
                sqlite_path=db_path,
                compiler=_fake_compile,
            )

            launch = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Prioritize the role-relevant summary",
                parent_run_id=None,
            )
            events = [
                event async for event in coordinator.stream_initial_version(launch)
            ]

            assert events[0].event == "run_started"
            assert events[-1].event == "run_completed"
            assert all(event.run_id == launch.run_id for event in events)
            completed = await coordinator.get_completed_version(launch)
            assert completed.session_id == launch.session_id
            assert completed.version_number == 1
            labels = [
                event.payload.message
                for event in events
                if event.event == "assistant_status"
            ]
            assert labels == [
                "Selecting relevant sections",
                "Tailoring selected sections",
                "Checking source support",
                "Generating PDF",
            ]

            async with factory() as session:
                persisted_session = await session.get(
                    CVTailoringSession, launch.session_id
                )
                run = await session.get(AgentRun, launch.run_id)
                version = (
                    await session.execute(
                        select(CVTailoringVersion).where(
                            CVTailoringVersion.session_id == launch.session_id
                        )
                    )
                ).scalar_one()
                assert persisted_session is not None
                assert persisted_session.state == "ready"
                assert persisted_session.latest_version_number == 1
                assert run is not None and run.state == "completed"
                assert version.version_number == 1
                assert version.parent_version_id is None
                assert storage.resolve_artifact(
                    relative_path=version.tex_relative_path
                ).is_file()
                assert storage.resolve_artifact(
                    relative_path=version.pdf_relative_path
                ).is_file()

            captured = "\n".join(
                str(getattr(message, "content", message))
                for call in invoker.messages
                for message in call
            )
            for contact in (profile.phone, profile.email, profile.github_url):
                if contact is not None:
                    assert contact not in captured
        finally:
            await engine.dispose()

    run_async(_body())


def test_stale_profile_blocks_manual_write_and_preserves_latest_version(
    db_path: Path, tmp_path: Path
) -> None:
    async def _body() -> None:
        from app.services.cv_tailoring import TailoringCoordinator, TailoringError

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=TailoringArtifactStorage(tmp_path / "files"),
                settings=_Settings(),
                invoker=_Invoker(_patch_for_summary(document, profile_model)),
                sqlite_path=db_path,
                compiler=_fake_compile,
            )
            launch = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Tailor the summary",
                parent_run_id=None,
            )
            events = [
                event async for event in coordinator.stream_initial_version(launch)
            ]
            assert events[-1].event == "run_completed"

            async with factory() as session:
                version = (
                    await session.execute(
                        select(CVTailoringVersion).where(
                            CVTailoringVersion.session_id == launch.session_id
                        )
                    )
                ).scalar_one()
                parent_content = version.content_json
                row = await session.get(Profile, profile_id)
                assert row is not None
                row.updated_at = utc_now() + timedelta(seconds=1)
                await session.commit()

            from app.schemas.cv_tailoring import TailoredCVContent

            with pytest.raises(TailoringError) as caught:
                await coordinator.create_manual_version(
                    session_id=launch.session_id,
                    parent_version_id=version.id,
                    content=TailoredCVContent.model_validate(parent_content),
                )
            assert caught.value.code == "TAILORING_SOURCE_STALE"

            async with factory() as session:
                persisted = await session.get(CVTailoringSession, launch.session_id)
                versions = list(
                    (
                        await session.execute(
                            select(CVTailoringVersion).where(
                                CVTailoringVersion.session_id == launch.session_id
                            )
                        )
                    ).scalars()
                )
                assert persisted is not None and persisted.state == "ready"
                assert persisted.latest_version_number == 1
                assert len(versions) == 1
        finally:
            await engine.dispose()

    run_async(_body())


def test_later_ai_and_manual_versions_form_one_immutable_parent_chain(
    db_path: Path, tmp_path: Path
) -> None:
    async def _body() -> None:
        from app.schemas.cv_tailoring import TailoredCVContent
        from app.services.cv_tailoring import TailoringCoordinator

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=TailoringArtifactStorage(tmp_path / "files"),
                settings=_Settings(),
                invoker=_Invoker(_patch_for_summary(document, profile_model)),
                sqlite_path=db_path,
                compiler=_fake_compile,
            )
            initial = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Tailor the summary",
                parent_run_id=None,
            )
            assert (
                [event async for event in coordinator.stream_initial_version(initial)][
                    -1
                ].event
                == "run_completed"
            )

            async with factory() as session:
                first = await tailoring_repo.get_latest_version(
                    session, initial.session_id
                )
                assert first is not None

            later = await coordinator.prepare_ai_version(
                session_id=initial.session_id,
                parent_version_id=first.id,
                instruction="Keep the summary concise",
                target_section_ids=["summary"],
            )
            assert (
                [event async for event in coordinator.stream_initial_version(later)][
                    -1
                ].event
                == "run_completed"
            )

            async with factory() as session:
                second = await tailoring_repo.get_latest_version(
                    session, initial.session_id
                )
                assert second is not None
                second_content = TailoredCVContent.model_validate(second.content_json)

            manual = await coordinator.create_manual_version(
                session_id=initial.session_id,
                parent_version_id=second.id,
                content=second_content,
            )
            assert manual.version_number == 3

            async with factory() as session:
                versions = await tailoring_repo.list_versions(
                    session, initial.session_id
                )
                assert [item.version_number for item in versions] == [1, 2, 3]
                assert [item.created_by for item in versions] == ["ai", "ai", "user"]
                assert [item.parent_version_id for item in versions] == [
                    None,
                    versions[0].id,
                    versions[1].id,
                ]
        finally:
            await engine.dispose()

    from app.repositories import cv_tailoring as tailoring_repo

    run_async(_body())


def test_compile_failure_is_durable_and_cleans_checkpoint_and_staging(
    db_path: Path, tmp_path: Path
) -> None:
    async def _body() -> None:
        from app.services.cv_tailoring import TailoringCoordinator

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        storage = TailoringArtifactStorage(tmp_path / "files")
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=storage,
                settings=_Settings(),
                invoker=_Invoker(_patch_for_summary(document, profile_model)),
                sqlite_path=db_path,
                compiler=_failing_compile,
            )
            launch = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Tailor the summary",
                parent_run_id=None,
            )

            events = [
                event async for event in coordinator.stream_initial_version(launch)
            ]

            assert events[-1].event == "run_failed"
            assert events[-1].payload.error_code == "TAILORING_COMPILE_FAILED"
            async with factory() as session:
                owner = await session.get(CVTailoringSession, launch.session_id)
                run = await session.get(AgentRun, launch.run_id)
                assert owner is not None and owner.state == "failed"
                assert owner.error_code == "TAILORING_COMPILE_FAILED"
                assert run is not None and run.state == "failed"
            async with open_checkpointer(db_path) as saver:
                assert await thread_has_checkpoints(saver, launch.run_id) is False
            staging_root = storage.root / ".staging"
            assert not staging_root.exists() or list(staging_root.iterdir()) == []
        finally:
            await engine.dispose()

    run_async(_body())


def test_failed_terminal_persistence_retains_checkpoint_for_recovery(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _body() -> None:
        from app.services.cv_tailoring import TailoringCoordinator

        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            profile_id, document, profile_model = await _seed_ready_source(factory)
            coordinator = TailoringCoordinator(
                session_factory=factory,
                storage=TailoringArtifactStorage(tmp_path / "files"),
                settings=_Settings(),
                invoker=_Invoker(_patch_for_summary(document, profile_model)),
                sqlite_path=db_path,
                compiler=_failing_compile,
            )
            launch = await coordinator.prepare_session(
                profile_id=profile_id,
                job_id=None,
                instruction="Tailor the summary",
                parent_run_id=None,
            )
            deleted: list[str] = []

            async def failed_terminal(*_args: Any, **_kwargs: Any) -> bool:
                return False

            async def record_delete(run_id: str) -> None:
                deleted.append(run_id)

            monkeypatch.setattr(coordinator, "_fail_generation", failed_terminal)
            monkeypatch.setattr(coordinator, "_delete_checkpoint", record_delete)
            events = [
                event async for event in coordinator.stream_initial_version(launch)
            ]
            assert events[-1].event == "run_failed"
            assert deleted == []
        finally:
            await engine.dispose()

    run_async(_body())
