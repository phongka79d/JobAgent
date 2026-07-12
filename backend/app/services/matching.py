"""Hybrid aggregation and top-10 ranking facade (Plan 6 §7.4–7.5).

Public facade for Phase 5 matching. Implementation is split across focused
modules so no production source exceeds the focused-module ceiling:

- ``matching_aggregate`` — seed weights, renormalization, quality, aggregation
- ``matching_rank`` — skill-path projection, MatchResult assembly, top-10 rank
- ``explanations`` — bounded evidence-backed explanation lines

Reuses 02A skill evidence and 02B components without duplicating formulas, LLM
scoring, or Job mutation. Stable task-facing imports remain on this module.
"""

from __future__ import annotations

from app.services.matching_aggregate import (
    QUALITY_MULTIPLIER_FULL,
    QUALITY_MULTIPLIER_PARTIAL,
    SEED_CONFIG_VERSION,
    SEED_WEIGHTS,
    MatchingAggregationError,
    aggregate_hybrid_score,
    quality_multiplier,
    renormalize_effective_weights,
    score_job_components,
    validate_seed_weights,
)
from app.services.matching_rank import (
    MatchingRankError,
    RankedJobCandidate,
    build_match_result,
    project_skill_paths,
    rank_match_results,
)

__all__ = [
    "QUALITY_MULTIPLIER_FULL",
    "QUALITY_MULTIPLIER_PARTIAL",
    "SEED_CONFIG_VERSION",
    "SEED_WEIGHTS",
    "MatchingAggregationError",
    "MatchingRankError",
    "RankedJobCandidate",
    "aggregate_hybrid_score",
    "build_match_result",
    "project_skill_paths",
    "quality_multiplier",
    "rank_match_results",
    "renormalize_effective_weights",
    "score_job_components",
    "validate_seed_weights",
]
