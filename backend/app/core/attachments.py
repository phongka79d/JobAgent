"""Schema-neutral attachment lifecycle vocabulary."""

from __future__ import annotations

ATTACHMENT_STATE_STAGED = "staged"
ATTACHMENT_STATE_ACTIVE = "active"
ATTACHMENT_STATE_ARCHIVED = "archived"
ATTACHMENT_STATE_FAILED = "failed"
ATTACHMENT_STATE_DELETING = "deleting"
ATTACHMENT_STATES: frozenset[str] = frozenset(
    {
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
        ATTACHMENT_STATE_DELETING,
    }
)
ATTACHMENT_MIME_TYPE_PDF = "application/pdf"
ATTACHMENT_STATE_DEFAULT = ATTACHMENT_STATE_STAGED
