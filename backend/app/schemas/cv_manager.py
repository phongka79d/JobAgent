'''Strict CV Manager transport and action contracts.'''

from __future__ import annotations

from typing import Final, Literal

from app.schemas.common import AwareUtcDatetime, StrictModelConfig, UuidStr
from pydantic import BaseModel, Field

CvManagerAction = Literal[
    'preview',
    'download',
    'reextract',
    'activate_profile',
    'retry_upload',
    'delete_cv',
]

# Stable reprocess precondition codes (Master §14.1).
ERROR_CV_ATTACHMENT_NOT_FOUND: Final[str] = 'CV_ATTACHMENT_NOT_FOUND'
ERROR_CV_NOT_REPROCESSABLE: Final[str] = 'CV_NOT_REPROCESSABLE'
ERROR_CV_FILE_UNAVAILABLE: Final[str] = 'CV_FILE_UNAVAILABLE'
ERROR_CHUNKS_UNAVAILABLE: Final[str] = 'CHUNKS_UNAVAILABLE'
ERROR_APPROVAL_ACTION_REQUIRED: Final[str] = 'APPROVAL_ACTION_REQUIRED'

# Stable delete codes (Master §10.5 / §14.1 / §20).
ERROR_CV_PROFILE_OWNED_DELETE_FORBIDDEN: Final[str] = (
    'CV_PROFILE_OWNED_DELETE_FORBIDDEN'
)
ERROR_CV_ACTIVE_DELETE_FORBIDDEN: Final[str] = 'CV_ACTIVE_DELETE_FORBIDDEN'
CV_PROFILE_OWNED_DELETE_SUMMARY: Final[str] = (
    'This CV belongs to a profile. Delete the profile from the Profile menu instead.'
)
ERROR_CV_DELETE_CHECKPOINT_FAILED: Final[str] = 'CV_DELETE_CHECKPOINT_FAILED'
ERROR_CV_DELETE_FILE_FAILED: Final[str] = 'CV_DELETE_FILE_FAILED'
ERROR_CV_DELETE_GRAPH_FAILED: Final[str] = 'CV_DELETE_GRAPH_FAILED'
ERROR_CV_DELETE_FINALIZE_FAILED: Final[str] = 'CV_DELETE_FINALIZE_FAILED'

# Safe retry guidance returned with partial-cleanup failures (no secrets/paths).
CV_DELETE_RETRY_SUMMARY: Final[str] = (
    'CV deletion is incomplete; the attachment remains in deleting state. '
    'Retry DELETE for the same attachment id.'
)


class CvManagerItem(BaseModel):
    model_config = StrictModelConfig

    id: UuidStr
    original_name: str = Field(min_length=1, max_length=500)
    state: Literal['staged', 'active', 'archived', 'failed', 'deleting']
    failure_code: str | None
    page_count: int | None
    file_available: bool
    profile_id: UuidStr | None
    profile_display_name: str | None
    profile_state: Literal['pending', 'ready', 'deleting'] | None
    is_active_profile: bool
    allowed_actions: list[CvManagerAction]
    created_at: AwareUtcDatetime
    updated_at: AwareUtcDatetime


class CvManagerListResponse(BaseModel):
    model_config = StrictModelConfig

    items: list[CvManagerItem]


__all__ = [
    'CV_DELETE_RETRY_SUMMARY',
    'CV_PROFILE_OWNED_DELETE_SUMMARY',
    'CvManagerAction',
    'CvManagerItem',
    'CvManagerListResponse',
    'ERROR_APPROVAL_ACTION_REQUIRED',
    'ERROR_CV_ACTIVE_DELETE_FORBIDDEN',
    'ERROR_CHUNKS_UNAVAILABLE',
    'ERROR_CV_ATTACHMENT_NOT_FOUND',
    'ERROR_CV_DELETE_CHECKPOINT_FAILED',
    'ERROR_CV_DELETE_FILE_FAILED',
    'ERROR_CV_DELETE_FINALIZE_FAILED',
    'ERROR_CV_DELETE_GRAPH_FAILED',
    'ERROR_CV_FILE_UNAVAILABLE',
    'ERROR_CV_NOT_REPROCESSABLE',
    'ERROR_CV_PROFILE_OWNED_DELETE_FORBIDDEN',
]
