"""Plan 6 privacy-safe evaluation dataset contracts (public facade).

Committed material is limited to versioned schemas, annotation templates,
synthetic fixtures, and aggregate-safe manifests. Real CV/JD bodies, contact
PII, private labels, and secrets must never appear in these contracts.

Implementation is split across focused modules (all ≤300 lines):

- ``dataset_privacy`` — forbidden fields, digests, safe-token helpers
- ``dataset_models`` — row/envelope contracts and locked count constants
- this module — count validators, parsers, aggregate manifests, re-exports

Stable task-facing imports remain on ``evaluation.dataset_contracts``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from evaluation.dataset_models import (
    DEFAULT_SPLIT_SEED,
    EXTRACTION_MIN,
    PROTOCOL_ID,
    RELEVANCE_MAX,
    RELEVANCE_MIN,
    REQUIRED_TOOL_CATEGORIES,
    SCHEMA_VERSION,
    SPLIT_SCHEME,
    TOOL_SCENARIOS_MIN,
    AccessRole,
    AggregateDatasetManifest,
    CandidateReference,
    ExtractionAnnotationItem,
    ExtractionDataset,
    RelevanceDataset,
    RelevanceLabelItem,
    SplitName,
    ToolScenarioItem,
    ToolSelectionDataset,
)
from evaluation.dataset_privacy import (
    DIGEST_HEX_PATTERN,
    FORBIDDEN_FIELD_NAMES,
    MAX_DIGEST_HEX_LEN,
    MAX_NOTES_LEN,
    MAX_SAFE_ID_LEN,
    MAX_SKILL_LIST,
    MAX_TOKEN_LEN,
    SAFE_ID_PATTERN,
    DatasetContractError,
    assert_no_forbidden_fields,
    content_digest,
)

# Re-export protocol constants and types for public import stability.
__all__ = [
    "DEFAULT_SPLIT_SEED",
    "DIGEST_HEX_PATTERN",
    "EXTRACTION_MIN",
    "FORBIDDEN_FIELD_NAMES",
    "MAX_DIGEST_HEX_LEN",
    "MAX_NOTES_LEN",
    "MAX_SAFE_ID_LEN",
    "MAX_SKILL_LIST",
    "MAX_TOKEN_LEN",
    "PROTOCOL_ID",
    "RELEVANCE_MAX",
    "RELEVANCE_MIN",
    "REQUIRED_TOOL_CATEGORIES",
    "SAFE_ID_PATTERN",
    "SCHEMA_VERSION",
    "SPLIT_SCHEME",
    "TOOL_SCENARIOS_MIN",
    "AccessRole",
    "AggregateDatasetManifest",
    "CandidateReference",
    "DatasetContractError",
    "ExtractionAnnotationItem",
    "ExtractionDataset",
    "RelevanceDataset",
    "RelevanceLabelItem",
    "SplitName",
    "ToolScenarioItem",
    "ToolSelectionDataset",
    "assert_no_forbidden_fields",
    "build_aggregate_manifest",
    "content_digest",
    "dataset_items_digest",
    "load_json_mapping",
    "parse_candidate_reference",
    "parse_extraction_dataset",
    "parse_relevance_dataset",
    "parse_tool_selection_dataset",
    "validate_candidate_reference",
    "validate_extraction_counts",
    "validate_relevance_counts",
    "validate_tool_selection_counts",
]


def validate_relevance_counts(dataset: RelevanceDataset) -> None:
    count = len(dataset.items)
    if count < RELEVANCE_MIN or count > RELEVANCE_MAX:
        raise DatasetContractError(
            f"relevance dataset must contain {RELEVANCE_MIN}-{RELEVANCE_MAX} "
            f"items, got {count}"
        )
    labels = {item.relevance for item in dataset.items}
    if not labels.issubset({0, 1, 2, 3}):
        raise DatasetContractError("relevance labels must be in 0-3")


def validate_extraction_counts(dataset: ExtractionDataset) -> None:
    count = len(dataset.items)
    if count < EXTRACTION_MIN:
        raise DatasetContractError(
            f"extraction dataset must contain at least {EXTRACTION_MIN} items, "
            f"got {count}"
        )


def validate_tool_selection_counts(dataset: ToolSelectionDataset) -> None:
    count = len(dataset.items)
    if count < TOOL_SCENARIOS_MIN:
        raise DatasetContractError(
            f"tool-selection dataset must contain at least {TOOL_SCENARIOS_MIN} "
            f"items, got {count}"
        )
    present = {item.category for item in dataset.items}
    missing = REQUIRED_TOOL_CATEGORIES - present
    if missing:
        raise DatasetContractError(
            "tool-selection dataset missing required categories: "
            + ", ".join(sorted(missing))
        )


def validate_candidate_reference(candidate: CandidateReference) -> None:
    # Structural validation is enforced by the model; keep explicit hook for callers.
    if candidate.representation_version != "candidate_embedding_text_v1":
        # Allow alternate synthetic tags for fixtures only when clearly marked.
        if not candidate.representation_version.startswith("candidate_"):
            raise DatasetContractError(
                "candidate representation_version must identify a Candidate builder"
            )


def load_json_mapping(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DatasetContractError(f"{path} root must be a JSON object")
    assert_no_forbidden_fields(raw)
    return raw


def parse_relevance_dataset(payload: Mapping[str, Any]) -> RelevanceDataset:
    assert_no_forbidden_fields(payload)
    dataset = RelevanceDataset.model_validate(payload)
    validate_relevance_counts(dataset)
    return dataset


def parse_extraction_dataset(payload: Mapping[str, Any]) -> ExtractionDataset:
    assert_no_forbidden_fields(payload)
    dataset = ExtractionDataset.model_validate(payload)
    validate_extraction_counts(dataset)
    return dataset


def parse_tool_selection_dataset(payload: Mapping[str, Any]) -> ToolSelectionDataset:
    assert_no_forbidden_fields(payload)
    dataset = ToolSelectionDataset.model_validate(payload)
    validate_tool_selection_counts(dataset)
    return dataset


def parse_candidate_reference(payload: Mapping[str, Any]) -> CandidateReference:
    assert_no_forbidden_fields(payload)
    candidate = CandidateReference.model_validate(payload)
    validate_candidate_reference(candidate)
    return candidate


def build_aggregate_manifest(
    *,
    relevance: RelevanceDataset,
    extraction: ExtractionDataset,
    tools: ToolSelectionDataset,
    candidate: CandidateReference,
    notes: str = "",
) -> AggregateDatasetManifest:
    return AggregateDatasetManifest(
        split_seed=relevance.split_seed,
        relevance_count=len(relevance.items),
        extraction_count=len(extraction.items),
        tool_scenario_count=len(tools.items),
        relevance_digest=content_digest(
            [item.model_dump(mode="json") for item in relevance.items]
        ),
        extraction_digest=content_digest(
            [item.model_dump(mode="json") for item in extraction.items]
        ),
        tool_selection_digest=content_digest(
            [item.model_dump(mode="json") for item in tools.items]
        ),
        candidate_ref_digest=content_digest(candidate.model_dump(mode="json")),
        notes=notes,
    )


def dataset_items_digest(items: Sequence[BaseModel]) -> str:
    return content_digest([item.model_dump(mode="json") for item in items])
