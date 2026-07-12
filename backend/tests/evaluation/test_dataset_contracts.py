"""Synthetic tests for Plan 6 privacy-safe dataset contracts (task 05A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from evaluation.dataset_contracts import (
    EXTRACTION_MIN,
    FORBIDDEN_FIELD_NAMES,
    PROTOCOL_ID,
    RELEVANCE_MAX,
    RELEVANCE_MIN,
    REQUIRED_TOOL_CATEGORIES,
    TOOL_SCENARIOS_MIN,
    AggregateDatasetManifest,
    CandidateReference,
    DatasetContractError,
    ExtractionAnnotationItem,
    ExtractionDataset,
    RelevanceDataset,
    RelevanceLabelItem,
    ToolScenarioItem,
    ToolSelectionDataset,
    assert_no_forbidden_fields,
    build_aggregate_manifest,
    content_digest,
    parse_candidate_reference,
    parse_extraction_dataset,
    parse_relevance_dataset,
    parse_tool_selection_dataset,
)
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPO_ROOT / "backend" / "evaluation"
SYNTHETIC_FIXTURE = EVAL_ROOT / "fixtures" / "matching_synthetic.json"
PROTOCOL_PATH = EVAL_ROOT / "labels" / "matching_protocol.json"
RELEVANCE_TEMPLATE = EVAL_ROOT / "labels" / "relevance_labels.template.json"
EXTRACTION_TEMPLATE = EVAL_ROOT / "labels" / "extraction_labels.template.json"
TOOL_TEMPLATE = EVAL_ROOT / "labels" / "tool_selection_scenarios.template.json"

_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_DIGEST_C = "c" * 64
_DIGEST_D = "d" * 64


def _digest_for(text: str) -> str:
    return content_digest(text)


def _make_relevance_items(n: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index in range(n):
        items.append(
            {
                "entity_id": f"syn_jd_{index:04d}",
                "relevance": index % 4,
                "label_provenance": "synthetic",
            }
        )
    return items


def _make_extraction_items(n: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index in range(n):
        items.append(
            {
                "entity_id": f"syn_jd_{index:04d}",
                "required_skills": ["python"],
                "preferred_skills": ["sql"] if index % 2 == 0 else [],
                "seniority": "mid",
                "work_mode": "remote",
                "location": "berlin",
                "label_provenance": "synthetic",
            }
        )
    return items


def _make_tool_items(n: int) -> list[dict[str, Any]]:
    categories = sorted(REQUIRED_TOOL_CATEGORIES)
    items: list[dict[str, Any]] = []
    for index in range(n):
        category = categories[index % len(categories)]
        items.append(
            {
                "scenario_id": f"syn_tool_{index:04d}",
                "category": category,
                "expected_tools": ["match_jobs"] if "match" in category else [],
                "expected_outcome": "ok",
                "prompt_digest": _digest_for(f"scenario-{index}"),
                "label_provenance": "synthetic",
            }
        )
    return items


def _full_relevance_payload(n: int = RELEVANCE_MIN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": 20260711,
        "items": _make_relevance_items(n),
    }


def _full_extraction_payload(n: int = EXTRACTION_MIN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": 20260711,
        "items": _make_extraction_items(n),
    }


def _full_tool_payload(n: int = TOOL_SCENARIOS_MIN) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": 20260711,
        "items": _make_tool_items(n),
    }


def _candidate_payload() -> dict[str, Any]:
    return {
        "candidate_ref_id": "syn_candidate_001",
        "representation_version": "candidate_embedding_text_v1",
        "redacted_text_digest": _DIGEST_A,
        "profile_digest": _DIGEST_B,
        "preferences_digest": _DIGEST_C,
        "label_provenance": "synthetic",
    }


def test_protocol_file_is_aggregate_safe() -> None:
    raw = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert raw["protocol_id"] == PROTOCOL_ID
    assert raw["split"]["scheme"] == "fixed_seeded_60_20_20"
    assert raw["dataset_requirements"]["relevance"]["min_items"] == RELEVANCE_MIN
    assert raw["dataset_requirements"]["relevance"]["max_items"] == RELEVANCE_MAX
    assert raw["dataset_requirements"]["extraction"]["min_items"] == EXTRACTION_MIN
    assert raw["dataset_requirements"]["tool_selection"]["min_items"] == TOOL_SCENARIOS_MIN
    assert_no_forbidden_fields(raw)


def test_templates_are_examples_not_full_evidence() -> None:
    for path in (RELEVANCE_TEMPLATE, EXTRACTION_TEMPLATE, TOOL_TEMPLATE):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert "items" in raw
        assert len(raw["items"]) == 1
        assert "_template_notes" in raw
        notes = " ".join(raw["_template_notes"]).lower()
        assert "schema example" in notes or "not evaluation evidence" in notes


def test_synthetic_fixture_has_no_private_bodies() -> None:
    raw = json.loads(SYNTHETIC_FIXTURE.read_text(encoding="utf-8"))
    assert raw["data_class"] == "synthetic"
    assert_no_forbidden_fields(raw)
    blob = json.dumps(raw).lower()
    for marker in ("raw_cv", "document_text", "contact_email", "sk-", "password="):
        assert marker not in blob


def test_relevance_count_bounds() -> None:
    parse_relevance_dataset(_full_relevance_payload(RELEVANCE_MIN))
    parse_relevance_dataset(_full_relevance_payload(RELEVANCE_MAX))
    with pytest.raises(DatasetContractError, match="150-200"):
        parse_relevance_dataset(_full_relevance_payload(RELEVANCE_MIN - 1))
    with pytest.raises(DatasetContractError, match="150-200"):
        parse_relevance_dataset(_full_relevance_payload(RELEVANCE_MAX + 1))


def test_relevance_labels_must_be_0_to_3() -> None:
    payload = _full_relevance_payload()
    payload["items"][0]["relevance"] = 4
    with pytest.raises(ValidationError):
        RelevanceDataset.model_validate(payload)


def test_relevance_ids_must_be_unique() -> None:
    payload = _full_relevance_payload()
    payload["items"][1]["entity_id"] = payload["items"][0]["entity_id"]
    with pytest.raises(ValidationError, match="unique"):
        RelevanceDataset.model_validate(payload)


def test_extraction_and_tool_minimums() -> None:
    parse_extraction_dataset(_full_extraction_payload(EXTRACTION_MIN))
    with pytest.raises(DatasetContractError, match="at least 30"):
        parse_extraction_dataset(_full_extraction_payload(EXTRACTION_MIN - 1))

    parse_tool_selection_dataset(_full_tool_payload(TOOL_SCENARIOS_MIN))
    with pytest.raises(DatasetContractError, match="at least 50"):
        parse_tool_selection_dataset(_full_tool_payload(TOOL_SCENARIOS_MIN - 1))


def test_tool_required_categories() -> None:
    payload = _full_tool_payload()
    # Drop all prompt_injection scenarios.
    payload["items"] = [
        item
        for item in payload["items"]
        if item["category"] != "prompt_injection"
    ]
    # Pad count back without the missing category.
    while len(payload["items"]) < TOOL_SCENARIOS_MIN:
        payload["items"].append(
            {
                "scenario_id": f"pad_{len(payload['items']):04d}",
                "category": "cv_upload",
                "expected_tools": [],
                "expected_outcome": "ok",
                "prompt_digest": _digest_for(f"pad-{len(payload['items'])}"),
                "label_provenance": "synthetic",
            }
        )
    with pytest.raises(DatasetContractError, match="prompt_injection"):
        parse_tool_selection_dataset(payload)


def test_forbidden_fields_rejected() -> None:
    payload = _full_relevance_payload()
    payload["document_text"] = "secret JD body"
    with pytest.raises(DatasetContractError, match="forbidden field"):
        parse_relevance_dataset(payload)

    for name in sorted(FORBIDDEN_FIELD_NAMES)[:5]:
        bad = {"entity_id": "x", name: "leak"}
        with pytest.raises(DatasetContractError):
            assert_no_forbidden_fields(bad)


def test_candidate_reference_digest_only() -> None:
    candidate = parse_candidate_reference(_candidate_payload())
    assert isinstance(candidate, CandidateReference)
    dumped = candidate.model_dump()
    assert "raw_cv" not in dumped
    assert "email" not in dumped

    bad = _candidate_payload()
    bad["contact_email"] = "user@example.com"
    with pytest.raises(DatasetContractError):
        parse_candidate_reference(bad)


def test_row_models_reject_raw_body_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RelevanceLabelItem.model_validate(
            {
                "entity_id": "jd_1",
                "relevance": 1,
                "document_text": "nope",
            }
        )
    with pytest.raises(ValidationError):
        ExtractionAnnotationItem.model_validate(
            {
                "entity_id": "jd_1",
                "required_skills": [],
                "preferred_skills": [],
                "seniority": "mid",
                "work_mode": "remote",
                "location": "berlin",
                "raw_jd": "nope",
            }
        )
    with pytest.raises(ValidationError):
        ToolScenarioItem.model_validate(
            {
                "scenario_id": "s1",
                "category": "cv_upload",
                "expected_tools": [],
                "expected_outcome": "ok",
                "prompt_digest": _DIGEST_D,
                "conversation_body": "nope",
            }
        )


def test_aggregate_manifest_has_counts_and_digests_only() -> None:
    relevance = parse_relevance_dataset(_full_relevance_payload())
    extraction = parse_extraction_dataset(_full_extraction_payload())
    tools = parse_tool_selection_dataset(_full_tool_payload())
    candidate = parse_candidate_reference(_candidate_payload())
    manifest = build_aggregate_manifest(
        relevance=relevance,
        extraction=extraction,
        tools=tools,
        candidate=candidate,
        notes="synthetic aggregate",
    )
    assert isinstance(manifest, AggregateDatasetManifest)
    assert manifest.relevance_count == RELEVANCE_MIN
    assert manifest.extraction_count == EXTRACTION_MIN
    assert manifest.tool_scenario_count == TOOL_SCENARIOS_MIN
    assert manifest.data_class == "safe_aggregate"
    blob = manifest.model_dump_json()
    assert "document_text" not in blob
    assert "raw_cv" not in blob


def test_content_digest_is_stable() -> None:
    first = content_digest({"b": 2, "a": 1})
    second = content_digest({"a": 1, "b": 2})
    assert first == second
    assert len(first) == 64


def test_template_item_shapes_validate_when_notes_stripped() -> None:
    relevance_raw = json.loads(RELEVANCE_TEMPLATE.read_text(encoding="utf-8"))
    relevance_raw.pop("_template_notes", None)
    # Single-item template is not full-count valid; model shape still parses.
    dataset = RelevanceDataset.model_validate(relevance_raw)
    assert len(dataset.items) == 1
    with pytest.raises(DatasetContractError):
        parse_relevance_dataset(relevance_raw)

    extraction_raw = json.loads(EXTRACTION_TEMPLATE.read_text(encoding="utf-8"))
    extraction_raw.pop("_template_notes", None)
    ExtractionDataset.model_validate(extraction_raw)

    tools_raw = json.loads(TOOL_TEMPLATE.read_text(encoding="utf-8"))
    tools_raw.pop("_template_notes", None)
    ToolSelectionDataset.model_validate(tools_raw)


def test_synthetic_fixture_samples_parse_row_models() -> None:
    raw = json.loads(SYNTHETIC_FIXTURE.read_text(encoding="utf-8"))
    for item in raw["relevance_sample"]["items"]:
        RelevanceLabelItem.model_validate(item)
    for item in raw["extraction_sample"]["items"]:
        ExtractionAnnotationItem.model_validate(item)
    for item in raw["tool_selection_sample"]["items"]:
        ToolScenarioItem.model_validate(item)
    CandidateReference.model_validate(raw["candidate_reference"])
