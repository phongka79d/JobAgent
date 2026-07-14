"""Scalar and batch embedding capability with list-order index assertions.

Vector validation and the locked model/dimension contract are owned by
production ``app.schemas.embeddings``; this module only performs the live HTTP
smoke and maps failures to diagnostic codes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx

from shopaikey_diag.common import (
    CODE_DIMENSION,
    CODE_MALFORMED,
    CODE_MODEL_ABSENCE,
    CODE_ORDERING,
    DiagnosticError,
    Settings,
    request_json,
)

# Production package lives under backend/; make it importable for the diagnostic.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.schemas.embeddings import (  # noqa: E402
    CODE_MODEL,
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    LOCKED_ENCODING_FORMAT,
    EmbeddingVectorError,
    require_locked_embedding_contract,
    validate_embedding_data_list,
    validate_embedding_item,
)

# Re-export production validators so callers share one owner (no local copy).
__all__ = [
    "check_scalar_batch_embeddings",
    "validate_embedding_data_list",
    "validate_embedding_item",
]


def _map_vector_error(exc: EmbeddingVectorError, capability: str) -> DiagnosticError:
    """Map production validation codes to diagnostic codes (same string values)."""
    code = exc.code
    if code == CODE_MODEL:
        return DiagnosticError(CODE_MODEL_ABSENCE, capability, exc.detail)
    if code not in {CODE_MALFORMED, CODE_DIMENSION, CODE_ORDERING}:
        code = CODE_MALFORMED
    return DiagnosticError(code, capability, exc.detail)


def _validate_data(
    data: Any,
    *,
    expected_count: int,
    capability: str,
) -> list[list[float]]:
    """Consume the production locked-length validator (always 1536)."""
    try:
        return validate_embedding_data_list(
            data,
            expected_count=expected_count,
        )
    except EmbeddingVectorError as exc:
        raise _map_vector_error(exc, capability) from exc


def check_scalar_batch_embeddings(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    cap = "scalar_batch_embeddings"
    try:
        require_locked_embedding_contract(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    except EmbeddingVectorError as exc:
        raise _map_vector_error(exc, cap) from exc

    dim = LOCKED_EMBEDDING_DIMENSIONS
    model = LOCKED_EMBEDDING_MODEL
    url = f"{settings.base_url}/embeddings"

    scalar_body = {
        "model": model,
        "input": "JobAgent scalar embedding probe alpha",
        "encoding_format": LOCKED_ENCODING_FORMAT,
        "dimensions": dim,
    }
    scalar = request_json(
        client, "POST", url, secret=settings.api_key, capability=cap, json_body=scalar_body
    )
    try:
        s_vectors = _validate_data(
            scalar["data"], expected_count=1, capability=cap
        )
        scalar_model = scalar.get("model") or model
    except DiagnosticError:
        raise
    except (KeyError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "scalar_shape") from exc

    inputs = [
        "JobAgent batch embedding probe first unique",
        "JobAgent batch embedding probe second unique",
    ]
    batch_body = {
        "model": model,
        "input": inputs,
        "encoding_format": LOCKED_ENCODING_FORMAT,
        "dimensions": dim,
    }
    batch = request_json(
        client, "POST", url, secret=settings.api_key, capability=cap, json_body=batch_body
    )
    try:
        b_vectors = _validate_data(
            batch["data"], expected_count=2, capability=cap
        )
        if b_vectors[0] == b_vectors[1]:
            raise DiagnosticError(CODE_ORDERING, cap, "batch_vectors_identical")
        batch_model = batch.get("model") or model
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
