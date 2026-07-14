"""Unit tests for production embedding adapter and vector validation (Plan 5 §7.5).

All transport uses injectable fakes — no live ShopAIKey network access.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from app.adapters import shopaikey_embeddings as adapter_mod
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_INVALID_RESPONSE,
    FAILURE_EMBEDDING_RATE_LIMIT,
    FAILURE_EMBEDDING_TIMEOUT,
    LOCKED_ENCODING_FORMAT,
    EmbeddingAdapterError,
    ShopAIKeyEmbeddingAdapter,
    build_shopaikey_embeddings,
    embed_text,
    embed_texts,
)
from app.schemas.embeddings import (
    CODE_DIMENSION,
    CODE_MALFORMED,
    CODE_MODEL,
    CODE_ORDERING,
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    EmbeddingVectorError,
    require_locked_embedding_contract,
    validate_embedding_data_list,
    validate_embedding_item,
    validate_finite_vector,
)
from langchain_openai import OpenAIEmbeddings
from pydantic import AnyHttpUrl, SecretStr


def _settings(
    *,
    model: str = LOCKED_EMBEDDING_MODEL,
    dimensions: int = LOCKED_EMBEDDING_DIMENSIONS,
) -> Any:
    class _S:
        EMBEDDING_MODEL = model
        EMBEDDING_DIMENSIONS = dimensions
        SHOPAIKEY_BASE_URL = AnyHttpUrl("https://api.shopaikey.com/v1")
        SHOPAIKEY_API_KEY = SecretStr("test-key-not-real")

    return _S()


def _vector(seed: float = 0.01, dim: int = LOCKED_EMBEDDING_DIMENSIONS) -> list[float]:
    # Deterministic non-constant finite floats of exact length.
    return [seed + (i * 1e-6) for i in range(dim)]


def _ok_data(vectors: list[list[float]]) -> list[dict[str, Any]]:
    return [{"index": i, "embedding": vec} for i, vec in enumerate(vectors)]


def _fake_create(
    vectors: list[list[float]],
    capture: dict[str, Any] | None = None,
) -> Any:
    bag: dict[str, Any] = capture if capture is not None else {}

    def _create(**kwargs: Any) -> dict[str, Any]:
        bag["last_kwargs"] = dict(kwargs)
        bag["calls"] = bag.get("calls", 0) + 1
        return {"data": _ok_data(vectors), "model": kwargs.get("model")}

    return _create


# ---------------------------------------------------------------------------
# Vector validation (production owner)
# ---------------------------------------------------------------------------


def test_validate_finite_vector_accepts_exact_1536() -> None:
    vec = _vector()
    out = validate_finite_vector(vec)
    assert len(out) == LOCKED_EMBEDDING_DIMENSIONS
    assert all(math.isfinite(x) for x in out)


def test_validate_finite_vector_rejects_short() -> None:
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector([0.1] * 10)
    assert exc_info.value.code == CODE_DIMENSION


def test_validate_finite_vector_rejects_long() -> None:
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector([0.1] * (LOCKED_EMBEDDING_DIMENSIONS + 1))
    assert exc_info.value.code == CODE_DIMENSION


def test_validate_finite_vector_rejects_non_finite() -> None:
    bad = _vector()
    bad[7] = float("nan")
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector(bad)
    assert exc_info.value.code == CODE_DIMENSION
    assert "non_finite" in exc_info.value.detail


def test_validate_finite_vector_rejects_inf() -> None:
    bad = _vector()
    bad[3] = float("inf")
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector(bad)
    assert exc_info.value.code == CODE_DIMENSION


def test_validate_embedding_item_requires_matching_index() -> None:
    item = {"index": 1, "embedding": _vector()}
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_embedding_item(item, expected_index=0)
    assert exc_info.value.code == CODE_ORDERING


def test_validate_embedding_item_missing_index() -> None:
    item = {"embedding": _vector()}
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_embedding_item(item, expected_index=0)
    assert exc_info.value.code == CODE_ORDERING


def test_validate_data_list_count_mismatch() -> None:
    data = _ok_data([_vector()])
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_embedding_data_list(data, expected_count=2)
    assert exc_info.value.code == CODE_ORDERING


def test_validate_data_list_reversed_indices_fail() -> None:
    v0, v1 = _vector(0.01), _vector(0.02)
    data = [
        {"index": 1, "embedding": v1},
        {"index": 0, "embedding": v0},
    ]
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_embedding_data_list(data, expected_count=2)
    assert exc_info.value.code == CODE_ORDERING


def test_validate_data_list_ordered_batch() -> None:
    v0, v1 = _vector(0.01), _vector(0.02)
    out = validate_embedding_data_list(_ok_data([v0, v1]), expected_count=2)
    assert out[0][0] == pytest.approx(v0[0])
    assert out[1][0] == pytest.approx(v1[0])


def test_validate_non_list_embedding_malformed() -> None:
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector("not-a-list")  # type: ignore[arg-type]
    assert exc_info.value.code == CODE_MALFORMED


def test_require_locked_embedding_contract_accepts_locked() -> None:
    require_locked_embedding_contract(
        model=LOCKED_EMBEDDING_MODEL,
        dimensions=LOCKED_EMBEDDING_DIMENSIONS,
    )


def test_require_locked_embedding_contract_rejects_alternate_model() -> None:
    with pytest.raises(EmbeddingVectorError) as exc_info:
        require_locked_embedding_contract(
            model="text-embedding-3-large",
            dimensions=LOCKED_EMBEDDING_DIMENSIONS,
        )
    assert exc_info.value.code == CODE_MODEL


def test_require_locked_embedding_contract_rejects_alternate_dimensions() -> None:
    with pytest.raises(EmbeddingVectorError) as exc_info:
        require_locked_embedding_contract(
            model=LOCKED_EMBEDDING_MODEL,
            dimensions=2,
        )
    assert exc_info.value.code == CODE_DIMENSION


def test_validator_rejects_dimension_override_kwargs() -> None:
    """Production validators always require 1536; no dimensions override path."""
    short = [0.1, 0.2]
    # A two-value vector cannot be accepted even if a caller wants dim=2.
    with pytest.raises(EmbeddingVectorError) as exc_info:
        validate_finite_vector(short)
    assert exc_info.value.code == CODE_DIMENSION
    # dimensions= keyword is not part of the production API.
    with pytest.raises(TypeError):
        validate_finite_vector(short, dimensions=2)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        validate_embedding_item(  # type: ignore[call-arg]
            {"index": 0, "embedding": short},
            expected_index=0,
            dimensions=2,
        )
    with pytest.raises(TypeError):
        validate_embedding_data_list(  # type: ignore[call-arg]
            [{"index": 0, "embedding": short}],
            expected_count=1,
            dimensions=2,
        )


# ---------------------------------------------------------------------------
# Adapter construction and request contract
# ---------------------------------------------------------------------------


def test_build_shopaikey_embeddings_locked_contract() -> None:
    emb = build_shopaikey_embeddings(_settings())
    assert isinstance(emb, OpenAIEmbeddings)
    assert emb.model == LOCKED_EMBEDDING_MODEL
    assert emb.dimensions == LOCKED_EMBEDDING_DIMENSIONS
    assert emb.check_embedding_ctx_length is False
    params = emb._invocation_params
    assert params["model"] == LOCKED_EMBEDDING_MODEL
    assert params["dimensions"] == LOCKED_EMBEDDING_DIMENSIONS
    assert params["encoding_format"] == LOCKED_ENCODING_FORMAT


def test_build_rejects_alternate_model_before_client() -> None:
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        build_shopaikey_embeddings(_settings(model="text-embedding-3-large"))
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE
    assert "MODEL_MISMATCH" in exc_info.value.message


def test_build_rejects_alternate_dimensions_before_client() -> None:
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        build_shopaikey_embeddings(_settings(dimensions=2))
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE
    assert "DIMENSION_MISMATCH" in exc_info.value.message


def test_alternate_model_cannot_produce_request() -> None:
    capture: dict[str, Any] = {}
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        ShopAIKeyEmbeddingAdapter(
            settings=_settings(model="text-embedding-ada-002"),
            create_fn=_fake_create([_vector()], capture),
        )
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE
    assert capture.get("calls", 0) == 0
    assert "last_kwargs" not in capture


def test_alternate_settings_dimension_cannot_produce_request() -> None:
    capture: dict[str, Any] = {}
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        ShopAIKeyEmbeddingAdapter(
            settings=_settings(dimensions=2),
            create_fn=_fake_create([[0.1, 0.2]], capture),
        )
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE
    assert capture.get("calls", 0) == 0
    assert "last_kwargs" not in capture


def test_scalar_embed_preserves_vector() -> None:
    capture: dict[str, Any] = {}
    vec = _vector(0.11)
    adapter = ShopAIKeyEmbeddingAdapter(
        settings=_settings(),
        create_fn=_fake_create([vec], capture),
    )
    out = adapter.embed_text("alpha probe")
    assert len(out) == LOCKED_EMBEDDING_DIMENSIONS
    assert out[0] == pytest.approx(0.11)
    kwargs = capture["last_kwargs"]
    assert kwargs["model"] == LOCKED_EMBEDDING_MODEL
    assert kwargs["dimensions"] == LOCKED_EMBEDDING_DIMENSIONS
    assert kwargs["encoding_format"] == "float"
    assert kwargs["input"] == ["alpha probe"]


def test_batch_embed_preserves_input_order() -> None:
    v0, v1, v2 = _vector(0.1), _vector(0.2), _vector(0.3)
    capture: dict[str, Any] = {}
    adapter = ShopAIKeyEmbeddingAdapter(
        settings=_settings(),
        create_fn=_fake_create([v0, v1, v2], capture),
    )
    texts = ["first unique", "second unique", "third unique"]
    out = adapter.embed_texts(texts)
    assert len(out) == 3
    assert out[0][0] == pytest.approx(0.1)
    assert out[1][0] == pytest.approx(0.2)
    assert out[2][0] == pytest.approx(0.3)
    assert capture["last_kwargs"]["input"] == texts


def test_empty_batch_skips_provider() -> None:
    calls = {"n": 0}

    def boom(**_kwargs: Any) -> Any:
        calls["n"] += 1
        raise AssertionError("provider must not be called")

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=boom)
    assert adapter.embed_texts([]) == []
    assert calls["n"] == 0


def test_count_mismatch_raises_invalid_response() -> None:
    def create(**_kwargs: Any) -> dict[str, Any]:
        return {"data": _ok_data([_vector()])}  # one vector for two inputs

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_texts(["a", "b"])
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE


def test_index_mismatch_raises_invalid_response() -> None:
    def create(**_kwargs: Any) -> dict[str, Any]:
        return {
            "data": [
                {"index": 1, "embedding": _vector(0.1)},
                {"index": 0, "embedding": _vector(0.2)},
            ]
        }

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_texts(["a", "b"])
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE


def test_short_vector_raises_invalid_response() -> None:
    def create(**_kwargs: Any) -> dict[str, Any]:
        return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_text("x")
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE


def test_non_finite_vector_raises_invalid_response() -> None:
    bad = _vector()
    bad[0] = float("nan")

    def create(**_kwargs: Any) -> dict[str, Any]:
        return {"data": [{"index": 0, "embedding": bad}]}

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_text("x")
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE


def test_timeout_maps_to_stable_code() -> None:
    class APITimeoutError(Exception):
        pass

    def create(**_kwargs: Any) -> Any:
        raise APITimeoutError("read timed out")

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_text("x")
    assert exc_info.value.code == FAILURE_EMBEDDING_TIMEOUT
    assert "timed out" in exc_info.value.message.lower()
    assert "test-key" not in str(exc_info.value)


def test_rate_limit_maps_to_stable_code() -> None:
    class RateLimitError(Exception):
        status_code = 429

    def create(**_kwargs: Any) -> Any:
        raise RateLimitError("429 too many")

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_text("x")
    assert exc_info.value.code == FAILURE_EMBEDDING_RATE_LIMIT


def test_generic_provider_error_sanitized() -> None:
    def create(**_kwargs: Any) -> Any:
        raise RuntimeError("secret bearer sk-live-abc full body dump")

    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings(), create_fn=create)
    with pytest.raises(EmbeddingAdapterError) as exc_info:
        adapter.embed_text("x")
    assert exc_info.value.code == FAILURE_EMBEDDING_INVALID_RESPONSE
    assert "sk-live" not in exc_info.value.message
    assert "full body" not in exc_info.value.message


def test_module_level_embed_helpers() -> None:
    vec = _vector(0.5)
    out = embed_text(
        "scalar",
        settings=_settings(),
        create_fn=_fake_create([vec]),
    )
    assert len(out) == LOCKED_EMBEDDING_DIMENSIONS
    batch = embed_texts(
        ["a", "b"],
        settings=_settings(),
        create_fn=_fake_create([_vector(0.1), _vector(0.2)]),
    )
    assert len(batch) == 2


def test_no_fallback_constants() -> None:
    assert LOCKED_EMBEDDING_MODEL == "text-embedding-3-small"
    assert LOCKED_EMBEDDING_DIMENSIONS == 1536
    assert LOCKED_ENCODING_FORMAT == "float"
    # Adapter module must not define alternate models/dimensions.
    source = Path(adapter_mod.__file__).read_text(encoding="utf-8")
    assert "text-embedding-ada" not in source
    assert "local embedding" not in source.lower()


def test_sdk_object_response_shape() -> None:
    """Adapter accepts OpenAI SDK-like objects (model_dump / attributes)."""
    vec = _vector(0.33)

    class _Item:
        def __init__(self) -> None:
            self.index = 0
            self.embedding = vec

    class _Resp:
        def __init__(self) -> None:
            self.data = [_Item()]

        def model_dump(self) -> dict[str, Any]:
            return {"data": [{"index": 0, "embedding": vec}]}

    adapter = ShopAIKeyEmbeddingAdapter(
        settings=_settings(),
        create_fn=lambda **_k: _Resp(),
    )
    out = adapter.embed_text("via sdk shape")
    assert out[0] == pytest.approx(0.33)


def test_adapter_exposes_locked_properties() -> None:
    adapter = ShopAIKeyEmbeddingAdapter(settings=_settings())
    assert adapter.model == LOCKED_EMBEDDING_MODEL
    assert adapter.dimensions == LOCKED_EMBEDDING_DIMENSIONS
    assert adapter.encoding_format == "float"


def test_diagnostic_consumes_production_validator() -> None:
    """Phase 0 diagnostic imports production validators/guard (no local rule)."""
    repo = Path(__file__).resolve().parents[3]
    diag_path = repo / "infrastructure" / "scripts" / "shopaikey_diag" / "embeddings.py"
    text = diag_path.read_text(encoding="utf-8")
    assert "from app.schemas.embeddings import" in text
    assert "validate_embedding_data_list" in text
    assert "require_locked_embedding_contract" in text
    assert "math.isfinite" not in text
    assert "import math" not in text
    # Must not pass a free-form dimensions override into the production validator.
    assert "dimensions=dim" not in text
    assert "dimensions=dimensions" not in text
