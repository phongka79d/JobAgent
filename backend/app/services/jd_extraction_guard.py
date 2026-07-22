"""Pure deterministic semantic guard for validated JD extraction output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from app.services.jd_extraction import ExtractedJobPost, ExtractedJobSkillItem
from app.services.skill_assertion_guard import (
    StructuralSkillIssue,
    is_label_grounded,
    is_source_grounded,
    normalize_assertion_text,
    structural_compound_part_count,
    structural_issue,
)
from app.services.skill_normalization import SkillNormalizer

GuardIssueCode = Literal[
    "EVIDENCE_NOT_IN_SOURCE",
    "SKILL_NAME_NOT_IN_SOURCE",
    "RESPONSIBILITY_NOT_IN_SOURCE",
    "METADATA_NOT_IN_SOURCE",
    "COMPOUND_SKILL_LABEL",
    "DUPLICATE_SKILL",
    "SKILL_GROUP_CONFLICT",
]

ISSUE_CODES: Final[tuple[GuardIssueCode, ...]] = (
    "EVIDENCE_NOT_IN_SOURCE",
    "SKILL_NAME_NOT_IN_SOURCE",
    "RESPONSIBILITY_NOT_IN_SOURCE",
    "METADATA_NOT_IN_SOURCE",
    "COMPOUND_SKILL_LABEL",
    "DUPLICATE_SKILL",
    "SKILL_GROUP_CONFLICT",
)

MAX_GUARD_ISSUES: Final[int] = 20

GuardIssue = StructuralSkillIssue


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
    return normalize_assertion_text(value)


def _normalized_key(
    item: ExtractedJobSkillItem,
    normalizer: SkillNormalizer,
) -> str | None:
    try:
        return normalizer.normalize_name(item.name).canonical_key
    except ValueError:
        return None


def _approved_labels(
    item: ExtractedJobSkillItem,
    normalizer: SkillNormalizer,
) -> tuple[str, ...]:
    try:
        ref = normalizer.normalize_name(item.name)
    except ValueError:
        return ()
    if not normalizer.is_seed_skill(ref.canonical_key):
        return ()
    return (ref.display_name, *ref.aliases)


def guard_extracted_job_post(
    raw_jd: str,
    extracted: ExtractedJobPost,
    normalizer: SkillNormalizer,
) -> JdExtractionGuardResult:
    """Inspect one validated provider result without mutation or side effects."""
    if not isinstance(raw_jd, str):
        raise TypeError("raw JD must be a string")

    normalized_source = normalize_guard_text(raw_jd)
    all_issues: list[GuardIssue] = []

    def add(code: GuardIssueCode, field_path: str, count: int = 1) -> None:
        all_issues.append(structural_issue(code, field_path, count=count))

    metadata = (
        ("title", extracted.title),
        ("company", extracted.company),
    )
    for field_path, value in metadata:
        if value is None:
            continue
        if not is_source_grounded(value, normalized_source):
            add("METADATA_NOT_IN_SOURCE", field_path)

    for index, responsibility in enumerate(extracted.responsibilities):
        if not is_source_grounded(responsibility, normalized_source):
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
        approved_labels = _approved_labels(item, normalizer)
        if not is_label_grounded(
            item.name,
            (normalized_source,),
            approved_aliases=approved_labels,
        ):
            add("SKILL_NAME_NOT_IN_SOURCE", name_path)
        compound_count = structural_compound_part_count(
            item.name,
            approved_atomic_labels=approved_labels,
        )
        if compound_count is not None:
            add("COMPOUND_SKILL_LABEL", name_path, compound_count)

        key = _normalized_key(item, normalizer)
        if key is not None:
            seen_required[key] = seen_required.get(key, 0) + 1
            if seen_required[key] > 1:
                add("DUPLICATE_SKILL", name_path, seen_required[key])

        for evidence_index, evidence in enumerate(item.evidence):
            if not is_source_grounded(evidence, normalized_source):
                add(
                    "EVIDENCE_NOT_IN_SOURCE",
                    f"required_skills[{index}].evidence[{evidence_index}]",
                )

    seen_preferred: dict[str, int] = {}
    for index, item in enumerate(extracted.preferred_skills):
        name_path = f"preferred_skills[{index}].name"
        approved_labels = _approved_labels(item, normalizer)
        if not is_label_grounded(
            item.name,
            (normalized_source,),
            approved_aliases=approved_labels,
        ):
            add("SKILL_NAME_NOT_IN_SOURCE", name_path)
        compound_count = structural_compound_part_count(
            item.name,
            approved_atomic_labels=approved_labels,
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
            if not is_source_grounded(evidence, normalized_source):
                add(
                    "EVIDENCE_NOT_IN_SOURCE",
                    f"preferred_skills[{index}].evidence[{evidence_index}]",
                )

    if extracted.location is not None and not is_source_grounded(
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
