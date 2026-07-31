"""Direct, durable profile CV re-extraction and review coordination."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import anyio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
)
from app.db.models.profiles import PROFILE_STATE_READY
from app.db.session import immediate_session_scope, session_scope
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profile_reextract_operations as operation_repo
from app.repositories import profiles as profile_repo
from app.repositories import workspace_state as workspace_repo
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    SafeWarning,
    parse_candidate_profile,
    parse_job_preferences,
    parse_profile_draft_payload,
)
from app.schemas.profile_reextraction import (
    ConfidenceDelta,
    ProfileCollectionDeltas,
    ProfileFieldChange,
    ProfilePreferenceChange,
    ProfilePreferenceField,
    ProfileReextractApprovalResponse,
    ProfileReextractEvent,
    ProfileReextractEventName,
    ProfileReextractFailed,
    ProfileReextractProgress,
    ProfileReextractReview,
    ProfileReextractReviewReady,
    ProfileReviewField,
    PublicProfileSnapshot,
    ReextractStage,
)
from app.services.activity_gate import (
    ActivityBlockedError,
    assert_profile_review_clear,
    assert_workspace_idle,
)
from app.services.profile_approval import commit_approved_draft
from app.services.profile_drafts import publish_reextract_stage, stage_cv_document
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage

_SCALAR_FIELDS: tuple[ProfileReviewField, ...] = (
    "full_name",
    "location",
    "phone",
    "email",
    "github_url",
    "summary",
    "current_title",
)

_PREFERENCE_FIELDS: tuple[ProfilePreferenceField, ...] = (
    "target_roles",
    "preferred_locations",
    "acceptable_work_modes",
    "target_seniority",
)

_PROGRESS_MESSAGES: dict[ReextractStage, str] = {
    "validating_source": "Validating the retained CV",
    "extracting_document": "Extracting the CV document",
    "projecting_profile": "Preparing the proposed profile",
    "publishing_review": "Publishing the review",
}


class ProfileReextractError(Exception):
    def __init__(
        self, code: str, summary: str, *, operation_id: str | None = None
    ) -> None:
        self.code = code
        self.summary = summary
        self.operation_id = operation_id
        super().__init__(summary)


@dataclass(frozen=True, slots=True)
class _Claim:
    operation_id: str
    profile_id: str
    attachment_id: str
    storage_path: str


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _bounded(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


def _snapshot(profile: CandidateProfile) -> PublicProfileSnapshot:
    labels = [
        item.skill.display_name[:200] for item in profile.skills if not item.excluded
    ][:50]
    return PublicProfileSnapshot(
        full_name=_bounded(profile.full_name, 200),
        location=_bounded(profile.location, 200),
        phone=_bounded(profile.phone, 50),
        email=_bounded(profile.email, 254),
        github_url=_bounded(profile.github_url, 500),
        summary=_bounded(profile.summary, 600) or "",
        current_title=_bounded(profile.current_title, 200),
        skill_labels=labels,
    )


def _skill_labels(profile: CandidateProfile) -> dict[str, str]:
    return {
        item.skill.canonical_key: item.skill.display_name[:200]
        for item in profile.skills
        if not item.excluded
    }


def _collection_size(profile: CandidateProfile, field: str) -> int:
    value = getattr(profile, field, ())
    return len(value) if isinstance(value, (list, tuple)) else 0


def _empty_preferences() -> JobPreferences:
    return JobPreferences(
        target_roles=[],
        preferred_locations=[],
        acceptable_work_modes=[],
        target_seniority=[],
    )


def _preference_changes(
    current: JobPreferences | None,
    proposed: JobPreferences | None,
) -> list[ProfilePreferenceChange]:
    if current is None or proposed is None:
        return []
    changes: list[ProfilePreferenceChange] = []
    for field in _PREFERENCE_FIELDS:
        before = list(getattr(current, field))
        after = list(getattr(proposed, field))
        if before != after:
            changes.append(
                ProfilePreferenceChange(field=field, before=before, after=after)
            )
    return changes


def build_review(
    *,
    current: CandidateProfile,
    proposed: CandidateProfile,
    current_preferences: JobPreferences | None = None,
    proposed_preferences: JobPreferences | None = None,
    profile_id: str,
    revision: datetime,
) -> ProfileReextractReview:
    """Build one bounded public diff without raw text or provider identity."""
    current_snapshot = _snapshot(current)
    proposed_snapshot = _snapshot(proposed)
    changes: list[ProfileFieldChange] = []
    for field in _SCALAR_FIELDS:
        before = getattr(current_snapshot, field)
        after = getattr(proposed_snapshot, field)
        if before != after:
            changes.append(ProfileFieldChange(field=field, before=before, after=after))

    current_skills = _skill_labels(current)
    proposed_skills = _skill_labels(proposed)
    skills_added = sorted(
        (proposed_skills[key] for key in proposed_skills.keys() - current_skills),
        key=str.casefold,
    )[:50]
    skills_removed = sorted(
        (current_skills[key] for key in current_skills.keys() - proposed_skills),
        key=str.casefold,
    )[:50]

    confidence = None
    if current.extraction_confidence != proposed.extraction_confidence:
        confidence = ConfidenceDelta(
            before=current.extraction_confidence,
            after=proposed.extraction_confidence,
        )

    return ProfileReextractReview(
        profile_id=profile_id,
        revision=_aware(revision),
        current=current_snapshot,
        proposed=proposed_snapshot,
        changed_fields=changes,
        preference_changes=_preference_changes(
            current_preferences, proposed_preferences
        ),
        skills_added=skills_added,
        skills_removed=skills_removed,
        collection_deltas=ProfileCollectionDeltas(
            experiences=_collection_size(proposed, "experiences")
            - _collection_size(current, "experiences"),
            education=_collection_size(proposed, "education")
            - _collection_size(current, "education"),
            languages=_collection_size(proposed, "languages")
            - _collection_size(current, "languages"),
            certifications=_collection_size(proposed, "certifications")
            - _collection_size(current, "certifications"),
        ),
        extraction_confidence=confidence,
        can_approve=True,
        can_discard=True,
    )


def _event(
    *,
    operation_id: str,
    profile_id: str,
    event: ProfileReextractEventName,
    payload: ProfileReextractProgress
    | ProfileReextractReviewReady
    | ProfileReextractFailed,
) -> ProfileReextractEvent:
    return ProfileReextractEvent(
        event_id=new_uuid(),
        operation_id=operation_id,
        profile_id=profile_id,
        timestamp=utc_now(),
        event=event,
        payload=payload,
    )


def _progress(
    *, operation_id: str, profile_id: str, stage: ReextractStage
) -> ProfileReextractEvent:
    return _event(
        operation_id=operation_id,
        profile_id=profile_id,
        event="reextract_progress",
        payload=ProfileReextractProgress(
            stage=stage,
            message=_PROGRESS_MESSAGES[stage],
        ),
    )


def _safe_failure_summary(code: str) -> str:
    return {
        "ATTACHMENT_NOT_FOUND": "The retained CV could not be found",
        "FILE_MISSING": "The retained CV file is unavailable",
        "NO_EXTRACTABLE_TEXT": "The retained CV contains no extractable text",
        "PROFILE_INCONSISTENT": "The profile and retained CV no longer match",
        "ATTACHMENT_NOT_PROCESSABLE": "The retained CV cannot be re-extracted",
    }.get(code, "CV re-extraction could not be completed")


class ProfileReextractionCoordinator:
    """Own direct re-extraction transport and durable review mutations."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: AttachmentStorage,
        normalizer: SkillNormalizer,
        invoker: Any,
        graph_driver: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._normalizer = normalizer
        self._invoker = invoker
        self._graph_driver = graph_driver

    async def _claim(self, profile_id: str) -> _Claim:
        try:
            async with immediate_session_scope(self._session_factory) as session:
                try:
                    await assert_workspace_idle(session)
                    await assert_profile_review_clear(session, profile_id=profile_id)
                except ActivityBlockedError as exc:
                    raise ProfileReextractError(exc.code, exc.summary) from exc
                profile = await profile_repo.get_profile(session, profile_id)
                active_id = await workspace_repo.get_active_profile_id(session)
                workspace = await workspace_repo.get_state(session)
                if profile is None:
                    raise ProfileReextractError(
                        "PROFILE_NOT_FOUND", "Profile not found"
                    )
                if profile.state != PROFILE_STATE_READY or active_id != profile_id:
                    raise ProfileReextractError(
                        "PROFILE_NOT_READY", "Profile is not the active ready profile"
                    )
                if workspace is None:
                    raise ProfileReextractError(
                        "WORKSPACE_UNAVAILABLE", "Workspace state is unavailable"
                    )
                attachment = await att_repo.get_by_id(session, profile.attachment_id)
                if attachment is None:
                    raise ProfileReextractError(
                        "CV_ATTACHMENT_NOT_FOUND", "The retained CV could not be found"
                    )
                if attachment.state not in {
                    ATTACHMENT_STATE_ACTIVE,
                    ATTACHMENT_STATE_ARCHIVED,
                }:
                    raise ProfileReextractError(
                        "CV_NOT_REPROCESSABLE", "The retained CV cannot be re-extracted"
                    )
                operation = await operation_repo.claim_operation(
                    session,
                    profile_id=profile_id,
                    source_attachment_id=attachment.id,
                    base_profile_updated_at=profile.updated_at,
                    base_workspace_updated_at=workspace.updated_at,
                )
                return _Claim(
                    operation_id=operation.id,
                    profile_id=profile_id,
                    attachment_id=attachment.id,
                    storage_path=attachment.storage_path,
                )
        except operation_repo.ProfileReextractOperationConflict as exc:
            operation_id = exc.operation_id
            if exc.code == "PROFILE_REEXTRACT_IN_PROGRESS" and operation_id is None:
                async with session_scope(self._session_factory) as session:
                    current = await operation_repo.get_latest_operation_for_profile(
                        session, profile_id
                    )
                    if current is not None and current.state in {
                        "running",
                        "review_ready",
                    }:
                        operation_id = current.id
            summary = (
                "A profile re-extraction is already in progress"
                if exc.code == "PROFILE_REEXTRACT_IN_PROGRESS"
                else exc.code
            )
            raise ProfileReextractError(
                exc.code, summary, operation_id=operation_id
            ) from exc

    async def _load_attachment(self, claim: _Claim) -> Any:
        async with session_scope(self._session_factory) as session:
            attachment = await att_repo.get_by_id(session, claim.attachment_id)
            if attachment is None or attachment.storage_path != claim.storage_path:
                raise ProfileReextractError(
                    "CV_ATTACHMENT_NOT_FOUND", "The retained CV could not be found"
                )
            return attachment

    async def _transition_failed(self, claim: _Claim, code: str) -> None:
        async with session_scope(self._session_factory) as session:
            await operation_repo.transition_running_operation(
                session,
                profile_id=claim.profile_id,
                operation_id=claim.operation_id,
                to_state="failed",
                error_code=code[:80],
            )

    async def _transition_interrupted(self, claim: _Claim) -> None:
        async with session_scope(self._session_factory) as session:
            await operation_repo.transition_running_operation(
                session,
                profile_id=claim.profile_id,
                operation_id=claim.operation_id,
                to_state="interrupted",
                error_code="PROFILE_REEXTRACT_INTERRUPTED",
            )

    async def _draft_available(self, profile_id: str) -> bool:
        async with self._session_factory() as session:
            draft = await profile_repo.get_draft_for_profile(session, profile_id)
            return draft is not None

    async def _current_preferences(self, profile_id: str) -> JobPreferences:
        async with session_scope(self._session_factory) as session:
            row = await profile_repo.get_profile_preferences(session, profile_id)
            if row is None:
                return _empty_preferences()
            try:
                return parse_job_preferences(row.preferences_json)
            except (TypeError, ValidationError) as exc:
                raise ProfileReextractError(
                    "PROFILE_INCONSISTENT", "The profile preferences are invalid"
                ) from exc

    async def stream(self, profile_id: str) -> AsyncIterator[ProfileReextractEvent]:
        claim = await self._claim(profile_id)
        operation_id = claim.operation_id
        try:
            yield _progress(
                operation_id=operation_id,
                profile_id=profile_id,
                stage="validating_source",
            )
            if not self._storage.exists(claim.storage_path):
                raise ProfileReextractError(
                    "FILE_MISSING", "The retained CV file is unavailable"
                )
            yield _progress(
                operation_id=operation_id,
                profile_id=profile_id,
                stage="extracting_document",
            )
            staged = await stage_cv_document(
                attachment=await self._load_attachment(claim),
                storage=self._storage,
                normalizer=self._normalizer,
                invoker=self._invoker,
            )
            staged = replace(
                staged,
                draft_payload=staged.draft_payload.model_copy(
                    update={
                        "job_preferences": await self._current_preferences(profile_id)
                    }
                ),
            )
            yield _progress(
                operation_id=operation_id,
                profile_id=profile_id,
                stage="projecting_profile",
            )
            yield _progress(
                operation_id=operation_id,
                profile_id=profile_id,
                stage="publishing_review",
            )
            published = await publish_reextract_stage(
                session_factory=self._session_factory,
                profile_id=profile_id,
                operation_id=operation_id,
                staged=staged,
            )
            if published.state != "review_ready" or published.revision is None:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_STALE",
                    "The profile changed during re-extraction",
                )
            yield _event(
                operation_id=operation_id,
                profile_id=profile_id,
                event="reextract_review_ready",
                payload=ProfileReextractReviewReady(
                    revision=_aware(published.revision)
                ),
            )
        except (asyncio.CancelledError, GeneratorExit):
            with anyio.CancelScope(shield=True):
                await self._transition_interrupted(claim)
            raise
        except ProfileReextractError as exc:
            await self._transition_failed(claim, exc.code)
            yield _event(
                operation_id=operation_id,
                profile_id=profile_id,
                event="reextract_failed",
                payload=ProfileReextractFailed(
                    code=exc.code[:80],
                    summary=exc.summary[:200],
                    draft_available=await self._draft_available(profile_id),
                ),
            )
        except Exception:
            await self._transition_failed(claim, "PROFILE_REEXTRACT_FAILED")
            yield _event(
                operation_id=operation_id,
                profile_id=profile_id,
                event="reextract_failed",
                payload=ProfileReextractFailed(
                    code="PROFILE_REEXTRACT_FAILED",
                    summary="CV re-extraction could not be completed",
                    draft_available=await self._draft_available(profile_id),
                ),
            )

    async def get_review(self, profile_id: str) -> ProfileReextractReview:
        async with self._session_factory() as session:
            profile = await profile_repo.get_profile(session, profile_id)
            if profile is None:
                raise ProfileReextractError("PROFILE_NOT_FOUND", "Profile not found")
            if profile.state != PROFILE_STATE_READY:
                raise ProfileReextractError("PROFILE_NOT_READY", "Profile is not ready")
            draft = await profile_repo.get_draft_for_profile(session, profile_id)
            if draft is None:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_DRAFT_NOT_FOUND",
                    "No review is available for this profile",
                )
            source_id = draft.source_attachment_id
            if source_id is not None and source_id != profile.attachment_id:
                raise ProfileReextractError(
                    "PROFILE_INCONSISTENT", "The review does not match this profile"
                )
            try:
                current = parse_candidate_profile(profile.profile_json)
                draft_payload = parse_profile_draft_payload(draft.draft_json)
                proposed = draft_payload.candidate_profile
            except (TypeError, ValidationError) as exc:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_DRAFT_INVALID",
                    "The review data is invalid",
                ) from exc
            prefs_row = await profile_repo.get_profile_preferences(session, profile_id)
            if prefs_row is None:
                current_preferences = _empty_preferences()
            else:
                try:
                    current_preferences = parse_job_preferences(
                        prefs_row.preferences_json
                    )
                except (TypeError, ValidationError) as exc:
                    raise ProfileReextractError(
                        "PROFILE_REEXTRACT_DRAFT_INVALID",
                        "The review data is invalid",
                    ) from exc
            if source_id is not None:
                document_draft = await cv_doc_repo.get_draft(
                    session, profile.attachment_id
                )
                if document_draft is None:
                    raise ProfileReextractError(
                        "PROFILE_REEXTRACT_DRAFT_INVALID",
                        "The review data is incomplete",
                    )
                try:
                    document_profile = parse_candidate_profile(
                        document_draft.profile_json
                    )
                except (TypeError, ValidationError) as exc:
                    raise ProfileReextractError(
                        "PROFILE_REEXTRACT_DRAFT_INVALID",
                        "The review data is invalid",
                    ) from exc
                if document_profile.model_dump(mode="json") != proposed.model_dump(
                    mode="json"
                ):
                    raise ProfileReextractError(
                        "PROFILE_REEXTRACT_DRAFT_INVALID",
                        "The review data is inconsistent",
                    )
            return build_review(
                current=current,
                proposed=proposed,
                current_preferences=current_preferences,
                proposed_preferences=draft_payload.job_preferences,
                profile_id=profile_id,
                revision=draft.updated_at,
            )

    async def approve(
        self, profile_id: str, *, revision: datetime
    ) -> ProfileReextractApprovalResponse:
        result = await commit_approved_draft(
            session_factory=self._session_factory,
            storage=self._storage,
            normalizer=self._normalizer,
            expected_profile_id=profile_id,
            expected_draft_updated_at=_aware(revision),
            driver=self._graph_driver,
        )
        if not result.sqlite_committed:
            code = result.code or "PROFILE_REEXTRACT_APPROVAL_FAILED"
            raise ProfileReextractError(code, result.summary[:200])
        warning = None
        if not result.sync_ok:
            warning = SafeWarning(
                code=result.code or "NEO4J_SYNC_FAILED",
                summary="Profile saved, but the derived graph could not be refreshed",
                guidance=str(
                    result.data.get(
                        "rebuild_instruction",
                        "Restore graph availability and run the supported rebuild",
                    )
                )[:500],
            )
        return ProfileReextractApprovalResponse(
            profile_id=profile_id,
            approved=True,
            sync_ok=result.sync_ok,
            warning=warning,
        )

    async def discard(self, profile_id: str, *, revision: datetime) -> None:
        expected = _aware(revision)
        async with session_scope(self._session_factory) as session:
            draft = await profile_repo.get_draft_for_profile(session, profile_id)
            if draft is None:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_DRAFT_NOT_FOUND",
                    "No review is available for this profile",
                )
            if _aware(draft.updated_at) != expected:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_CONFLICT",
                    "The review changed; reload it before discarding",
                )
            attachment_id = draft.source_attachment_id
            deleted = await profile_repo.delete_draft_for_profile(
                session,
                profile_id=profile_id,
                expected_revision=expected,
            )
            if not deleted:
                raise ProfileReextractError(
                    "PROFILE_REEXTRACT_CONFLICT",
                    "The review changed; reload it before discarding",
                )
            if attachment_id is not None:
                await cv_doc_repo.delete_draft(session, attachment_id)
            operation_id = draft.reextract_operation_id
            if operation_id is not None:
                await operation_repo.delete_operation(
                    session,
                    profile_id=profile_id,
                    operation_id=operation_id,
                    expected_state="review_ready",
                )


async def recover_running_profile_reextract_operations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Mark only operations left running by a prior process as interrupted."""
    async with session_scope(session_factory) as session:
        operations = await operation_repo.list_running_operations(session)
        for operation in operations:
            await operation_repo.transition_running_operation(
                session,
                profile_id=operation.profile_id,
                operation_id=operation.id,
                to_state="interrupted",
                error_code="PROFILE_REEXTRACT_INTERRUPTED",
            )


__all__ = [
    "ProfileReextractError",
    "ProfileReextractionCoordinator",
    "build_review",
    "recover_running_profile_reextract_operations",
]
