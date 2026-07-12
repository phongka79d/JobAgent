"""Synthetic tests for sealed 60/20/20 split protocol and held-out guards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from evaluation.dataset_contracts import (
    EXTRACTION_MIN,
    PROTOCOL_ID,
    RELEVANCE_MIN,
    TOOL_SCENARIOS_MIN,
    content_digest,
    parse_relevance_dataset,
)
from evaluation.split_protocol import (
    HeldOutAccessError,
    MatchingConfigLock,
    SealedTestDatasetReader,
    SplitAccessMode,
    SplitProtocolError,
    TuningDatasetReader,
    assert_no_cross_split_leakage,
    assert_sealed_test_excludes_tuning_slices,
    assert_tuning_excludes_held_out,
    assign_entity_splits,
    assign_relevance_splits,
    build_lock_artifact,
    compute_split_sizes,
    load_relevance_for_sealed_test,
    load_relevance_for_tuning,
    membership_digest,
    refuse_held_out_without_lock,
    require_lock_for_held_out,
    validate_fraction_tolerance,
    verify_assignment_reproducible,
    write_lock_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPO_ROOT / "backend" / "evaluation"
PROTOCOL_PATH = EVAL_ROOT / "labels" / "matching_protocol.json"


def _make_relevance_payload(n: int = RELEVANCE_MIN, seed: int = 20260711) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "split_seed": seed,
        "items": [
            {
                "entity_id": f"syn_jd_{index:04d}",
                "relevance": index % 4,
                "label_provenance": "synthetic",
            }
            for index in range(n)
        ],
    }


def test_compute_split_sizes_sum_and_nonempty() -> None:
    for n in (5, 10, 150, 160, 200):
        dev, val, held = compute_split_sizes(n)
        assert dev + val + held == n
        assert dev >= 1 and val >= 1 and held >= 1
        assert dev == int(n * 0.6)
        assert val == int(n * 0.2)


def test_assign_entity_splits_reproducible() -> None:
    ids = [f"e{i:03d}" for i in range(150)]
    first = assign_entity_splits(ids, seed=20260711)
    second = assign_entity_splits(ids, seed=20260711)
    assert first.membership == second.membership
    assert first.counts == second.counts
    verify_assignment_reproducible(ids, seed=20260711, expected=first)
    validate_fraction_tolerance(first.counts, total=150)

    third = assign_entity_splits(ids, seed=99)
    assert third.membership != first.membership


def test_assign_rejects_duplicates() -> None:
    with pytest.raises(SplitProtocolError, match="unique"):
        assign_entity_splits(["a", "a", "b", "c", "d", "e"], seed=1)


def test_relevance_split_deterministic_60_20_20() -> None:
    dataset = parse_relevance_dataset(_make_relevance_payload(160))
    assignment = assign_relevance_splits(dataset)
    assert assignment.counts["development"] == 96
    assert assignment.counts["validation"] == 32
    assert assignment.counts["held_out_test"] == 32
    assert len(assignment.membership) == 160
    # Stable digest for lock material.
    assert len(membership_digest(assignment)) == 64


def test_tuning_reader_never_returns_held_out() -> None:
    payload = _make_relevance_payload(150)
    load, assignment = load_relevance_for_tuning(payload)
    assert_tuning_excludes_held_out(load)
    assert load.held_out_test == ()
    assert len(load.development) == assignment.counts["development"]
    assert len(load.validation) == assignment.counts["validation"]
    held_ids = {
        entity_id
        for entity_id, split in assignment.membership.items()
        if split == "held_out_test"
    }
    returned_ids = {item.entity_id for item in load.development + load.validation}
    assert returned_ids.isdisjoint(held_ids)

    # Direct reader path.
    reader = TuningDatasetReader(assignment)
    dataset = parse_relevance_dataset(payload)
    again = reader.load_relevance(dataset)
    assert again.held_out_test == ()
    assert {i.entity_id for i in again.development} == {
        i.entity_id for i in load.development
    }


def test_sealed_test_requires_lock(tmp_path: Path) -> None:
    payload = _make_relevance_payload(150)
    lock_path = tmp_path / "matching_config.json"
    with pytest.raises(HeldOutAccessError, match="lock artifact missing"):
        load_relevance_for_sealed_test(payload, lock_path=lock_path)

    refuse_held_out_without_lock(mode=SplitAccessMode.TUNING, lock_path=None)
    with pytest.raises(HeldOutAccessError):
        refuse_held_out_without_lock(
            mode=SplitAccessMode.SEALED_TEST,
            lock_path=lock_path,
        )


def test_sealed_test_returns_held_out_only_after_lock(tmp_path: Path) -> None:
    payload = _make_relevance_payload(150)
    dataset = parse_relevance_dataset(payload)
    data_digest = content_digest(
        [item.model_dump(mode="json") for item in dataset.items]
    )
    lock = build_lock_artifact(
        split_seed=dataset.split_seed,
        data_digest=data_digest,
        config_digest=content_digest({"weights": "seed"}),
    )
    lock_path = tmp_path / "matching_config.json"
    write_lock_artifact(lock_path, lock)

    load, assignment, loaded_lock = load_relevance_for_sealed_test(
        payload,
        lock_path=lock_path,
        expected_data_digest=data_digest,
    )
    assert isinstance(loaded_lock, MatchingConfigLock)
    assert_sealed_test_excludes_tuning_slices(load)
    assert load.development == ()
    assert load.validation == ()
    assert len(load.held_out_test) == assignment.counts["held_out_test"]

    held_ids = {item.entity_id for item in load.held_out_test}
    for entity_id in held_ids:
        assert assignment.membership[entity_id] == "held_out_test"


def test_lock_digest_mismatch_denied(tmp_path: Path) -> None:
    payload = _make_relevance_payload(150)
    dataset = parse_relevance_dataset(payload)
    lock = build_lock_artifact(
        split_seed=dataset.split_seed,
        data_digest="f" * 64,
        config_digest="e" * 64,
    )
    lock_path = tmp_path / "matching_config.json"
    write_lock_artifact(lock_path, lock)
    with pytest.raises(HeldOutAccessError, match="data_digest"):
        load_relevance_for_sealed_test(
            payload,
            lock_path=lock_path,
            expected_data_digest="0" * 64,
        )


def test_completed_lock_blocks_reentry(tmp_path: Path) -> None:
    lock = build_lock_artifact(
        split_seed=20260711,
        data_digest="a" * 64,
        config_digest="b" * 64,
        sealed_test_completed=True,
    )
    lock_path = tmp_path / "matching_config.json"
    write_lock_artifact(lock_path, lock)
    with pytest.raises(HeldOutAccessError, match="already completed"):
        require_lock_for_held_out(lock_path)


def test_cross_split_leakage_detected() -> None:
    from evaluation.dataset_contracts import RelevanceLabelItem

    item = RelevanceLabelItem(
        entity_id="dup_1",
        relevance=1,
        label_provenance="synthetic",
    )
    partitions = {
        "development": (item,),
        "validation": (item,),
        "held_out_test": (),
    }
    with pytest.raises(SplitProtocolError, match="cross-split leakage"):
        assert_no_cross_split_leakage(
            partitions,
            id_of=lambda row: row.entity_id,
        )


def test_tuning_extraction_and_tools_drop_held_out() -> None:
    payload = _make_relevance_payload(150)
    dataset = parse_relevance_dataset(payload)
    assignment = assign_relevance_splits(dataset)
    reader = TuningDatasetReader(assignment)

    extraction_items = [
        {
            "entity_id": f"syn_jd_{index:04d}",
            "required_skills": ["python"],
            "preferred_skills": [],
            "seniority": "mid",
            "work_mode": "remote",
            "location": "berlin",
            "label_provenance": "synthetic",
        }
        for index in range(EXTRACTION_MIN)
    ]
    from evaluation.dataset_contracts import (
        REQUIRED_TOOL_CATEGORIES,
        ExtractionDataset,
        ToolSelectionDataset,
    )

    extraction = ExtractionDataset.model_validate(
        {
            "schema_version": 1,
            "protocol_id": PROTOCOL_ID,
            "split_seed": 20260711,
            "items": extraction_items,
        }
    )
    parts = reader.load_extraction(extraction)
    assert parts["held_out_test"] == ()
    returned = {item.entity_id for item in parts["development"] + parts["validation"]}
    held = {
        eid
        for eid, split in assignment.membership.items()
        if split == "held_out_test"
    }
    assert returned.isdisjoint(held)

    categories = sorted(REQUIRED_TOOL_CATEGORIES)
    tool_items = []
    for index in range(TOOL_SCENARIOS_MIN):
        tool_items.append(
            {
                "scenario_id": f"syn_tool_{index:04d}",
                "category": categories[index % len(categories)],
                "expected_tools": [],
                "expected_outcome": "ok",
                "prompt_digest": content_digest(f"tool-{index}"),
                "label_provenance": "synthetic",
            }
        )
    tools = ToolSelectionDataset.model_validate(
        {
            "schema_version": 1,
            "protocol_id": PROTOCOL_ID,
            "split_seed": 20260711,
            "items": tool_items,
        }
    )
    tool_parts = reader.load_tool_scenarios(tools)
    assert tool_parts["held_out_test"] == ()
    returned_tools = tool_parts["development"] + tool_parts["validation"]
    # Independent seeded assignment places ~20% of scenarios in held-out; those
    # must not appear in tuning partitions.
    assert 0 < len(returned_tools) < len(tool_items)
    assert len(returned_tools) == int(len(tool_items) * 0.6) + int(
        len(tool_items) * 0.2
    )
    assert all(
        item.scenario_id.startswith("syn_tool_") for item in returned_tools
    )


def test_sealed_reader_class_requires_lock(tmp_path: Path) -> None:
    payload = _make_relevance_payload(150)
    dataset = parse_relevance_dataset(payload)
    assignment = assign_relevance_splits(dataset)
    with pytest.raises(HeldOutAccessError):
        SealedTestDatasetReader(assignment, lock_path=tmp_path / "missing.json")


def test_protocol_documents_held_out_policy() -> None:
    raw = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    policy = raw["access_policy"]
    assert policy["held_out_reader"] == "sealed_test_only"
    assert policy["tuning_may_not_read_held_out_labels_or_results"] is True
    assert "matching_config_lock_v1" in policy["held_out_requires"]


def test_private_probe_paths_are_gitignored() -> None:
    # Evidence-only: git check-ignore is also a required shell validation.
    probes = [
        "backend/evaluation/private/probe.json",
        "backend/evaluation/labels/local-private/probe.json",
        "backend/evaluation/fixtures/local-private/probe.json",
    ]
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", *probes],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    ignored = {line.strip().replace("\\", "/") for line in result.stdout.splitlines()}
    for probe in probes:
        assert probe in ignored or probe.replace("backend/", "") in ignored or any(
            probe.endswith(line) or line.endswith(probe) for line in ignored
        )
