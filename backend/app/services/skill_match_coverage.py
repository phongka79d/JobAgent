"""Skill-component coverage and aggregation (Plan 6 §7.2 / Master §18.1).

Owns required/preferred mean coverage, 0.80/0.20 renormalization, and the
skill-component evidence lists. Edge indexing and strongest-path matching live
in ``skill_match_evidence``. Contracts live in ``skill_match_contracts``.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.candidate import CandidateSkill
from app.schemas.job_post import JobSkill
from app.services.skill_match_contracts import (
    PREFERRED_COVERAGE_WEIGHT,
    REQUIRED_COVERAGE_WEIGHT,
    STRENGTH_DIRECT,
    STRENGTH_NONE,
    STRENGTH_VERIFIED_RELATED,
    MatchKind,
    SkillComponentResult,
    SkillMatchEvidence,
    VerifiedRelatedEdge,
)
from app.services.skill_match_evidence import (
    index_verified_related_edges,
    match_skill_list,
)


def coverage_mean(matches: Sequence[SkillMatchEvidence]) -> float | None:
    """Mean strongest strength; None when the list is empty (unavailable side)."""
    if not matches:
        return None
    total = 0.0
    for item in matches:
        total += item.strength
    return total / float(len(matches))


def combine_skill_score(
    required_coverage: float | None,
    preferred_coverage: float | None,
) -> tuple[bool, float | None]:
    """Apply 0.80/0.20 renormalization; both empty → unavailable.

    Returns ``(available, skill_score)``. One-side empty renormalizes the
    remaining weight to 1.0 within the skill component.
    """
    if required_coverage is None and preferred_coverage is None:
        return False, None
    if required_coverage is not None and preferred_coverage is not None:
        score = (
            REQUIRED_COVERAGE_WEIGHT * required_coverage
            + PREFERRED_COVERAGE_WEIGHT * preferred_coverage
        )
        return True, score
    if required_coverage is not None:
        return True, required_coverage
    return True, preferred_coverage


def compute_skill_component(
    *,
    required_skills: Sequence[JobSkill] = (),
    preferred_skills: Sequence[JobSkill] = (),
    candidate_skills: Sequence[CandidateSkill] = (),
    related_edges: Sequence[VerifiedRelatedEdge] = (),
) -> SkillComponentResult:
    """Compute skill availability, score, sub-coverages, and evidence lists.

    - Matched: strength 1.0 (direct or verified alias), required + preferred.
    - Related: strength 0.6 verified RELATED_TO with a named path.
    - Missing required: required skills whose strongest strength is 0.0.
    """
    related_index = index_verified_related_edges(related_edges)

    required_matches = match_skill_list(
        required_skills,
        candidate_skills,
        related_index=related_index,
    )
    preferred_matches = match_skill_list(
        preferred_skills,
        candidate_skills,
        related_index=related_index,
    )

    required_coverage = coverage_mean(required_matches)
    preferred_coverage = coverage_mean(preferred_matches)
    available, skill_score = combine_skill_score(
        required_coverage, preferred_coverage
    )

    all_matches = (*required_matches, *preferred_matches)
    matched = tuple(
        m
        for m in all_matches
        if m.strength == STRENGTH_DIRECT
        and m.match_kind in {MatchKind.DIRECT, MatchKind.VERIFIED_ALIAS}
    )
    # Prefer stable order: required first (already), then preferred; within
    # each list preserve job skill order from match_skill_list.
    related = tuple(
        m
        for m in all_matches
        if m.match_kind is MatchKind.VERIFIED_RELATED
        and m.strength == STRENGTH_VERIFIED_RELATED
    )
    missing_required = tuple(
        m for m in required_matches if m.strength == STRENGTH_NONE
    )

    return SkillComponentResult(
        available=available,
        skill_score=skill_score,
        required_coverage=required_coverage,
        preferred_coverage=preferred_coverage,
        matched=matched,
        related=related,
        missing_required=missing_required,
    )


__all__ = [
    "combine_skill_score",
    "compute_skill_component",
    "coverage_mean",
]
