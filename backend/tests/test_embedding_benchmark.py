"""Synthetic tests for the focused ShopAIKey embedding benchmark (05B).

Uses only an injectable fake provider. Never reaches the live ShopAIKey API.
Does not require or load held-out outcomes for threshold setting.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

import pytest

from evaluation.benchmark_embeddings import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    ConfigurationError,
    EmbeddingConfig,
    EmbeddingProviderError,
    EmbeddingRequestResult,
    EmbeddingVector,
    REDACTED,
    build_aggregate,
    compute_quality_metrics,
    cosine_similarity,
    embed_batch,
    embed_scalar,
    load_embedding_config,
    load_protocol,
    load_validation_pairs,
    median,
    ndcg_at_k,
    normalize_embedding_text,
    percentile,
    recall_at_k,
    reject_if_disallowed_contract,
    run_benchmark,
    run_compatibility,
    sanitize_failure_message,
    validate_embedding_vectors,
    write_aggregate,
)
from evaluation.embedding_benchmark_schema import (
    AggregateEmbeddingResult,
    CompatibilityEvidence,
    LatencyMetrics,
    PassCriteriaSnapshot,
    QualityMetrics,
)


SENTINEL_SECRET = "sentinel-embedding-secret-never-emit"
PRIVATE_MARKER = "PRIVATE_QUERY_DOCUMENT_TEXT_MUST_NOT_APPEAR"


def valid_environment() -> dict[str, str]:
    return {
        "SHOPAIKEY_BASE_URL": "https://provider.example/v1",
        "SHOPAIKEY_API_KEY": SENTINEL_SECRET,
        "EMBEDDING_MODEL": ALLOWED_EMBEDDING_MODEL,
        "EMBEDDING_DIMENSIONS": str(ALLOWED_EMBEDDING_DIMENSIONS),
    }


def make_config(**overrides: object) -> EmbeddingConfig:
    base = {
        "base_url": "https://provider.example/v1",
        "api_key": SENTINEL_SECRET,
        "model": ALLOWED_EMBEDDING_MODEL,
        "dimensions": ALLOWED_EMBEDDING_DIMENSIONS,
        "max_batch_size": 4,
        "timeout_seconds": 30,
    }
    base.update(overrides)
    return EmbeddingConfig(**base)  # type: ignore[arg-type]


def _unit_vector_from_text(text: str, dimensions: int) -> tuple[float, ...]:
    """Deterministic pseudo-embedding from text content (fake provider only)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(block), 4):
            if len(values) >= dimensions:
                break
            chunk = int.from_bytes(block[index : index + 4], "big")
            # Map to (-1, 1)
            values.append((chunk / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    # L2-normalize for stable cosine ranks.
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return tuple(v / norm for v in values)


class FakeEmbeddingClient:
    """Injectable provider double. Never performs network I/O."""

    def __init__(
        self,
        *,
        dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
        model: str = ALLOWED_EMBEDDING_MODEL,
        latency_ms: float = 12.0,
        fail_on_call: bool = False,
        wrong_order: bool = False,
        wrong_dimensions: bool = False,
        non_finite: bool = False,
        permute_batch_values: bool = False,
    ) -> None:
        self.dimensions = dimensions
        self.model = model
        self.latency_ms = latency_ms
        self.fail_on_call = fail_on_call
        self.wrong_order = wrong_order
        self.wrong_dimensions = wrong_dimensions
        self.non_finite = non_finite
        self.permute_batch_values = permute_batch_values
        self.calls: list[list[str]] = []

    def create(
        self,
        *,
        model: str,
        dimensions: int,
        inputs: Sequence[str],
        timeout_seconds: int,
    ) -> EmbeddingRequestResult:
        self.calls.append(list(inputs))
        if self.fail_on_call:
            raise EmbeddingProviderError("provider_timeout")
        vectors: list[EmbeddingVector] = []
        for index, text in enumerate(inputs):
            dim = 8 if self.wrong_dimensions else dimensions
            values = list(_unit_vector_from_text(text, dim))
            if self.non_finite and index == 0:
                values[0] = float("nan")
            if self.permute_batch_values and len(inputs) > 1 and index == 0:
                # Intentionally attach the second input's vector to index 0.
                values = list(_unit_vector_from_text(inputs[1], dim))
            report_index = (index + 1) % len(inputs) if self.wrong_order else index
            vectors.append(EmbeddingVector(index=report_index, values=tuple(values)))
        if self.wrong_order:
            # Return in the wrong index order so validation must sort/detect.
            vectors = sorted(vectors, key=lambda item: item.index, reverse=True)
        else:
            vectors = sorted(vectors, key=lambda item: item.index)
        return EmbeddingRequestResult(
            model=model if model else self.model,
            vectors=tuple(vectors),
            latency_ms=self.latency_ms,
        )


def _tiny_protocol(tmp_path: Path, seed: int = 20260711) -> Path:
    payload = {
        "protocol_id": "test_embedding_protocol",
        "protocol_version": 1,
        "provider_contract": {
            "model": ALLOWED_EMBEDDING_MODEL,
            "dimensions": ALLOWED_EMBEDDING_DIMENSIONS,
            "encoding": "float",
        },
        "preprocessing": {
            "e5_query_prefix": False,
            "e5_passage_prefix": False,
        },
        "evaluation_inputs": {
            "split": {
                "seed": seed,
                "phase0_active_slice": "validation",
            }
        },
        "pass_criteria": {
            "status": "PRE_RECORDED",
            "numeric_baselines": {
                "nDCG@10_min": 0.3,
                "Recall@10_min": 0.35,
                "median_provider_request_latency_ms_max": 3000,
                "p95_provider_request_latency_ms_max": 8000,
            },
        },
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _tiny_subset_and_private(
    tmp_path: Path,
    *,
    seed: int = 20260711,
    include_private_marker: bool = True,
) -> tuple[Path, Path]:
    validation_ids = ["syn_pair_a", "syn_pair_b", "syn_pair_c", "syn_pair_d"]
    manifest = {
        "seed": seed,
        "validation_record_ids": validation_ids,
        "phase0_active_slice": "validation",
    }
    private_marker = PRIVATE_MARKER if include_private_marker else "safe"
    records = [
        {
            "record_id": "syn_pair_a",
            "query_entity_id": "q1",
            "document_entity_id": "d1",
            "query_text": f"{private_marker} query one backend python",
            "document_text": f"{private_marker} doc one backend python role",
            "relevance_label": 3,
            "split": "validation",
        },
        {
            "record_id": "syn_pair_b",
            "query_entity_id": "q1",
            "document_entity_id": "d2",
            "query_text": f"{private_marker} query one backend python",
            "document_text": f"{private_marker} doc two unrelated gardening",
            "relevance_label": 0,
            "split": "validation",
        },
        {
            "record_id": "syn_pair_c",
            "query_entity_id": "q2",
            "document_entity_id": "d3",
            "query_text": f"{private_marker} query two frontend react",
            "document_text": f"{private_marker} doc three frontend react role",
            "relevance_label": 2,
            "split": "validation",
        },
        {
            "record_id": "syn_pair_d",
            "query_entity_id": "q2",
            "document_entity_id": "d4",
            "query_text": f"{private_marker} query two frontend react",
            "document_text": f"{private_marker} doc four unrelated cooking",
            "relevance_label": 1,
            "split": "validation",
        },
        {
            "record_id": "syn_pair_held",
            "query_entity_id": "q_held",
            "document_entity_id": "d_held",
            "query_text": "held out query must not load",
            "document_text": "held out document must not load",
            "relevance_label": 3,
            "split": "held_out_test",
        },
    ]
    manifest_path = tmp_path / "subset.json"
    private_path = tmp_path / "private.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    private_path.write_text(
        json.dumps({"seed": seed, "records": records}), encoding="utf-8"
    )
    return manifest_path, private_path


# ---------------------------------------------------------------------------
# Config / allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SHOPAIKEY_BASE_URL", ""),
        ("SHOPAIKEY_BASE_URL", "file:///private"),
        (
            "SHOPAIKEY_BASE_URL",
            f"https://user:{SENTINEL_SECRET}@provider.example/v1",
        ),
        ("SHOPAIKEY_API_KEY", ""),
        ("EMBEDDING_MODEL", ""),
        ("EMBEDDING_DIMENSIONS", ""),
        ("EMBEDDING_DIMENSIONS", "not-a-number"),
        ("EMBEDDING_MODEL", "text-embedding-3-large"),
        ("EMBEDDING_DIMENSIONS", "768"),
    ],
)
def test_configuration_rejects_invalid_or_disallowed_without_echoing_secrets(
    name: str, value: str
) -> None:
    environment = valid_environment()
    environment[name] = value
    with pytest.raises(ConfigurationError) as raised:
        load_embedding_config(environment)
    rendered = str(raised.value)
    assert SENTINEL_SECRET not in rendered
    assert "Authorization" not in rendered


