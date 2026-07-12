"""Pure ranking scores, ablations, and grid search (Plan 6 / 05C facade).

Precomputed features + labels only. Never loads held-out data or mutates
production weights. Split: ranking_types, ranking_features, ranking_report;
this module owns scoring/ablations/grid and stable public re-exports.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Final

from app.services.matching_aggregate import SEED_WEIGHTS

from evaluation.metrics import (
    MATCHING_LATENCY_JOB_COUNT,
    RANKING_METRIC_K,
    RELEVANT_LABEL_MIN,
    ndcg_at_k,
    percentile,
    precision_at_k,
)
from evaluation.ranking_features import parse_ranking_items
from evaluation.ranking_report import (
    build_sealed_result_dict,
    build_tune_result_dict,
    ranking_gates,
)
from evaluation.ranking_types import (
    ABLATION_NAMES,
    COMPONENT_KEYS,
    RUNNER_ID,
    WEIGHT_CONFIG_VERSION,
    AblationName,
    AblationResult,
    GridSelection,
    RankingItem,
    RankingRunnerError,
    config_digest_for_weights,
    normalize_weights,
    seed_weights,
)

# Bounded Master §18.4 grid axes (deterministic Cartesian product).
_SEMANTIC_GRID: Final[tuple[float, ...]] = (0.15, 0.25, 0.30, 0.35, 0.45)
_SKILL_GRID: Final[tuple[float, ...]] = (0.25, 0.35, 0.40, 0.45, 0.55)
_SENIORITY_GRID: Final[tuple[float, ...]] = (0.05, 0.10, 0.15)


def generate_weight_grid() -> tuple[dict[str, float], ...]:
    """Bounded deterministic weight candidates; always includes seed weights."""
    seen: set[tuple[float, ...]] = set()
    out: list[dict[str, float]] = []

    def _push(raw: Mapping[str, float]) -> None:
        try:
            normalized = normalize_weights(raw)
        except RankingRunnerError:
            return
        key = tuple(round(normalized[name], 12) for name in COMPONENT_KEYS)
        if key in seen:
            return
        seen.add(key)
        out.append(normalized)

    _push(seed_weights())
    exp_seed = float(SEED_WEIGHTS["experience_score"])
    loc_seed = float(SEED_WEIGHTS["location_score"])
    wm_seed = float(SEED_WEIGHTS["work_mode_score"])
    rest_seed = exp_seed + loc_seed + wm_seed
    for semantic in _SEMANTIC_GRID:
        for skill in _SKILL_GRID:
            for seniority in _SENIORITY_GRID:
                remaining = 1.0 - semantic - skill - seniority
                if remaining < 0.05:
                    continue
                experience = remaining * (exp_seed / rest_seed)
                location = remaining * (loc_seed / rest_seed)
                work_mode = remaining * (wm_seed / rest_seed)
                _push(
                    {
                        "semantic_similarity": semantic,
                        "skill_score": skill,
                        "seniority_score": seniority,
                        "experience_score": experience,
                        "location_score": location,
                        "work_mode_score": work_mode,
                    }
                )
    out.sort(key=lambda w: tuple(w[name] for name in COMPONENT_KEYS))
    return tuple(out)


def _component_map(
    item: RankingItem,
    *,
    use_graph_skill: bool,
) -> dict[str, float | None]:
    skill = item.skill_score_graph if use_graph_skill else item.skill_score_exact
    return {
        "semantic_similarity": item.semantic_similarity,
        "skill_score": skill,
        "seniority_score": item.seniority_score,
        "experience_score": item.experience_score,
        "location_score": item.location_score,
        "work_mode_score": item.work_mode_score,
    }


def score_item(
    item: RankingItem,
    weights: Mapping[str, float],
    *,
    mode: AblationName,
) -> float:
    """Deterministic hybrid-style score for one ablation mode."""
    normalized = normalize_weights(weights)
    if mode == "semantic_only":
        return float(item.semantic_similarity)
    if mode == "exact_skill_only":
        return float(item.skill_score_exact)
    use_graph = mode in ("semantic_plus_skill_graph", "full_hybrid")
    components = _component_map(item, use_graph_skill=use_graph)
    if mode in ("semantic_plus_exact", "semantic_plus_skill_graph"):
        active: tuple[str, ...] = ("semantic_similarity", "skill_score")
    else:  # full_hybrid
        active = COMPONENT_KEYS
    available: list[str] = []
    for name in active:
        value = components[name]
        if value is None:
            continue
        if not math.isfinite(float(value)):
            raise RankingRunnerError(f"non-finite component {name} for {item.entity_id}")
        available.append(name)
    if not available:
        return 0.0
    raw_total = sum(normalized[name] for name in available)
    if raw_total <= 0.0:
        return 0.0
    return sum(
        (normalized[name] / raw_total) * float(components[name] or 0.0)
        for name in available
    )


def rank_items(
    items: Sequence[RankingItem],
    weights: Mapping[str, float],
    *,
    mode: AblationName,
) -> tuple[RankingItem, ...]:
    """Sort by score desc, stable entity_id asc tie-break."""
    scored = [
        (score_item(item, weights, mode=mode), item.entity_id, item) for item in items
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return tuple(row[2] for row in scored)


def evaluate_ranked_list(
    ranked: Sequence[RankingItem],
    *,
    k: int = RANKING_METRIC_K,
) -> tuple[float, float]:
    labels = [item.relevance for item in ranked]
    return (
        round(ndcg_at_k(labels, k=k), 6),
        round(precision_at_k(labels, k=k, relevant_min=RELEVANT_LABEL_MIN), 6),
    )


def run_ablation(
    items: Sequence[RankingItem],
    weights: Mapping[str, float],
    *,
    mode: AblationName,
) -> AblationResult:
    ranked = rank_items(items, weights, mode=mode)
    ndcg, prec = evaluate_ranked_list(ranked)
    return AblationResult(
        name=mode,
        ndcg_at_10=ndcg,
        precision_at_10=prec,
        ranked_entity_ids=tuple(item.entity_id for item in ranked[:RANKING_METRIC_K]),
    )


def run_all_ablations(
    items: Sequence[RankingItem],
    weights: Mapping[str, float],
) -> tuple[AblationResult, ...]:
    return tuple(run_ablation(items, weights, mode=mode) for mode in ABLATION_NAMES)


def select_weights_by_validation_ndcg(
    development: Sequence[RankingItem],
    validation: Sequence[RankingItem],
    *,
    grid: Sequence[Mapping[str, float]] | None = None,
) -> GridSelection:
    """Tune on validation nDCG@10 only; development reported for diagnostics."""
    if not validation:
        raise RankingRunnerError("validation set is empty; cannot tune")
    candidates = tuple(grid) if grid is not None else generate_weight_grid()
    if not candidates:
        raise RankingRunnerError("weight grid is empty")

    best_weights: dict[str, float] | None = None
    best_val = float("-inf")
    best_dev = 0.0
    for raw in candidates:
        weights = normalize_weights(raw)
        val_ndcg, _ = evaluate_ranked_list(
            rank_items(validation, weights, mode="full_hybrid")
        )
        weight_key = tuple(weights[name] for name in COMPONENT_KEYS)
        better = val_ndcg > best_val + 1e-15
        tied = abs(val_ndcg - best_val) <= 1e-15
        if better or (
            tied
            and (
                best_weights is None
                or weight_key < tuple(best_weights[name] for name in COMPONENT_KEYS)
            )
        ):
            best_val = val_ndcg
            best_weights = weights
            if development:
                best_dev, _ = evaluate_ranked_list(
                    rank_items(development, weights, mode="full_hybrid")
                )
            else:
                best_dev = 0.0
    assert best_weights is not None
    return GridSelection(
        weights=best_weights,
        validation_ndcg_at_10=round(best_val, 6),
        development_ndcg_at_10=round(best_dev, 6),
        candidates_evaluated=len(candidates),
        config_digest=config_digest_for_weights(best_weights),
    )


def graph_boosts_enabled(ablations: Sequence[AblationResult]) -> bool:
    """Enable related boosts only when graph expansion improves held-out nDCG@10."""
    by_name = {item.name: item for item in ablations}
    graph = by_name.get("semantic_plus_skill_graph")
    exact = by_name.get("semantic_plus_exact")
    if graph is None or exact is None:
        raise RankingRunnerError("graph ablation pair missing")
    return graph.ndcg_at_10 > exact.ndcg_at_10


def matching_latency_p95(latencies_seconds: Sequence[float]) -> float:
    if len(latencies_seconds) < MATCHING_LATENCY_JOB_COUNT:
        raise RankingRunnerError(
            f"matching latency requires {MATCHING_LATENCY_JOB_COUNT} samples, "
            f"got {len(latencies_seconds)}"
        )
    samples = [float(v) for v in latencies_seconds[:MATCHING_LATENCY_JOB_COUNT]]
    for value in samples:
        if not math.isfinite(value) or value < 0.0:
            raise RankingRunnerError("latency samples must be finite and non-negative")
    return round(percentile(samples, 95.0), 6)


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
    "build_sealed_result_dict",
    "build_tune_result_dict",
    "config_digest_for_weights",
    "generate_weight_grid",
    "graph_boosts_enabled",
    "matching_latency_p95",
    "normalize_weights",
    "parse_ranking_items",
    "rank_items",
    "ranking_gates",
    "run_ablation",
    "run_all_ablations",
    "score_item",
    "seed_weights",
    "select_weights_by_validation_ndcg",
]
