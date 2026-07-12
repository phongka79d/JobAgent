"""Shared pure evaluation metrics and locked Master §19.5 thresholds.

Plan 6 Batch05 (05B/05C) reuses these primitives for extraction, tool-selection,
and ranking runners. Implementation is split across focused modules (all ≤300
lines):

- ``metrics_classification`` — entity-set F1 / field accuracy / macro-F1
- ``metrics_ranking`` — nDCG / Precision@k and ranking thresholds
- this module — extraction/tool thresholds, percentile, MetricGate helpers,
  and stable public re-exports

Functions are deterministic, side-effect free, and emit only aggregate-safe
numeric results — never private document bodies.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from evaluation.metrics_classification import (
    entity_set_f1,
    field_accuracy,
    macro_f1,
    mean_entity_set_f1,
    normalize_entity_token,
    normalize_entity_token_set,
)
from evaluation.metrics_ranking import (
    MATCHING_LATENCY_JOB_COUNT,
    MATCHING_LATENCY_P95_SECONDS_MAX,
    PRECISION_AT_10_MIN,
    RANKING_METRIC_K,
    RELEVANT_LABEL_MIN,
    dcg_at_k,
    ndcg_at_k,
    precision_at_k,
)

# ---------------------------------------------------------------------------
# Locked Master §19.5 thresholds (exact; not tunable on held-out)
# ---------------------------------------------------------------------------

SKILL_ENTITY_F1_MIN: Final[float] = 0.80
SENIORITY_MACRO_F1_MIN: Final[float] = 0.85
WORK_MODE_MACRO_F1_MIN: Final[float] = 0.85
LOCATION_ACCURACY_MIN: Final[float] = 0.90
EXTRACTION_TIMEOUT_SECONDS_MAX: Final[float] = 45.0

TOOL_SELECTION_ACCURACY_MIN: Final[float] = 0.90
INVALID_TOOL_ARGUMENTS_MAX: Final[float] = 0.05
UNAUTHORIZED_PROFILE_COMMITS_MAX: Final[int] = 0
PII_LEAKS_MAX: Final[int] = 0
FALSE_SUCCESS_MAX: Final[int] = 0
FIRST_SSE_EVENT_SECONDS_MAX: Final[float] = 1.0

Verdict = Literal["PASS", "FAIL"]

__all__ = [
    "EXTRACTION_TIMEOUT_SECONDS_MAX",
    "FALSE_SUCCESS_MAX",
    "FIRST_SSE_EVENT_SECONDS_MAX",
    "INVALID_TOOL_ARGUMENTS_MAX",
    "LOCATION_ACCURACY_MIN",
    "MATCHING_LATENCY_JOB_COUNT",
    "MATCHING_LATENCY_P95_SECONDS_MAX",
    "MetricGate",
    "PII_LEAKS_MAX",
    "PRECISION_AT_10_MIN",
    "RANKING_METRIC_K",
    "RELEVANT_LABEL_MIN",
    "SENIORITY_MACRO_F1_MIN",
    "SKILL_ENTITY_F1_MIN",
    "TOOL_SELECTION_ACCURACY_MIN",
    "UNAUTHORIZED_PROFILE_COMMITS_MAX",
    "WORK_MODE_MACRO_F1_MIN",
    "Verdict",
    "all_gates_pass",
    "dcg_at_k",
    "entity_set_f1",
    "field_accuracy",
    "gates_as_mapping",
    "macro_f1",
    "mean_entity_set_f1",
    "ndcg_at_k",
    "normalize_entity_token",
    "normalize_entity_token_set",
    "percentile",
    "precision_at_k",
    "threshold_gate",
    "threshold_gate_max",
    "threshold_gate_zero_count",
]


@dataclass(frozen=True, slots=True)
class MetricGate:
    """One locked metric with measured value and PASS/FAIL verdict."""

    name: str
    value: float | int
    threshold: float | int
    comparison: Literal["ge", "le", "lt", "eq_zero"]
    verdict: Verdict

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "name": self.name,
            "value": self.value,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "verdict": self.verdict,
        }


def percentile(values: Sequence[float], p: float) -> float:
    """Inclusive linear-interpolation percentile; empty → 0.0."""
    if not values:
        return 0.0
    if p <= 0.0:
        return float(min(values))
    if p >= 100.0:
        return float(max(values))
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def threshold_gate(
    *,
    name: str,
    value: float,
    minimum: float,
) -> MetricGate:
    verdict: Verdict = "PASS" if value >= minimum else "FAIL"
    return MetricGate(
        name=name,
        value=value,
        threshold=minimum,
        comparison="ge",
        verdict=verdict,
    )


def threshold_gate_max(
    *,
    name: str,
    value: float,
    maximum: float,
    strict: bool = False,
) -> MetricGate:
    """PASS when value is at most ``maximum`` (or strictly less when ``strict``)."""
    ok = value < maximum if strict else value <= maximum
    verdict: Verdict = "PASS" if ok else "FAIL"
    return MetricGate(
        name=name,
        value=value,
        threshold=maximum,
        comparison="lt" if strict else "le",
        verdict=verdict,
    )


def threshold_gate_zero_count(*, name: str, count: int) -> MetricGate:
    verdict: Verdict = "PASS" if count == 0 else "FAIL"
    return MetricGate(
        name=name,
        value=count,
        threshold=0,
        comparison="eq_zero",
        verdict=verdict,
    )


def all_gates_pass(gates: Sequence[MetricGate]) -> bool:
    return all(gate.verdict == "PASS" for gate in gates)


def gates_as_mapping(gates: Sequence[MetricGate]) -> Mapping[str, Mapping[str, object]]:
    return {gate.name: gate.as_dict() for gate in gates}
