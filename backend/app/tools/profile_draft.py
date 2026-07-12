"""Candidate profile draft proposal tools with application-state authorization."""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, model_validator

from app.db.enums import ProfileDraftState
from app.db.session import DatabaseSessionManager
from app.repositories.profile_drafts import (
    ProfileDraftRecord,
    ProfileDraftRepository,
    ProfileDraftRepositoryError,
)
from app.repositories.profiles import ProfileRepository, ProfileRepositoryError
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.cv_ingestion import CvIngestionError


class ProfileDraftProposalPort(Protocol):
    async def propose_profile_from_cv(
        self, attachment_id: UUID
    ) -> ProfileDraftRecord: ...


class ProposeProfileFromCvInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: UUID


class ProposeProfileUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: UUID | None = None
    profile: CandidateProfile
    preferences: JobPreferences | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_null_preferences(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("preferences", ...) is None:
            raise ValueError("preferences must be omitted when unchanged")
        return value


def _error(code: str) -> str:
    return f'ERROR:{{"code":"{code}","ok":false}}'


def _approval(record: ProfileDraftRecord) -> str:
    summary = record.document.approval_summary
    payload = json.dumps(
        {
            "draft_id": str(record.id),
            "kind": "approval_required",
            "approval_kind": "profile_draft",
            "summary": summary.summary,
            "current_title": summary.current_title,
            "skill_names": list(summary.skill_names),
            "experience_count": summary.experience_count,
            "education_count": summary.education_count,
            "has_preference_changes": summary.has_preference_changes,
            "target_roles_preview": list(summary.target_roles_preview),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"APPROVAL_REQUIRED:{payload}"


class ProfileDraftToolService:
    """Reuse CV extraction and draft repositories without approved writes."""

    def __init__(
        self,
        database: DatabaseSessionManager,
        cv_proposals: ProfileDraftProposalPort,
    ) -> None:
        self._database = database
        self._cv_proposals = cv_proposals

    async def propose_from_cv(self, attachment_id: UUID) -> str:
        try:
            async with self._database.session_scope() as session:
                if await ProfileDraftRepository(session).get_pending() is not None:
                    return _error("PROFILE_DRAFT_PENDING")
            return _approval(
                await self._cv_proposals.propose_profile_from_cv(attachment_id)
            )
        except CvIngestionError as exc:
            return _error(exc.code)
        except ProfileDraftRepositoryError:
            return _error("PROFILE_DRAFT_FAILED")

    async def propose_update(
        self,
        *,
        draft_id: UUID | None,
        profile: CandidateProfile,
        preferences: JobPreferences | None,
    ) -> str:
        try:
            async with self._database.session_scope() as session:
                drafts = ProfileDraftRepository(session)
                if draft_id is not None:
                    current = await drafts.get(draft_id)
                    if current is None:
                        return _error("PROFILE_DRAFT_NOT_FOUND")
                    if current.state != ProfileDraftState.PENDING.value:
                        return _error("PROFILE_DRAFT_NOT_PENDING")
                    effective_preferences = preferences
                    if (
                        effective_preferences is None
                        and current.document.replaces_preferences()
                    ):
                        effective_preferences = current.document.preferences
                    document = self._document(profile, effective_preferences)
                    return _approval(await drafts.update(draft_id, document))

                if await drafts.get_pending() is not None:
                    return _error("PROFILE_DRAFT_ID_REQUIRED")
                approved = await ProfileRepository(session).get()
                if approved is None or approved.active_attachment_id is None:
                    return _error("ACTIVE_PROFILE_UNAVAILABLE")
                return _approval(
                    await drafts.create(
                        self._document(profile, preferences),
                        source_attachment_id=approved.active_attachment_id,
                    )
                )
        except (ProfileDraftRepositoryError, ProfileRepositoryError):
            return _error("PROFILE_DRAFT_FAILED")

    @staticmethod
    def _document(
        profile: CandidateProfile,
        preferences: JobPreferences | None,
    ) -> ProfileDraftDocument:
        values: dict[str, Any] = {
            "profile": profile,
            "approval_summary": build_approval_summary(
                profile, preferences=preferences
            ),
        }
        if preferences is not None:
            values["preferences"] = preferences
        return ProfileDraftDocument(**values)


def create_profile_draft_tools(
    service: ProfileDraftToolService,
) -> tuple[StructuredTool, StructuredTool]:
    async def _from_cv(attachment_id: UUID) -> str:
        return await service.propose_from_cv(attachment_id)

    async def _update(
        profile: CandidateProfile,
        draft_id: UUID | None = None,
        preferences: JobPreferences | None = None,
    ) -> str:
        return await service.propose_update(
            draft_id=draft_id,
            profile=profile,
            preferences=preferences,
        )

    return (
        StructuredTool.from_function(
            coroutine=_from_cv,
            name="propose_profile_from_cv",
            description="Create a pending profile draft from a staged or active CV.",
            args_schema=ProposeProfileFromCvInput,
        ),
        StructuredTool.from_function(
            coroutine=_update,
            name="propose_profile_update",
            description="Correct one pending draft or propose from active context.",
            args_schema=ProposeProfileUpdateInput,
        ),
    )


__all__ = [
    "ProfileDraftProposalPort",
    "ProfileDraftToolService",
    "ProposeProfileFromCvInput",
    "ProposeProfileUpdateInput",
    "create_profile_draft_tools",
]
