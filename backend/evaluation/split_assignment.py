"""Deterministic entity-level 60/20/20 membership assignment.

Pure split math and partitioning only. Lock artifacts and access readers live
in companion modules so assignment rules are not duplicated.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evaluation.dataset_contracts import (
    DEFAULT_SPLIT_SEED,
    PROTOCOL_ID,
    RELEVANCE_MAX,
    RELEVANCE_MIN,
    SPLIT_SCHEME,
    DatasetContractError,
    RelevanceDataset,
    SplitName,
)

DEVELOPMENT_FRACTION: Final[float] = 0.6
VALIDATION_FRACTION: Final[float] = 0.2
HELD_OUT_FRACTION: Final[float] = 0.2


class SplitProtocolError(DatasetContractError):
    """Raised when split membership or access rules are violated."""


class SplitAssignment(BaseModel):
    """Entity → split membership for one sealed partition map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_scheme: Literal["fixed_seeded_60_20_20"] = SPLIT_SCHEME
    seed: int = Field(ge=0)
    membership: dict[str, SplitName]
    counts: dict[SplitName, int]

    @field_validator("membership")
    @classmethod
    def _non_empty(cls, value: dict[str, SplitName]) -> dict[str, SplitName]:
        if not value:
            raise ValueError("membership must not be empty")
        return value


def compute_split_sizes(n: int) -> tuple[int, int, int]:
    """Return (development, validation, held_out) sizes for n entities.

    Uses floor(0.6n) / floor(0.2n) / remainder so sizes always sum to n.
    Requires n >= 5 so every partition is non-empty under 60/20/20.
    """
    if n < 5:
        raise SplitProtocolError(
            f"entity count {n} is too small for a non-empty 60/20/20 split"
        )
    n_dev = int(n * DEVELOPMENT_FRACTION)
    n_val = int(n * VALIDATION_FRACTION)
    n_test = n - n_dev - n_val
    if n_dev < 1 or n_val < 1 or n_test < 1:
        raise SplitProtocolError(
            f"could not form non-empty 60/20/20 partitions for n={n}"
        )
    return n_dev, n_val, n_test


def assign_entity_splits(
    entity_ids: Sequence[str],
    *,
    seed: int = DEFAULT_SPLIT_SEED,
) -> SplitAssignment:
    """Deterministic entity-level 60/20/20 assignment."""
    unique = list(dict.fromkeys(entity_ids))
    if len(unique) != len(entity_ids):
        raise SplitProtocolError("entity_ids must be unique before split assignment")
    if not unique:
        raise SplitProtocolError("entity_ids must be non-empty")

    ordered = sorted(unique)
    rng = random.Random(seed)
    shuffled = list(ordered)
    rng.shuffle(shuffled)

    n_dev, n_val, n_test = compute_split_sizes(len(shuffled))
    membership: dict[str, SplitName] = {}
    for entity_id in shuffled[:n_dev]:
        membership[entity_id] = "development"
    for entity_id in shuffled[n_dev : n_dev + n_val]:
        membership[entity_id] = "validation"
    for entity_id in shuffled[n_dev + n_val :]:
        membership[entity_id] = "held_out_test"

    if len(membership) != len(shuffled):
        raise SplitProtocolError("split assignment lost entities")
    if sum(1 for _ in membership.values() if _ == "held_out_test") != n_test:
        raise SplitProtocolError("held-out size mismatch")

    counts: dict[SplitName, int] = {
        "development": n_dev,
        "validation": n_val,
        "held_out_test": n_test,
    }
    return SplitAssignment(seed=seed, membership=membership, counts=counts)


def assign_relevance_splits(dataset: RelevanceDataset) -> SplitAssignment:
    if len(dataset.items) < RELEVANCE_MIN or len(dataset.items) > RELEVANCE_MAX:
        raise SplitProtocolError(
            f"relevance count must be {RELEVANCE_MIN}-{RELEVANCE_MAX} before split"
        )
    return assign_entity_splits(
        [item.entity_id for item in dataset.items],
        seed=dataset.split_seed,
    )


def partition_by_assignment[T](
    items: Sequence[T],
    *,
    id_of: Callable[[T], str],
    assignment: SplitAssignment,
    require_full_coverage: bool = False,
) -> dict[SplitName, tuple[T, ...]]:
    """Group items by sealed membership; reject unknown or duplicate IDs."""
    buckets: dict[SplitName, list[T]] = {
        "development": [],
        "validation": [],
        "held_out_test": [],
    }
    seen: set[str] = set()
    for item in items:
        entity_id = str(id_of(item))
        if entity_id in seen:
            raise SplitProtocolError(f"duplicate entity_id in partition: {entity_id}")
        seen.add(entity_id)
        split = assignment.membership.get(entity_id)
        if split is None:
            raise SplitProtocolError(
                f"entity_id {entity_id!r} missing from sealed membership"
            )
        buckets[split].append(item)

    if require_full_coverage:
        missing = set(assignment.membership) - seen
        if missing:
            raise SplitProtocolError(
                f"partition missing {len(missing)} assigned entity ids"
            )

    return {name: tuple(values) for name, values in buckets.items()}


def assert_no_cross_split_leakage(
    partitions: Mapping[SplitName, Sequence[Any]],
    *,
    id_of: Callable[[Any], str],
) -> None:
    """Ensure entity IDs never appear in more than one split."""
    ownership: dict[str, SplitName] = {}
    for split_name, items in partitions.items():
        for item in items:
            entity_id = str(id_of(item))
            prior = ownership.get(entity_id)
            if prior is not None and prior != split_name:
                raise SplitProtocolError(
                    f"cross-split leakage for {entity_id!r}: {prior} and {split_name}"
                )
            ownership[entity_id] = split_name


def verify_assignment_reproducible(
    entity_ids: Sequence[str],
    *,
    seed: int,
    expected: SplitAssignment,
) -> None:
    recomputed = assign_entity_splits(entity_ids, seed=seed)
    if recomputed.membership != expected.membership:
        raise SplitProtocolError("split membership is not reproducible for seed")
    if recomputed.counts != expected.counts:
        raise SplitProtocolError("split counts are not reproducible for seed")


def validate_fraction_tolerance(
    counts: Mapping[str, int],
    *,
    total: int,
) -> None:
    """Confirm observed counts match floor-based 60/20/20 for ``total``."""
    expected = compute_split_sizes(total)
    got = (
        int(counts["development"]),
        int(counts["validation"]),
        int(counts["held_out_test"]),
    )
    if got != expected:
        raise SplitProtocolError(
            f"split counts {got} do not match sealed 60/20/20 for n={total}: {expected}"
        )


def iter_split_names() -> tuple[SplitName, ...]:
    return ("development", "validation", "held_out_test")
