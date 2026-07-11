"""Attachment storage domain errors and OS-error sanitization.

Public exception messages, ``repr``, ``__cause__``, and ``__context__`` must not
expose absolute or outside filesystem paths.
"""

from __future__ import annotations


class AttachmentStorageError(Exception):
    """Base storage error. Messages must not include absolute paths."""


class InvalidStoragePathError(AttachmentStorageError):
    """Path fails lexical validation or escapes FILES_DIR."""


class AttachmentStorageNotFoundError(AttachmentStorageError):
    """Target object is missing or not in a usable state for the operation."""


class AttachmentStorageStateError(AttachmentStorageError):
    """Operation is invalid for the object's current storage area/state."""


class AttachmentStorageCollisionError(AttachmentStorageStateError):
    """Destination already holds a logical attachment; never overwrite."""


class AttachmentStorageIOError(AttachmentStorageError):
    """Filesystem failure during stage/open/delete (sanitized)."""


class AttachmentStorageInvalidContentError(AttachmentStorageError):
    """Chunk stream yielded a non-bytes-like value."""


def safe_message(kind: str) -> str:
    """Return a generic error message without path disclosure."""
    return f"attachment storage {kind}"


def sanitize_os_error(exc: BaseException) -> AttachmentStorageError:
    """Map OS failures to domain errors without chaining path-bearing messages."""
    if isinstance(exc, FileNotFoundError):
        return AttachmentStorageNotFoundError(safe_message("not found"))
    if isinstance(exc, PermissionError):
        return AttachmentStorageIOError(safe_message("permission denied"))
    if isinstance(exc, FileExistsError):
        return AttachmentStorageCollisionError(safe_message("collision"))
    if isinstance(exc, IsADirectoryError):
        return InvalidStoragePathError(safe_message("invalid path"))
    return AttachmentStorageIOError(safe_message("io failed"))
