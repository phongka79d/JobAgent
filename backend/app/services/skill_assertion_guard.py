"""Pure profession-neutral primitives shared by CV and JD skill guards.

This module owns normalization and structural checks only. Provider invocation,
logging, persistence, graph access, API mapping, and domain-specific rules stay
with their existing service owners.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_CLEAR_ENUMERATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:[,;|]|\s+/\s+|\s+or\s+|\s+ho\u1eb7c\s+)\s*",
    re.IGNORECASE,
)
_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class StructuralSkillIssue:
    """Sanitized issue projection without source or provider values."""

    code: str
    field_path: str
    count: int


def normalize_assertion_text(value: str) -> str:
    """Return NFKC, collapsed-whitespace, Unicode-casefold comparison text."""
    normalized = unicodedata.normalize("NFKC", value or "")
    return _WHITESPACE_RE.sub(" ", normalized).strip().casefold()


def is_source_grounded(value: str, source: str) -> bool:
    """Return whether a non-blank value occurs in source under one comparison."""
    normalized_value = normalize_assertion_text(value)
    if not normalized_value:
        return True
    return normalized_value in normalize_assertion_text(source)


def matches_heading(label: str, headings: Iterable[str]) -> bool:
    """Return whether label exactly equals one source heading after normalization."""
    normalized_label = normalize_assertion_text(label)
    return bool(normalized_label) and any(
        normalized_label == normalize_assertion_text(heading) for heading in headings
    )


def is_group_label_in_source(label: str, source: str) -> bool:
    """Return whether *label* is a structural ``label: nonempty value`` prefix."""
    normalized_label = normalize_assertion_text(label)
    normalized_source = normalize_assertion_text(source)
    if not normalized_label or not normalized_source:
        return False
    cursor = 0
    while True:
        position = normalized_source.find(normalized_label, cursor)
        if position < 0:
            return False
        before_ok = position == 0 or not normalized_source[position - 1].isalnum()
        suffix = normalized_source[position + len(normalized_label) :].lstrip()
        if before_ok and suffix.startswith(":") and suffix[1:].strip():
            return True
        cursor = position + len(normalized_label)


def structural_compound_part_count(
    label: str,
    *,
    approved_atomic_labels: Iterable[str] = (),
) -> int | None:
    """Return a clear enumeration count without consulting a skill dictionary.

    Contiguous punctuation such as ``C/C++`` or ``SEO/SEM`` remains ambiguous and
    therefore atomic at this pure boundary. Separators with unambiguous list shape
    are rejected. An exact approved full label always remains atomic.
    """
    normalized = normalize_assertion_text(label)
    if not normalized:
        return None
    if normalized in {
        normalize_assertion_text(item) for item in approved_atomic_labels
    }:
        return None
    parts = tuple(
        part
        for part in _CLEAR_ENUMERATION_RE.split(normalized)
        if _WORD_RE.search(part)
    )
    return len(parts) if len(parts) >= 2 else None


def structural_issue(
    code: str,
    field_path: str,
    *,
    count: int = 1,
) -> StructuralSkillIssue:
    """Create one safe structural issue with a positive count."""
    if not code or not code.strip():
        raise ValueError("issue code must be non-blank")
    if not field_path or not field_path.strip():
        raise ValueError("issue field_path must be non-blank")
    if count < 1:
        raise ValueError("issue count must be positive")
    return StructuralSkillIssue(
        code=code.strip(),
        field_path=field_path.strip(),
        count=count,
    )


__all__ = [
    "StructuralSkillIssue",
    "is_group_label_in_source",
    "is_source_grounded",
    "matches_heading",
    "normalize_assertion_text",
    "structural_compound_part_count",
    "structural_issue",
]
