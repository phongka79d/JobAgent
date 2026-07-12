"""Ranking evaluation types, constants, and weight helpers (Plan 6 / 05C)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from app.services.matching_aggregate import SEED_CONFIG_VERSION, SEED_WEIGHTS

from evaluation.dataset_contracts import content_digest

RUNNER_ID: Final[str] = "plan6_ranking_runner_v1"
WEIGHT_CONFIG_VERSION: Final[str] = SEED_CONFIG_VERSION
COMPONENT_KEYS: Final[tuple[str, ...]] = (
    "semantic_similarity",
    "skill_score",
    "seniority_score",
    "experience_score",
    "location_score",
    "work_mode_score",
)

AblationName = Literal[
    "semantic_only",
    "exact_skill_only",
    "semantic_plus_exact",
    "semantic_plus_skill_graph",
    "full_hybrid",
]

ABLATION_NAMES: Final[tuple[AblationName, ...]] = (
    "semantic_only",
    "exact_skill_only",
    "semantic_plus_exact",
    "semantic_plus_skill_graph",
    "full_hybrid",
)


class RankingRunnerError(ValueError):
    """Invalid ranking evaluation inputs or protocol violations."""


@dataclass(frozen=True, slots=True)
class RankingItem:
    """One scorable entity with gold relevance and precomputed components."""

    entity_id: str
    relevance: int
    semantic_similarity: float
    skill_score_exact: float
    skill_score_graph: float
    seniority_score: float | None
    experience_score: float | None
    location_score: float | None
    work_mode_score: float | None
    match_latency_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class AblationResult:
    name: AblationName
    ndcg_at_10: float
    precision_at_10: float
    ranked_entity_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GridSelection:
    weights: dict[str, float]
    validation_ndcg_at_10: float
    development_ndcg_at_10: float
    candidates_evaluated: int
    config_digest: str


def seed_weights() -> dict[str, float]:
    return {key: float(SEED_WEIGHTS[key]) for key in COMPONENT_KEYS}


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key in COMPONENT_KEYS:
        if key not in weights:
            raise RankingRunnerError(f"missing weight component: {key}")
        raw = weights[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise RankingRunnerError(f"non-numeric weight for {key}")
        value = float(raw)
        if not math.isfinite(value) or value < 0.0:
            raise RankingRunnerError(f"invalid weight for {key}")
        cleaned[key] = value
    total = sum(cleaned.values())
    if not math.isfinite(total) or total <= 0.0:
        raise RankingRunnerError("weights must sum to a positive total")
    return {key: cleaned[key] / total for key in COMPONENT_KEYS}


def config_digest_for_weights(
    weights: Mapping[str, float],
    *,
    weight_config_version: str = WEIGHT_CONFIG_VERSION,
) -> str:
    normalized = normalize_weights(weights)
    payload = {
        "weight_config_version": weight_config_version,
        "weights": {key: round(normalized[key], 12) for key in COMPONENT_KEYS},
    }
    return content_digest(payload)


__all__ = [
    "ABLATION_NAMES",
    "COMPONENT_KEYS",
    "RUNNER_ID",
    "WEIGHT_CONFIG_VERSION",
    "AblationName",
    "AblationResult",
    "GridSelection",
    "RankingItem",
    "RankingRunnerError",
    "config_digest_for_weights",
    "normalize_weights",
    "seed_weights",
]
