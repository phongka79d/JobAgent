"""Ranking IR metric primitives and locked ranking thresholds (Plan 6 / 05C)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

# Locked Master §19.5 ranking / matching latency thresholds (exact; not tunable).
PRECISION_AT_10_MIN: Final[float] = 0.70
MATCHING_LATENCY_P95_SECONDS_MAX: Final[float] = 2.0
RELEVANT_LABEL_MIN: Final[int] = 2
RANKING_METRIC_K: Final[int] = 10
MATCHING_LATENCY_JOB_COUNT: Final[int] = 200

__all__ = [
    "MATCHING_LATENCY_JOB_COUNT",
    "MATCHING_LATENCY_P95_SECONDS_MAX",
    "PRECISION_AT_10_MIN",
    "RANKING_METRIC_K",
    "RELEVANT_LABEL_MIN",
    "dcg_at_k",
    "ndcg_at_k",
    "precision_at_k",
]


def dcg_at_k(relevances: Sequence[float], k: int = RANKING_METRIC_K) -> float:
    """Discounted cumulative gain for labels in rank order."""
    total = 0.0
    for index, relevance in enumerate(relevances[:k]):
        total += (2.0 ** float(relevance) - 1.0) / math.log2(index + 2.0)
    return total


def ndcg_at_k(
    relevances_in_rank_order: Sequence[float],
    k: int = RANKING_METRIC_K,
) -> float:
    """Normalized DCG@k; empty or non-positive ideal → 0.0."""
    if not relevances_in_rank_order or k <= 0:
        return 0.0
    dcg = dcg_at_k(relevances_in_rank_order, k)
    ideal = dcg_at_k(sorted(relevances_in_rank_order, reverse=True), k)
    if ideal <= 0.0:
        return 0.0
    return dcg / ideal


def precision_at_k(
    relevances_in_rank_order: Sequence[int | float],
    *,
    k: int = RANKING_METRIC_K,
    relevant_min: int = RELEVANT_LABEL_MIN,
) -> float:
    """Precision@k for labels >= relevant_min (Master: labels 2–3)."""
    if not relevances_in_rank_order or k <= 0:
        return 0.0
    top = list(relevances_in_rank_order[:k])
    if not top:
        return 0.0
    hits = sum(1 for rel in top if float(rel) >= float(relevant_min))
    return hits / len(top)
