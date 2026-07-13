"""Scalar and batch embedding capability with list-order index assertions."""

from __future__ import annotations

import math
from typing import Any

import httpx

from shopaikey_diag.common import (
    CODE_DIMENSION,
    CODE_MALFORMED,
    CODE_MODEL_ABSENCE,
    CODE_ORDERING,
    LOCKED_DIMENSIONS,
    LOCKED_EMBED_MODEL,
    DiagnosticError,
    Settings,
    request_json,
)


def validate_embedding_item(
    item: Any,
    expected_index: int,
    dimensions: int,
    capability: str,
) -> list[float]:
    """Validate one embedding item at its list position (no reordering)."""
    if not isinstance(item, dict):
        raise DiagnosticError(CODE_MALFORMED, capability, "embedding_item_type")
    if "index" not in item:
        raise DiagnosticError(
            CODE_ORDERING,
            capability,
            f"missing_index expected_index={expected_index}",
        )
    idx = item["index"]
    if idx != expected_index:
        raise DiagnosticError(
            CODE_ORDERING,
            capability,
            f"expected_index={expected_index} got={idx}",
        )
    vec = item.get("embedding")
    if not isinstance(vec, list):
        raise DiagnosticError(CODE_MALFORMED, capability, "embedding_not_list")
    if len(vec) != dimensions:
        raise DiagnosticError(
            CODE_DIMENSION,
            capability,
            f"len={len(vec)} expected={dimensions}",
        )
    floats: list[float] = []
    for v in vec:
        try:
            f = float(v)
        except (TypeError, ValueError) as exc:
            raise DiagnosticError(CODE_MALFORMED, capability, "non_float") from exc
        if not math.isfinite(f):
            raise DiagnosticError(CODE_DIMENSION, capability, "non_finite")
        floats.append(f)
    return floats


def validate_embedding_data_list(
    data: Any,
    *,
    expected_count: int,
    dimensions: int,
    capability: str,
) -> list[list[float]]:
    """Validate provider `data` list in returned order against expected indices."""
    if not isinstance(data, list):
        raise DiagnosticError(CODE_MALFORMED, capability, "embedding_data_type")
    if len(data) != expected_count:
        raise DiagnosticError(
            CODE_ORDERING,
            capability,
            f"count={len(data)} expected={expected_count}",
        )
    vectors: list[list[float]] = []
    for expected_index, item in enumerate(data):
        vectors.append(
            validate_embedding_item(item, expected_index, dimensions, capability)
        )
    return vectors


def check_scalar_batch_embeddings(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    cap = "scalar_batch_embeddings"
    if settings.embedding_dimensions != LOCKED_DIMENSIONS:
        raise DiagnosticError(
            CODE_DIMENSION,
            cap,
            f"config_dim={settings.embedding_dimensions} locked={LOCKED_DIMENSIONS}",
        )
    if settings.embedding_model != LOCKED_EMBED_MODEL:
        raise DiagnosticError(
            CODE_MODEL_ABSENCE,
            cap,
            f"config_embed={settings.embedding_model} locked={LOCKED_EMBED_MODEL}",
        )

    dim = settings.embedding_dimensions
    url = f"{settings.base_url}/embeddings"

    scalar_body = {
        "model": settings.embedding_model,
        "input": "JobAgent scalar embedding probe alpha",
        "encoding_format": "float",
        "dimensions": dim,
    }
    scalar = request_json(
        client, "POST", url, secret=settings.api_key, capability=cap, json_body=scalar_body
    )
    try:
        s_vectors = validate_embedding_data_list(
            scalar["data"], expected_count=1, dimensions=dim, capability=cap
        )
        scalar_model = scalar.get("model") or settings.embedding_model
    except DiagnosticError:
        raise
    except (KeyError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "scalar_shape") from exc

    inputs = [
        "JobAgent batch embedding probe first unique",
        "JobAgent batch embedding probe second unique",
    ]
    batch_body = {
        "model": settings.embedding_model,
        "input": inputs,
        "encoding_format": "float",
        "dimensions": dim,
    }
    batch = request_json(
        client, "POST", url, secret=settings.api_key, capability=cap, json_body=batch_body
    )
    try:
        b_vectors = validate_embedding_data_list(
            batch["data"], expected_count=2, dimensions=dim, capability=cap
        )
        if b_vectors[0] == b_vectors[1]:
            raise DiagnosticError(CODE_ORDERING, cap, "batch_vectors_identical")
        batch_model = batch.get("model") or settings.embedding_model
    except DiagnosticError:
        raise
    except (KeyError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "batch_shape") from exc

    _ = s_vectors  # validated; dimensions already checked per item
    return (
        "PASS",
        (
            f"scalar_dim={dim} batch_n=2 batch_dim={dim} finite=yes ordered=yes "
            f"scalar_model={scalar_model} batch_model={batch_model}"
        ),
    )
