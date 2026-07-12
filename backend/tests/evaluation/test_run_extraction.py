"""Tests for Plan 6 extraction evaluation runner (task 05B)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from evaluation.dataset_contracts import (
    EXTRACTION_MIN,
    PROTOCOL_ID,
    DatasetContractError,
    parse_extraction_dataset,
)
from evaluation.extraction_scoring import ExtractionRunnerError
from evaluation.metrics import (
    EXTRACTION_TIMEOUT_SECONDS_MAX,
    LOCATION_ACCURACY_MIN,
    SENIORITY_MACRO_F1_MIN,
    SKILL_ENTITY_F1_MIN,
    WORK_MODE_MACRO_F1_MIN,
    entity_set_f1,
    field_accuracy,
    macro_f1,
    mean_entity_set_f1,
)
from evaluation.run_extraction import (
    build_parser,
    evaluate_extraction,
    main,
    parse_extraction_predictions,
    write_result,
)


def _gold_items(n: int = EXTRACTION_MIN) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seniorities = ["intern", "junior", "mid", "senior", "lead"]
    modes = ["remote", "hybrid", "onsite"]
    for index in range(n):
        items.append(
            {
                "entity_id": f"syn_ext_{index:04d}",
                "required_skills": ["python", "sql"],
                "preferred_skills": ["docker"] if index % 2 == 0 else [],
                "seniority": seniorities[index % len(seniorities)],
                "work_mode": modes[index % len(modes)],
                "location": "berlin" if index % 3 else "munich",
                "label_provenance": "synthetic",
            }
        )
    return items


def _gold_payload(n: int = EXTRACTION_MIN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": 20260711,
        "items": _gold_items(n),
    }


def _perfect_predictions(n: int = EXTRACTION_MIN) -> dict[str, Any]:
    preds: list[dict[str, Any]] = []
    for item in _gold_items(n):
        preds.append(
            {
                "entity_id": item["entity_id"],
                "required_skills": list(item["required_skills"]),
                "preferred_skills": list(item["preferred_skills"]),
                "seniority": item["seniority"],
                "work_mode": item["work_mode"],
                "location": item["location"],
                "duration_seconds": 1.25,
                "status": "ok",
            }
        )
    return {"schema_version": 1, "predictions": preds}


def test_entity_set_f1_boundaries() -> None:
    assert entity_set_f1([], []) == 1.0
    assert entity_set_f1(["python"], []) == 0.0
    assert entity_set_f1([], ["python"]) == 0.0
    assert entity_set_f1(["Python"], ["python"]) == 1.0
    assert entity_set_f1(["python", "sql"], ["python"]) == pytest.approx(2 / 3, rel=1e-6)


def test_macro_f1_and_location_accuracy() -> None:
    gold = ["mid", "senior", "mid", "junior"]
    pred = ["mid", "senior", "junior", "junior"]
    assert 0.0 < macro_f1(gold, pred) < 1.0
    assert macro_f1(gold, gold) == 1.0
    assert field_accuracy(["Berlin"], ["berlin"]) == 1.0
    assert field_accuracy(["berlin"], ["munich"]) == 0.0


def test_perfect_predictions_pass_all_gates() -> None:
    gold = parse_extraction_dataset(_gold_payload())
    preds = parse_extraction_predictions(_perfect_predictions())
    result = evaluate_extraction(gold, preds)
    assert result.overall == "PASS"
    assert result.item_count == EXTRACTION_MIN
    assert result.metrics["skill_entity_f1"] >= SKILL_ENTITY_F1_MIN
    assert result.metrics["seniority_macro_f1"] >= SENIORITY_MACRO_F1_MIN
    assert result.metrics["work_mode_macro_f1"] >= WORK_MODE_MACRO_F1_MIN
    assert result.metrics["location_accuracy"] >= LOCATION_ACCURACY_MIN
    assert (
        result.metrics["extraction_timeout_seconds_max"]
        <= EXTRACTION_TIMEOUT_SECONDS_MAX
    )
    assert result.missing_prediction_count == 0
    assert result.invalid_prediction_count == 0
    assert result.timeout_count == 0
    assert result.as_dict()["data_class"] == "safe_aggregate"
    # Aggregate only: no private document bodies.
    blob = json.dumps(result.as_dict())
    for banned in ("document_text", "raw_jd", "cv_text", "contact_email"):
        assert banned not in blob


def test_missing_prediction_counts_as_failure() -> None:
    gold = parse_extraction_dataset(_gold_payload())
    payload = _perfect_predictions()
    # Drop one prediction — not skipped as pass.
    payload["predictions"] = payload["predictions"][1:]
    preds = parse_extraction_predictions(payload)
    result = evaluate_extraction(gold, preds)
    assert result.missing_prediction_count == 1
    assert result.overall == "FAIL"
    assert result.metrics["skill_entity_f1"] < 1.0


def test_invalid_and_timeout_fail_closed() -> None:
    gold = parse_extraction_dataset(_gold_payload())
    payload = _perfect_predictions()
    payload["predictions"][0]["status"] = "invalid"
    payload["predictions"][1]["status"] = "timeout"
    payload["predictions"][1]["duration_seconds"] = 50.0
    preds = parse_extraction_predictions(payload)
    result = evaluate_extraction(gold, preds)
    assert result.invalid_prediction_count == 1
    assert result.timeout_count == 1
    assert result.overall == "FAIL"
    assert (
        result.metrics["extraction_timeout_seconds_max"]
        > EXTRACTION_TIMEOUT_SECONDS_MAX
    )


def test_forbidden_fields_rejected() -> None:
    payload = _perfect_predictions()
    payload["predictions"][0]["document_text"] = "secret body"
    with pytest.raises((ExtractionRunnerError, DatasetContractError)):
        parse_extraction_predictions(payload)


def test_mean_entity_set_f1_partial() -> None:
    pairs = [
        (["python", "sql"], ["python", "sql"]),
        (["java"], ["python"]),
    ]
    score = mean_entity_set_f1(pairs)
    assert 0.0 < score < 1.0


def test_cli_help_exposes_modes() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "--labels" in help_text
    assert "--predictions" in help_text
    assert "--output" in help_text
    assert "--split" in help_text
    assert "held_out_test" in help_text


def test_cli_main_pass_and_fail(tmp_path: Path) -> None:
    labels = tmp_path / "labels.json"
    preds_path = tmp_path / "preds.json"
    out = tmp_path / "out.json"
    labels.write_text(json.dumps(_gold_payload()), encoding="utf-8")
    preds_path.write_text(json.dumps(_perfect_predictions()), encoding="utf-8")
    code = main(
        [
            "--labels",
            str(labels),
            "--predictions",
            str(preds_path),
            "--output",
            str(out),
            "--split",
            "all",
        ]
    )
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["overall"] == "PASS"
    assert payload["protocol_id"] == PROTOCOL_ID

    # Force failure via empty skills mismatch.
    bad = _perfect_predictions()
    for item in bad["predictions"]:
        item["required_skills"] = ["totally_wrong_skill"]
        item["preferred_skills"] = ["another_wrong"]
        item["seniority"] = "intern"
        item["work_mode"] = "remote"
        item["location"] = "nowhere"
    bad_path = tmp_path / "bad.json"
    bad_out = tmp_path / "bad_out.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    code_fail = main(
        [
            "--labels",
            str(labels),
            "--predictions",
            str(bad_path),
            "--output",
            str(bad_out),
        ]
    )
    assert code_fail == 1
    assert json.loads(bad_out.read_text(encoding="utf-8"))["overall"] == "FAIL"


def test_write_result_is_aggregate_only(tmp_path: Path) -> None:
    gold = parse_extraction_dataset(_gold_payload())
    preds = parse_extraction_predictions(_perfect_predictions())
    result = evaluate_extraction(gold, preds)
    path = tmp_path / "agg.json"
    write_result(path, result)
    text = path.read_text(encoding="utf-8")
    assert "data_class" in text
    assert "raw_jd" not in text
    assert "document_text" not in text


def test_no_network_imports_for_runner() -> None:
    """Runner modules must not depend on live provider clients at import time."""
    import evaluation.run_extraction as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "ShopAIKey" not in source
    assert "httpx" not in source
    assert "neo4j" not in source.lower()
