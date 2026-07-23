"""Public attachment / CV-upload response contracts (Plan 4 §7.3 / §7.8).

Compact metadata only: no ``storage_path``, no raw PDF bytes, no secrets.
Validated at the HTTP boundary before responses leave the route.
"""

from __future__ import annotations

from typing import Literal

from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
)
from app.schemas.common import StrictModelConfig, UuidStr
from pydantic import BaseModel, Field

# Public lifecycle states returned on profile/upload boundaries. Includes
# archived so pending drafts from CV Manager reprocess of archived CVs can
# surface without 500s (upload outcomes still use staged/active/failed only).
AttachmentState = Literal["staged", "active", "archived", "failed"]

assert frozenset(("staged", "active", "archived", "failed")) == frozenset(
    {
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
    }
)


class AttachmentPublic(BaseModel):
    """Safe public attachment metadata (no filesystem path)."""

    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1)
    mime_type: Literal["application/pdf"] = ATTACHMENT_MIME_TYPE_PDF  # type: ignore[assignment]
    size_bytes: int = Field(gt=0)
    page_count: int | None = Field(default=None, gt=0)
    state: AttachmentState
    failure_code: str | None = None


class ProfileUploadSummary(BaseModel):
    """Compact approved-profile presence for active-hash reuse responses."""

    model_config = StrictModelConfig

    present: bool
    profile_id: UuidStr | None = None
    current_title: str | None = None


class DraftUploadSummary(BaseModel):
    """Compact current-draft presence for staged-hash reuse responses."""

    model_config = StrictModelConfig

    present: bool
    draft_id: Literal["current"] | None = None
    source_attachment_id: UuidStr | None = None


__all__ = [
    "AttachmentPublic",
    "AttachmentState",
    "DraftUploadSummary",
    "ProfileUploadSummary",
]
