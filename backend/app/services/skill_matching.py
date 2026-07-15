"""Pure deterministic skill matching and coverage (Plan 6 02A)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from app.schemas.jobs import JobSkill
from app.schemas.profile import CandidateSkill
from app.services.skill_normalization import RelatedToEdge, SkillNormalizer

MATCH_STRENGTH_DIRECT: Final[float] = 1.0
MATCH_STRENGTH_RELATED: Final[float] = 0.6
MATCH_STRENGTH_NONE: Final[float] = 0.0

SkillMatchType = Literal["direct", "related", "none"]


@dataclass(frozen=True, slots=True)
class SkillMatchFact:
    """Winning Candidate-vs-Job skill fact for later deterministic explanation."""

    job_skill: JobSkill
    candidate_skill: CandidateSkill | None
    match_type: SkillMatchType
    strength: float
    relationship: RelatedToEdge | None = None


@dataclass(frozen=True, slots=True)
class SkillCoverageResult:
    """Nullable required/preferred coverage plus renormalized skill score."""

    required_matches: tuple[SkillMatchFact, ...]
    preferred_matches: tuple[SkillMatchFact, ...]
    required_skill_coverage: float | None
    preferred_skill_coverage: float | None
    skill_score: float | None


def match_job_skill(
    job_skill: JobSkill,
    candidate_skills: Sequence[CandidateSkill],
    normalizer: SkillNormalizer,
) -> SkillMatchFact:
    """Select the strongest eligible Candidate match for one Job skill."""

    eligible = tuple(skill for skill in candidate_skills if not skill.excluded)
    job_key = job_skill.skill.canonical_key

    direct = _first_direct_match(job_key, eligible)
    if direct is not None:
        return SkillMatchFact(
            job_skill=job_skill,
            candidate_skill=direct,
            match_type="direct",
            strength=MATCH_STRENGTH_DIRECT,
        )

    related = _first_related_match(job_key, eligible, normalizer)
    if related is not None:
        candidate, edge = related
        return SkillMatchFact(
            job_skill=job_skill,
            candidate_skill=candidate,
            match_type="related",
            strength=MATCH_STRENGTH_RELATED,
            relationship=edge,
        )

    return SkillMatchFact(
        job_skill=job_skill,
        candidate_skill=None,
        match_type="none",
        strength=MATCH_STRENGTH_NONE,
    )


def compute_skill_coverage(
    candidate_skills: Sequence[CandidateSkill],
    *,
    required_skills: Sequence[JobSkill],
    preferred_skills: Sequence[JobSkill],
    normalizer: SkillNormalizer,
) -> SkillCoverageResult:
    """Compute required/preferred coverage and the renormalized skill score."""

    required_matches = _match_skills(required_skills, candidate_skills, normalizer)
    preferred_matches = _match_skills(preferred_skills, candidate_skills, normalizer)
    required_coverage = _coverage(required_matches)
    preferred_coverage = _coverage(preferred_matches)

    return SkillCoverageResult(
        required_matches=required_matches,
        preferred_matches=preferred_matches,
        required_skill_coverage=required_coverage,
        preferred_skill_coverage=preferred_coverage,
        skill_score=_skill_score(required_coverage, preferred_coverage),
    )


def _match_skills(
    job_skills: Sequence[JobSkill],
    candidate_skills: Sequence[CandidateSkill],
    normalizer: SkillNormalizer,
) -> tuple[SkillMatchFact, ...]:
    return tuple(
        match_job_skill(job_skill, candidate_skills, normalizer)
        for job_skill in job_skills
    )


def _first_direct_match(
    job_key: str,
    candidate_skills: Sequence[CandidateSkill],
) -> CandidateSkill | None:
    for candidate in candidate_skills:
        if candidate.skill.canonical_key == job_key:
            return candidate
    return None


def _first_related_match(
    job_key: str,
    candidate_skills: Sequence[CandidateSkill],
    normalizer: SkillNormalizer,
) -> tuple[CandidateSkill, RelatedToEdge] | None:
    for candidate in candidate_skills:
        for edge in normalizer.relationships_for(candidate.skill.canonical_key):
            if edge.to_key == job_key:
                return candidate, edge
    return None


def _coverage(matches: Sequence[SkillMatchFact]) -> float | None:
    if not matches:
        return None
    return sum(match.strength for match in matches) / len(matches)


def _skill_score(
    required_skill_coverage: float | None,
    preferred_skill_coverage: float | None,
) -> float | None:
    weighted_sum = 0.0
    weight_sum = 0.0
    if required_skill_coverage is not None:
        weighted_sum += 0.80 * required_skill_coverage
        weight_sum += 0.80
    if preferred_skill_coverage is not None:
        weighted_sum += 0.20 * preferred_skill_coverage
        weight_sum += 0.20
    if weight_sum == 0.0:
        return None
    return weighted_sum / weight_sum


__all__ = [
    "MATCH_STRENGTH_DIRECT",
    "MATCH_STRENGTH_NONE",
    "MATCH_STRENGTH_RELATED",
    "SkillCoverageResult",
    "SkillMatchFact",
    "SkillMatchType",
    "compute_skill_coverage",
    "match_job_skill",
]
