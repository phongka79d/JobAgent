"""Strict CV-upload bootstrap contracts for pending profile setup."""

from __future__ import annotations

from typing import Literal

from app.schemas.attachments import (
    AttachmentPublic,
    DraftUploadSummary,
    ProfileUploadSummary,
)
from app.schemas.chat import ConversationSummary
from app.schemas.common import StrictModelConfig
from app.schemas.profile import ProfileListItem
from pydantic import BaseModel, model_validator

CvUploadOutcome = Literal[
    "new_pending",
    "retry_pending",
    "existing_pending",
    "existing_active",
    "existing_profile",
]

_PENDING_OUTCOMES = frozenset(
    {"new_pending", "retry_pending", "existing_pending"}
)
_READY_OUTCOMES = frozenset({"existing_active", "existing_profile"})


class PendingProfileBootstrap(BaseModel):
    model_config = StrictModelConfig

    profile: ProfileListItem
    conversation: ConversationSummary
    start_extraction: bool

    @model_validator(mode="after")
    def validate_owner(self) -> PendingProfileBootstrap:
        if self.profile.state != "pending":
            raise ValueError("bootstrap profile must be pending")
        if self.conversation.profile_id != self.profile.id:
            raise ValueError("bootstrap conversation owner mismatch")
        return self


class CvUploadResponse(BaseModel):
    model_config = StrictModelConfig

    attachment: AttachmentPublic
    outcome: CvUploadOutcome
    profile: ProfileUploadSummary | None = None
    draft: DraftUploadSummary | None = None
    bootstrap: PendingProfileBootstrap | None = None

    @model_validator(mode="after")
    def validate_outcome_coupling(self) -> CvUploadResponse:
        if self.outcome in _PENDING_OUTCOMES:
            if self.bootstrap is None:
                raise ValueError("pending upload outcome requires bootstrap")
            if self.profile is not None:
                raise ValueError("pending upload outcome cannot include ready profile")
            if (
                self.outcome in {"new_pending", "retry_pending"}
                and not self.bootstrap.start_extraction
            ):
                raise ValueError("new and retry pending outcomes must start extraction")
        elif self.outcome in _READY_OUTCOMES:
            if self.bootstrap is not None:
                raise ValueError("ready upload outcome cannot include bootstrap")
            if self.profile is None:
                raise ValueError("ready upload outcome requires profile summary")
        else:  # pragma: no cover - Literal validation rejects this first.
            raise ValueError("unsupported upload outcome")
        return self


__all__ = [
    "CvUploadOutcome",
    "CvUploadResponse",
    "PendingProfileBootstrap",
]
