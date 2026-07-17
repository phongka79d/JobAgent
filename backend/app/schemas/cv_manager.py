"""CV Manager mutation transport contracts (Plan 9 / Master §14.1).

Stable application error codes for reprocess and delete routes.
No business rules, SQL, SSE framing, or Agent construction live here.
"""

from __future__ import annotations

from typing import Final

# Stable reprocess precondition codes (Master §14.1).
ERROR_CV_ATTACHMENT_NOT_FOUND: Final[str] = "CV_ATTACHMENT_NOT_FOUND"
ERROR_CV_NOT_REPROCESSABLE: Final[str] = "CV_NOT_REPROCESSABLE"
ERROR_CV_FILE_UNAVAILABLE: Final[str] = "CV_FILE_UNAVAILABLE"
ERROR_CHUNKS_UNAVAILABLE: Final[str] = "CHUNKS_UNAVAILABLE"
ERROR_APPROVAL_ACTION_REQUIRED: Final[str] = "APPROVAL_ACTION_REQUIRED"

# Stable delete codes (Master §10.5 / §14.1 / §20).
ERROR_CV_ACTIVE_DELETE_FORBIDDEN: Final[str] = "CV_ACTIVE_DELETE_FORBIDDEN"
ERROR_CV_DELETE_CHECKPOINT_FAILED: Final[str] = "CV_DELETE_CHECKPOINT_FAILED"
ERROR_CV_DELETE_FILE_FAILED: Final[str] = "CV_DELETE_FILE_FAILED"
ERROR_CV_DELETE_GRAPH_FAILED: Final[str] = "CV_DELETE_GRAPH_FAILED"
ERROR_CV_DELETE_FINALIZE_FAILED: Final[str] = "CV_DELETE_FINALIZE_FAILED"

# Safe retry guidance returned with partial-cleanup failures (no secrets/paths).
CV_DELETE_RETRY_SUMMARY: Final[str] = (
    "CV deletion is incomplete; the attachment remains in deleting state. "
    "Retry DELETE for the same attachment id."
)

__all__ = [
    "CV_DELETE_RETRY_SUMMARY",
    "ERROR_APPROVAL_ACTION_REQUIRED",
    "ERROR_CHUNKS_UNAVAILABLE",
    "ERROR_CV_ACTIVE_DELETE_FORBIDDEN",
    "ERROR_CV_ATTACHMENT_NOT_FOUND",
    "ERROR_CV_DELETE_CHECKPOINT_FAILED",
    "ERROR_CV_DELETE_FILE_FAILED",
    "ERROR_CV_DELETE_FINALIZE_FAILED",
    "ERROR_CV_DELETE_GRAPH_FAILED",
    "ERROR_CV_FILE_UNAVAILABLE",
    "ERROR_CV_NOT_REPROCESSABLE",
]
