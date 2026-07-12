"""Public approved-profile read contracts (Plan 4 §7.1; Master §14).

``GET /api/profile`` exposes one deterministic no-profile / active document.
It never carries drafts, raw PDF text, storage paths, hashes, embeddings, or
provider payloads. Active-CV bytes are served only by ``GET /api/profile/cv``.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences


class ProfilePresenceState(StrEnum):
    """Deterministic public profile presence for the approved singleton."""

    NONE = "none"
    ACTIVE = "active"


class SafeActiveAttachment(BaseModel):
    """Safe active-CV metadata only (no path, hash, or provider fields)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    original_name: str = Field(..., min_length=1, max_length=512)
    mime_type: str = Field(..., min_length=1, max_length=128)
    size_bytes: int = Field(..., ge=0)
    page_count: int | None = Field(default=None, ge=0)
    state: str = Field(..., min_length=1, max_length=32)


class ProfileResponse(BaseModel):
    """One typed contract for no-profile and active approved state.

    When ``state`` is ``none``, ``profile``, ``preferences``, and
    ``active_attachment`` are always null. When ``state`` is ``active``,
    ``profile`` is always present; preferences and attachment metadata are
    optional and never invent a second active CV.
    """

    model_config = ConfigDict(extra="forbid")

    state: ProfilePresenceState
    profile: CandidateProfile | None = None
    preferences: JobPreferences | None = None
    active_attachment: SafeActiveAttachment | None = None

    @model_validator(mode="after")
    def _consistent_presence(self) -> ProfileResponse:
        if self.state is ProfilePresenceState.NONE:
            if (
                self.profile is not None
                or self.preferences is not None
                or self.active_attachment is not None
            ):
                raise ValueError("no-profile state must not carry domain payloads")
            return self
        if self.profile is None:
            raise ValueError("active state requires an approved profile")
        return self


__all__ = [
    "ProfilePresenceState",
    "ProfileResponse",
    "SafeActiveAttachment",
]
