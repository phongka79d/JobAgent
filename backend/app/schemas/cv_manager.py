"""CV Manager mutation transport contracts (Plan 9 / Master §14.1).

Stable application error codes for reprocess (and later delete) routes.
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

__all__ = [
    "ERROR_APPROVAL_ACTION_REQUIRED",
    "ERROR_CHUNKS_UNAVAILABLE",
    "ERROR_CV_ATTACHMENT_NOT_FOUND",
    "ERROR_CV_FILE_UNAVAILABLE",
    "ERROR_CV_NOT_REPROCESSABLE",
]
