"""Pure selected-JD compatibility facts built from authoritative SQLite skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.schemas.jobs import JobPostExtraction, JobSkill
from app.schemas.profile import CandidateProfile, CandidateSkill
from app.services.skill_matching import SkillMatchFact, compute_skill_coverage
from app.services.skill_normalization import RelatedToEdge, SkillNormalizer

MAX_SKILL_MAP_ITEMS: Final[int] = 200

CompatibilityMatchType = Literal[
    "direct",
    "related",
    "missing_required",
    "missing_preferred",
    "candidate_only",
]
CompatibilityRequirement = Literal["required", "preferred", "none"]


class SkillCompatibilityError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SkillAssertionView:
    canonical_key: str
    display_name: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkillCompatibilityItem:
    match_type: CompatibilityMatchType
    requirement: CompatibilityRequirement
    strength: float
    candidate_skill: SkillAssertionView | None
    job_skill: SkillAssertionView | None
    relationship: RelatedToEdge | None


@dataclass(frozen=True, slots=True)
class SkillCompatibilityCounts:
    direct: int
    related: int
    missing_required: int
    missing_preferred: int
    candidate_only: int

    def as_dict(self) -> dict[str, int]:
        return {
            "direct": self.direct,
            "related": self.related,
            "missing_required": self.missing_required,
            "missing_preferred": self.missing_preferred,
            "candidate_only": self.candidate_only,
        }


@dataclass(frozen=True, slots=True)
class SkillCompatibilityProjection:
    items: tuple[SkillCompatibilityItem, ...]
    counts: SkillCompatibilityCounts


def _candidate_view(skill: CandidateSkill) -> SkillAssertionView:
    return SkillAssertionView(
        canonical_key=skill.skill.canonical_key,
        display_name=skill.skill.display_name,
        confidence=float(skill.confidence),
        evidence=tuple(skill.evidence),
    )


def _job_view(skill: JobSkill) -> SkillAssertionView:
    return SkillAssertionView(
        canonical_key=skill.skill.canonical_key,
        display_name=skill.skill.display_name,
        confidence=float(skill.confidence),
        evidence=tuple(skill.evidence),
    )


def _job_item(
    fact: SkillMatchFact,
    *,
    requirement: Literal["required", "preferred"],
) -> SkillCompatibilityItem:
    if fact.match_type == "direct":
        match_type: CompatibilityMatchType = "direct"
    elif fact.match_type == "related":
        match_type = "related"
    elif requirement == "required":
        match_type = "missing_required"
    else:
        match_type = "missing_preferred"
    return SkillCompatibilityItem(
        match_type=match_type,
        requirement=requirement,
        strength=fact.strength,
        candidate_skill=(
            None
            if fact.candidate_skill is None
            else _candidate_view(fact.candidate_skill)
        ),
        job_skill=_job_view(fact.job_skill),
        relationship=fact.relationship,
    )


def _counts(items: tuple[SkillCompatibilityItem, ...]) -> SkillCompatibilityCounts:
    values = {key: 0 for key in (
        "direct",
        "related",
        "missing_required",
        "missing_preferred",
        "candidate_only",
    )}
    for item in items:
        values[item.match_type] += 1
    return SkillCompatibilityCounts(**values)


def build_skill_compatibility(
    profile: CandidateProfile,
    extraction: JobPostExtraction,
    normalizer: SkillNormalizer,
) -> SkillCompatibilityProjection:
    """Classify stored atomic assertions using the existing matching owner."""
    candidates = tuple(skill for skill in profile.skills if not skill.excluded)
    coverage = compute_skill_coverage(
        candidates,
        required_skills=extraction.required_skills,
        preferred_skills=extraction.preferred_skills,
        normalizer=normalizer,
    )
    items: list[SkillCompatibilityItem] = [
        *(
            _job_item(fact, requirement="required")
            for fact in coverage.required_matches
        ),
        *(
            _job_item(fact, requirement="preferred")
            for fact in coverage.preferred_matches
        ),
    ]
    winning_candidates = {
        id(fact.candidate_skill)
        for fact in (*coverage.required_matches, *coverage.preferred_matches)
        if fact.candidate_skill is not None
    }
    items.extend(
        SkillCompatibilityItem(
            match_type="candidate_only",
            requirement="none",
            strength=0.0,
            candidate_skill=_candidate_view(skill),
            job_skill=None,
            relationship=None,
        )
        for skill in candidates
        if id(skill) not in winning_candidates
    )
    if len(items) > MAX_SKILL_MAP_ITEMS:
        raise SkillCompatibilityError(
            "SKILL_MAP_LIMIT_EXCEEDED",
            "Selected skill map exceeds the 200-item safety bound.",
        )
    frozen_items = tuple(items)
    return SkillCompatibilityProjection(
        items=frozen_items,
        counts=_counts(frozen_items),
    )


__all__ = [
    "MAX_SKILL_MAP_ITEMS",
    "CompatibilityMatchType",
    "CompatibilityRequirement",
    "SkillAssertionView",
    "SkillCompatibilityCounts",
    "SkillCompatibilityError",
    "SkillCompatibilityItem",
    "SkillCompatibilityProjection",
    "build_skill_compatibility",
]
