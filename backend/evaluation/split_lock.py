"""Lock artifact gate for sealed held-out evaluation access.

Tuning must write a validated ``matching_config_lock_v1`` before any held-out
read. Completed locks deny re-entry unless explicitly allowed.
"""

from __future__ import annotations

import json
import math
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from evaluation.dataset_contracts import DIGEST_HEX_PATTERN, PROTOCOL_ID, SPLIT_SCHEME
from evaluation.split_assignment import SplitProtocolError

LOCK_SCHEMA_VERSION: Final[int] = 1
LOCK_FILENAME_HINT: Final[str] = "matching_config.json"


class HeldOutAccessError(SplitProtocolError):
    """Raised when tuning code attempts held-out access without a seal lock."""


class SplitAccessMode(StrEnum):
    """Which partitions a reader may return."""

    TUNING = "tuning"
    SEALED_TEST = "sealed_test"


class MatchingConfigLock(BaseModel):
    """Lock artifact written after validation-only tuning (before held-out).

    Weight fields are optional for gate-only locks (05A tests) and required for
    ranking sealed-test evaluation (05C). ``related_skill_boosts_enabled`` is
    None until sealed-test applies the graph ablation decision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    lock_kind: Literal["matching_config_lock_v1"] = "matching_config_lock_v1"
    protocol_id: Literal["plan6_matching_evaluation_v1"] = PROTOCOL_ID
    split_scheme: Literal["fixed_seeded_60_20_20"] = SPLIT_SCHEME
    split_seed: int = Field(ge=0)
    data_digest: str = Field(min_length=64, max_length=64)
    config_digest: str = Field(min_length=64, max_length=64)
    held_out_access: Literal["authorized_once_after_lock"] = (
        "authorized_once_after_lock"
    )
    sealed_test_completed: bool = False
    weight_config_version: str = "hybrid_seed_v1"
    weights: dict[str, float] = Field(default_factory=dict)
    related_skill_boosts_enabled: bool | None = None
    validation_ndcg_at_10: float | None = None

    @field_validator("data_digest", "config_digest")
    @classmethod
    def _hex_digest(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not DIGEST_HEX_PATTERN.fullmatch(cleaned):
            raise ValueError("digest must be a 64-char lowercase hex SHA-256")
        return cleaned

    @field_validator("weights")
    @classmethod
    def _finite_weights(cls, value: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for key, raw in value.items():
            name = str(key)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"non-numeric weight for {name}")
            number = float(raw)
            if not math.isfinite(number) or number < 0.0:
                raise ValueError(f"invalid weight for {name}")
            cleaned[name] = number
        return cleaned


def load_lock_artifact(path: Path) -> MatchingConfigLock:
    if not path.is_file():
        raise HeldOutAccessError(f"lock artifact missing: {path.name}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeldOutAccessError("lock artifact unreadable or invalid JSON") from exc
    if not isinstance(raw, dict):
        raise HeldOutAccessError("lock artifact root must be an object")
    try:
        lock = MatchingConfigLock.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        raise HeldOutAccessError("lock artifact failed schema validation") from exc
    return lock


def write_lock_artifact(path: Path, lock: MatchingConfigLock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        lock.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def build_lock_artifact(
    *,
    split_seed: int,
    data_digest: str,
    config_digest: str,
    sealed_test_completed: bool = False,
    weight_config_version: str = "hybrid_seed_v1",
    weights: dict[str, float] | None = None,
    related_skill_boosts_enabled: bool | None = None,
    validation_ndcg_at_10: float | None = None,
) -> MatchingConfigLock:
    return MatchingConfigLock(
        split_seed=split_seed,
        data_digest=data_digest.lower(),
        config_digest=config_digest.lower(),
        sealed_test_completed=sealed_test_completed,
        weight_config_version=weight_config_version,
        weights=dict(weights or {}),
        related_skill_boosts_enabled=related_skill_boosts_enabled,
        validation_ndcg_at_10=validation_ndcg_at_10,
    )


def require_lock_for_held_out(
    lock_path: Path,
    *,
    expected_data_digest: str | None = None,
    expected_split_seed: int | None = None,
    allow_completed: bool = False,
) -> MatchingConfigLock:
    """Gate held-out access behind an existing unconsumed lock artifact."""
    lock = load_lock_artifact(lock_path)
    if lock.protocol_id != PROTOCOL_ID:
        raise HeldOutAccessError("lock protocol_id mismatch")
    if lock.sealed_test_completed and not allow_completed:
        raise HeldOutAccessError(
            "sealed-test already completed for this lock; held-out re-entry denied"
        )
    if (
        expected_data_digest is not None
        and lock.data_digest != expected_data_digest.lower()
    ):
        raise HeldOutAccessError("lock data_digest mismatch")
    if expected_split_seed is not None and lock.split_seed != expected_split_seed:
        raise HeldOutAccessError("lock split_seed mismatch")
    return lock


def refuse_held_out_without_lock(
    *,
    mode: SplitAccessMode,
    lock_path: Path | None,
) -> None:
    """Hard guard used by future runners before any held-out read."""
    if mode is SplitAccessMode.TUNING:
        return
    if mode is SplitAccessMode.SEALED_TEST:
        if lock_path is None:
            raise HeldOutAccessError("sealed-test requires an explicit lock path")
        require_lock_for_held_out(lock_path)
        return
    raise SplitProtocolError(f"unknown access mode: {mode}")
