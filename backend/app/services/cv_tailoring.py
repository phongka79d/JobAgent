"""Source-resolving coordinator for grounded, immutable tailored-CV versions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol, cast

from anyio import CancelScope
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.checkpoint import (
    delete_run_checkpoint,
    open_checkpointer,
    thread_config,
)
from app.agent.tailoring_graph import (
    TAILORING_GROUNDING_FAILED,
    ShopAIKeyTailoringStructuredInvoker,
    TailoringStructuredInvoker,
    build_tailoring_graph,
    initial_tailoring_state,
)
from app.core.ids import new_uuid
from app.core.settings import Settings, get_settings
from app.core.time import utc_now
from app.db.models.chat import AGENT_RUN_STATE_COMPLETED, AGENT_RUN_STATE_RUNNING
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.db.models.profiles import PROFILE_STATE_READY, Profile
from app.db.session import get_session_factory, session_scope
from app.repositories import agent_runs as runs_repo
from app.repositories import cv_documents as documents_repo
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories.cv_tailoring import (
    CVTailoringVersionWrite,
    TailoringParentConflict,
)
from app.schemas.cv_document import CVDocument, parse_cv_document
from app.schemas.cv_tailoring import (
    TAILORING_CREATED_BY_AI,
    TAILORING_CREATED_BY_USER,
    TAILORING_SESSION_STATE_GENERATING,
    TAILORING_TEMPLATE_VERSION,
    TailoredCVContent,
    TailoredFactEvidence,
    TailoringJobLabel,
    TailoringProvenance,
    TailoringSourceRevision,
    TailoringVersionCreateResponse,
    parse_tailored_content,
)
from app.schemas.jobs import JobPostExtraction, parse_job_post_extraction
from app.schemas.profile import CandidateProfile, parse_candidate_profile
from app.schemas.sse import SseEvent, build_sse_event
from app.services.activity_gate import (
    ActivityBlockedError,
    assert_tailoring_start_allowed,
)
from app.services.agent_activity import AgentActivityService, AgentActivityServiceError
from app.services.cv_document_projection import project_outline
from app.services.cv_tailoring_compiler import (
    TailoringCompileError,
    TailoringCompileResult,
    compile_latex_cv,
)
from app.services.cv_tailoring_guard import guard_manual_tailored_content
from app.services.cv_tailoring_projection import (
    TailoringBaseline,
    project_tailoring_baseline,
    select_section_context,
)
from app.services.cv_tailoring_renderer import render_latex_cv
from app.storage.cv_tailoring import TailoringArtifactStorage

PROFILE_NOT_READY = "PROFILE_NOT_READY"
TAILORING_CONTACT_REQUIRED = "TAILORING_CONTACT_REQUIRED"
JOB_NOT_SCORABLE = "JOB_NOT_SCORABLE"
TAILORING_SESSION_NOT_FOUND = "TAILORING_SESSION_NOT_FOUND"
TAILORING_VERSION_NOT_FOUND = "TAILORING_VERSION_NOT_FOUND"
TAILORING_SOURCE_STALE = "TAILORING_SOURCE_STALE"
TAILORING_PARENT_CONFLICT = "TAILORING_PARENT_CONFLICT"
TAILORING_COMPILE_FAILED = "TAILORING_COMPILE_FAILED"
TAILORING_ARTIFACT_UNAVAILABLE = "TAILORING_ARTIFACT_UNAVAILABLE"

_SAFE_MESSAGES = {
    PROFILE_NOT_READY: "Profile is not ready for CV tailoring",
    TAILORING_CONTACT_REQUIRED: "Approved profile name is required",
    JOB_NOT_SCORABLE: "Selected Job is not ready for CV tailoring",
    TAILORING_SESSION_NOT_FOUND: "Tailoring session was not found",
    TAILORING_VERSION_NOT_FOUND: "Tailoring version was not found",
    TAILORING_SOURCE_STALE: "Tailoring sources have changed",
    TAILORING_PARENT_CONFLICT: "Tailoring version has changed",
    TAILORING_GROUNDING_FAILED: "Tailored content is not source-supported",
    TAILORING_COMPILE_FAILED: "Tailored CV compilation failed",
    TAILORING_ARTIFACT_UNAVAILABLE: "Tailoring artifact is unavailable",
}


class TailoringError(Exception):
    def __init__(self, code: str, message: str) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("TailoringError code must be non-empty")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("TailoringError message must be non-empty")
        self.code = code.strip()
        self.message = message.strip()
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class TailoringSourceSnapshot:
    profile_id: str
    attachment_id: str
    source_hash: str
    profile_updated_at: datetime
    profile: CandidateProfile
    document: CVDocument
    outline: list[dict[str, Any]]
    job_id: str | None
    job_updated_at: datetime | None
    job_label: TailoringJobLabel | None
    job_context: JobPostExtraction | None


@dataclass(frozen=True, slots=True)
class TailoringLaunch:
    session_id: str
    run_id: str
    profile_id: str


@dataclass(frozen=True, slots=True)
class _PreparedGeneration:
    launch: TailoringLaunch
    parent_version_id: str | None
    expected_latest_version_number: int
    instruction: str
    requested_section_ids: tuple[str, ...]


class _CoordinatorSettings(Protocol):
    CV_TAILOR_MAX_INSTRUCTION_CHARS: int
    CV_TAILOR_MAX_TEX_CHARS: int
    CV_TAILOR_COMPILE_TIMEOUT_SECONDS: int
    CV_TAILOR_MAX_PDF_MB: int


Compiler = Callable[
    ...,
    Awaitable[TailoringCompileResult],
]


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _same_revision(left: datetime, right: datetime) -> bool:
    return _aware_utc(left) == _aware_utc(right)


def _error(code: str) -> TailoringError:
    return TailoringError(code, _SAFE_MESSAGES[code])


class TailoringCoordinator:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        storage: TailoringArtifactStorage | None = None,
        settings: _CoordinatorSettings | None = None,
        invoker: TailoringStructuredInvoker | None = None,
        sqlite_path: str | Path | None = None,
        compiler: Compiler = compile_latex_cv,
        activity_service: AgentActivityService | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._settings = settings or get_settings()
        cfg = self._settings
        files_dir = getattr(cfg, "FILES_DIR", None)
        if storage is None:
            if files_dir is None:
                raise ValueError("storage or Settings.FILES_DIR is required")
            storage = TailoringArtifactStorage(files_dir)
        self._storage = storage
        self._invoker = invoker
        self._sqlite_path = sqlite_path
        self._compiler = compiler
        self._activity_service = activity_service or AgentActivityService(
            self._session_factory
        )
        self._prepared: dict[str, _PreparedGeneration] = {}

    async def prepare_session(
        self,
        *,
        profile_id: str,
        job_id: str | None,
        instruction: str,
        parent_run_id: str | None,
    ) -> TailoringLaunch:
        cleaned = self._bounded_instruction(instruction)
        async with session_scope(self._session_factory) as session:
            await self._assert_start_allowed(
                session, profile_id=profile_id, parent_run_id=parent_run_id
            )
            snapshot = await self._resolve_new_snapshot(
                session,
                profile_id=profile_id,
                job_id=job_id,
                instruction=cleaned,
            )
            row = await tailoring_repo.create_session(
                session,
                profile_id=snapshot.profile_id,
                source_attachment_id=snapshot.attachment_id,
                source_hash=snapshot.source_hash,
                profile_updated_at=snapshot.profile_updated_at,
                job_id=snapshot.job_id,
                job_updated_at=snapshot.job_updated_at,
                job_label_json=(
                    snapshot.job_label.model_dump(mode="json")
                    if snapshot.job_label is not None
                    else None
                ),
                instruction=cleaned,
                template_version=TAILORING_TEMPLATE_VERSION,
            )
            run = await runs_repo.create_tailoring_run(
                session,
                tailoring_session_id=row.id,
                parent_run_id=parent_run_id,
                source_attachment_id=snapshot.attachment_id,
            )
            launch = TailoringLaunch(
                session_id=row.id,
                run_id=run.id,
                profile_id=snapshot.profile_id,
            )
        self._prepared[launch.run_id] = _PreparedGeneration(
            launch=launch,
            parent_version_id=None,
            expected_latest_version_number=0,
            instruction=cleaned,
            requested_section_ids=(),
        )
        return launch

    async def stream_initial_version(
        self, launch: TailoringLaunch
    ) -> AsyncIterator[SseEvent]:
        prepared = self._prepared.pop(launch.run_id, None)
        if prepared is None or prepared.launch != launch:
            raise _error(TAILORING_SESSION_NOT_FOUND)
        try:
            yield build_sse_event(
                "run_started",
                launch.run_id,
                {"state": "running", "resumed": False},
            )
            async with open_checkpointer(
                self._sqlite_path,
                settings=(
                    self._settings
                    if isinstance(self._settings, Settings)
                    else None
                ),
            ) as saver:
                snapshot, parent, baseline = await self._generation_context(prepared)
                yield await self._status_event(
                    launch.run_id, "Selecting relevant sections", "select_sections"
                )
                bundle = build_tailoring_graph(
                    invoker=self._structured_invoker(),
                    load_selected_context=lambda section_ids: select_section_context(
                        baseline, section_ids=section_ids
                    ),
                    parent=parent,
                    approved_skill_labels=baseline.approved_skill_labels,
                    checkpointer=saver,
                )
                state = initial_tailoring_state(
                    run_id=launch.run_id,
                    instruction=prepared.instruction,
                    job_context=(
                        snapshot.job_context.model_dump(mode="json")
                        if snapshot.job_context is not None
                        else None
                    ),
                    outline=snapshot.outline,
                    requested_section_ids=prepared.requested_section_ids,
                )
                result = await bundle.compiled.ainvoke(
                    state, config=thread_config(launch.run_id)
                )
                yield await self._status_event(
                    launch.run_id,
                    "Tailoring selected sections",
                    "rewrite_sections",
                )
                yield await self._status_event(
                    launch.run_id,
                    "Checking source support",
                    "ground_patch",
                )
                if result.get("error") is not None or result.get("patch") is None:
                    raise _error(TAILORING_GROUNDING_FAILED)
                content = parse_tailored_content(result["patch"])
                selected_ids = tuple(result.get("selected_section_ids") or ())
                yield await self._status_event(
                    launch.run_id, "Generating PDF", "generate_pdf"
                )
                await self._render_promote_commit(
                    prepared=prepared,
                    snapshot=snapshot,
                    baseline=baseline,
                    content=content,
                    targeted_section_ids=selected_ids,
                    created_by=TAILORING_CREATED_BY_AI,
                )
                await self._delete_checkpoint(launch.run_id)
        except (asyncio.CancelledError, GeneratorExit):
            with CancelScope(shield=True):
                if await self._fail_generation(
                    prepared, TAILORING_GROUNDING_FAILED
                ):
                    await self._delete_checkpoint(launch.run_id)
            raise
        except TailoringError as exc:
            if await self._fail_generation(prepared, exc.code):
                await self._delete_checkpoint(launch.run_id)
            yield build_sse_event(
                "run_failed",
                launch.run_id,
                {
                    "state": "failed",
                    "error_code": exc.code,
                    "summary": exc.message,
                },
            )
            return
        except TailoringCompileError:
            if await self._fail_generation(prepared, TAILORING_COMPILE_FAILED):
                await self._delete_checkpoint(launch.run_id)
            yield build_sse_event(
                "run_failed",
                launch.run_id,
                {
                    "state": "failed",
                    "error_code": TAILORING_COMPILE_FAILED,
                    "summary": _SAFE_MESSAGES[TAILORING_COMPILE_FAILED],
                },
            )
            return
        except Exception:
            if await self._fail_generation(
                prepared, TAILORING_GROUNDING_FAILED
            ):
                await self._delete_checkpoint(launch.run_id)
            yield build_sse_event(
                "run_failed",
                launch.run_id,
                {
                    "state": "failed",
                    "error_code": TAILORING_GROUNDING_FAILED,
                    "summary": _SAFE_MESSAGES[TAILORING_GROUNDING_FAILED],
                },
            )
            return
        yield build_sse_event(
            "run_completed",
            launch.run_id,
            {"state": "completed"},
        )

    async def get_completed_version(
        self, launch: TailoringLaunch
    ) -> TailoringVersionCreateResponse:
        """Return the exact durable version owned by a completed launch."""
        async with self._session_factory() as session:
            run = await runs_repo.get_run(session, launch.run_id)
            owner = await tailoring_repo.get_session(session, launch.session_id)
            version = await tailoring_repo.get_latest_version(
                session, launch.session_id
            )
            if (
                run is None
                or run.state != AGENT_RUN_STATE_COMPLETED
                or run.tailoring_session_id != launch.session_id
                or owner is None
                or owner.profile_id != launch.profile_id
                or version is None
                or version.version_number != owner.latest_version_number
            ):
                raise _error(TAILORING_GROUNDING_FAILED)
            return TailoringVersionCreateResponse(
                session_id=owner.id,
                version_id=version.id,
                version_number=version.version_number,
            )

    async def prepare_ai_version(
        self,
        *,
        session_id: str,
        parent_version_id: str | None,
        instruction: str,
        target_section_ids: Sequence[str],
    ) -> TailoringLaunch:
        cleaned = self._bounded_instruction(instruction)
        requested = tuple(target_section_ids)
        if len(requested) != len(set(requested)):
            raise _error(TAILORING_PARENT_CONFLICT)
        async with session_scope(self._session_factory) as session:
            owner = await tailoring_repo.get_session(session, session_id)
            if owner is None:
                raise _error(TAILORING_SESSION_NOT_FOUND)
            await self._assert_start_allowed(
                session, profile_id=owner.profile_id, parent_run_id=None
            )
            await self._resolve_session_snapshot(session, owner)
            expected = owner.latest_version_number
            if expected == 0:
                if parent_version_id is not None or requested:
                    raise _error(TAILORING_PARENT_CONFLICT)
                cleaned = owner.instruction
            else:
                latest = await tailoring_repo.get_latest_version(session, owner.id)
                if (
                    latest is None
                    or latest.id != parent_version_id
                    or not requested
                    or not cleaned
                ):
                    raise _error(TAILORING_PARENT_CONFLICT)
                parent = parse_tailored_content(latest.content_json)
                known = {section.id for section in parent.sections}
                if any(section_id not in known for section_id in requested):
                    raise _error(TAILORING_PARENT_CONFLICT)
            await tailoring_repo.mark_session_generating(session, owner.id)
            run = await runs_repo.create_tailoring_run(
                session,
                tailoring_session_id=owner.id,
                source_attachment_id=owner.source_attachment_id,
            )
            launch = TailoringLaunch(
                session_id=owner.id,
                run_id=run.id,
                profile_id=owner.profile_id,
            )
        self._prepared[launch.run_id] = _PreparedGeneration(
            launch=launch,
            parent_version_id=parent_version_id,
            expected_latest_version_number=expected,
            instruction=cleaned,
            requested_section_ids=requested,
        )
        return launch

    async def create_manual_version(
        self,
        *,
        session_id: str,
        parent_version_id: str,
        content: TailoredCVContent,
    ) -> TailoringVersionCreateResponse:
        async with session_scope(self._session_factory) as session:
            owner = await tailoring_repo.get_session(session, session_id)
            if owner is None:
                raise _error(TAILORING_SESSION_NOT_FOUND)
            await self._assert_start_allowed(
                session, profile_id=owner.profile_id, parent_run_id=None
            )
            snapshot = await self._resolve_session_snapshot(session, owner)
            latest = await tailoring_repo.get_latest_version(session, owner.id)
            if latest is None or latest.id != parent_version_id:
                raise _error(TAILORING_PARENT_CONFLICT)
            parent = parse_tailored_content(latest.content_json)
            await tailoring_repo.mark_session_generating(session, owner.id)
            expected = owner.latest_version_number
        baseline = project_tailoring_baseline(
            snapshot.document,
            profile=snapshot.profile,
            source_hash=snapshot.source_hash,
        )
        targeted = tuple(
            candidate.id
            for candidate, previous in zip(
                content.sections, parent.sections, strict=False
            )
            if candidate != previous
        )
        try:
            guarded, issues = guard_manual_tailored_content(
                content,
                parent=parent,
                allowed_section_ids=targeted,
                fact_bank=baseline.fact_bank,
                approved_skill_labels=baseline.approved_skill_labels,
                semantic_checker=self._structured_invoker(),
            )
            if guarded is None or issues:
                raise _error(TAILORING_GROUNDING_FAILED)
            prepared = _PreparedGeneration(
                launch=TailoringLaunch(
                    session_id=session_id,
                    run_id=new_uuid(),
                    profile_id=snapshot.profile_id,
                ),
                parent_version_id=parent_version_id,
                expected_latest_version_number=expected,
                instruction="",
                requested_section_ids=targeted,
            )
            return await self._render_promote_commit(
                prepared=prepared,
                snapshot=snapshot,
                baseline=baseline,
                content=guarded,
                targeted_section_ids=targeted,
                created_by=TAILORING_CREATED_BY_USER,
                complete_run=False,
            )
        except TailoringError:
            await self._restore_ready(session_id)
            raise
        except TailoringCompileError as exc:
            await self._restore_ready(session_id)
            raise _error(TAILORING_COMPILE_FAILED) from exc
        except Exception as exc:
            await self._restore_ready(session_id)
            raise _error(TAILORING_GROUNDING_FAILED) from exc

    def _bounded_instruction(self, instruction: str) -> str:
        if not isinstance(instruction, str):
            raise _error(TAILORING_GROUNDING_FAILED)
        cleaned = instruction.strip()
        if len(cleaned) > self._settings.CV_TAILOR_MAX_INSTRUCTION_CHARS:
            raise _error(TAILORING_GROUNDING_FAILED)
        return cleaned

    def _structured_invoker(self) -> TailoringStructuredInvoker:
        if self._invoker is None:
            self._invoker = ShopAIKeyTailoringStructuredInvoker()
        return self._invoker

    async def _assert_start_allowed(
        self,
        session: AsyncSession,
        *,
        profile_id: str,
        parent_run_id: str | None,
    ) -> None:
        try:
            await assert_tailoring_start_allowed(
                session,
                profile_id=profile_id,
                parent_run_id=parent_run_id,
            )
        except ActivityBlockedError as exc:
            raise TailoringError(exc.code, exc.summary) from exc

    async def _resolve_new_snapshot(
        self,
        session: AsyncSession,
        *,
        profile_id: str,
        job_id: str | None,
        instruction: str,
    ) -> TailoringSourceSnapshot:
        if job_id is None and not instruction:
            raise _error(JOB_NOT_SCORABLE)
        profile = await session.get(Profile, profile_id)
        return await self._resolve_snapshot(
            session, profile=profile, job_id=job_id, stale=False
        )

    async def _resolve_session_snapshot(
        self, session: AsyncSession, owner: Any
    ) -> TailoringSourceSnapshot:
        if owner.template_version != TAILORING_TEMPLATE_VERSION:
            raise _error(TAILORING_SOURCE_STALE)
        if owner.job_id is None and owner.job_updated_at is not None:
            raise _error(TAILORING_SOURCE_STALE)
        profile = await session.get(Profile, owner.profile_id)
        snapshot = await self._resolve_snapshot(
            session, profile=profile, job_id=owner.job_id, stale=True
        )
        if (
            snapshot.attachment_id != owner.source_attachment_id
            or snapshot.source_hash != owner.source_hash
            or not _same_revision(
                snapshot.profile_updated_at, owner.profile_updated_at
            )
            or (
                owner.job_updated_at is not None
                and (
                    snapshot.job_updated_at is None
                    or not _same_revision(
                        snapshot.job_updated_at, owner.job_updated_at
                    )
                )
            )
        ):
            raise _error(TAILORING_SOURCE_STALE)
        return snapshot

    async def _resolve_snapshot(
        self,
        session: AsyncSession,
        *,
        profile: Profile | None,
        job_id: str | None,
        stale: bool,
    ) -> TailoringSourceSnapshot:
        source_error = TAILORING_SOURCE_STALE if stale else PROFILE_NOT_READY
        if (
            profile is None
            or profile.state != PROFILE_STATE_READY
            or profile.profile_json is None
            or profile.source_hash is None
        ):
            raise _error(source_error)
        document_row = await documents_repo.get_document(
            session, profile.attachment_id
        )
        if (
            document_row is None
            or document_row.source_hash != profile.source_hash
        ):
            raise _error(source_error)
        try:
            profile_model = parse_candidate_profile(profile.profile_json)
            document = parse_cv_document(document_row.document_json)
        except Exception as exc:
            raise _error(source_error) from exc
        if not profile_model.full_name:
            raise _error(
                TAILORING_SOURCE_STALE if stale else TAILORING_CONTACT_REQUIRED
            )
        job_updated_at: datetime | None = None
        job_label: TailoringJobLabel | None = None
        job_context: JobPostExtraction | None = None
        if job_id is not None:
            job = await session.get(JobPost, job_id)
            job_error = TAILORING_SOURCE_STALE if stale else JOB_NOT_SCORABLE
            if (
                job is None
                or job.processing_status != JOB_PROCESSING_STATUS_PROCESSED
                or job.jd_quality
                not in {JOB_JD_QUALITY_FULL, JOB_JD_QUALITY_PARTIAL}
                or job.extraction_json is None
            ):
                raise _error(job_error)
            try:
                job_context = parse_job_post_extraction(job.extraction_json)
            except Exception as exc:
                raise _error(job_error) from exc
            job_updated_at = _aware_utc(job.updated_at)
            job_label = TailoringJobLabel(
                title=job_context.title,
                company=job_context.company,
            )
        return TailoringSourceSnapshot(
            profile_id=profile.id,
            attachment_id=profile.attachment_id,
            source_hash=profile.source_hash,
            profile_updated_at=_aware_utc(profile.updated_at),
            profile=profile_model,
            document=document,
            outline=project_outline(document),
            job_id=job_id,
            job_updated_at=job_updated_at,
            job_label=job_label,
            job_context=job_context,
        )

    async def _generation_context(
        self, prepared: _PreparedGeneration
    ) -> tuple[TailoringSourceSnapshot, TailoredCVContent, TailoringBaseline]:
        async with self._session_factory() as session:
            owner = await tailoring_repo.get_session(
                session, prepared.launch.session_id
            )
            run = await runs_repo.get_run(session, prepared.launch.run_id)
            if (
                owner is None
                or run is None
                or run.state != AGENT_RUN_STATE_RUNNING
                or owner.state != TAILORING_SESSION_STATE_GENERATING
            ):
                raise _error(TAILORING_SESSION_NOT_FOUND)
            snapshot = await self._resolve_session_snapshot(session, owner)
            baseline = project_tailoring_baseline(
                snapshot.document,
                profile=snapshot.profile,
                source_hash=snapshot.source_hash,
            )
            if prepared.expected_latest_version_number == 0:
                parent = baseline.content
            else:
                version = await tailoring_repo.get_version(
                    session, prepared.parent_version_id or ""
                )
                if (
                    version is None
                    or version.session_id != owner.id
                    or version.version_number
                    != prepared.expected_latest_version_number
                ):
                    raise _error(TAILORING_PARENT_CONFLICT)
                parent = parse_tailored_content(version.content_json)
            return snapshot, parent, baseline

    async def _render_promote_commit(
        self,
        *,
        prepared: _PreparedGeneration,
        snapshot: TailoringSourceSnapshot,
        baseline: TailoringBaseline,
        content: TailoredCVContent,
        targeted_section_ids: Sequence[str],
        created_by: str,
        complete_run: bool = True,
    ) -> TailoringVersionCreateResponse:
        version_id = new_uuid()
        staging = self._storage.create_staging_dir(version_id=version_id)
        try:
            tex_source = render_latex_cv(content)
            compiled = await self._compiler(
                tex_source,
                staging_dir=staging,
                settings=self._settings,
            )
        except Exception:
            self._discard_staging(
                profile_id=snapshot.profile_id,
                session_id=prepared.launch.session_id,
                version_id=version_id,
                staging=staging,
            )
            raise
        paths = self._storage.promote(
            profile_id=snapshot.profile_id,
            session_id=prepared.launch.session_id,
            version_id=version_id,
            staged_tex=compiled.tex_path,
            staged_pdf=compiled.pdf_path,
        )
        selected_set = set(targeted_section_ids)
        facts: list[TailoredFactEvidence] = [
            evidence
            for evidence in baseline.fact_bank.values()
            if evidence.section_id in selected_set
        ]
        provenance = TailoringProvenance(
            targeted_section_ids=list(targeted_section_ids),
            facts=facts,
        )
        revision = TailoringSourceRevision(
            profile_updated_at=snapshot.profile_updated_at,
            source_hash=snapshot.source_hash,
            job_updated_at=snapshot.job_updated_at,
            template_version=cast(
                Literal["latex-cv-v1"], TAILORING_TEMPLATE_VERSION
            ),
        )
        try:
            async with session_scope(self._session_factory) as session:
                await session.execute(text("BEGIN IMMEDIATE"))
                owner = await tailoring_repo.get_session(
                    session, prepared.launch.session_id
                )
                if owner is None:
                    raise _error(TAILORING_SESSION_NOT_FOUND)
                await self._resolve_session_snapshot(session, owner)
                row = await tailoring_repo.create_version_cas(
                    session,
                    session_id=owner.id,
                    expected_latest_version_number=(
                        prepared.expected_latest_version_number
                    ),
                    expected_parent_version_id=prepared.parent_version_id,
                    version=CVTailoringVersionWrite(
                        id=version_id,
                        parent_version_id=prepared.parent_version_id,
                        created_by=created_by,
                        content_json=content.model_dump(mode="json"),
                        provenance_json=provenance.model_dump(mode="json"),
                        source_revision_json=revision.model_dump(mode="json"),
                        tex_relative_path=paths.tex_relative_path,
                        pdf_relative_path=paths.pdf_relative_path,
                        tex_sha256=compiled.tex_sha256,
                        pdf_sha256=compiled.pdf_sha256,
                        page_count=compiled.page_count,
                        page_warning=compiled.page_warning,
                        created_at=utc_now(),
                    ),
                )
                if complete_run:
                    await runs_repo.complete_run(session, prepared.launch.run_id)
                version_number = row.version_number
        except TailoringParentConflict as exc:
            self._storage.delete_version(
                profile_id=snapshot.profile_id,
                session_id=prepared.launch.session_id,
                version_id=version_id,
            )
            raise _error(TAILORING_PARENT_CONFLICT) from exc
        except Exception:
            self._storage.delete_version(
                profile_id=snapshot.profile_id,
                session_id=prepared.launch.session_id,
                version_id=version_id,
            )
            raise
        return TailoringVersionCreateResponse(
            session_id=prepared.launch.session_id,
            version_id=version_id,
            version_number=version_number,
        )

    async def _fail_generation(
        self, prepared: _PreparedGeneration, error_code: str
    ) -> bool:
        try:
            async with session_scope(self._session_factory) as session:
                owner = await tailoring_repo.get_session(
                    session, prepared.launch.session_id
                )
                if owner is not None:
                    if owner.latest_version_number == 0:
                        await tailoring_repo.mark_session_failed(
                            session, owner.id, error_code=error_code
                        )
                    else:
                        await tailoring_repo.restore_session_ready(session, owner.id)
                run = await runs_repo.get_run(session, prepared.launch.run_id)
                if run is not None and run.state == AGENT_RUN_STATE_RUNNING:
                    await runs_repo.fail_run(
                        session, run.id, error_code=error_code
                    )
            return True
        except Exception:
            return False

    async def _restore_ready(self, session_id: str) -> None:
        try:
            async with session_scope(self._session_factory) as session:
                await tailoring_repo.restore_session_ready(session, session_id)
        except Exception:
            return

    async def _delete_checkpoint(self, run_id: str) -> None:
        try:
            async with open_checkpointer(
                self._sqlite_path,
                settings=(
                    self._settings
                    if isinstance(self._settings, Settings)
                    else None
                ),
            ) as saver:
                await delete_run_checkpoint(saver, run_id)
        except Exception:
            return

    def _discard_staging(
        self,
        *,
        profile_id: str,
        session_id: str,
        version_id: str,
        staging: Path,
    ) -> None:
        try:
            self._storage.promote(
                profile_id=profile_id,
                session_id=session_id,
                version_id=version_id,
                staged_tex=staging / "resume.tex",
                staged_pdf=staging / "resume.pdf",
            )
        except Exception:
            return
        self._storage.delete_version(
            profile_id=profile_id,
            session_id=session_id,
            version_id=version_id,
        )

    async def _status_event(
        self, run_id: str, label: str, technical_name: str
    ) -> SseEvent:
        activity = None
        started = perf_counter()
        try:
            activity = await self._activity_service.start_assistant(
                run_id=run_id,
                label=label,
                technical_name=technical_name,
            )
            activity = await self._activity_service.finish(
                activity_id=activity.activity_id,
                state="completed",
                duration_ms=max(0, int((perf_counter() - started) * 1_000)),
                error_code=None,
            )
        except AgentActivityServiceError:
            activity = None
        return build_sse_event(
            "assistant_status",
            run_id,
            {
                "message": label,
                "activity": (
                    activity.model_dump(mode="json")
                    if activity is not None
                    else None
                ),
            },
        )


__all__ = [
    "JOB_NOT_SCORABLE",
    "PROFILE_NOT_READY",
    "TAILORING_COMPILE_FAILED",
    "TAILORING_ARTIFACT_UNAVAILABLE",
    "TAILORING_CONTACT_REQUIRED",
    "TAILORING_GROUNDING_FAILED",
    "TAILORING_PARENT_CONFLICT",
    "TAILORING_SESSION_NOT_FOUND",
    "TAILORING_SOURCE_STALE",
    "TAILORING_VERSION_NOT_FOUND",
    "TailoringCoordinator",
    "TailoringError",
    "TailoringLaunch",
    "TailoringSourceSnapshot",
]
