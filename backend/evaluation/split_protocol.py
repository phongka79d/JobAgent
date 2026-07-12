"""Deterministic sealed 60/20/20 split protocol (public facade).

Entity-level assignment is seeded and reproducible. Tuning readers may load
development and validation only. Held-out labels and results are available only
through the explicit sealed-test path after a lock artifact exists.

Implementation is split across focused modules (all ≤300 lines):

- ``split_assignment`` — membership math, partition, leakage checks
- ``split_lock`` — lock artifact load/write and held-out access gate
- ``split_readers`` — tuning vs sealed-test dataset readers
- this module — public re-exports and aggregate-safe constants

Stable task-facing imports remain on ``evaluation.split_protocol``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.dataset_contracts import (
    DEFAULT_SPLIT_SEED,
    PROTOCOL_ID,
    RELEVANCE_MAX,
    RELEVANCE_MIN,
    SCHEMA_VERSION,
    SPLIT_SCHEME,
    content_digest,
    parse_extraction_dataset,
    parse_relevance_dataset,
    parse_tool_selection_dataset,
)
from evaluation.split_assignment import (
    DEVELOPMENT_FRACTION,
    HELD_OUT_FRACTION,
    VALIDATION_FRACTION,
    SplitAssignment,
    SplitProtocolError,
    assert_no_cross_split_leakage,
    assign_entity_splits,
    assign_relevance_splits,
    compute_split_sizes,
    iter_split_names,
    partition_by_assignment,
    validate_fraction_tolerance,
    verify_assignment_reproducible,
)
from evaluation.split_lock import (
    LOCK_FILENAME_HINT,
    LOCK_SCHEMA_VERSION,
    HeldOutAccessError,
    MatchingConfigLock,
    SplitAccessMode,
    build_lock_artifact,
    load_lock_artifact,
    refuse_held_out_without_lock,
    require_lock_for_held_out,
    write_lock_artifact,
)
from evaluation.split_readers import (
    SealedRelevanceLoad,
    SealedTestDatasetReader,
    TuningDatasetReader,
    assert_sealed_test_excludes_tuning_slices,
    assert_tuning_excludes_held_out,
    load_relevance_for_sealed_test,
    load_relevance_for_tuning,
)


def membership_digest(assignment: SplitAssignment) -> str:
    return content_digest(
        {
            "seed": assignment.seed,
            "membership": assignment.membership,
            "counts": assignment.counts,
        }
    )


def export_public_constants() -> dict[str, Any]:
    """Aggregate-safe protocol constants for manifests and reports."""
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "split_scheme": SPLIT_SCHEME,
        "default_split_seed": DEFAULT_SPLIT_SEED,
        "development_fraction": DEVELOPMENT_FRACTION,
        "validation_fraction": VALIDATION_FRACTION,
        "held_out_fraction": HELD_OUT_FRACTION,
        "relevance_min": RELEVANCE_MIN,
        "relevance_max": RELEVANCE_MAX,
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "lock_filename_hint": LOCK_FILENAME_HINT,
        "held_out_access_policy": "lock_required_sealed_test_only",
    }


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SplitProtocolError(f"{path} root must be a JSON object")
    return raw


# Convenience re-exports for runner modules (05B/05C) without deep imports.
__all__ = [
    "DEVELOPMENT_FRACTION",
    "HELD_OUT_FRACTION",
    "VALIDATION_FRACTION",
    "HeldOutAccessError",
    "MatchingConfigLock",
    "SealedRelevanceLoad",
    "SealedTestDatasetReader",
    "SplitAccessMode",
    "SplitAssignment",
    "SplitProtocolError",
    "TuningDatasetReader",
    "assign_entity_splits",
    "assign_relevance_splits",
    "assert_no_cross_split_leakage",
    "assert_sealed_test_excludes_tuning_slices",
    "assert_tuning_excludes_held_out",
    "build_lock_artifact",
    "compute_split_sizes",
    "export_public_constants",
    "iter_split_names",
    "load_json_object",
    "load_lock_artifact",
    "load_relevance_for_sealed_test",
    "load_relevance_for_tuning",
    "membership_digest",
    "parse_extraction_dataset",
    "parse_relevance_dataset",
    "parse_tool_selection_dataset",
    "partition_by_assignment",
    "refuse_held_out_without_lock",
    "require_lock_for_held_out",
    "validate_fraction_tolerance",
    "verify_assignment_reproducible",
    "write_lock_artifact",
]
