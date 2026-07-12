"""CLI entry for deterministic tool-selection evaluation (Plan 6 / task 05B).

Scores gold tool scenarios against observed runs using production contracts.
Writes aggregate-only JSON and exits nonzero on any locked-threshold FAIL.
No private conversation bodies, provider calls, or production mutations.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evaluation.dataset_contracts import (
    REQUIRED_TOOL_CATEGORIES,
    DatasetContractError,
    ToolSelectionDataset,
    parse_tool_selection_dataset,
)
from evaluation.tool_selection_scoring import (
    RUNNER_ID,
    ToolScenarioRun,
    ToolSelectionEvalResult,
    ToolSelectionRunnerError,
    evaluate_tool_selection,
    parse_tool_scenario_runs,
    score_tool_selection_match,
    synthesize_valid_commit_args,
    validate_tool_arguments,
)

__all__ = [
    "RUNNER_ID",
    "ToolScenarioRun",
    "ToolSelectionEvalResult",
    "ToolSelectionRunnerError",
    "build_parser",
    "evaluate_tool_selection",
    "load_tool_gold",
    "load_tool_runs",
    "main",
    "parse_tool_scenario_runs",
    "score_tool_selection_match",
    "synthesize_valid_commit_args",
    "validate_tool_arguments",
    "write_result",
]


def load_tool_gold(path: Path) -> ToolSelectionDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ToolSelectionRunnerError(f"{path} root must be a JSON object")
    try:
        return parse_tool_selection_dataset(raw)
    except (DatasetContractError, ValueError) as exc:
        raise ToolSelectionRunnerError(str(exc)) from exc


def load_tool_runs(path: Path) -> dict[str, ToolScenarioRun]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ToolSelectionRunnerError(f"{path} root must be a JSON object")
    return parse_tool_scenario_runs(raw)


def write_result(path: Path, result: ToolSelectionEvalResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.run_tool_selection",
        description=(
            "Evaluate tool-selection scenario runs against gold scenarios. "
            "Uses production tool name contracts and optional fake-backed "
            "argument schema checks. Aggregate-only output; no private rows, "
            "providers, or live graph calls. "
            "Required inputs: --input, --runs, --output."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to tool-selection gold scenarios JSON.",
    )
    parser.add_argument(
        "--runs",
        type=Path,
        help="Path to observed scenario run results JSON.",
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
            "provided scenario file; split filtering is owned by 05A loaders."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.input is None or args.runs is None or args.output is None:
        parser.error("--input, --runs, and --output are required to run")
    try:
        gold = load_tool_gold(args.input)
        present = {item.category for item in gold.items}
        if not REQUIRED_TOOL_CATEGORIES.issubset(present):
            missing_cats = sorted(REQUIRED_TOOL_CATEGORIES - present)
            raise ToolSelectionRunnerError(
                "missing required categories: " + ", ".join(missing_cats)
            )
        runs = load_tool_runs(args.runs)
        result = evaluate_tool_selection(gold, runs)
    except (
        ToolSelectionRunnerError,
        DatasetContractError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"tool-selection evaluation failed: {exc}", file=sys.stderr)
        return 2
    write_result(args.output, result)
    print(
        json.dumps(
            {
                "overall": result.overall,
                "scenario_count": result.scenario_count,
                "metrics": result.metrics,
                "split_mode": args.split,
            },
            sort_keys=True,
        )
    )
    return 0 if result.overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
