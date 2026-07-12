"""CLI for ranking grid search and sealed held-out evaluation (Plan 6 / 05C).

Subcommands:
  tune         — development/validation grid search; writes lock + validation JSON
  sealed-test  — one-shot held-out ablations, metrics, latency, graph decision

Never loads private data by default; paths are explicit. Aggregate-only output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evaluation.dataset_contracts import DatasetContractError, parse_relevance_dataset
from evaluation.ranking_scoring import RankingRunnerError
from evaluation.ranking_sealed import run_sealed_test
from evaluation.ranking_tune import tune_weights, write_tuning_lock
from evaluation.split_assignment import SplitProtocolError
from evaluation.split_lock import HeldOutAccessError

__all__ = [
    "build_parser",
    "load_json_object",
    "main",
    "write_json",
]


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RankingRunnerError(f"{path} root must be a JSON object")
    return raw


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.run_ranking",
        description=(
            "Ranking evaluation CLI. "
            "tune: bounded grid search on development/validation only; "
            "writes a content-digested matching_config lock (no held-out). "
            "sealed-test: requires lock; runs five ablations, Precision@10, "
            "nDCG@10 baselines, 200-job P95 latency, and graph-enable decision "
            "exactly once. Paths are explicit; no private defaults."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    tune = sub.add_parser(
        "tune",
        help=(
            "Grid-search weights on development/validation nDCG@10; "
            "emit lock artifact (never reads held-out labels)."
        ),
    )
    tune.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Relevance labels JSON (RelevanceDataset envelope; 150-200 items).",
    )
    tune.add_argument(
        "--features",
        type=Path,
        required=True,
        help=(
            "Ranking features JSON with per-entity components "
            "(semantic/skill exact|graph/non-skill scores; safe IDs only)."
        ),
    )
    tune.add_argument(
        "--lock",
        type=Path,
        required=True,
        help="Output path for matching_config_lock_v1 (content-digested).",
    )
    tune.add_argument(
        "--validation-output",
        type=Path,
        required=True,
        help="Aggregate-only validation tuning result JSON.",
    )

    sealed = sub.add_parser(
        "sealed-test",
        help=(
            "One-time held-out evaluation after lock; five ablations, "
            "latency, graph decision; refuses missing/tampered/reused locks."
        ),
    )
    sealed.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Relevance labels JSON (same digest as lock data_digest).",
    )
    sealed.add_argument(
        "--features",
        type=Path,
        required=True,
        help="Ranking features JSON covering held-out entities.",
    )
    sealed.add_argument(
        "--lock",
        type=Path,
        required=True,
        help="Existing matching_config_lock_v1 from tune (not yet completed).",
    )
    sealed.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Immutable aggregate sealed-test result JSON.",
    )
    return parser


def _cmd_tune(args: argparse.Namespace) -> int:
    relevance = load_json_object(args.input)
    features = load_json_object(args.features)
    selection, report, data_digest = tune_weights(
        relevance_payload=relevance,
        ranking_payload=features,
    )
    dataset = parse_relevance_dataset(relevance)
    write_tuning_lock(
        args.lock,
        split_seed=dataset.split_seed,
        data_digest=data_digest,
        selection=selection,
    )
    write_json(args.validation_output, report)
    print(
        json.dumps(
            {
                "mode": "tune",
                "validation_ndcg_at_10": selection.validation_ndcg_at_10,
                "config_digest": selection.config_digest,
                "lock": str(args.lock),
                "held_out_used": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_sealed(args: argparse.Namespace) -> int:
    relevance = load_json_object(args.input)
    features = load_json_object(args.features)
    result = run_sealed_test(
        relevance_payload=relevance,
        ranking_payload=features,
        lock_path=args.lock,
    )
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "mode": "sealed_test",
                "overall": result["overall"],
                "related_skill_boosts_enabled": result["related_skill_boosts_enabled"],
                "metrics": result["metrics"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["overall"] == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "tune":
            return _cmd_tune(args)
        if args.command == "sealed-test":
            return _cmd_sealed(args)
        parser.error(f"unknown command: {args.command}")
    except (
        RankingRunnerError,
        DatasetContractError,
        HeldOutAccessError,
        SplitProtocolError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"ranking evaluation failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
