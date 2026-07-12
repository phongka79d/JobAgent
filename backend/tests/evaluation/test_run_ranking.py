"""Tests for Plan 6 ranking grid search, sealed-test, and ablations (task 05C)."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from evaluation.dataset_contracts import PROTOCOL_ID, RELEVANCE_MIN
from evaluation.metrics import (
    MATCHING_LATENCY_JOB_COUNT,
    MATCHING_LATENCY_P95_SECONDS_MAX,
    PRECISION_AT_10_MIN,
    ndcg_at_k,
    precision_at_k,
)
from evaluation.ranking_scoring import (
    ABLATION_NAMES,
    COMPONENT_KEYS,
    RankingRunnerError,
    config_digest_for_weights,
    generate_weight_grid,
    graph_boosts_enabled,
    matching_latency_p95,
    normalize_weights,
    parse_ranking_items,
    rank_items,
    ranking_gates,
    run_all_ablations,
    score_item,
    seed_weights,
    select_weights_by_validation_ndcg,
)
from evaluation.ranking_sealed import run_sealed_test, verify_lock_integrity
from evaluation.ranking_tune import tune_weights, write_tuning_lock
from evaluation.run_ranking import build_parser, main
from evaluation.split_lock import (
    HeldOutAccessError,
    build_lock_artifact,
    load_lock_artifact,
    write_lock_artifact,
)
from evaluation.split_readers import load_relevance_for_tuning

EVAL_DIR = Path(__file__).resolve().parents[2] / "evaluation"


def _relevance_payload(n: int = RELEVANCE_MIN, seed: int = 20260711) -> dict[str, Any]:
    items = []
    for index in range(n):
        # Mix labels so ranking metrics are meaningful.
        relevance = [3, 2, 1, 0, 2, 3, 1, 0][index % 8]
        items.append(
            {
                "entity_id": f"syn_rank_{index:04d}",
                "relevance": relevance,
                "label_provenance": "synthetic",
            }
        )
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": seed,
        "items": items,
    }


def _features_for_relevance(
    relevance: dict[str, Any],
    *,
    graph_helps: bool = True,
    latency_seconds: float = 0.1,
) -> dict[str, Any]:
    """Build components correlated with gold labels (deterministic synthetic)."""
    items: list[dict[str, Any]] = []
    for row in relevance["items"]:
        rel = int(row["relevance"])
        base = rel / 3.0
        skill_exact = max(0.0, min(1.0, base * 0.9 + 0.05))
        # Graph either improves or hurts skill signal vs exact.
        if graph_helps:
            skill_graph = max(0.0, min(1.0, skill_exact + 0.15 * (rel >= 2)))
        else:
            skill_graph = max(0.0, min(1.0, skill_exact - 0.2 * (rel >= 2)))
        semantic = max(0.0, min(1.0, base * 0.85 + 0.1))
        items.append(
            {
                "entity_id": row["entity_id"],
                "relevance": rel,
                "label_provenance": "synthetic",
                "match_latency_seconds": latency_seconds,
                "components": {
                    "semantic_similarity": round(semantic, 6),
                    "skill_score_exact": round(skill_exact, 6),
                    "skill_score_graph": round(skill_graph, 6),
                    "seniority_score": 1.0 if rel >= 2 else 0.0,
                    "experience_score": round(base, 6),
                    "location_score": 1.0,
                    "work_mode_score": 1.0 if rel > 0 else 0.0,
                },
            }
        )
    return {"schema_version": 1, "protocol_id": PROTOCOL_ID, "items": items}


def test_ndcg_and_precision_metric_math() -> None:
    perfect = [3, 2, 1, 0]
    inverse = [0, 1, 2, 3]
    assert ndcg_at_k(perfect, k=10) == pytest.approx(1.0)
    assert ndcg_at_k(inverse, k=10) < ndcg_at_k(perfect, k=10)
    assert precision_at_k([3, 2, 0, 0], k=2) == pytest.approx(1.0)
    assert precision_at_k([0, 1, 0, 0], k=2) == pytest.approx(0.0)
    assert precision_at_k([2, 0, 3, 1], k=10) == pytest.approx(0.5)


def test_weight_grid_bounds_and_normalization() -> None:
    grid = generate_weight_grid()
    assert len(grid) >= 2
    assert len(grid) <= 200  # bounded
    seed = seed_weights()
    assert any(
        all(abs(candidate[k] - seed[k]) < 1e-9 for k in COMPONENT_KEYS)
        for candidate in grid
    )
    for weights in grid:
        assert set(weights) == set(COMPONENT_KEYS)
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        assert all(v >= 0.0 for v in weights.values())


def test_stable_weight_selection_tie_break() -> None:
    # Two weight vectors that produce identical ranks on a tiny set.
    items_payload = {
        "items": [
            {
                "entity_id": "a",
                "relevance": 3,
                "components": {
                    "semantic_similarity": 1.0,
                    "skill_score_exact": 1.0,
                    "skill_score_graph": 1.0,
                    "seniority_score": 1.0,
                    "experience_score": 1.0,
                    "location_score": 1.0,
                    "work_mode_score": 1.0,
                },
            },
            {
                "entity_id": "b",
                "relevance": 0,
                "components": {
                    "semantic_similarity": 0.0,
                    "skill_score_exact": 0.0,
                    "skill_score_graph": 0.0,
                    "seniority_score": 0.0,
                    "experience_score": 0.0,
                    "location_score": 0.0,
                    "work_mode_score": 0.0,
                },
            },
        ]
    }
    items = parse_ranking_items(items_payload)
    w1 = normalize_weights(
        {
            "semantic_similarity": 0.5,
            "skill_score": 0.5,
            "seniority_score": 0.0,
            "experience_score": 0.0,
            "location_score": 0.0,
            "work_mode_score": 0.0,
        }
    )
    w2 = normalize_weights(
        {
            "semantic_similarity": 0.6,
            "skill_score": 0.4,
            "seniority_score": 0.0,
            "experience_score": 0.0,
            "location_score": 0.0,
            "work_mode_score": 0.0,
        }
    )
    # Force identical nDCG: both perfect ranking; stable pick is lex-smaller weights.
    selection = select_weights_by_validation_ndcg(
        development=items,
        validation=items,
        grid=(w2, w1),
    )
    key1 = tuple(w1[k] for k in COMPONENT_KEYS)
    key2 = tuple(w2[k] for k in COMPONENT_KEYS)
    expected = w1 if key1 < key2 else w2
    assert selection.weights == expected


def test_tune_uses_validation_only_no_held_out(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance)
    load, _ = load_relevance_for_tuning(relevance)
    assert load.held_out_test == ()

    selection, report, data_digest = tune_weights(
        relevance_payload=relevance,
        ranking_payload=features,
    )
    assert report["held_out_used"] is False
    assert report["mode"] == "tune"
    assert selection.validation_ndcg_at_10 >= 0.0
    assert abs(sum(selection.weights.values()) - 1.0) < 1e-9
    assert all(v >= 0.0 for v in selection.weights.values())
    assert selection.config_digest == config_digest_for_weights(selection.weights)
    assert len(data_digest) == 64

    lock_path = tmp_path / "matching_config.json"
    write_tuning_lock(
        lock_path,
        split_seed=20260711,
        data_digest=data_digest,
        selection=selection,
    )
    lock = load_lock_artifact(lock_path)
    assert lock.sealed_test_completed is False
    assert lock.weights == selection.weights
    assert lock.related_skill_boosts_enabled is None


def test_tuning_module_has_no_held_out_reader_imports() -> None:
    source = (EVAL_DIR / "ranking_tune.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    assert "load_relevance_for_sealed_test" not in imported
    assert "SealedTestDatasetReader" not in imported
    assert "SplitAccessMode" not in imported
    # String deny-list remains documented in module.
    assert "SealedTestDatasetReader" in source or "held-out" in source.lower()


def test_cannot_emit_lock_from_empty_weights(tmp_path: Path) -> None:
    from evaluation.ranking_scoring import GridSelection

    with pytest.raises(RankingRunnerError, match="empty weights"):
        write_tuning_lock(
            tmp_path / "lock.json",
            split_seed=1,
            data_digest="a" * 64,
            selection=GridSelection(
                weights={},
                validation_ndcg_at_10=0.0,
                development_ndcg_at_10=0.0,
                candidates_evaluated=0,
                config_digest="b" * 64,
            ),
        )


def _graph_decision_items(*, graph_helps: bool) -> tuple[Any, ...]:
    """Tiny corpus where graph skill signal changes rank order vs exact."""
    # High-relevance item needs graph to surface; exact skill alone mis-ranks it.
    rows = [
        {
            "entity_id": "rel_high",
            "relevance": 3,
            "components": {
                "semantic_similarity": 0.4,
                "skill_score_exact": 0.1,
                "skill_score_graph": 0.95 if graph_helps else 0.05,
                "seniority_score": 0.5,
                "experience_score": 0.5,
                "location_score": 0.5,
                "work_mode_score": 0.5,
            },
        },
        {
            "entity_id": "rel_low",
            "relevance": 0,
            "components": {
                "semantic_similarity": 0.4,
                "skill_score_exact": 0.9,
                "skill_score_graph": 0.2 if graph_helps else 0.95,
                "seniority_score": 0.5,
                "experience_score": 0.5,
                "location_score": 0.5,
                "work_mode_score": 0.5,
            },
        },
    ]
    return parse_ranking_items({"items": rows})


def test_five_ablations_and_graph_decision() -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance, graph_helps=True)
    items = parse_ranking_items(features)
    ablations = run_all_ablations(items, seed_weights())
    assert len(ablations) == 5
    assert tuple(a.name for a in ablations) == ABLATION_NAMES

    help_items = _graph_decision_items(graph_helps=True)
    hurt_items = _graph_decision_items(graph_helps=False)
    assert graph_boosts_enabled(run_all_ablations(help_items, seed_weights())) is True
    assert graph_boosts_enabled(run_all_ablations(hurt_items, seed_weights())) is False


def test_score_modes_differ() -> None:
    item = parse_ranking_items(
        {
            "items": [
                {
                    "entity_id": "x",
                    "relevance": 2,
                    "components": {
                        "semantic_similarity": 0.9,
                        "skill_score_exact": 0.2,
                        "skill_score_graph": 0.8,
                        "seniority_score": 0.5,
                        "experience_score": 0.5,
                        "location_score": 0.5,
                        "work_mode_score": 0.5,
                    },
                }
            ]
        }
    )[0]
    weights = seed_weights()
    semantic = score_item(item, weights, mode="semantic_only")
    exact = score_item(item, weights, mode="exact_skill_only")
    graph = score_item(item, weights, mode="semantic_plus_skill_graph")
    hybrid = score_item(item, weights, mode="full_hybrid")
    assert semantic == pytest.approx(0.9)
    assert exact == pytest.approx(0.2)
    assert graph > score_item(item, weights, mode="semantic_plus_exact")
    assert 0.0 <= hybrid <= 1.0


def test_rank_stable_tie_break() -> None:
    items = parse_ranking_items(
        {
            "items": [
                {
                    "entity_id": "job_b",
                    "relevance": 1,
                    "components": {
                        "semantic_similarity": 0.5,
                        "skill_score_exact": 0.5,
                        "skill_score_graph": 0.5,
                        "seniority_score": None,
                        "experience_score": None,
                        "location_score": None,
                        "work_mode_score": None,
                    },
                },
                {
                    "entity_id": "job_a",
                    "relevance": 1,
                    "components": {
                        "semantic_similarity": 0.5,
                        "skill_score_exact": 0.5,
                        "skill_score_graph": 0.5,
                        "seniority_score": None,
                        "experience_score": None,
                        "location_score": None,
                        "work_mode_score": None,
                    },
                },
            ]
        }
    )
    ranked = rank_items(items, seed_weights(), mode="semantic_only")
    assert [i.entity_id for i in ranked] == ["job_a", "job_b"]


def test_latency_threshold_and_sample_count() -> None:
    good = [0.1] * MATCHING_LATENCY_JOB_COUNT
    assert matching_latency_p95(good) < MATCHING_LATENCY_P95_SECONDS_MAX
    # Enough high samples that P95 exceeds the 2s ceiling.
    bad = [0.1] * 180 + [3.0] * 20
    assert matching_latency_p95(bad) >= MATCHING_LATENCY_P95_SECONDS_MAX
    with pytest.raises(RankingRunnerError, match="200"):
        matching_latency_p95([0.1] * 10)


def test_sealed_test_happy_path(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance, graph_helps=True, latency_seconds=0.05)
    selection, report, data_digest = tune_weights(
        relevance_payload=relevance,
        ranking_payload=features,
    )
    lock_path = tmp_path / "matching_config.json"
    write_tuning_lock(
        lock_path,
        split_seed=20260711,
        data_digest=data_digest,
        selection=selection,
    )
    result = run_sealed_test(
        relevance_payload=relevance,
        ranking_payload=features,
        lock_path=lock_path,
    )
    assert result["mode"] == "sealed_test"
    assert result["held_out_used"] is True
    assert set(result["ablations"]) == set(ABLATION_NAMES)
    assert "precision_at_10" in result["metrics"]
    assert "ndcg_at_10" in result["metrics"]
    assert "matching_latency_p95_seconds" in result["metrics"]
    assert isinstance(result["related_skill_boosts_enabled"], bool)
    assert result["data_class"] == "safe_aggregate"
    # No private/raw fields in aggregate.
    blob = json.dumps(result)
    for forbidden in ("raw_jd", "document_text", "cv_text", "contact_email"):
        assert forbidden not in blob

    lock = load_lock_artifact(lock_path)
    assert lock.sealed_test_completed is True
    assert lock.related_skill_boosts_enabled == result["related_skill_boosts_enabled"]

    # Reuse denied.
    with pytest.raises(HeldOutAccessError, match="already completed"):
        run_sealed_test(
            relevance_payload=relevance,
            ranking_payload=features,
            lock_path=lock_path,
        )


def test_sealed_test_refuses_missing_lock(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance)
    with pytest.raises(HeldOutAccessError, match="missing"):
        run_sealed_test(
            relevance_payload=relevance,
            ranking_payload=features,
            lock_path=tmp_path / "absent.json",
        )


def test_sealed_test_refuses_tampered_lock(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance)
    selection, _, data_digest = tune_weights(
        relevance_payload=relevance,
        ranking_payload=features,
    )
    lock_path = tmp_path / "matching_config.json"
    write_tuning_lock(
        lock_path,
        split_seed=20260711,
        data_digest=data_digest,
        selection=selection,
    )
    # Tamper weights without updating config_digest.
    lock = load_lock_artifact(lock_path)
    tampered = build_lock_artifact(
        split_seed=lock.split_seed,
        data_digest=lock.data_digest,
        config_digest=lock.config_digest,
        weights={**lock.weights, "semantic_similarity": 0.99},
        weight_config_version=lock.weight_config_version,
        validation_ndcg_at_10=lock.validation_ndcg_at_10,
    )
    write_lock_artifact(lock_path, tampered)
    with pytest.raises(HeldOutAccessError, match="config_digest"):
        run_sealed_test(
            relevance_payload=relevance,
            ranking_payload=features,
            lock_path=lock_path,
        )


def test_sealed_test_refuses_data_digest_mismatch(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance)
    selection, _, data_digest = tune_weights(
        relevance_payload=relevance,
        ranking_payload=features,
    )
    lock_path = tmp_path / "matching_config.json"
    write_tuning_lock(
        lock_path,
        split_seed=20260711,
        data_digest=data_digest,
        selection=selection,
    )
    # Mutate a label after lock → data_digest mismatch.
    relevance2 = json.loads(json.dumps(relevance))
    relevance2["items"][0]["relevance"] = (
        0 if relevance2["items"][0]["relevance"] != 0 else 1
    )
    with pytest.raises(HeldOutAccessError, match="data_digest"):
        run_sealed_test(
            relevance_payload=relevance2,
            ranking_payload=features,
            lock_path=lock_path,
        )


def test_baseline_gates_report_failures() -> None:
    from evaluation.ranking_scoring import AblationResult

    full = AblationResult(
        name="full_hybrid",
        ndcg_at_10=0.4,
        precision_at_10=0.5,
        ranked_entity_ids=(),
    )
    semantic = AblationResult(
        name="semantic_only",
        ndcg_at_10=0.5,
        precision_at_10=0.5,
        ranked_entity_ids=(),
    )
    skill = AblationResult(
        name="exact_skill_only",
        ndcg_at_10=0.45,
        precision_at_10=0.5,
        ranked_entity_ids=(),
    )
    gates = ranking_gates(
        full_hybrid=full,
        semantic_only=semantic,
        exact_skill_only=skill,
        latency_p95_seconds=0.1,
    )
    by_name = {g.name: g for g in gates}
    assert by_name["precision_at_10"].verdict == "FAIL"
    assert by_name["full_hybrid_ndcg_gt_semantic_only"].verdict == "FAIL"
    assert by_name["full_hybrid_ndcg_gt_skill_only"].verdict == "FAIL"
    assert full.precision_at_10 < PRECISION_AT_10_MIN


def test_cli_help_documents_tune_and_sealed_test() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "tune" in help_text
    assert "sealed-test" in help_text
    assert "grid search" in help_text.lower() or "validation" in help_text.lower()
    # Subparser help exits 0.
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["tune", "--help"])
    assert exc.value.code == 0
    with pytest.raises(SystemExit) as exc2:
        build_parser().parse_args(["sealed-test", "--help"])
    assert exc2.value.code == 0


def test_cli_tune_and_sealed_end_to_end(tmp_path: Path) -> None:
    relevance = _relevance_payload()
    features = _features_for_relevance(relevance, latency_seconds=0.08)
    rel_path = tmp_path / "relevance.json"
    feat_path = tmp_path / "features.json"
    lock_path = tmp_path / "matching_config.json"
    val_out = tmp_path / "validation.json"
    test_out = tmp_path / "sealed.json"
    rel_path.write_text(json.dumps(relevance), encoding="utf-8")
    feat_path.write_text(json.dumps(features), encoding="utf-8")

    code = main(
        [
            "tune",
            "--input",
            str(rel_path),
            "--features",
            str(feat_path),
            "--lock",
            str(lock_path),
            "--validation-output",
            str(val_out),
        ]
    )
    assert code == 0
    assert lock_path.is_file()
    val = json.loads(val_out.read_text(encoding="utf-8"))
    assert val["held_out_used"] is False

    code2 = main(
        [
            "sealed-test",
            "--input",
            str(rel_path),
            "--features",
            str(feat_path),
            "--lock",
            str(lock_path),
            "--output",
            str(test_out),
        ]
    )
    assert code2 in (0, 1)  # PASS or FAIL gates; must not crash (2)
    sealed = json.loads(test_out.read_text(encoding="utf-8"))
    assert len(sealed["ablations"]) == 5
    assert sealed["held_out_used"] is True

    # Second sealed-test fails closed (exit 2).
    code3 = main(
        [
            "sealed-test",
            "--input",
            str(rel_path),
            "--features",
            str(feat_path),
            "--lock",
            str(lock_path),
            "--output",
            str(tmp_path / "again.json"),
        ]
    )
    assert code3 == 2


def test_privacy_forbidden_fields_in_features() -> None:
    from evaluation.dataset_contracts import DatasetContractError

    with pytest.raises(DatasetContractError):
        parse_ranking_items(
            {
                "items": [
                    {
                        "entity_id": "x",
                        "relevance": 1,
                        "document_text": "secret body",
                        "components": {
                            "semantic_similarity": 0.1,
                            "skill_score_exact": 0.1,
                            "skill_score_graph": 0.1,
                        },
                    }
                ]
            }
        )


def test_no_provider_or_network_imports_in_ranking_modules() -> None:
    for name in (
        "ranking_scoring.py",
        "ranking_tune.py",
        "ranking_sealed.py",
        "run_ranking.py",
    ):
        text = (EVAL_DIR / name).read_text(encoding="utf-8")
        assert "ShopAIKey" not in text
        assert "httpx" not in text
        assert "GraphDatabase" not in text
        assert "openai" not in text.lower() or "openai" not in text


def test_verify_lock_requires_weights() -> None:
    lock = build_lock_artifact(
        split_seed=20260711,
        data_digest="a" * 64,
        config_digest="b" * 64,
        weights={},
    )
    with pytest.raises(HeldOutAccessError, match="weights"):
        verify_lock_integrity(lock, data_digest="a" * 64, split_seed=20260711)


def test_shared_ndcg_matches_metrics_module() -> None:
    from evaluation.benchmark_embeddings import ndcg_at_k as bench_ndcg
    from evaluation.metrics import ndcg_at_k as metrics_ndcg

    labels = [3, 0, 2, 1, 0]
    assert bench_ndcg(labels, k=10) == metrics_ndcg(labels, k=10)
