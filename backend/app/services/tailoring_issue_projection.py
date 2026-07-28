"""Bounded, privacy-safe projection of internal tailoring grounding issues."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from app.schemas.cv_tailoring import TailoredCVContent, TailoringUserIssue
from app.services.cv_tailoring_guard import GroundingIssue

_PREFIX = "tailoring-grounding:v1:"
_PATH = re.compile(
    r"^(?:sections|sections\[(?P<section>\d+)\](?:\.items\[(?P<item>\d+)\])?(?:\.(?P<field>title|subtitle|date_text|location|body|bullets\[\d+\]|attributes(?:\[\d+\])?))?)$"
)
_Reason = Literal[
    "not_in_source",
    "belongs_to_another_section",
    "structure_changed",
    "required_source_missing",
    "unsupported_value",
]
_REASONS: dict[str, _Reason] = {
    "UNKNOWN_FACT": "required_source_missing",
    "CROSS_SECTION_FACT": "belongs_to_another_section",
    "UNSUPPORTED_ANCHOR": "not_in_source",
    "EMPTY_PROVENANCE": "required_source_missing",
    "SECTION_IDENTITY_CHANGED": "structure_changed",
    "ATTRIBUTE_IDENTITY_CHANGED": "structure_changed",
    "CONTENT_BOUNDS_EXCEEDED": "unsupported_value",
}


def _is_safe_path(path: str) -> bool:
    if len(path) > 240:
        return False
    match = _PATH.fullmatch(path)
    if match is None:
        return False
    section = match.group("section")
    item = match.group("item")
    return (section is None or int(section) <= 20) and (
        item is None or int(item) <= 30
    )


def encode_internal_issue(issue: GroundingIssue) -> str:
    if not _is_safe_path(issue.path):
        return f"{_PREFIX}UNKNOWN_FACT|sections"
    return f"{_PREFIX}{issue.code}|{issue.path}"


def decode_internal_issue(value: str | None) -> GroundingIssue | None:
    if value is None or not value.startswith(_PREFIX):
        return None
    encoded = value[len(_PREFIX) :]
    code, separator, path = encoded.partition("|")
    if separator == "" or not _is_safe_path(path):
        return None
    try:
        return GroundingIssue(code=code, path=path)
    except ValueError:
        return None


def _field(value: str | None) -> Literal[
    "title", "subtitle", "date", "location", "body", "bullet", "attribute", "section"
]:
    if value is None:
        return "section"
    if value == "date_text":
        return "date"
    if value.startswith("bullets"):
        return "bullet"
    if value.startswith("attributes"):
        return "attribute"
    if value in {"title", "subtitle", "location", "body"}:
        return value
    return "section"


def _generic(parent: TailoredCVContent) -> TailoringUserIssue:
    section = parent.sections[0]
    return TailoringUserIssue(
        section_id=section.id,
        section_heading=section.heading,
        item_index=None,
        field="section",
        reason="required_source_missing",
    )


def project_grounding_issues(
    *, issue_list: Sequence[GroundingIssue], parent: TailoredCVContent
) -> list[TailoringUserIssue]:
    if not parent.sections:
        return []
    projected: list[TailoringUserIssue] = []
    seen: set[tuple[str, int | None, str, str]] = set()
    for issue in issue_list[:10]:
        match = _PATH.fullmatch(issue.path)
        reason = _REASONS.get(issue.code)
        if match is None or reason is None or match.group("section") is None:
            candidate = _generic(parent)
        else:
            section_index = int(match.group("section"))
            if section_index >= len(parent.sections):
                candidate = _generic(parent)
            else:
                section = parent.sections[section_index]
                item = match.group("item")
                item_index = int(item) if item is not None else None
                if item_index is not None and item_index >= len(section.items):
                    candidate = _generic(parent)
                else:
                    candidate = TailoringUserIssue(
                        section_id=section.id,
                        section_heading=section.heading,
                        item_index=item_index,
                        field=_field(match.group("field")),
                        reason=reason,
                    )
        key = (
            candidate.section_id,
            candidate.item_index,
            candidate.field,
            candidate.reason,
        )
        if key not in seen:
            seen.add(key)
            projected.append(candidate)
        if len(projected) == 10:
            break
    return projected or [_generic(parent)]


def is_internal_issue_activity(value: str | None) -> bool:
    return value is not None and value.startswith(_PREFIX)


__all__ = [
    "decode_internal_issue",
    "encode_internal_issue",
    "is_internal_issue_activity",
    "project_grounding_issues",
]