def test_configuration_accepts_locked_contract_and_hides_key() -> None:
    config = load_embedding_config(valid_environment())
    assert config.model == ALLOWED_EMBEDDING_MODEL
    assert config.dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert SENTINEL_SECRET not in repr(config)
    assert SENTINEL_SECRET not in str(config)
    assert REDACTED in repr(config)


def test_allowlist_rejects_alternate_model_and_dimensions() -> None:
    with pytest.raises(ConfigurationError):
        reject_if_disallowed_contract(model="other-model", dimensions=1536)
    with pytest.raises(ConfigurationError):
        reject_if_disallowed_contract(
            model=ALLOWED_EMBEDDING_MODEL, dimensions=3072
        )


# ---------------------------------------------------------------------------
# Normalization / no E5 prefixes
# ---------------------------------------------------------------------------


def test_normalize_strips_whitespace_and_does_not_add_e5_prefixes() -> None:
    assert normalize_embedding_text("  hello   world  ") == "hello world"
    out = normalize_embedding_text("plain text")
    assert not out.lower().startswith("query:")
    assert not out.lower().startswith("passage:")


def test_normalize_strips_accidental_e5_prefixes() -> None:
    assert normalize_embedding_text("query: hello") == "hello"
    assert normalize_embedding_text("passage: world") == "world"


