"""Tests for Plan 6 tool-selection evaluation runner (task 05B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from app.tools.registry import PRODUCTION_TOOL_NAMES
from evaluation.dataset_contracts import (
    PROTOCOL_ID,
    REQUIRED_TOOL_CATEGORIES,
    TOOL_SCENARIOS_MIN,
    DatasetContractError,
    parse_tool_selection_dataset,
)
from evaluation.metrics import (
    FIRST_SSE_EVENT_SECONDS_MAX,
    INVALID_TOOL_ARGUMENTS_MAX,
    TOOL_SELECTION_ACCURACY_MIN,
)
from evaluation.run_tool_selection import (
    build_parser,
    evaluate_tool_selection,
    main,
    parse_tool_scenario_runs,
    score_tool_selection_match,
    synthesize_valid_commit_args,
    validate_tool_arguments,
    write_result,
)
from evaluation.tool_run_parse import ToolSelectionRunnerError


def _digest(index: int) -> str:
    return f"{index:064x}"[-64:]


def _category_cycle() -> list[str]:
    return sorted(REQUIRED_TOOL_CATEGORIES)


def _expected_for_category(category: str) -> tuple[list[str], str]:
    mapping: dict[str, tuple[list[str], str]] = {
        "cv_upload": (["propose_profile_from_cv"], "draft_created"),
        "profile_correction": (["propose_profile_update"], "draft_created"),
        "approval": (["commit_profile_draft"], "committed"),
        "rejection": ([], "rejected"),
        "jd_url_ingestion": (["save_job"], "job_saved"),
        "jd_text_ingestion": (["save_job"], "job_saved"),
        "duplicate_job": (["save_job"], "duplicate_existing"),
        "match_with_profile": (["match_jobs"], "success_with_matches"),
        "match_without_profile": (["match_jobs"], "guidance_no_profile"),
        "unrelated_conversation": ([], "no_tool"),
        "tool_failure": (["query_jobs"], "tool_error"),
        "prompt_injection": ([], "injection_rejected"),
    }
    return mapping[category]


def _gold_items(n: int = TOOL_SCENARIOS_MIN) -> list[dict[str, Any]]:
    categories = _category_cycle()
    items: list[dict[str, Any]] = []
    for index in range(n):
        category = categories[index % len(categories)]
        tools, outcome = _expected_for_category(category)
        items.append(
            {
                "scenario_id": f"syn_tool_{index:04d}",
                "category": category,
                "expected_tools": tools,
                "expected_outcome": outcome,
                "prompt_digest": _digest(index + 1),
                "label_provenance": "synthetic",
            }
        )
    return items


def _gold_payload(n: int = TOOL_SCENARIOS_MIN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": 20260711,
        "items": _gold_items(n),
    }


def _tool_args_for(tools: list[str]) -> dict[str, dict[str, Any]]:
    args: dict[str, dict[str, Any]] = {}
    for name in tools:
        if name == "propose_profile_from_cv":
            args[name] = {"attachment_id": str(UUID(int=10))}
        elif name == "propose_profile_update":
            # Skip schema validation path via arguments_valid flag in perfect runs.
            pass
        elif name == "commit_profile_draft":
            args[name] = synthesize_valid_commit_args()
        elif name == "save_job":
            args[name] = {"url": "https://example.com/jobs/1", "force_new": False}
        elif name == "query_jobs":
            args[name] = {"limit": 5}
        elif name == "match_jobs":
            args[name] = {"limit": 10}
        elif name == "get_candidate_context":
            args[name] = {"scope": "approved"}
    return args


def _perfect_runs(n: int = TOOL_SCENARIOS_MIN) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for item in _gold_items(n):
        tools = list(item["expected_tools"])
        runs.append(
            {
                "scenario_id": item["scenario_id"],
                "selected_tools": tools,
                "arguments_valid": True,
                "outcome": item["expected_outcome"],
                "unauthorized_profile_commit": False,
                "pii_leak_to_adapter": False,
                "false_success_after_failure": False,
                "first_sse_event_seconds": 0.05,
                "status": "ok",
                "tool_arguments": _tool_args_for(tools),
            }
        )
    return {"schema_version": 1, "runs": runs}


def test_production_tool_names_are_seven() -> None:
    assert len(PRODUCTION_TOOL_NAMES) == 7
    assert "match_jobs" in PRODUCTION_TOOL_NAMES


def test_validate_tool_arguments_with_production_schemas() -> None:
    assert validate_tool_arguments(
        "match_jobs", {"limit": 5}
    )
    assert validate_tool_arguments(
        "commit_profile_draft", synthesize_valid_commit_args()
    )
    assert not validate_tool_arguments("commit_profile_draft", {})
    assert not validate_tool_arguments("unknown_tool", {})
    assert validate_tool_arguments("get_candidate_context", {})
    assert not validate_tool_arguments("save_job", {})  # needs url or raw_text


def test_score_tool_selection_match() -> None:
    assert score_tool_selection_match(
        expected_tools=["match_jobs"],
        selected_tools=["match_jobs"],
        expected_outcome="success_with_matches",
        actual_outcome="success_with_matches",
    )
    assert not score_tool_selection_match(
        expected_tools=["match_jobs"],
        selected_tools=["query_jobs"],
        expected_outcome="success_with_matches",
        actual_outcome="success_with_matches",
    )


def test_perfect_runs_pass_all_gates() -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    runs = parse_tool_scenario_runs(_perfect_runs())
    result = evaluate_tool_selection(gold, runs)
    assert result.overall == "PASS"
    assert result.scenario_count == TOOL_SCENARIOS_MIN
    assert result.metrics["tool_selection_accuracy"] >= TOOL_SELECTION_ACCURACY_MIN
    assert (
        float(result.metrics["invalid_tool_arguments_rate"])
        <= INVALID_TOOL_ARGUMENTS_MAX
    )
    assert result.metrics["unauthorized_profile_commits"] == 0
    assert result.metrics["pii_leaks"] == 0
    assert result.metrics["false_success_after_failure"] == 0
    assert (
        float(result.metrics["first_sse_event_seconds_max"])
        < FIRST_SSE_EVENT_SECONDS_MAX
    )
    covered = set(result.categories_covered)
    assert REQUIRED_TOOL_CATEGORIES.issubset(covered)
    blob = json.dumps(result.as_dict())
    for banned in ("document_text", "raw_cv", "conversation_body", "contact_email"):
        assert banned not in blob


def test_missing_run_fails_not_skipped() -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    payload = _perfect_runs()
    payload["runs"] = payload["runs"][1:]
    runs = parse_tool_scenario_runs(payload)
    result = evaluate_tool_selection(gold, runs)
    assert result.missing_run_count == 1
    assert result.overall == "FAIL"


def test_safety_metrics_zero_required() -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    payload = _perfect_runs()
    payload["runs"][0]["unauthorized_profile_commit"] = True
    result = evaluate_tool_selection(gold, parse_tool_scenario_runs(payload))
    assert result.overall == "FAIL"
    assert result.metrics["unauthorized_profile_commits"] == 1

    payload = _perfect_runs()
    payload["runs"][1]["pii_leak_to_adapter"] = True
    result = evaluate_tool_selection(gold, parse_tool_scenario_runs(payload))
    assert result.metrics["pii_leaks"] == 1
    assert result.overall == "FAIL"

    payload = _perfect_runs()
    payload["runs"][2]["false_success_after_failure"] = True
    result = evaluate_tool_selection(gold, parse_tool_scenario_runs(payload))
    assert result.metrics["false_success_after_failure"] == 1
    assert result.overall == "FAIL"


def test_invalid_arguments_and_latency_thresholds() -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    payload = _perfect_runs()
    # Make more than 5% invalid.
    for run in payload["runs"][:5]:
        run["arguments_valid"] = False
    result = evaluate_tool_selection(gold, parse_tool_scenario_runs(payload))
    assert float(result.metrics["invalid_tool_arguments_rate"]) > INVALID_TOOL_ARGUMENTS_MAX
    assert result.overall == "FAIL"

    payload = _perfect_runs()
    payload["runs"][0]["first_sse_event_seconds"] = 1.5
    result = evaluate_tool_selection(gold, parse_tool_scenario_runs(payload))
    assert (
        float(result.metrics["first_sse_event_seconds_max"])
        > FIRST_SSE_EVENT_SECONDS_MAX
    )
    assert result.overall == "FAIL"


def test_schema_derived_invalid_arguments() -> None:
    payload = {
        "schema_version": 1,
        "runs": [
            {
                "scenario_id": "syn_tool_0000",
                "selected_tools": ["commit_profile_draft"],
                "outcome": "committed",
                "tool_arguments": {
                    "commit_profile_draft": {"draft_id": "not-a-uuid"}
                },
                "first_sse_event_seconds": 0.01,
            }
        ],
    }
    runs = parse_tool_scenario_runs(payload)
    assert runs["syn_tool_0000"].arguments_valid is False


def test_forbidden_fields_rejected() -> None:
    payload = _perfect_runs()
    payload["runs"][0]["raw_cv"] = "leak"
    with pytest.raises((ToolSelectionRunnerError, DatasetContractError)):
        parse_tool_scenario_runs(payload)


def test_all_required_categories_present_in_fixture() -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    present = {item.category for item in gold.items}
    assert present == REQUIRED_TOOL_CATEGORIES or REQUIRED_TOOL_CATEGORIES.issubset(
        present
    )


def test_cli_help_and_main(tmp_path: Path) -> None:
    help_text = build_parser().format_help()
    assert "--input" in help_text
    assert "--runs" in help_text
    assert "--output" in help_text
    assert "--split" in help_text

    gold_path = tmp_path / "gold.json"
    runs_path = tmp_path / "runs.json"
    out_path = tmp_path / "out.json"
    gold_path.write_text(json.dumps(_gold_payload()), encoding="utf-8")
    runs_path.write_text(json.dumps(_perfect_runs()), encoding="utf-8")
    code = main(
        [
            "--input",
            str(gold_path),
            "--runs",
            str(runs_path),
            "--output",
            str(out_path),
            "--split",
            "development",
        ]
    )
    assert code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["overall"] == "PASS"
    assert payload["data_class"] == "safe_aggregate"

    # Wrong tools -> FAIL exit 1
    bad = _perfect_runs()
    for run in bad["runs"]:
        run["selected_tools"] = ["query_jobs"]
        run["outcome"] = "wrong"
    bad_path = tmp_path / "bad.json"
    bad_out = tmp_path / "bad_out.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    code_fail = main(
        [
            "--input",
            str(gold_path),
            "--runs",
            str(bad_path),
            "--output",
            str(bad_out),
        ]
    )
    assert code_fail == 1


def test_write_result_aggregate_only(tmp_path: Path) -> None:
    gold = parse_tool_selection_dataset(_gold_payload())
    runs = parse_tool_scenario_runs(_perfect_runs())
    result = evaluate_tool_selection(gold, runs)
    path = tmp_path / "agg.json"
    write_result(path, result)
    text = path.read_text(encoding="utf-8")
    assert "tool_selection_accuracy" in text
    assert "conversation_body" not in text
    assert "raw_cv" not in text


def test_no_provider_or_neo4j_in_runner_source() -> None:
    import evaluation.run_tool_selection as mod
    import evaluation.tool_run_parse as parse_mod
    import evaluation.tool_selection_scoring as scoring

    for module in (mod, scoring, parse_mod):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "ShopAIKey" not in source
        assert "httpx" not in source
        assert "GraphDatabase" not in source
