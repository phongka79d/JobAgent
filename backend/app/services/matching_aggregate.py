"""Hybrid aggregation: seed weights, renormalization, quality (Plan 6 §7.4).

Owns immutable seed configuration, missing-component renormalization, quality
multiplier, and pure hybrid aggregation. Ranking lives in ``matching_rank``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from app.schemas.job_post import JdQuality, JobSeniority, JobWorkMode
from app.schemas.preferences import TargetSeniority, WorkMode
from app.schemas.score_breakdown import (
    COMPONENT_ORDER,
    WEIGHT_SUM_TOLERANCE,
    ComponentValue,
    HybridScoreBreakdown,
    ScoreComponentName,
)
from app.services.score_components import (
    compute_experience_score,
    compute_location_score,
    compute_semantic_similarity,
    compute_seniority_score,
    compute_work_mode_score,
)

# Versioned seed configuration (Master §18.2). Not tuned / not held-out.
SEED_CONFIG_VERSION: Final[str] = "hybrid_seed_v1"

_SEED_WEIGHT_VALUES: Final[dict[str, float]] = {
    ScoreComponentName.SEMANTIC_SIMILARITY.value: 0.30,
    ScoreComponentName.SKILL_SCORE.value: 0.40,
    ScoreComponentName.SENIORITY_SCORE.value: 0.10,
    ScoreComponentName.EXPERIENCE_SCORE.value: 0.10,
    ScoreComponentName.LOCATION_SCORE.value: 0.05,
    ScoreComponentName.WORK_MODE_SCORE.value: 0.05,
}

# Immutable public seed map; callers must not mutate.
SEED_WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(dict(_SEED_WEIGHT_VALUES))
QUALITY_MULTIPLIER_FULL: Final[float] = 1.00
QUALITY_MULTIPLIER_PARTIAL: Final[float] = 0.85


class MatchingAggregationError(ValueError):
    """Invalid seed weights or aggregation inputs (code-friendly message)."""


def quality_multiplier(quality: JdQuality | str) -> float | None:
    """Return full/partial multiplier; unscorable → None (cannot score)."""
    token = quality.value if isinstance(quality, JdQuality) else str(quality)
    if token == JdQuality.FULL.value:
        return QUALITY_MULTIPLIER_FULL
    if token == JdQuality.PARTIAL.value:
        return QUALITY_MULTIPLIER_PARTIAL
    if token == JdQuality.UNSCORABLE.value:
        return None
    raise MatchingAggregationError(f"unknown quality: {token}")


def validate_seed_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Require exactly the six locked component keys before renormalization."""
    if not isinstance(weights, Mapping) or not weights:
        raise MatchingAggregationError("seed weights must be a non-empty mapping")
    allowed = {name.value for name in ScoreComponentName}
    cleaned: dict[str, float] = {}
    for key, raw in weights.items():
        name = str(key)
        if name not in allowed:
            raise MatchingAggregationError(f"unknown component weight: {name}")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise MatchingAggregationError(f"non-numeric weight for {name}")
        value = float(raw)
        if not math.isfinite(value) or value < 0.0:
            raise MatchingAggregationError(f"invalid weight for {name}")
        cleaned[name] = value
    missing = allowed - cleaned.keys()
    if missing:
        raise MatchingAggregationError(
            "seed weights missing locked components: " + ", ".join(sorted(missing))
        )
    total = sum(cleaned.values())
    if not math.isfinite(total) or total <= 0.0:
        raise MatchingAggregationError("seed weights must sum to a positive total")
    return cleaned


