"""Embedding vector validation contracts (Plan 5 §7.5 / Master §17.1).

Owns ordered finite-vector validation for ShopAIKey embedding responses and the
sole locked model/dimension guard. Exactly 1536 finite floats per input,
response count/index order, and stable malformed/dimension/ordering codes.
No HTTP/provider transport lives here.

The Phase 0 diagnostic consumes these validators/guard rather than re-implementing
the contract.
"""

from __future__ import annotations

import math
from typing import Any, Final

# Locked embedding wire contract (Master §17.1).
LOCKED_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
LOCKED_EMBEDDING_DIMENSIONS: Final[int] = 1536
LOCKED_ENCODING_FORMAT: Final[str] = "float"

# Stable validation codes (aligned with Phase 0 diagnostic codes).
CODE_MALFORMED: Final[str] = "MALFORMED_RESPONSE"
CODE_DIMENSION: Final[str] = "DIMENSION_MISMATCH"
CODE_ORDERING: Final[str] = "ORDERING_MISMATCH"
CODE_MODEL: Final[str] = "MODEL_MISMATCH"


class EmbeddingVectorError(Exception):
    """Embedding response or configuration failed locked-contract validation."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def require_locked_embedding_contract(*, model: str, dimensions: int) -> None:
    """Reject any model/dimension other than the locked production contract.

    Single authoritative guard for adapter construction, request emission, and
    diagnostic config checks. Call before building or invoking a client.
    """
    if model != LOCKED_EMBEDDING_MODEL:
        raise EmbeddingVectorError(
            CODE_MODEL,
            f"model={model!r} expected={LOCKED_EMBEDDING_MODEL!r}",
        )
    if int(dimensions) != LOCKED_EMBEDDING_DIMENSIONS:
        raise EmbeddingVectorError(
            CODE_DIMENSION,
            f"dimensions={dimensions} expected={LOCKED_EMBEDDING_DIMENSIONS}",
        )


def validate_finite_vector(vec: Any) -> list[float]:
    """Validate one embedding vector: exactly 1536 finite floats (no override)."""
    if not isinstance(vec, list):
        raise EmbeddingVectorError(CODE_MALFORMED, "embedding_not_list")
    if len(vec) != LOCKED_EMBEDDING_DIMENSIONS:
        raise EmbeddingVectorError(
            CODE_DIMENSION,
            f"len={len(vec)} expected={LOCKED_EMBEDDING_DIMENSIONS}",
        )
    floats: list[float] = []
    for value in vec:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise EmbeddingVectorError(CODE_MALFORMED, "non_float") from exc
        if not math.isfinite(number):
            raise EmbeddingVectorError(CODE_DIMENSION, "non_finite")
        floats.append(number)
    return floats


def validate_embedding_item(item: Any, expected_index: int) -> list[float]:
    """Validate one embedding data item at its list position (no reordering)."""
    if not isinstance(item, dict):
        raise EmbeddingVectorError(CODE_MALFORMED, "embedding_item_type")
    if "index" not in item:
        raise EmbeddingVectorError(
            CODE_ORDERING,
            f"missing_index expected_index={expected_index}",
        )
    idx = item["index"]
    if idx != expected_index:
        raise EmbeddingVectorError(
            CODE_ORDERING,
            f"expected_index={expected_index} got={idx}",
        )
    return validate_finite_vector(item.get("embedding"))


def validate_embedding_data_list(
    data: Any,
    *,
    expected_count: int,
) -> list[list[float]]:
    """Validate provider ``data`` list in returned order against expected indices.

    Does not sort or reorder. Count must match ``expected_count``; each item's
    ``index`` must equal its position in the returned list. Vector length is
    always the locked 1536 (no dimension override).
    """
    if not isinstance(data, list):
        raise EmbeddingVectorError(CODE_MALFORMED, "embedding_data_type")
    if len(data) != expected_count:
        raise EmbeddingVectorError(
            CODE_ORDERING,
            f"count={len(data)} expected={expected_count}",
        )
    vectors: list[list[float]] = []
    for expected_index, item in enumerate(data):
        vectors.append(validate_embedding_item(item, expected_index))
    return vectors
