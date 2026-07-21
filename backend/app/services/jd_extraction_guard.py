"""Pure deterministic semantic guard for validated JD extraction output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

from app.services.jd_extraction import ExtractedJobPost, ExtractedJobSkillItem
from app.services.skill_normalization import (
    SkillNormalizer,
    collapse_whitespace,
    comparison_lowercase,
    unicode_normalize,
)

GuardIssueCode = Literal[
    "EVIDENCE_NOT_IN_SOURCE",
    "RESPONSIBILITY_NOT_IN_SOURCE",
    "METADATA_NOT_IN_SOURCE",
    "COMPOUND_SKILL_LABEL",
    "DUPLICATE_SKILL",
    "SKILL_GROUP_CONFLICT",
]

ISSUE_CODES: Final[frozenset[str]] = frozenset(
    {
        "EVIDENCE_NOT_IN_SOURCE",
        "RESPONSIBILITY_NOT_IN_SOURCE",
        "METADATA_NOT_IN_SOURCE",
        "COMPOUND_SKILL_LABEL",
        "DUPLICATE_SKILL",
        "SKILL_GROUP_CONFLICT",
    }
)

MAX_GUARD_ISSUES: Final[int] = 20

_PUNCTUATION_EXCEPTIONS: Final[frozenset[str]] = frozenset(
    {"c/c++", ".net", "node.js", "ci/cd"}
)

_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W_]+", re.UNICODE)
_ENUMERATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:[,;|/]|\b(?:and|or|và|hoặc)\b)\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GuardIssue:
    """One safe semantic issue without source or provider values."""

    code: GuardIssueCode
    field_path: str
    count: int


@dataclass(frozen=True, slots=True)
class JdExtractionGuardResult:
    """Accepted input or bounded safe issues; repr never exposes extraction data."""

    extraction: ExtractedJobPost | None = field(repr=False)
    issues: tuple[GuardIssue, ...]
    omitted_issue_count: int

    @property
    def accepted(self) -> bool:
        return self.extraction is not None


def normalize_guard_text(value: str) -> str:
    """Return the sole source-containment form: NFKC, whitespace, casefold."""
    return comparison_lowercase(collapse_whitespace(unicode_normalize(value)))


def _word_tokens(value: str) -> tuple[str, ...]:
    return tuple(_WORD_RE.findall(normalize_guard_text(value)))


def _approved_label_tokens(
    normalizer: SkillNormalizer,
) -> tuple[dict[str, str], tuple[tuple[tuple[str, ...], str], ...]]:
    exact_labels: dict[str, str] = {}
    token_labels: list[tuple[tuple[str, ...], str]] = []
    for skill in normalizer.taxonomy.skills:
        for label in (skill.display_name, *skill.aliases):
            normalized = normalize_guard_text(label)
            exact_labels[normalized] = skill.canonical_key
            tokens = _word_tokens(label)
            if tokens:
                token_labels.append((tokens, skill.canonical_key))
    return exact_labels, tuple(token_labels)


def _contains_token_sequence(
    tokens: tuple[str, ...],
    candidate: tuple[str, ...],
) -> bool:
    width = len(candidate)
    return any(
        tokens[index : index + width] == candidate
        for index in range(len(tokens) - width + 1)
    )


def _compound_part_count(
    label: str,
    *,
    exact_labels: dict[str, str],
    token_labels: tuple[tuple[tuple[str, ...], str], ...],
) -> int | None:
    normalized = normalize_guard_text(label)
    if normalized in _PUNCTUATION_EXCEPTIONS or normalized in exact_labels:
        return None

    enumerated_parts = tuple(
        part
        for part in _ENUMERATION_RE.split(normalized)
        if _word_tokens(part)
    )
    if len(enumerated_parts) >= 2:
        return len(enumerated_parts)

    tokens = _word_tokens(label)
    matched_keys = {
        canonical_key
        for approved_tokens, canonical_key in token_labels
        if _contains_token_sequence(tokens, approved_tokens)
    }
    if len(matched_keys) >= 2:
        return len(matched_keys)
    if matched_keys:
        return 2
    return None


def _grounded(value: str, normalized_source: str) -> bool:
    normalized_value = normalize_guard_text(value)
    return (not normalized_value) or (normalized_value in normalized_source)


def _normalized_key(
    item: ExtractedJobSkillItem,
    normalizer: SkillNormalizer,
) -> str | None:
    try:
        return normalizer.normalize_name(item.name).canonical_key
    except ValueError:
        return None


def guard_extracted_job_post(
    raw_jd: str,
    extracted: ExtractedJobPost,
    normalizer: SkillNormalizer,
) -> JdExtractionGuardResult:
    """Inspect one validated provider result without mutation or side effects."""
    if not isinstance(raw_jd, str):
        raise TypeError("raw JD must be a string")

    normalized_source = normalize_guard_text(raw_jd)
    exact_labels, token_labels = _approved_label_tokens(normalizer)
    all_issues: list[GuardIssue] = []

    def add(code: GuardIssueCode, field_path: str, count: int = 1) -> None:
        all_issues.append(GuardIssue(code=code, field_path=field_path, count=count))

    metadata = (
        ("title", extracted.title),
        ("company", extracted.company),
    )
    for field_path, value in metadata:
        if value is None:
            continue
        if not _grounded(value, normalized_source):
            add("METADATA_NOT_IN_SOURCE", field_path)

    for index, responsibility in enumerate(extracted.responsibilities):
        if not _grounded(responsibility, normalized_source):
            add("RESPONSIBILITY_NOT_IN_SOURCE", f"responsibilities[{index}]")

    required_counts: dict[str, int] = {}
    for item in extracted.required_skills:
        key = _normalized_key(item, normalizer)
        if key is None:
            continue
        required_counts[key] = required_counts.get(key, 0) + 1

    seen_required: dict[str, int] = {}
    for index, item in enumerate(extracted.required_skills):
        name_path = f"required_skills[{index}].name"
        compound_count = _compound_part_count(
            item.name,
            exact_labels=exact_labels,
            token_labels=token_labels,
        )
        if compound_count is not None:
            add("COMPOUND_SKILL_LABEL", name_path, compound_count)

        key = _normalized_key(item, normalizer)
        if key is not None:
            seen_required[key] = seen_required.get(key, 0) + 1
            if seen_required[key] > 1:
                add("DUPLICATE_SKILL", name_path, seen_required[key])

        for evidence_index, evidence in enumerate(item.evidence):
            if not _grounded(evidence, normalized_source):
                add(
                    "EVIDENCE_NOT_IN_SOURCE",
                    f"required_skills[{index}].evidence[{evidence_index}]",
                )

    seen_preferred: dict[str, int] = {}
    for index, item in enumerate(extracted.preferred_skills):
        name_path = f"preferred_skills[{index}].name"
        compound_count = _compound_part_count(
            item.name,
            exact_labels=exact_labels,
            token_labels=token_labels,
        )
        if compound_count is not None:
            add("COMPOUND_SKILL_LABEL", name_path, compound_count)

        key = _normalized_key(item, normalizer)
        if key is not None:
            seen_preferred[key] = seen_preferred.get(key, 0) + 1
            if seen_preferred[key] > 1:
                add("DUPLICATE_SKILL", name_path, seen_preferred[key])
            if key in required_counts:
                add(
                    "SKILL_GROUP_CONFLICT",
                    name_path,
                    required_counts[key] + seen_preferred[key],
                )

        for evidence_index, evidence in enumerate(item.evidence):
            if not _grounded(evidence, normalized_source):
                add(
                    "EVIDENCE_NOT_IN_SOURCE",
                    f"preferred_skills[{index}].evidence[{evidence_index}]",
                )

    if extracted.location is not None and not _grounded(
        extracted.location,
        normalized_source,
    ):
        add("METADATA_NOT_IN_SOURCE", "location")

    issues = tuple(all_issues[:MAX_GUARD_ISSUES])
    omitted_issue_count = len(all_issues) - len(issues)
    return JdExtractionGuardResult(
        extraction=None if all_issues else extracted,
        issues=issues,
        omitted_issue_count=omitted_issue_count,
    )


__all__ = [
    "GuardIssue",
    "GuardIssueCode",
    "ISSUE_CODES",
    "JdExtractionGuardResult",
    "MAX_GUARD_ISSUES",
    "guard_extracted_job_post",
    "normalize_guard_text",
]