def renormalize_effective_weights(
    available_names: Sequence[str],
    *,
    seed_weights: Mapping[str, float] = SEED_WEIGHTS,
) -> dict[str, float]:
    """Remove unavailable components and renormalize remaining weights to one."""
    seed = validate_seed_weights(seed_weights)
    present: list[str] = []
    for name in available_names:
        key = str(name)
        if key in seed and key not in present:
            present.append(key)
    if not present:
        return {}
    raw_total = sum(seed[name] for name in present)
    if not math.isfinite(raw_total) or raw_total <= 0.0:
        raise MatchingAggregationError(
            "available seed weights must sum to a positive total"
        )
    effective = {name: seed[name] / raw_total for name in present}
    if abs(sum(effective.values()) - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise MatchingAggregationError(
            "effective weights failed to sum to one within tolerance"
        )
    return effective


def _component_value(
    name: ScoreComponentName,
    raw: float | None,
) -> ComponentValue:
    if raw is None:
        return ComponentValue(name=name, available=False, value=None)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return ComponentValue(name=name, available=False, value=None)
    number = float(raw)
    if not math.isfinite(number):
        return ComponentValue(name=name, available=False, value=None)
    if number < 0.0:
        number = 0.0
    elif number > 1.0:
        number = 1.0
    return ComponentValue(name=name, available=True, value=number)


def aggregate_hybrid_score(
    component_values: Mapping[str, float | None],
    *,
    quality: JdQuality | str,
    seed_weights: Mapping[str, float] = SEED_WEIGHTS,
    seed_config_version: str = SEED_CONFIG_VERSION,
) -> HybridScoreBreakdown:
    """Aggregate available components, then apply quality once.

    Unscorable quality never receives base/final scores. All-unavailable
    components yield empty effective weights and None scores. Effective
    weights always sum to one within ``WEIGHT_SUM_TOLERANCE`` when non-empty.
    """
    quality_enum = (
        quality if isinstance(quality, JdQuality) else JdQuality(str(quality))
    )
    multiplier = quality_multiplier(quality_enum)

    components: list[ComponentValue] = []
    for name in COMPONENT_ORDER:
        raw = component_values.get(name.value)
        components.append(_component_value(name, raw))

    available_names = [c.name.value for c in components if c.available]
    effective = renormalize_effective_weights(
        available_names,
        seed_weights=seed_weights,
    )

    # Unscorable cannot enter aggregation (Master §18.3).
    if multiplier is None:
        return HybridScoreBreakdown(
            components=tuple(components),
            effective_weights=MappingProxyType(dict(effective)),
            base_score=None,
            final_score=None,
            quality=quality_enum,
            quality_multiplier=None,
            seed_config_version=seed_config_version,
        )

    if not effective:
        return HybridScoreBreakdown(
            components=tuple(components),
            effective_weights=MappingProxyType({}),
            base_score=None,
            final_score=None,
            quality=quality_enum,
            quality_multiplier=multiplier,
            seed_config_version=seed_config_version,
        )

    value_by_name = {c.name.value: c.value for c in components if c.available}
    base = 0.0
    for component_key, weight in effective.items():
        value = value_by_name[component_key]
        assert value is not None  # available components always have values
        base += weight * value

    if not math.isfinite(base):
        raise MatchingAggregationError("base score is not finite")
    if base < 0.0:
        base = 0.0
    elif base > 1.0:
        base = 1.0

    final = base * multiplier
    if not math.isfinite(final):
        raise MatchingAggregationError("final score is not finite")
    if final < 0.0:
        final = 0.0
    elif final > 1.0:
        final = 1.0

    return HybridScoreBreakdown(
        components=tuple(components),
        effective_weights=MappingProxyType(dict(effective)),
        base_score=base,
        final_score=final,
        quality=quality_enum,
        quality_multiplier=multiplier,
        seed_config_version=seed_config_version,
    )


def score_job_components(
    *,
    semantic_similarity: object,
    skill_score: float | None,
    job_seniority: JobSeniority | str | None,
    target_seniorities: Sequence[TargetSeniority | str],
    candidate_years: object,
    min_experience_years: object,
    job_location: str | None,
    preferred_locations: Sequence[str],
    job_work_mode: JobWorkMode | str | None,
    acceptable_work_modes: Sequence[WorkMode | str],
    quality: JdQuality | str,
    seed_weights: Mapping[str, float] = SEED_WEIGHTS,
    seed_config_version: str = SEED_CONFIG_VERSION,
) -> HybridScoreBreakdown:
    """Compute all hybrid components and aggregate for one eligible Job.

    ``skill_score`` is the 02A result (float in ``[0, 1]`` or None unavailable).
    This function does not recompute skill coverage.
    """
    components: dict[str, float | None] = {
        ScoreComponentName.SEMANTIC_SIMILARITY.value: compute_semantic_similarity(
            semantic_similarity
        ),
        ScoreComponentName.SKILL_SCORE.value: skill_score,
        ScoreComponentName.SENIORITY_SCORE.value: compute_seniority_score(
            job_seniority,
            target_seniorities,
        ),
        ScoreComponentName.EXPERIENCE_SCORE.value: compute_experience_score(
            candidate_years,
            min_experience_years,
        ),
        ScoreComponentName.LOCATION_SCORE.value: compute_location_score(
            job_location,
            preferred_locations,
        ),
        ScoreComponentName.WORK_MODE_SCORE.value: compute_work_mode_score(
            job_work_mode,
            acceptable_work_modes,
        ),
    }
    return aggregate_hybrid_score(
        components,
        quality=quality,
        seed_weights=seed_weights,
        seed_config_version=seed_config_version,
    )


__all__ = [
    "QUALITY_MULTIPLIER_FULL",
    "QUALITY_MULTIPLIER_PARTIAL",
    "SEED_CONFIG_VERSION",
    "SEED_WEIGHTS",
    "MatchingAggregationError",
    "aggregate_hybrid_score",
    "quality_multiplier",
    "renormalize_effective_weights",
    "score_job_components",
    "validate_seed_weights",
]