# ---------------------------------------------------------------------------
# Metrics and percentiles
# ---------------------------------------------------------------------------


def test_ndcg_perfect_and_inverse_rankings() -> None:
    perfect = ndcg_at_k([3, 2, 1, 0], k=10)
    inverse = ndcg_at_k([0, 1, 2, 3], k=10)
    assert perfect == pytest.approx(1.0)
    assert 0.0 <= inverse < perfect


def test_recall_at_k_threshold() -> None:
    # Labels >= 2 are relevant: positions 0 and 2 of full list; top-2 hits one of two.
    score = recall_at_k([3, 0, 2, 1], k=2, relevant_min=2)
    assert score == pytest.approx(0.5)
    assert recall_at_k([0, 1, 0], k=10, relevant_min=2) == 0.0


def test_median_and_percentile() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 100.0]
    assert median(values) == 30.0
    assert percentile(values, 0) == 10.0
    assert percentile(values, 100) == 100.0
    assert percentile(values, 50) == 30.0
    assert percentile([5.0], 95) == 5.0
    p95 = percentile(values, 95)
    assert 40.0 <= p95 <= 100.0


def test_cosine_similarity_identical_and_orthogonal() -> None:
    left = (1.0, 0.0, 0.0)
    right = (1.0, 0.0, 0.0)
    ortho = (0.0, 1.0, 0.0)
    assert cosine_similarity(left, right) == pytest.approx(1.0)
    assert cosine_similarity(left, ortho) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Vector validation / ordering / dimensions / finite
# ---------------------------------------------------------------------------


def test_validate_vectors_accepts_ordered_finite_1536() -> None:
    values = tuple(0.01 for _ in range(ALLOWED_EMBEDDING_DIMENSIONS))
    vectors = (EmbeddingVector(index=0, values=values),)
    validate_embedding_vectors(input_count=1, vectors=vectors)


def test_validate_vectors_rejects_order_dimension_and_non_finite() -> None:
    values = tuple(0.01 for _ in range(ALLOWED_EMBEDDING_DIMENSIONS))
    with pytest.raises(EmbeddingProviderError, match="ordering_violation"):
        validate_embedding_vectors(
            input_count=1,
            vectors=(EmbeddingVector(index=1, values=values),),
        )
    short = tuple(0.01 for _ in range(8))
    with pytest.raises(EmbeddingProviderError, match="dimension_mismatch"):
        validate_embedding_vectors(
            input_count=1,
            vectors=(EmbeddingVector(index=0, values=short),),
        )
    bad = list(values)
    bad[0] = float("nan")
    with pytest.raises(EmbeddingProviderError, match="non_finite_value"):
        validate_embedding_vectors(
            input_count=1,
            vectors=(EmbeddingVector(index=0, values=tuple(bad)),),
        )


def test_scalar_and_batch_preserve_ordering_and_equivalence() -> None:
    client = FakeEmbeddingClient(latency_ms=5.0)
    config = make_config()
    texts = ["alpha probe", "beta probe", "gamma probe"]
    scalar_vectors = [
        embed_scalar(config, text, client=client).vectors[0].values for text in texts
    ]
    batch = embed_batch(config, texts, client=client)
    assert [vector.index for vector in batch.vectors] == [0, 1, 2]
    for index, text in enumerate(texts):
        assert batch.vectors[index].values == scalar_vectors[index]
        assert len(batch.vectors[index].values) == ALLOWED_EMBEDDING_DIMENSIONS
        assert all(math.isfinite(v) for v in batch.vectors[index].values)
    # Normalized inputs were sent (no E5 prefixes).
    for call in client.calls:
        for item in call:
            assert not item.lower().startswith("query:")
            assert not item.lower().startswith("passage:")


