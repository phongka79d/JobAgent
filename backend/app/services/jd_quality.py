"""Deterministic JD quality classification (Master §7.5 / Plan 5 §7.2).

Classifies a grounded ``JobPostExtraction`` as ``full``, ``partial``, or
``unscorable`` using only structured field occupancy and grounded skill /
responsibility signals. Reasons for every non-full outcome are returned
separately from the extraction object.

Rules (conservative):

- ``full``: usable title and description, grounded responsibility or skill
  evidence, and a majority of scoring-field groups populated.
- ``partial``: semantic content plus grounded skill signals, but misses the
  full threshold.
- ``unscorable``: insufficient semantic/skill content, contact-only, or no
  meaningful responsibility/skill evidence.

Salary is never a scoring-field group. Classification is pure and
side-effect-free; it does not call providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.schemas.job_post import (
    EmploymentType,
    JdQuality,
    JobPostExtraction,
    JobSeniority,
    JobSkill,
    JobWorkMode,
)

# Stable reason codes persisted outside the extraction object (Plan 5 §7.2).
REASON_MISSING_TITLE: Final[str] = "missing_usable_title"
REASON_MISSING_DESCRIPTION: Final[str] = "missing_usable_description"
REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE: Final[str] = (
    "missing_grounded_responsibility_or_skill_evidence"
)
REASON_MISSING_SKILL_SIGNALS: Final[str] = "missing_grounded_skill_signals"
REASON_MISSING_SEMANTIC: Final[str] = "missing_semantic_content"
REASON_SCORING_FIELDS_INSUFFICIENT: Final[str] = "scoring_field_groups_below_majority"
REASON_CONTACT_ONLY: Final[str] = "contact_only_or_insufficient_job_content"

# Hybrid-aligned scoring groups (Master §18.2) plus related readiness fields.
# Salary is intentionally excluded (display-only).
_SCORING_GROUP_NAMES: Final[tuple[str, ...]] = (
    "skills",
    "seniority",
    "experience",
    "location",
    "work_mode",
    "employment_type",
    "education",
    "language",
    "job_family",
)


@dataclass(frozen=True, slots=True)
class JdQualityAssessment:
    """Quality category plus reasons stored outside ``JobPostExtraction``."""

    quality: JdQuality
    reasons: tuple[str, ...]

    @property
    def reason_list(self) -> list[str]:
        """Mutable list copy suitable for JSON persistence."""
        return list(self.reasons)


def has_usable_title(extraction: JobPostExtraction) -> bool:
    return bool(extraction.title and extraction.title.strip())


def has_usable_description(extraction: JobPostExtraction) -> bool:
    if extraction.summary and extraction.summary.strip():
        return True
    return any(item.strip() for item in extraction.responsibilities)


def has_semantic_content(extraction: JobPostExtraction) -> bool:
    """Title or description present (minimum semantic signal)."""
    return has_usable_title(extraction) or has_usable_description(extraction)


def _skill_has_grounded_evidence(skill: JobSkill) -> bool:
    if skill.evidence:
        return True
    return bool(skill.skill.evidence)


def has_grounded_skill_signals(extraction: JobPostExtraction) -> bool:
    skills = list(extraction.required_skills) + list(extraction.preferred_skills)
    return any(_skill_has_grounded_evidence(s) for s in skills)


def has_grounded_responsibility_or_skill_evidence(
    extraction: JobPostExtraction,
) -> bool:
    if any(item.strip() for item in extraction.responsibilities):
        return True
    return has_grounded_skill_signals(extraction)


def populated_scoring_field_groups(extraction: JobPostExtraction) -> frozenset[str]:
    """Return names of scoring-field groups that are meaningfully populated."""
    populated: set[str] = set()

    if has_grounded_skill_signals(extraction):
        populated.add("skills")

    if extraction.seniority is not JobSeniority.UNKNOWN:
        populated.add("seniority")

    if (
        extraction.min_experience_years is not None
        or extraction.max_experience_years is not None
    ):
        populated.add("experience")

    if extraction.location and extraction.location.strip():
        populated.add("location")

    if extraction.work_mode is not JobWorkMode.UNKNOWN:
        populated.add("work_mode")

    if extraction.employment_type is not EmploymentType.UNKNOWN:
        populated.add("employment_type")

    if any(item.strip() for item in extraction.education_requirements):
        populated.add("education")

    if any(item.strip() for item in extraction.language_requirements):
        populated.add("language")

    if extraction.job_family and extraction.job_family.strip():
        populated.add("job_family")

    return frozenset(populated)


def majority_scoring_groups_populated(extraction: JobPostExtraction) -> bool:
    """True when more than half of the fixed scoring groups are populated."""
    total = len(_SCORING_GROUP_NAMES)
    majority_threshold = (total // 2) + 1  # strict majority of 9 → 5
    return len(populated_scoring_field_groups(extraction)) >= majority_threshold


def is_contact_only_or_empty(extraction: JobPostExtraction) -> bool:
    """True when the extraction carries no meaningful job structure."""
    if has_usable_title(extraction):
        return False
    if has_usable_description(extraction):
        return False
    if has_grounded_skill_signals(extraction):
        return False
    if extraction.company and extraction.company.strip():
        # Company alone without title/description/skills is still non-job content.
        return True
    return True


def classify_jd_quality(extraction: JobPostExtraction) -> JdQualityAssessment:
    """Classify quality conservatively; never trusts ``extraction.jd_quality``."""
    reasons: list[str] = []

    usable_title = has_usable_title(extraction)
    usable_description = has_usable_description(extraction)
    grounded_resp_or_skill = has_grounded_responsibility_or_skill_evidence(extraction)
    grounded_skills = has_grounded_skill_signals(extraction)
    semantic = has_semantic_content(extraction)
    majority = majority_scoring_groups_populated(extraction)

    # --- full ---
    if usable_title and usable_description and grounded_resp_or_skill and majority:
        return JdQualityAssessment(quality=JdQuality.FULL, reasons=())

    # --- partial: semantic + grounded skill signals, misses full ---
    if semantic and grounded_skills:
        if not usable_title:
            reasons.append(REASON_MISSING_TITLE)
        if not usable_description:
            reasons.append(REASON_MISSING_DESCRIPTION)
        if not grounded_resp_or_skill:
            reasons.append(REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE)
        if not majority:
            reasons.append(REASON_SCORING_FIELDS_INSUFFICIENT)
        # Guarantee at least one reason when not full (defensive).
        if not reasons:
            reasons.append(REASON_SCORING_FIELDS_INSUFFICIENT)
        return JdQualityAssessment(
            quality=JdQuality.PARTIAL,
            reasons=tuple(reasons),
        )

    # --- unscorable ---
    if is_contact_only_or_empty(extraction):
        reasons.append(REASON_CONTACT_ONLY)
    if not semantic:
        reasons.append(REASON_MISSING_SEMANTIC)
    if not grounded_skills:
        reasons.append(REASON_MISSING_SKILL_SIGNALS)
    if not grounded_resp_or_skill:
        reasons.append(REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    if not ordered:
        ordered.append(REASON_CONTACT_ONLY)
    return JdQualityAssessment(
        quality=JdQuality.UNSCORABLE,
        reasons=tuple(ordered),
    )


def apply_jd_quality(extraction: JobPostExtraction) -> tuple[JobPostExtraction, JdQualityAssessment]:
    """Return a copy with deterministic ``jd_quality`` and the assessment."""
    assessment = classify_jd_quality(extraction)
    updated = extraction.model_copy(update={"jd_quality": assessment.quality})
    return updated, assessment


__all__ = [
    "REASON_CONTACT_ONLY",
    "REASON_MISSING_DESCRIPTION",
    "REASON_MISSING_RESPONSIBILITY_OR_SKILL_EVIDENCE",
    "REASON_MISSING_SEMANTIC",
    "REASON_MISSING_SKILL_SIGNALS",
    "REASON_MISSING_TITLE",
    "REASON_SCORING_FIELDS_INSUFFICIENT",
    "JdQualityAssessment",
    "apply_jd_quality",
    "classify_jd_quality",
    "has_grounded_responsibility_or_skill_evidence",
    "has_grounded_skill_signals",
    "has_semantic_content",
    "has_usable_description",
    "has_usable_title",
    "is_contact_only_or_empty",
    "majority_scoring_groups_populated",
    "populated_scoring_field_groups",
]
