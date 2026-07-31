"""Strict public contracts for direct profile CV re-extraction review."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import (
    AwareUtcDatetime,
    ProfileReextractOperationEnvelope,
    ProfileReextractOperationStatus,
    SafeWarning,
    StrictModelConfig,
    UuidStr,
)
from pydantic import BaseModel, Field, model_validator

ReextractStage = Literal[
    "validating_source",
    "extracting_document",
    "projecting_profile",
    "publishing_review",
]


class ProfileReextractInProgressDetail(BaseModel):
    model_config = StrictModelConfig

    code: Literal["PROFILE_REEXTRACT_IN_PROGRESS"]
    summary: str
    profile_id: UuidStr
    operation_id: UuidStr


class ProfileReviewPendingDetail(BaseModel):
    model_config = StrictModelConfig

    code: Literal["PROFILE_REVIEW_PENDING"]
    summary: str
    profile_id: UuidStr
    review_source: Literal["agent_update", "reextract"]
    operation_id: UuidStr | None
    review_revision: AwareUtcDatetime

    @model_validator(mode="after")
    def validate_owner(self) -> ProfileReviewPendingDetail:
        if (self.review_source == "reextract") != (self.operation_id is not None):
            raise ValueError("reextract review identity is inconsistent")
        return self


class ProfileReextractProgress(BaseModel):
    model_config = StrictModelConfig

    stage: ReextractStage
    message: str = Field(min_length=1, max_length=160)


class PublicProfileSnapshot(BaseModel):
    model_config = StrictModelConfig

    full_name: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=254)
    github_url: str | None = Field(default=None, max_length=500)
    summary: str = Field(max_length=600)
    current_title: str | None = Field(default=None, max_length=200)
    skill_labels: list[str] = Field(max_length=50)


ProfileReviewField = Literal[
    "full_name",
    "location",
    "phone",
    "email",
    "github_url",
    "summary",
    "current_title",
]


ProfilePreferenceField = Literal[
    "target_roles",
    "preferred_locations",
    "acceptable_work_modes",
    "target_seniority",
]


class ProfileFieldChange(BaseModel):
    model_config = StrictModelConfig

    field: ProfileReviewField
    before: str | float | None
    after: str | float | None


class ProfilePreferenceChange(BaseModel):
    model_config = StrictModelConfig

    field: ProfilePreferenceField
    before: list[str] = Field(max_length=50)
    after: list[str] = Field(max_length=50)


class ProfileCollectionDeltas(BaseModel):
    model_config = StrictModelConfig

    experiences: int
    education: int
    languages: int
    certifications: int


class ConfidenceDelta(BaseModel):
    model_config = StrictModelConfig

    before: float = Field(ge=0, le=1)
    after: float = Field(ge=0, le=1)


class ProfileReextractReview(BaseModel):
    model_config = StrictModelConfig

    profile_id: UuidStr
    source: Literal["agent_update", "reextract"]
    operation_id: UuidStr | None
    operation_state: Literal["review_ready", "stale"] | None
    revision: AwareUtcDatetime
    current: PublicProfileSnapshot
    proposed: PublicProfileSnapshot
    changed_fields: list[ProfileFieldChange] = Field(max_length=24)
    preference_changes: list[ProfilePreferenceChange] = Field(max_length=8)
    skills_added: list[str] = Field(max_length=50)
    skills_removed: list[str] = Field(max_length=50)
    collection_deltas: ProfileCollectionDeltas
    extraction_confidence: ConfidenceDelta | None
    can_approve: bool
    can_discard: bool

    @model_validator(mode="after")
    def source_matches_operation(self) -> ProfileReextractReview:
        if self.source == "agent_update":
            if self.operation_id is not None or self.operation_state is not None:
                raise ValueError("agent_update reviews cannot have operation state")
            if not self.can_approve or not self.can_discard:
                raise ValueError("ordinary reviews must be actionable")
        elif self.operation_id is None or self.operation_state is None:
            raise ValueError("reextract reviews require operation identity and state")
        if self.source == "reextract" and not self.can_discard:
            raise ValueError("reextract reviews must be discardable")
        if self.operation_state == "review_ready" and not self.can_approve:
            raise ValueError("review-ready operation reviews must be approvable")
        if self.operation_state == "stale" and self.can_approve:
            raise ValueError("stale operation reviews cannot be approvable")
        return self


class ProfileReextractReviewReady(BaseModel):
    model_config = StrictModelConfig

    revision: AwareUtcDatetime


class ProfileReextractFailed(BaseModel):
    model_config = StrictModelConfig

    code: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=200)
    draft_available: bool


class ProfileReextractApproveRequest(BaseModel):
    model_config = StrictModelConfig

    operation_id: UuidStr | None
    revision: AwareUtcDatetime


class ProfileReextractApprovalResponse(BaseModel):
    model_config = StrictModelConfig

    profile_id: UuidStr
    approved: bool
    sync_ok: bool
    warning: SafeWarning | None


ProfileReextractEventName = Literal[
    "reextract_progress",
    "reextract_review_ready",
    "reextract_failed",
]


class ProfileReextractEvent(BaseModel):
    model_config = StrictModelConfig

    event_id: UuidStr
    operation_id: UuidStr
    profile_id: UuidStr
    timestamp: AwareUtcDatetime
    event: ProfileReextractEventName
    payload: (
        ProfileReextractProgress | ProfileReextractReviewReady | ProfileReextractFailed
    )

    @model_validator(mode="after")
    def event_matches_payload(self) -> ProfileReextractEvent:
        expected = {
            "reextract_progress": ProfileReextractProgress,
            "reextract_review_ready": ProfileReextractReviewReady,
            "reextract_failed": ProfileReextractFailed,
        }[self.event]
        if not isinstance(self.payload, expected):
            raise ValueError("profile re-extract event/payload mismatch")
        return self


__all__ = [
    "ConfidenceDelta",
    "ProfileCollectionDeltas",
    "ProfileFieldChange",
    "ProfilePreferenceChange",
    "ProfilePreferenceField",
    "ProfileReextractApprovalResponse",
    "ProfileReextractApproveRequest",
    "ProfileReextractEvent",
    "ProfileReextractEventName",
    "ProfileReextractFailed",
    "ProfileReextractInProgressDetail",
    "ProfileReextractProgress",
    "ProfileReextractReview",
    "ProfileReextractReviewReady",
    "ProfileReextractOperationEnvelope",
    "ProfileReextractOperationStatus",
    "ProfileReviewPendingDetail",
    "ProfileReviewField",
    "PublicProfileSnapshot",
    "ReextractStage",
]