def test_embed_batch_rejects_oversize_and_wrong_contract() -> None:
    client = FakeEmbeddingClient()
    config = make_config(max_batch_size=2)
    with pytest.raises(EmbeddingProviderError, match="batch_size_exceeded"):
        embed_batch(config, ["a", "b", "c"], client=client)
    bad_config = make_config(model="text-embedding-3-large")
    with pytest.raises(ConfigurationError):
        embed_scalar(bad_config, "x", client=client)


def test_provider_failure_is_sanitized() -> None:
    client = FakeEmbeddingClient(fail_on_call=True)
    config = make_config()
    with pytest.raises(EmbeddingProviderError) as raised:
        embed_scalar(config, "probe", client=client)
    assert SENTINEL_SECRET not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_wrong_order_and_non_finite_surface_as_provider_errors() -> None:
    config = make_config()
    with pytest.raises(EmbeddingProviderError):
        embed_batch(
            config,
            ["a", "b"],
            client=FakeEmbeddingClient(wrong_order=True),
        )
    with pytest.raises(EmbeddingProviderError):
        embed_scalar(config, "a", client=FakeEmbeddingClient(non_finite=True))
    with pytest.raises(EmbeddingProviderError):
        embed_scalar(config, "a", client=FakeEmbeddingClient(wrong_dimensions=True))


# ---------------------------------------------------------------------------
# Seed handling / validation slice only
# ---------------------------------------------------------------------------


def test_load_validation_pairs_uses_seed_and_excludes_held_out(
    tmp_path: Path,
) -> None:
    protocol_path = _tiny_protocol(tmp_path, seed=20260711)
    manifest_path, private_path = _tiny_subset_and_private(tmp_path, seed=20260711)
    protocol = load_protocol(protocol_path)
    pairs, seed = load_validation_pairs(
        private_records_path=private_path,
        subset_manifest_path=manifest_path,
        protocol=protocol,
    )
    assert seed == 20260711
    assert len(pairs) == 4
    assert all(pair.split == "validation" for pair in pairs)
    assert "syn_pair_held" not in {pair.record_id for pair in pairs}


def test_seed_mismatch_is_rejected(tmp_path: Path) -> None:
    protocol_path = _tiny_protocol(tmp_path, seed=111)
    manifest_path, private_path = _tiny_subset_and_private(tmp_path, seed=222)
    protocol = load_protocol(protocol_path)
    with pytest.raises(ValueError, match="seed"):
        load_validation_pairs(
            private_records_path=private_path,
            subset_manifest_path=manifest_path,
            protocol=protocol,
        )


def test_compute_quality_metrics_deterministic_for_seeded_pairs(
    tmp_path: Path,
) -> None:
    protocol_path = _tiny_protocol(tmp_path)
    manifest_path, private_path = _tiny_subset_and_private(tmp_path)
    protocol = load_protocol(protocol_path)
    pairs, seed = load_validation_pairs(
        private_records_path=private_path,
        subset_manifest_path=manifest_path,
        protocol=protocol,
    )
    # Build embeddings from the same fake mapping twice.
    entity_ids = sorted(
        {p.query_entity_id for p in pairs} | {p.document_entity_id for p in pairs}
    )
    embeddings = {
        entity_id: _unit_vector_from_text(entity_id, ALLOWED_EMBEDDING_DIMENSIONS)
        for entity_id in entity_ids
    }
    first = compute_quality_metrics(pairs, embeddings, seed=seed)
    second = compute_quality_metrics(pairs, embeddings, seed=seed)
    assert first == second
    assert first.seed == seed
    assert 0.0 <= first.ndcg_at_10 <= 1.0
    assert 0.0 <= first.recall_at_10 <= 1.0


# ---------------------------------------------------------------------------
# Compatibility runner / aggregate / private-text suppression
# ---------------------------------------------------------------------------


def test_run_compatibility_reports_required_fields() -> None:
    config = make_config(max_batch_size=3)
    client = FakeEmbeddingClient(latency_ms=7.5)
    evidence, latencies, failures = run_compatibility(config, client=client)
    assert evidence.model == ALLOWED_EMBEDDING_MODEL
    assert evidence.dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert evidence.e5_prefixes_applied is False
    assert evidence.scalar_ok is True
    assert evidence.batch_ok is True
    assert evidence.ordering_preserved is True
    assert evidence.finite_floats_only is True
    assert evidence.vector_length_ok is True
    assert evidence.scalar_batch_equivalence is True
    assert evidence.sanitized_failure_ok is True
    assert latencies
    assert SENTINEL_SECRET not in json.dumps(evidence.model_dump())
    assert failures == [] or all(SENTINEL_SECRET not in item for item in failures)


