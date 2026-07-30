"""Thin profile-scoped CV-tailoring routes and immutable artifact downloads."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.sse import EventSourceResponse
from sqlalchemy import select

from app.api.dependencies import CVTailoringDeps, get_cv_tailoring_deps
from app.api.sse import open_sse_response
from app.db.models.chat import AgentRun
from app.db.models.cv_tailoring import CVTailoringSession, CVTailoringVersion
from app.db.models.jobs import JobPost
from app.repositories import agent_activities as activities_repo
from app.repositories import cv_tailoring as tailoring_repo
from app.repositories import profiles as profiles_repo
from app.schemas.common import UuidStr
from app.schemas.cv_tailoring import (
    CV_TAILORING_SESSION_HEADER,
    TAILORING_CURRENT,
    TAILORING_STALE,
    CreateTailoringAiVersionRequest,
    CreateTailoringManualVersionRequest,
    CreateTailoringSessionRequest,
    TailoringDeleteResponse,
    TailoringJobLabel,
    TailoringRunSummary,
    TailoringSessionDetailResponse,
    TailoringSessionListResponse,
    TailoringSessionSummary,
    TailoringVersionMutationResponse,
    TailoringVersionSummary,
    parse_tailored_content,
    parse_tailoring_provenance,
)
from app.schemas.jobs import JobPostExtraction, parse_job_post_extraction
from app.services.agent_activity import activity_payload
from app.services.cv_tailoring import (
    TAILORING_ARTIFACT_UNAVAILABLE,
    TAILORING_PARENT_CONFLICT,
    TAILORING_SESSION_NOT_FOUND,
    TAILORING_SOURCE_STALE,
    TAILORING_VERSION_NOT_FOUND,
    TailoringError,
)
from app.services.cv_tailoring_deletion import delete_tailoring_session
from app.services.cv_tailoring_fit import fit_warning_for_content_change
from app.services.tailoring_issue_projection import (
    decode_internal_issue,
    is_internal_issue_activity,
    project_grounding_issues,
)

router = APIRouter(tags=["cv-tailoring"])


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _http_error(exc: Exception) -> HTTPException:
    if not isinstance(exc, TailoringError):
        return HTTPException(
            status_code=500,
            detail={"code": "TAILORING_COMPILE_FAILED", "summary": "Tailoring failed"},
        )
    status = {
        "PROFILE_NOT_READY": 409,
        "TAILORING_CONTACT_REQUIRED": 422,
        "JOB_NOT_SCORABLE": 409,
        TAILORING_SESSION_NOT_FOUND: 404,
        TAILORING_VERSION_NOT_FOUND: 404,
        TAILORING_SOURCE_STALE: 409,
        TAILORING_PARENT_CONFLICT: 409,
        "TAILORING_GROUNDING_FAILED": 422,
        "TAILORING_COMPILE_FAILED": 500,
        TAILORING_ARTIFACT_UNAVAILABLE: 404,
        "TAILORING_DELETE_FAILED": 500,
    }.get(exc.code, 400)
    detail: dict[str, Any] = {"code": exc.code, "summary": exc.message}
    if exc.user_issues:
        detail["issues"] = [
            item.model_dump(mode="json") for item in exc.user_issues
        ]
    return HTTPException(status_code=status, detail=detail)


async def _active_profile_id(deps: CVTailoringDeps) -> str:
    async with deps.session_factory() as session:
        profile = await profiles_repo.get_selected_ready_profile(session)
        if profile is None:
            raise TailoringError("PROFILE_NOT_READY", "Profile is not ready")
        return profile.id


def _is_current(
    row: CVTailoringSession, profile: Any, job_updated_at: datetime | None
) -> bool:
    return bool(
        row.template_version == "latex-cv-v1"
        and profile is not None
        and profile.state == "ready"
        and profile.attachment_id == row.source_attachment_id
        and profile.source_hash == row.source_hash
        and _aware(profile.updated_at) == _aware(row.profile_updated_at)
        and (
            row.job_updated_at is None
            or (
                row.job_id is not None
                and job_updated_at is not None
                and _aware(job_updated_at) == _aware(row.job_updated_at)
            )
        )
    )


async def _summary(session: Any, row: CVTailoringSession) -> TailoringSessionSummary:
    profile = await profiles_repo.get_profile(session, row.profile_id)
    job_updated_at = None
    if row.job_id is not None:
        job = await session.get(JobPost, row.job_id)
        job_updated_at = job.updated_at if job is not None else None
    label = (
        TailoringJobLabel.model_validate(row.job_label_json)
        if row.job_label_json is not None
        else None
    )
    return TailoringSessionSummary(
        id=row.id,
        profile_id=row.profile_id,
        job_label=label,
        instruction=row.instruction,
        template_version=cast(Any, row.template_version),
        state=cast(Any, row.state),
        currentness=cast(
            Any,
            TAILORING_CURRENT
            if _is_current(row, profile, job_updated_at)
            else TAILORING_STALE,
        ),
        latest_version_number=row.latest_version_number,
        error_code=row.error_code,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _version_summary(row: CVTailoringVersion) -> TailoringVersionSummary:
    return TailoringVersionSummary(
        id=row.id,
        version_number=row.version_number,
        parent_version_id=row.parent_version_id,
        created_by=cast(Any, row.created_by),
        page_count=row.page_count,
        page_warning=row.page_warning,
        created_at=_aware(row.created_at),
    )


def _parse_job_context(row: JobPost | None) -> JobPostExtraction | None:
    if row is None or row.extraction_json is None:
        return None
    try:
        return parse_job_post_extraction(row.extraction_json)
    except Exception:
        return None


async def _fit_warning(
    session: Any,
    *,
    owner: CVTailoringSession,
    selected: CVTailoringVersion | None,
) -> str | None:
    if selected is None or selected.parent_version_id is None:
        return None
    parent = await tailoring_repo.get_version(session, selected.parent_version_id)
    if parent is None or parent.session_id != owner.id:
        return None
    job_context = _parse_job_context(
        await session.get(JobPost, owner.job_id) if owner.job_id is not None else None
    )
    if job_context is None:
        return None
    return fit_warning_for_content_change(
        content=parse_tailored_content(selected.content_json),
        parent=parse_tailored_content(parent.content_json),
        job_context=job_context,
    )


async def _owned_session(
    session: Any, session_id: str, profile_id: str
) -> CVTailoringSession:
    row = await tailoring_repo.get_session(session, session_id)
    if row is None or row.profile_id != profile_id:
        raise TailoringError(
            TAILORING_SESSION_NOT_FOUND, "Tailoring session was not found"
        )
    return row


@router.post("/cv-tailoring/sessions")
async def create_session(
    body: CreateTailoringSessionRequest,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> EventSourceResponse:
    try:
        profile_id = await _active_profile_id(deps)
        launch = await deps.coordinator.prepare_session(
            profile_id=profile_id,
            job_id=body.job_id,
            instruction=body.instruction,
            parent_run_id=None,
        )
        return await open_sse_response(
            deps.coordinator.stream_initial_version(launch),
            error_mapper=_http_error,
            error_types=(TailoringError,),
            headers={CV_TAILORING_SESSION_HEADER: launch.session_id},
        )
    except TailoringError as exc:
        raise _http_error(exc) from exc


@router.get("/cv-tailoring/sessions", response_model=TailoringSessionListResponse)
async def list_sessions(
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> TailoringSessionListResponse:
    try:
        profile_id = await _active_profile_id(deps)
        async with deps.session_factory() as session:
            rows = (
                await tailoring_repo.list_sessions_for_profile(session, profile_id)
            )[:100]
            items = [await _summary(session, row) for row in rows]
        return TailoringSessionListResponse(items=items)
    except TailoringError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/cv-tailoring/sessions/{session_id}",
    response_model=TailoringSessionDetailResponse,
)
async def get_session(
    session_id: UuidStr,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
    version_id: Annotated[UuidStr | None, Query()] = None,
) -> TailoringSessionDetailResponse:
    try:
        profile_id = await _active_profile_id(deps)
        async with deps.session_factory() as session:
            owner = await _owned_session(session, session_id, profile_id)
            versions = await tailoring_repo.list_versions(session, owner.id)
            selected = None
            if version_id is not None:
                candidate = await tailoring_repo.get_version(session, version_id)
                if candidate is None or candidate.session_id != owner.id:
                    raise TailoringError(
                        TAILORING_VERSION_NOT_FOUND,
                        "Tailoring version was not found",
                    )
                selected = candidate
            elif versions:
                selected = versions[-1]
            run = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.tailoring_session_id == owner.id)
                    .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            latest_run = None
            if run is not None:
                activities = await activities_repo.list_for_run_ids(session, [run.id])
                internal_issues = [
                    issue
                    for item in activities
                    if (issue := decode_internal_issue(item.technical_name)) is not None
                ]
                issue_parent = (
                    parse_tailored_content(versions[-1].content_json)
                    if versions
                    else None
                )
                latest_run = TailoringRunSummary(
                    id=run.id,
                    state=cast(Any, run.state),
                    error_code=run.error_code,
                    activities=[
                        activity_payload(item)
                        for item in activities
                        if not is_internal_issue_activity(item.technical_name)
                    ],
                    issues=(
                        project_grounding_issues(
                            issue_list=internal_issues, parent=issue_parent
                        )
                        if internal_issues and issue_parent is not None
                        else []
                    ),
                )
            content = (
                parse_tailored_content(selected.content_json) if selected else None
            )
            evidence = (
                parse_tailoring_provenance(selected.provenance_json).facts
                if selected
                else []
            )
            source_available = False
            pdf_available = False
            if selected is not None:
                source_available = _artifact_exists(
                    deps, selected.tex_relative_path
                )
                pdf_available = _artifact_exists(
                    deps, selected.pdf_relative_path
                )
            return TailoringSessionDetailResponse(
                session=await _summary(session, owner),
                versions=[_version_summary(item) for item in versions],
                selected_version=_version_summary(selected) if selected else None,
                content=content,
                evidence=evidence,
                latest_run=latest_run,
                fit_warning=await _fit_warning(
                    session, owner=owner, selected=selected
                ),
                source_available=source_available,
                pdf_available=pdf_available,
            )
    except TailoringError as exc:
        raise _http_error(exc) from exc


def _artifact_exists(deps: CVTailoringDeps, relative_path: str) -> bool:
    try:
        return deps.storage.resolve_artifact(relative_path=relative_path).is_file()
    except Exception:
        return False


@router.post("/cv-tailoring/sessions/{session_id}/ai-versions")
async def create_ai_version(
    session_id: UuidStr,
    body: CreateTailoringAiVersionRequest,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> EventSourceResponse:
    try:
        profile_id = await _active_profile_id(deps)
        async with deps.session_factory() as session:
            await _owned_session(session, session_id, profile_id)
        launch = await deps.coordinator.prepare_ai_version(
            session_id=session_id,
            parent_version_id=body.parent_version_id,
            instruction=body.instruction,
            target_section_ids=body.target_section_ids,
        )
        return await open_sse_response(
            deps.coordinator.stream_initial_version(launch),
            error_mapper=_http_error,
            error_types=(TailoringError,),
        )
    except TailoringError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/cv-tailoring/sessions/{session_id}/manual-versions",
    response_model=TailoringVersionMutationResponse,
)
async def create_manual_version(
    session_id: UuidStr,
    body: CreateTailoringManualVersionRequest,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> TailoringVersionMutationResponse:
    try:
        profile_id = await _active_profile_id(deps)
        async with deps.session_factory() as session:
            await _owned_session(session, session_id, profile_id)
        return await deps.coordinator.create_manual_version(
            session_id=session_id,
            parent_version_id=body.parent_version_id,
            content=body.content,
        )
    except TailoringError as exc:
        raise _http_error(exc) from exc


async def _artifact_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            yield chunk


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


async def _download(
    version_id: str, *, kind: str, deps: CVTailoringDeps
) -> StreamingResponse:
    profile_id = await _active_profile_id(deps)
    async with deps.session_factory() as session:
        version = await tailoring_repo.get_version(session, version_id)
        if version is None:
            raise TailoringError(
                TAILORING_VERSION_NOT_FOUND, "Tailoring version was not found"
            )
        await _owned_session(session, version.session_id, profile_id)
        relative = (
            version.tex_relative_path if kind == "source" else version.pdf_relative_path
        )
        expected_hash = version.tex_sha256 if kind == "source" else version.pdf_sha256
        version_number = version.version_number
    try:
        path = deps.storage.resolve_artifact(relative_path=relative)
        if not path.is_file() or path.is_symlink():
            raise OSError
        digest = _sha256_file(path)
        if digest != expected_hash:
            raise OSError
    except Exception as exc:
        raise TailoringError(
            TAILORING_ARTIFACT_UNAVAILABLE,
            "Tailoring artifact is unavailable",
        ) from exc
    media = "text/x-tex; charset=utf-8" if kind == "source" else "application/pdf"
    disposition = "attachment" if kind == "source" else "inline"
    suffix = "tex" if kind == "source" else "pdf"
    filename = f"resume-v{version_number}.{suffix}"
    return StreamingResponse(
        _artifact_chunks(path),
        media_type=media,
        headers={
            "Content-Length": str(path.stat().st_size),
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/cv-tailoring/versions/{version_id}/source")
async def download_source(
    version_id: UuidStr,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> StreamingResponse:
    try:
        return await _download(version_id, kind="source", deps=deps)
    except TailoringError as exc:
        raise _http_error(exc) from exc


@router.get("/cv-tailoring/versions/{version_id}/pdf")
async def download_pdf(
    version_id: UuidStr,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> StreamingResponse:
    try:
        return await _download(version_id, kind="pdf", deps=deps)
    except TailoringError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/cv-tailoring/sessions/{session_id}",
    response_model=TailoringDeleteResponse,
)
async def delete_session(
    session_id: UuidStr,
    deps: Annotated[CVTailoringDeps, Depends(get_cv_tailoring_deps)],
) -> TailoringDeleteResponse:
    try:
        profile_id = await _active_profile_id(deps)
        async with deps.session_factory() as session:
            await _owned_session(session, session_id, profile_id)
        return await delete_tailoring_session(
            session_id=session_id,
            session_factory=deps.session_factory,
            sqlite_path=deps.settings.SQLITE_PATH,
            storage=deps.storage,
        )
    except TailoringError as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
