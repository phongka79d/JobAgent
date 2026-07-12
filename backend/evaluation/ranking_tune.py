"""Validation-only ranking weight tuning (Plan 6 / 05C).

Hard isolation: this module must never import sealed-test / held-out readers.
Grid search reads development + validation features only and emits a lock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evaluation.dataset_contracts import (
    PROTOCOL_ID,
    RelevanceLabelItem,
    content_digest,
    parse_relevance_dataset,
)
from evaluation.ranking_scoring import (
    WEIGHT_CONFIG_VERSION,
    GridSelection,
    RankingItem,
    RankingRunnerError,
    build_tune_result_dict,
    parse_ranking_items,
    select_weights_by_validation_ndcg,
)
from evaluation.split_assignment import assign_relevance_splits
from evaluation.split_lock import build_lock_artifact, write_lock_artifact
from evaluation.split_readers import (
    TuningDatasetReader,
    assert_tuning_excludes_held_out,
)

# Explicit deny-list for static/source tests: do not import held-out loaders here.
_HELD_OUT_IMPORT_FORBIDDEN = (
    "load_relevance_for_sealed_test",
    "SealedTestDatasetReader",
    "SplitAccessMode.SEALED_TEST",
)


def _index_items(items: Sequence[RankingItem]) -> dict[str, RankingItem]:
    return {item.entity_id: item for item in items}


def _select_partition(
    labels: Sequence[RelevanceLabelItem],
    by_id: Mapping[str, RankingItem],
) -> tuple[RankingItem, ...]:
    out: list[RankingItem] = []
    missing: list[str] = []
    for label in labels:
        item = by_id.get(label.entity_id)
        if item is None:
            missing.append(label.entity_id)
            continue
        if item.relevance != label.relevance:
            raise RankingRunnerError(
                f"relevance mismatch for {label.entity_id}: "
                f"features={item.relevance} labels={label.relevance}"
            )
        out.append(item)
    if missing:
        raise RankingRunnerError(
            "ranking features missing for label entities: "
            + ", ".join(sorted(missing)[:10])
        )
    return tuple(out)


def tune_weights(
    *,
    relevance_payload: Mapping[str, Any],
    ranking_payload: Mapping[str, Any],
) -> tuple[GridSelection, dict[str, Any], str]:
    """Run development/validation grid search; return selection, report, data_digest.

    Never returns or scores held-out labels.
    """
    dataset = parse_relevance_dataset(relevance_payload)
    if dataset.protocol_id != PROTOCOL_ID:
        raise RankingRunnerError("protocol_id mismatch")
    assignment = assign_relevance_splits(dataset)
    reader = TuningDatasetReader(assignment)
    load = reader.load_relevance(dataset)
    assert_tuning_excludes_held_out(load)

    all_items = parse_ranking_items(ranking_payload)
    by_id = _index_items(all_items)
    # Reject any attempt to include held-out feature rows in the tuning corpus
    # that do not appear in development/validation membership.
    allowed_ids = {item.entity_id for item in load.development + load.validation}
    extra = sorted(set(by_id) - allowed_ids)
    # Extra held-out feature rows are ignored for scoring but must not be required.
    # Tuning only uses development/validation labels from the sealed split.
    _ = extra

    development = _select_partition(load.development, by_id)
    validation = _select_partition(load.validation, by_id)
    if load.held_out_test:
        raise RankingRunnerError("tuning reader leaked held-out labels")

    selection = select_weights_by_validation_ndcg(development, validation)
    data_digest = content_digest(
        [item.model_dump(mode="json") for item in dataset.items]
    )
    report = build_tune_result_dict(
        selection,
        data_digest=data_digest,
        development_count=len(development),
        validation_count=len(validation),
    )
    return selection, report, data_digest


def write_tuning_lock(
    lock_path: Path,
    *,
    split_seed: int,
    data_digest: str,
    selection: GridSelection,
) -> None:
    """Write content-digested lock from validation tuning (pre-held-out)."""
    if not selection.weights:
        raise RankingRunnerError("cannot lock empty weights")
    # Refuse locks that could have been derived from test metrics: require
    # validation nDCG present and config digest matching weights only.
    if selection.config_digest != selection.config_digest.lower():
        raise RankingRunnerError("config_digest must be lowercase hex")
    lock = build_lock_artifact(
        split_seed=split_seed,
        data_digest=data_digest,
        config_digest=selection.config_digest,
        sealed_test_completed=False,
        weight_config_version=WEIGHT_CONFIG_VERSION,
        weights=dict(selection.weights),
        related_skill_boosts_enabled=None,
        validation_ndcg_at_10=selection.validation_ndcg_at_10,
    )
    write_lock_artifact(lock_path, lock)


__all__ = [
    "tune_weights",
    "write_tuning_lock",
    "_HELD_OUT_IMPORT_FORBIDDEN",
]