def test_run_benchmark_and_write_aggregate_suppress_private_text(
    tmp_path: Path,
) -> None:
    protocol_path = _tiny_protocol(tmp_path)
    manifest_path, private_path = _tiny_subset_and_private(tmp_path)
    config = make_config(max_batch_size=8)
    client = FakeEmbeddingClient(latency_ms=11.0)
    result = run_benchmark(
        config,
        client=client,
        protocol_path=protocol_path,
        subset_manifest_path=manifest_path,
        private_records_path=private_path,
        probe_texts=["synthetic alpha", "synthetic beta"],
    )
    assert isinstance(result, AggregateEmbeddingResult)
    assert result.model == ALLOWED_EMBEDDING_MODEL
    assert result.dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert result.held_out_used is False
    assert result.quality.slice == "validation"
    assert result.quality.labeled_pair_count == 4
    assert result.compatibility.scalar_ok is True
    assert result.latency.sample_count >= 1
    assert result.pass_criteria.status == "PRE_RECORDED"

    output = tmp_path / "embedding_benchmark.json"
    write_aggregate(result, output)
    raw = output.read_text(encoding="utf-8")
    assert PRIVATE_MARKER not in raw
    assert SENTINEL_SECRET not in raw
    assert "query_text" not in raw
    assert "document_text" not in raw
    assert "Authorization" not in raw
    payload = json.loads(raw)
    assert payload["quality"]["ndcg_at_10"] == result.quality.ndcg_at_10
    assert payload["latency"]["median_provider_request_latency_ms"] >= 0


def test_sanitize_failure_message_redacts_secrets_and_private_fragments() -> None:
    message = f"Authorization: Bearer {SENTINEL_SECRET} body={PRIVATE_MARKER}xxx"
    sanitized = sanitize_failure_message(
        message,
        secrets=[SENTINEL_SECRET],
        private_fragments=[PRIVATE_MARKER],
    )
    assert SENTINEL_SECRET not in sanitized
    assert PRIVATE_MARKER not in sanitized
    assert "Authorization" not in sanitized or sanitized == "sanitized_provider_failure"


def test_schema_forbids_extra_and_requires_core_fields() -> None:
    evidence = CompatibilityEvidence(
        model=ALLOWED_EMBEDDING_MODEL,
        dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
        scalar_ok=True,
        batch_ok=True,
        ordering_preserved=True,
        finite_floats_only=True,
        vector_length_ok=True,
        scalar_batch_equivalence=True,
        max_batch_size=16,
        sanitized_failure_ok=True,
    )
    quality = QualityMetrics(
        k=10,
        relevant_label_threshold_min=2,
        ndcg_at_10=0.5,
        recall_at_10=0.4,
        query_count=2,
        labeled_pair_count=4,
        seed=20260711,
    )
    latency = LatencyMetrics(
        sample_count=3,
        median_provider_request_latency_ms=10.0,
        p95_provider_request_latency_ms=20.0,
    )
    result = AggregateEmbeddingResult(
        protocol_id="x",
        protocol_version=1,
        model=ALLOWED_EMBEDDING_MODEL,
        dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
        seed=20260711,
        compatibility=evidence,
        quality=quality,
        latency=latency,
        pass_criteria=PassCriteriaSnapshot(
            status="PRE_RECORDED",
            ndcg_at_10_min=0.3,
            recall_at_10_min=0.35,
            median_provider_request_latency_ms_max=3000,
            p95_provider_request_latency_ms_max=8000,
        ),
        subset_manifest_path="backend/evaluation/labels/retrieval_subset_manifest.json",
        protocol_path="backend/evaluation/labels/embedding_validation_protocol.json",
    )
    dumped = result.model_dump()
    assert "query_text" not in dumped
    assert dumped["encoding"] == "float"


def test_frozen_protocol_defaults_are_loadable() -> None:
    """Smoke: committed 05A freeze artifacts parse for runner defaults."""
    protocol = load_protocol()
    assert protocol["provider_contract"]["model"] == ALLOWED_EMBEDDING_MODEL
    assert int(protocol["provider_contract"]["dimensions"]) == ALLOWED_EMBEDDING_DIMENSIONS
    assert protocol["preprocessing"]["e5_query_prefix"] is False
    assert protocol["preprocessing"]["e5_passage_prefix"] is False
    assert protocol["evaluation_inputs"]["split"]["seed"] == 20260711
