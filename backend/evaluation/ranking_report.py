"""Aggregate-only ranking result builders and locked ranking gates (05C)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from evaluation.dataset_contracts import PROTOCOL_ID, SCHEMA_VERSION
from evaluation.metrics import (
    MATCHING_LATENCY_P95_SECONDS_MAX,
    PRECISION_AT_10_MIN,
    MetricGate,
    all_gates_pass,
    gates_as_mapping,
    threshold_gate,
    threshold_gate_max,
)
from evaluation.ranking_types import (
    RUNNER_ID,
    WEIGHT_CONFIG_VERSION,
    AblationResult,
    GridSelection,
)

__all__ = [
    "ablations_as_mapping",
    "build_sealed_result_dict",
    "build_tune_result_dict",
    "ranking_gates",
]


def ranking_gates(
    *,
    full_hybrid: AblationResult,
    semantic_only: AblationResult,
    exact_skill_only: AblationResult,
    latency_p95_seconds: float,
) -> tuple[MetricGate, ...]:
    precision_gate = threshold_gate(
        name="precision_at_10",
        value=full_hybrid.precision_at_10,
        minimum=PRECISION_AT_10_MIN,
    )
    beats_semantic = full_hybrid.ndcg_at_10 > semantic_only.ndcg_at_10
    beats_skill = full_hybrid.ndcg_at_10 > exact_skill_only.ndcg_at_10
    baseline_semantic = MetricGate(
        name="full_hybrid_ndcg_gt_semantic_only",
        value=1 if beats_semantic else 0,
        threshold=1,
        comparison="ge",
        verdict="PASS" if beats_semantic else "FAIL",
    )
    baseline_skill = MetricGate(
        name="full_hybrid_ndcg_gt_skill_only",
        value=1 if beats_skill else 0,
        threshold=1,
        comparison="ge",
        verdict="PASS" if beats_skill else "FAIL",
    )
    latency_gate = threshold_gate_max(
        name="matching_latency_p95_seconds",
        value=latency_p95_seconds,
        maximum=MATCHING_LATENCY_P95_SECONDS_MAX,
        strict=True,
    )
    return (precision_gate, baseline_semantic, baseline_skill, latency_gate)


def ablations_as_mapping(
    ablations: Sequence[AblationResult],
) -> dict[str, dict[str, Any]]:
    return {
        item.name: {
            "ndcg_at_10": item.ndcg_at_10,
            "precision_at_10": item.precision_at_10,
            # Top-k IDs only (safe IDs); no labels/raw content.
            "top10_entity_ids": list(item.ranked_entity_ids),
        }
        for item in ablations
    }


def build_tune_result_dict(
    selection: GridSelection,
    *,
    data_digest: str,
    development_count: int,
    validation_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "data_class": "safe_aggregate",
        "protocol_id": PROTOCOL_ID,
        "runner_id": RUNNER_ID,
        "mode": "tune",
        "weight_config_version": WEIGHT_CONFIG_VERSION,
        "weights": selection.weights,
        "config_digest": selection.config_digest,
        "data_digest": data_digest,
        "development_count": development_count,
        "validation_count": validation_count,
        "development_ndcg_at_10": selection.development_ndcg_at_10,
        "validation_ndcg_at_10": selection.validation_ndcg_at_10,
        "grid_candidates_evaluated": selection.candidates_evaluated,
        "held_out_used": False,
    }


def build_sealed_result_dict(
    *,
    ablations: Sequence[AblationResult],
    gates: Sequence[MetricGate],
    latency_p95_seconds: float,
    related_skill_boosts_enabled: bool,
    data_digest: str,
    config_digest: str,
    weights: Mapping[str, float],
    held_out_count: int,
) -> dict[str, Any]:
    by_name = {item.name: item for item in ablations}
    full = by_name["full_hybrid"]
    return {
        "schema_version": SCHEMA_VERSION,
        "data_class": "safe_aggregate",
        "protocol_id": PROTOCOL_ID,
        "runner_id": RUNNER_ID,
        "mode": "sealed_test",
        "weight_config_version": WEIGHT_CONFIG_VERSION,
        "weights": dict(weights),
        "config_digest": config_digest,
        "data_digest": data_digest,
        "held_out_count": held_out_count,
        "held_out_used": True,
        "ablations": ablations_as_mapping(ablations),
        "metrics": {
            "precision_at_10": full.precision_at_10,
            "ndcg_at_10": full.ndcg_at_10,
            "matching_latency_p95_seconds": latency_p95_seconds,
            "full_hybrid_beats_semantic_only": full.ndcg_at_10
            > by_name["semantic_only"].ndcg_at_10,
            "full_hybrid_beats_skill_only": full.ndcg_at_10
            > by_name["exact_skill_only"].ndcg_at_10,
        },
        "gates": gates_as_mapping(gates),
        "overall": "PASS" if all_gates_pass(gates) else "FAIL",
        "related_skill_boosts_enabled": related_skill_boosts_enabled,
        "graph_decision_rule": (
            "enable_related_boosts_iff_semantic_plus_skill_graph_ndcg_gt_"
            "semantic_plus_exact_ndcg"
        ),
    }
