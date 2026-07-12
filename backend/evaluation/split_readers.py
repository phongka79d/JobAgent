"""Access-controlled dataset readers for tuning vs sealed held-out evaluation.

``TuningDatasetReader`` never returns held-out labels. ``SealedTestDatasetReader``
requires a valid lock artifact and returns held-out only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.dataset_contracts import (
    AccessRole,
    ExtractionAnnotationItem,
    ExtractionDataset,
    RelevanceDataset,
    RelevanceLabelItem,
    SplitName,
    ToolScenarioItem,
    ToolSelectionDataset,
    content_digest,
    parse_relevance_dataset,
)
from evaluation.split_assignment import (
    SplitAssignment,
    SplitProtocolError,
    assign_entity_splits,
    assign_relevance_splits,
)
from evaluation.split_lock import (
    HeldOutAccessError,
    MatchingConfigLock,
    require_lock_for_held_out,
)


@dataclass(frozen=True, slots=True)
class SealedRelevanceLoad:
    """Relevance rows returned by an access-controlled loader."""

    role: AccessRole
    development: tuple[RelevanceLabelItem, ...]
    validation: tuple[RelevanceLabelItem, ...]
    held_out_test: tuple[RelevanceLabelItem, ...]


def _filter_relevance(
    items: Sequence[RelevanceLabelItem],
    membership: Mapping[str, SplitName],
    allowed: frozenset[SplitName],
) -> tuple[RelevanceLabelItem, ...]:
    out: list[RelevanceLabelItem] = []
    for item in items:
        split = membership.get(item.entity_id)
        if split is None:
            raise SplitProtocolError(
                f"relevance entity {item.entity_id!r} has no split membership"
            )
        if split in allowed:
            out.append(item)
    return tuple(out)


class TuningDatasetReader:
    """Development + validation only. Never returns held-out labels."""

    role: AccessRole = "tuning"
    allowed_splits: frozenset[SplitName] = frozenset({"development", "validation"})

    def __init__(self, assignment: SplitAssignment) -> None:
        self._assignment = assignment

    @property
    def assignment(self) -> SplitAssignment:
        return self._assignment

    def load_relevance(
        self,
        dataset: RelevanceDataset,
    ) -> SealedRelevanceLoad:
        development = _filter_relevance(
            dataset.items,
            self._assignment.membership,
            frozenset({"development"}),
        )
        validation = _filter_relevance(
            dataset.items,
            self._assignment.membership,
            frozenset({"validation"}),
        )
        # Explicit empty held-out — callers must not see labels even if present.
        return SealedRelevanceLoad(
            role="tuning",
            development=development,
            validation=validation,
            held_out_test=(),
        )

    def load_extraction(
        self,
        dataset: ExtractionDataset,
    ) -> dict[SplitName, tuple[ExtractionAnnotationItem, ...]]:
        return self._partition_tuning_subset(
            dataset.items,
            id_of=lambda item: item.entity_id,
            seed=dataset.split_seed,
        )

    def load_tool_scenarios(
        self,
        dataset: ToolSelectionDataset,
    ) -> dict[SplitName, tuple[ToolScenarioItem, ...]]:
        return self._partition_tuning_subset(
            dataset.items,
            id_of=lambda item: item.scenario_id,
            seed=dataset.split_seed,
        )

    def _partition_tuning_subset[T](
        self,
        items: Sequence[T],
        *,
        id_of: Callable[[T], str],
        seed: int,
    ) -> dict[SplitName, tuple[T, ...]]:
        """Partition a subset using relevance membership when present.

        IDs absent from the relevance map receive an independent seeded
        assignment; held-out members are always dropped for tuning.
        """
        known_ids = [
            str(id_of(item))
            for item in items
            if str(id_of(item)) in self._assignment.membership
        ]
        unknown_ids = [
            str(id_of(item))
            for item in items
            if str(id_of(item)) not in self._assignment.membership
        ]
        membership: dict[str, SplitName] = {
            entity_id: self._assignment.membership[entity_id] for entity_id in known_ids
        }
        if unknown_ids:
            extra = assign_entity_splits(unknown_ids, seed=seed)
            membership.update(extra.membership)

        buckets: dict[SplitName, list[T]] = {
            "development": [],
            "validation": [],
            "held_out_test": [],
        }
        for item in items:
            entity_id = str(id_of(item))
            split = membership[entity_id]
            if split == "held_out_test":
                continue
            buckets[split].append(item)
        return {
            "development": tuple(buckets["development"]),
            "validation": tuple(buckets["validation"]),
            "held_out_test": (),
        }


class SealedTestDatasetReader:
    """Held-out access only after a valid lock artifact is present."""

    role: AccessRole = "sealed_test"
    allowed_splits: frozenset[SplitName] = frozenset({"held_out_test"})

    def __init__(
        self,
        assignment: SplitAssignment,
        *,
        lock_path: Path,
        expected_data_digest: str | None = None,
    ) -> None:
        self._assignment = assignment
        self._lock = require_lock_for_held_out(
            lock_path,
            expected_data_digest=expected_data_digest,
            expected_split_seed=assignment.seed,
        )

    @property
    def assignment(self) -> SplitAssignment:
        return self._assignment

    @property
    def lock(self) -> MatchingConfigLock:
        return self._lock

    def load_relevance(
        self,
        dataset: RelevanceDataset,
    ) -> SealedRelevanceLoad:
        held = _filter_relevance(
            dataset.items,
            self._assignment.membership,
            frozenset({"held_out_test"}),
        )
        return SealedRelevanceLoad(
            role="sealed_test",
            development=(),
            validation=(),
            held_out_test=held,
        )


def load_relevance_for_tuning(
    payload: Mapping[str, Any],
    *,
    seed: int | None = None,
) -> tuple[SealedRelevanceLoad, SplitAssignment]:
    """Parse relevance dataset and return development/validation only."""
    dataset = parse_relevance_dataset(payload)
    if seed is not None and seed != dataset.split_seed:
        raise SplitProtocolError("split seed mismatch vs dataset")
    assignment = assign_relevance_splits(dataset)
    reader = TuningDatasetReader(assignment)
    return reader.load_relevance(dataset), assignment


def load_relevance_for_sealed_test(
    payload: Mapping[str, Any],
    *,
    lock_path: Path,
    expected_data_digest: str | None = None,
) -> tuple[SealedRelevanceLoad, SplitAssignment, MatchingConfigLock]:
    """Parse relevance dataset and return held-out only when lock is valid."""
    dataset = parse_relevance_dataset(payload)
    assignment = assign_relevance_splits(dataset)
    data_digest = expected_data_digest or content_digest(
        [item.model_dump(mode="json") for item in dataset.items]
    )
    reader = SealedTestDatasetReader(
        assignment,
        lock_path=lock_path,
        expected_data_digest=data_digest,
    )
    return reader.load_relevance(dataset), assignment, reader.lock


def assert_tuning_excludes_held_out(load: SealedRelevanceLoad) -> None:
    if load.role != "tuning":
        raise SplitProtocolError("expected tuning load role")
    if load.held_out_test:
        raise HeldOutAccessError("tuning reader must not return held-out labels")


def assert_sealed_test_excludes_tuning_slices(load: SealedRelevanceLoad) -> None:
    if load.role != "sealed_test":
        raise SplitProtocolError("expected sealed_test load role")
    if load.development or load.validation:
        raise SplitProtocolError(
            "sealed-test reader must not return development/validation labels"
        )
