"""Authoritative service-path grammar for attachment storage and metadata.

Single source of truth for ``staged/<uuid>`` / ``active/<uuid>`` validation.
Both the filesystem storage layer and the attachment repository import from here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final
from uuid import UUID

from app.services.attachment_storage_errors import (
    InvalidStoragePathError,
    safe_message,
)

STAGED_AREA: Final[str] = "staged"
ACTIVE_AREA: Final[str] = "active"
ALLOWED_AREAS: Final[frozenset[str]] = frozenset({STAGED_AREA, ACTIVE_AREA})
PARTIAL_SUFFIX: Final[str] = ".partial"
DEFAULT_CHUNK_SIZE: Final[int] = 64 * 1024

# Reserved Windows device names (case-insensitive) rejected as path leaves.
_RESERVED_LEAF_NAMES: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)


def _looks_encoded_or_malformed(name: str) -> bool:
    """Reject percent-encoding, nested escapes, and non-plain leaf forms."""
    if "%" in name or name != name.strip():
        return True
    if name.startswith(".") or name.endswith("."):
        return True
    if name.startswith("{") or name.endswith("}") or ":" in name:
        return True
    return False


def _is_reserved_leaf(name: str) -> bool:
    reserved = name.split(".")[0].lower()
    return name.lower() in _RESERVED_LEAF_NAMES or reserved in _RESERVED_LEAF_NAMES


def parse_service_storage_path(storage_path: str) -> tuple[str, str]:
    """Parse and fully validate a service-relative storage path.

    Accepted form: ``staged/<uuid>`` or ``active/<uuid>`` using forward slashes
    where ``<uuid>`` is exactly ``str(UUID)`` (lowercase hex with hyphens).
    Rejects empty values, absolute paths, drive letters, parent traversal,
    multi-segment names, reserved device names, encoded forms, and non-UUID leaves.
    Does not touch the filesystem.
    """
    if not isinstance(storage_path, str) or not storage_path:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if "\x00" in storage_path:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if storage_path.startswith(("/", "\\")):
        raise InvalidStoragePathError(safe_message("invalid path"))
    if len(storage_path) >= 2 and storage_path[1] == ":":
        raise InvalidStoragePathError(safe_message("invalid path"))
    if "\\" in storage_path:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if storage_path.strip() != storage_path or storage_path in {".", ".."}:
        raise InvalidStoragePathError(safe_message("invalid path"))

    try:
        as_path = Path(storage_path)
    except (TypeError, ValueError):
        raise InvalidStoragePathError(safe_message("invalid path")) from None

    if as_path.is_absolute() or as_path.drive:
        raise InvalidStoragePathError(safe_message("invalid path"))

    parts = as_path.parts
    if len(parts) != 2:
        raise InvalidStoragePathError(safe_message("invalid path"))
    area, name = parts
    if area not in ALLOWED_AREAS:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if not name or name in {".", ".."} or name.endswith(PARTIAL_SUFFIX):
        raise InvalidStoragePathError(safe_message("invalid path"))
    if "/" in name or "\\" in name or ".." in name:
        raise InvalidStoragePathError(safe_message("invalid path"))
    if _looks_encoded_or_malformed(name) or _is_reserved_leaf(name):
        raise InvalidStoragePathError(safe_message("invalid path"))

    # Canonical UUID leaf only (exact str(UUID) spelling).
    try:
        parsed = UUID(name)
    except (ValueError, AttributeError, TypeError):
        raise InvalidStoragePathError(safe_message("invalid path")) from None
    if name != str(parsed):
        raise InvalidStoragePathError(safe_message("invalid path"))
    return area, name


def require_canonical_service_path(
    storage_path: str,
    attachment_id: UUID,
    *,
    expected_area: str,
) -> str:
    """Require ``area/<uuid>`` with leaf exactly matching ``str(attachment_id)``.

    Used by the metadata repository. Storage path grammar is identical to
    :func:`parse_service_storage_path`; this adds area and identity matching.
    """
    if expected_area not in ALLOWED_AREAS:
        raise InvalidStoragePathError(safe_message("invalid path"))
    try:
        area, name = parse_service_storage_path(storage_path)
    except InvalidStoragePathError:
        raise InvalidStoragePathError(safe_message("invalid path")) from None

    if area != expected_area:
        raise InvalidStoragePathError(safe_message("invalid path"))

    expected_leaf = str(attachment_id)
    if name != expected_leaf:
        try:
            parsed = UUID(name)
        except (ValueError, AttributeError, TypeError):
            raise InvalidStoragePathError(safe_message("invalid path")) from None
        if parsed != attachment_id:
            # Distinguish identity mismatch for repository mapping.
            raise InvalidStoragePathError(safe_message("path identity mismatch"))
        raise InvalidStoragePathError(safe_message("invalid path"))
    return storage_path


def service_path_for(area: str, attachment_id: UUID) -> str:
    """Build a canonical service-relative path for an attachment id."""
    if area not in ALLOWED_AREAS:
        raise InvalidStoragePathError(safe_message("invalid path"))
    return f"{area}/{attachment_id}"
