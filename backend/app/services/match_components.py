"""Pure Plan 6 score component helpers."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
)
from app.schemas.jobs import JobSeniority, JobWorkMode
from app.schemas.profile import TargetSeniority, WorkMode

_MATCH_RESULT_LIMIT_MIN = 1
_MATCH_RESULT_LIMIT_MAX = 10

@dataclass(frozen=True, slots=True)
class MatchScoreComponents:
    """All pure component inputs needed to score one retrieved Job."""

    job_id: str
    semantic_similarity: float
    skill_score: float | None
    seniority_score: float | None
    experience_score: float | None
    location_score: float | None
    work_mode_score: float | None
    jd_quality: str


@dataclass(frozen=True, slots=True)
class ScoredMatchCandidate:
    """Computed Plan 6 score facts for one match candidate."""

    components: MatchScoreComponents
    base_score: float
    final_score: float
    quality_multiplier: float
    effective_weights: dict[str, float]


def _clamp_unit(value: float) -> float:
    """Clamp a numeric component value into the normalized score range."""
    return max(0.0, min(1.0, value))


def compute_seniority_score(
    job_seniority: JobSeniority,
    target_seniority: Sequence[TargetSeniority],
) -> float | None:
    """Return exact seniority membership, or unavailable when source data is absent."""
    if job_seniority == "unknown" or not target_seniority:
        return None
    return 1.0 if job_seniority in target_seniority else 0.0


def compute_experience_score(
    candidate_years: float | None,
    min_experience_years: float | None,
) -> float | None:
    """Return the minimum-years score, or unavailable when either input is absent."""
    if candidate_years is None or min_experience_years is None:
        return None
    if min_experience_years == 0:
        return 1.0
    if candidate_years >= min_experience_years:
        return 1.0
    return _clamp_unit(candidate_years / min_experience_years)


def normalize_location_for_match(raw: str) -> str:
    """Normalize location text with only NFKC, whitespace collapse, and casefold."""
    return " ".join(unicodedata.normalize("NFKC", raw).split()).casefold()


def compute_location_score(
    job_location: str | None,
    preferred_locations: Sequence[str],
) -> float | None:
    """Return exact normalized location membership, or unavailable if absent."""
    if job_location is None:
        return None

    normalized_job_location = normalize_location_for_match(job_location)
    if not normalized_job_location:
        return None

    normalized_preferences = {
        normalized
        for raw_location in preferred_locations
        if (normalized := normalize_location_for_match(raw_location))
    }
    if not normalized_preferences:
        return None

    return 1.0 if normalized_job_location in normalized_preferences else 0.0


def compute_work_mode_score(
    job_work_mode: JobWorkMode,
    acceptable_work_modes: Sequence[WorkMode],
) -> float | None:
    """Return exact work-mode membership, or unavailable when source data is absent."""
    if job_work_mode == "unknown" or not acceptable_work_modes:
        return None
    return 1.0 if job_work_mode in acceptable_work_modes else 0.0


def score_match_candidate(components: MatchScoreComponents) -> ScoredMatchCandidate:
    """Return the unrounded hybrid score for one scorable match candidate."""
    quality_multiplier = _quality_multiplier(components.jd_quality)
    weighted_components = _available_weighted_components(components)
    effective_weights = _effective_component_weights(weighted_components)
    base_score = sum(
        value * effective_weights[name] for name, _, value in weighted_components
    )
    return ScoredMatchCandidate(
        components=components,
        base_score=base_score,
        final_score=base_score * quality_multiplier,
        quality_multiplier=quality_multiplier,
        effective_weights=effective_weights,
    )


def order_scored_match_candidates(
    candidates: Sequence[ScoredMatchCandidate],
    *,
    limit: int,
) -> list[ScoredMatchCandidate]:
    """Return the deterministic top scored candidates within the caller limit."""
    _validate_match_limit(limit)
    return sorted(candidates, key=_scored_match_order_key)[:limit]


def rank_match_candidates(
    candidates: Sequence[MatchScoreComponents],
    *,
    limit: int,
) -> list[ScoredMatchCandidate]:
    """Score, sort, and bound scorable match candidates."""
    return order_scored_match_candidates(
        [score_match_candidate(candidate) for candidate in candidates],
        limit=limit,
    )


def _quality_multiplier(jd_quality: str) -> float:
    if jd_quality == JOB_JD_QUALITY_FULL:
        return 1.0
    if jd_quality == JOB_JD_QUALITY_PARTIAL:
        return 0.85
    if jd_quality == JOB_JD_QUALITY_UNSCORABLE:
        raise ValueError("unscorable jobs cannot receive a final score")
    raise ValueError(f"jd_quality must be full or partial, got {jd_quality!r}")


def _effective_component_weights(
    weighted_components: Sequence[tuple[str, float, float]],
) -> dict[str, float]:
    total_weight = sum(weight for _, weight, _ in weighted_components)
    return {name: weight / total_weight for name, weight, _ in weighted_components}


def _available_weighted_components(
    components: MatchScoreComponents,
) -> list[tuple[str, float, float]]:
    available: list[tuple[str, float, float]] = []
    for name, weight, value in _weighted_component_values(components):
        if value is not None:
            available.append((name, weight, value))
    return available


def _weighted_component_values(
    components: MatchScoreComponents,
) -> tuple[tuple[str, float, float | None], ...]:
    return (
        ("semantic_similarity", 0.30, components.semantic_similarity),
        ("skill_score", 0.40, components.skill_score),
        ("seniority_score", 0.10, components.seniority_score),
        ("experience_score", 0.10, components.experience_score),
        ("location_score", 0.05, components.location_score),
        ("work_mode_score", 0.05, components.work_mode_score),
    )


def _validate_match_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError(
            f"limit must be an int in {_MATCH_RESULT_LIMIT_MIN}.."
            f"{_MATCH_RESULT_LIMIT_MAX}"
        )
    if limit < _MATCH_RESULT_LIMIT_MIN or limit > _MATCH_RESULT_LIMIT_MAX:
        raise ValueError(
            f"limit must be in {_MATCH_RESULT_LIMIT_MIN}.."
            f"{_MATCH_RESULT_LIMIT_MAX}, got {limit!r}"
        )


def _scored_match_order_key(
    candidate: ScoredMatchCandidate,
) -> tuple[float, bool, float, float, str]:
    skill_score = candidate.components.skill_score
    return (
        -candidate.final_score,
        skill_score is None,
        -(skill_score if skill_score is not None else 0.0),
        -candidate.components.semantic_similarity,
        candidate.components.job_id,
    )


__all__ = [
    "MatchScoreComponents",
    "ScoredMatchCandidate",
    "compute_experience_score",
    "compute_location_score",
    "compute_seniority_score",
    "compute_work_mode_score",
    "normalize_location_for_match",
    "order_scored_match_candidates",
    "rank_match_candidates",
    "score_match_candidate",
]
