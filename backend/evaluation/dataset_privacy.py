"""Privacy guards and safe-field helpers for Plan 6 evaluation contracts.

Rejects raw document bodies, contact PII, secrets, and path-like private fields
before schema parse. Shared by row models, envelopes, and loaders without
duplicating forbidden-name rules.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

MAX_SAFE_ID_LEN: Final[int] = 128
MAX_TOKEN_LEN: Final[int] = 64
MAX_SKILL_LIST: Final[int] = 64
MAX_DIGEST_HEX_LEN: Final[int] = 64
MAX_NOTES_LEN: Final[int] = 256

SAFE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$"
)
DIGEST_HEX_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-f0-9]{64}$")

# Field names that must never appear on committed or validated private inputs.
FORBIDDEN_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "raw_cv",
        "raw_jd",
        "document_text",
        "document_body",
        "cv_text",
        "jd_text",
        "job_description",
        "full_text",
        "body",
        "contact_email",
        "contact_phone",
        "phone",
        "email",
        "contact_address",
        "home_address",
        "ssn",
        "api_key",
        "authorization",
        "password",
        "secret",
        "private_path",
        "absolute_path",
        "file_path",
        "attachment_path",
    }
)

FORBIDDEN_VALUE_MARKERS: Final[tuple[str, ...]] = (
    "-----BEGIN",
    "sk-",
    "Bearer ",
    "@gmail.com",
    "@yahoo.com",
    "password=",
    "api_key=",
)


class DatasetContractError(ValueError):
    """Raised when a dataset contract or privacy rule is violated."""


def normalize_safe_id(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be non-empty")
    if len(cleaned) > MAX_SAFE_ID_LEN:
        raise ValueError(f"{field_name} exceeds {MAX_SAFE_ID_LEN} characters")
    if not SAFE_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a safe alphanumeric ID")
    return cleaned


def normalize_token(value: str, *, field_name: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError(f"{field_name} must be non-empty")
    if len(cleaned) > MAX_TOKEN_LEN:
        raise ValueError(f"{field_name} exceeds {MAX_TOKEN_LEN} characters")
    lower = cleaned.lower()
    for marker in FORBIDDEN_VALUE_MARKERS:
        if marker.lower() in lower:
            raise ValueError(f"{field_name} contains prohibited content marker")
    return cleaned


def normalize_token_list(
    values: Sequence[str],
    *,
    field_name: str,
    max_items: int = MAX_SKILL_LIST,
) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} exceeds {max_items} items")
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        token = normalize_token(str(raw), field_name=field_name)
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def assert_no_forbidden_fields(payload: Mapping[str, Any], *, path: str = "$") -> None:
    """Reject known private/raw field names anywhere in a nested mapping."""
    for key, value in payload.items():
        key_str = str(key)
        lowered = key_str.casefold()
        if lowered in FORBIDDEN_FIELD_NAMES or any(
            marker in lowered for marker in ("raw_", "secret", "password", "api_key")
        ):
            raise DatasetContractError(f"forbidden field {key_str!r} at {path}")
        if isinstance(value, Mapping):
            assert_no_forbidden_fields(value, path=f"{path}.{key_str}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    assert_no_forbidden_fields(
                        item, path=f"{path}.{key_str}[{index}]"
                    )


def content_digest(payload: Mapping[str, Any] | Sequence[Any] | str) -> str:
    """Stable SHA-256 hex digest of canonical JSON (or UTF-8 string)."""
    if isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def normalize_digest_hex(value: str) -> str:
    cleaned = value.strip().lower()
    if not DIGEST_HEX_PATTERN.fullmatch(cleaned):
        raise ValueError("digest must be a 64-char lowercase hex SHA-256")
    return cleaned
