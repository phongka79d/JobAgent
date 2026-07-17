"""Historical CV ownership resolution for deletion (Plan 9).

One shared resolver over validated structured payload / tool-result shapes.
Never regexes free-form chat text. Explicit ``source_attachment_id`` columns
are preferred; structured maps are scanned only for allowlisted UUID keys.
"""

from __future__ import annotations

import uuid
from typing import Any

# Allowlisted map keys that may identify a CV attachment (observability parity).
_ATTACHMENT_ID_KEYS: frozenset[str] = frozenset(
    {
        "attachment_id",
        "source_attachment_id",
        "active_attachment_id",
    }
)


def is_uuid_v4(value: object) -> bool:
    """Return True when *value* is a lowercase-or-mixed UUID v4 string."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = uuid.UUID(value.strip().lower())
    except ValueError:
        return False
    return parsed.version == 4


def normalize_attachment_id(value: object) -> str | None:
    """Return a stripped UUID v4 string, or ``None`` when not valid."""
    if not is_uuid_v4(value):
        return None
    assert isinstance(value, str)
    return value.strip().lower()


def structured_map_owns_attachment(
    mapping: dict[str, Any] | None,
    attachment_id: str,
) -> bool:
    """True when a validated structured map names *attachment_id* via allowlist.

    Scans only top-level keys and one nested ``card`` object (approval
    projection shape). Does not walk arbitrary depth or free-form strings.
    """
    target = normalize_attachment_id(attachment_id)
    if target is None or not isinstance(mapping, dict):
        return False

    def _hit(obj: dict[str, Any]) -> bool:
        for key, value in obj.items():
            if key not in _ATTACHMENT_ID_KEYS:
                continue
            found = normalize_attachment_id(value)
            if found is not None and found == target:
                return True
        return False

    if _hit(mapping):
        return True
    card = mapping.get("card")
    if isinstance(card, dict) and _hit(card):
        return True
    return False


def tool_record_owns_attachment(
    *,
    source_attachment_id: str | None,
    arguments_summary_json: dict[str, Any] | None,
    result_json: dict[str, Any] | None,
    attachment_id: str,
) -> bool:
    """True when a tool execution is owned by *attachment_id*.

    Prefer explicit ``source_attachment_id``. Otherwise inspect validated
    argument summary keys and ``ToolResult.data`` only.
    """
    target = normalize_attachment_id(attachment_id)
    if target is None:
        return False
    explicit = normalize_attachment_id(source_attachment_id)
    if explicit is not None and explicit == target:
        return True
    if structured_map_owns_attachment(arguments_summary_json, target):
        return True
    if isinstance(result_json, dict):
        data = result_json.get("data")
        if isinstance(data, dict) and structured_map_owns_attachment(data, target):
            return True
    return False


def message_owns_attachment(
    *,
    source_attachment_id: str | None,
    structured_payload: dict[str, Any] | None,
    attachment_id: str,
) -> bool:
    """True when a chat message is owned by *attachment_id*."""
    target = normalize_attachment_id(attachment_id)
    if target is None:
        return False
    explicit = normalize_attachment_id(source_attachment_id)
    if explicit is not None and explicit == target:
        return True
    return structured_map_owns_attachment(structured_payload, target)


__all__ = [
    "is_uuid_v4",
    "message_owns_attachment",
    "normalize_attachment_id",
    "structured_map_owns_attachment",
    "tool_record_owns_attachment",
]
