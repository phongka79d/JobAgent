"""CLI entry for deterministic extraction evaluation (Plan 6 / task 05B).

Loads gold labels and prediction records, scores locked Master §19.5 extraction
metrics, writes aggregate-only JSON, and exits nonzero on any FAIL gate.
Does not call providers, mutate production state, or emit private row reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evaluation.dataset_contracts import (
    DatasetContractError,
    ExtractionDataset,
    parse_extraction_dataset,
)
from evaluation.extraction_scoring import (
    RUNNER_ID,
    ExtractionEvalResult,
    ExtractionPrediction,
    ExtractionRunnerError,
    evaluate_extraction,
    parse_extraction_predictions,
)

__all__ = [
    "RUNNER_ID",
    "ExtractionEvalResult",
    "ExtractionPrediction",
    "ExtractionRunnerError",
    "build_parser",
    "evaluate_extraction",
    "load_extraction_gold",
    "load_extraction_predictions",
    "main",
    "parse_extraction_predictions",
    "write_result",
]


def load_extraction_gold(path: Path) -> ExtractionDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ExtractionRunnerError(f"{path} root must be a JSON object")
    try:
        return parse_extraction_dataset(raw)
    except (DatasetContractError, ValueError) as exc:
        raise ExtractionRunnerError(str(exc)) from exc


def load_extraction_predictions(path: Path) -> dict[str, ExtractionPrediction]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ExtractionRunnerError(f"{path} root must be a JSON object")
    return parse_extraction_predictions(raw)


def write_result(path: Path, result: ExtractionEvalResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.run_extraction",
        description=(
            "Evaluate JD extraction predictions against gold annotations. "
            "Outputs aggregate-only metrics (no private row reports). "
            "Does not call providers or load held-out data by default. "
            "Required inputs: --labels, --predictions, --output."
        ),
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="Path to extraction gold labels JSON (ExtractionDataset envelope).",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Path to extraction predictions JSON (predictions list).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for aggregate-only result JSON.",
    )
    parser.add_argument(
        "--split",
        choices=("all", "development", "validation", "held_out_test"),
        default="all",
        help=(
            "Split mode metadata for callers. This runner scores the full "
            "provided label file; split filtering is owned by 05A loaders."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.labels is None or args.predictions is None or args.output is None:
        parser.error("--labels, --predictions, and --output are required to run")
    try:
        gold = load_extraction_gold(args.labels)
        predictions = load_extraction_predictions(args.predictions)
        result = evaluate_extraction(gold, predictions)
    except (
        ExtractionRunnerError,
        DatasetContractError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"extraction evaluation failed: {exc}", file=sys.stderr)
        return 2
    write_result(args.output, result)
    print(
        json.dumps(
            {
                "overall": result.overall,
                "item_count": result.item_count,
                "metrics": result.metrics,
                "split_mode": args.split,
            },
            sort_keys=True,
        )
    )
    return 0 if result.overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
