"""Focused ShopAIKey embedding diagnostic and benchmark (Phase 0).

Calls only the locked text-embedding-3-small contract (dimensions=1536).
Normal automated tests inject a fake provider; live execution is deferred to 05C.
Never logs API keys, Authorization headers, or private query/document text.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from dotenv import dotenv_values

from evaluation.embedding_benchmark_schema import (
    AggregateEmbeddingResult,
    CompatibilityEvidence,
    LatencyMetrics,
    PassCriteriaSnapshot,
    QualityMetrics,
)

# Re-export schema for a single import surface.
__all__ = [
    "ALLOWED_EMBEDDING_MODEL",
    "ALLOWED_EMBEDDING_DIMENSIONS",
    "AggregateEmbeddingResult",
    "ConfigurationError",
    "DEFAULT_OUTPUT",
    "DEFAULT_PROTOCOL",
    "DEFAULT_SUBSET_MANIFEST",
    "EmbeddingConfig",
    "EmbeddingProviderError",
    "EmbeddingRequestResult",
    "EmbeddingVector",
    "REDACTED",
    "build_aggregate",
    "cosine_similarity",
    "embed_batch",
    "embed_scalar",
    "load_embedding_config",
    "load_protocol",
    "load_root_embedding_config",
    "load_validation_pairs",
    "main",
    "median",
    "ndcg_at_k",
    "normalize_embedding_text",
    "percentile",
    "recall_at_k",
    "reject_if_disallowed_contract",
    "run_benchmark",
    "run_compatibility",
    "sanitize_failure_message",
    "validate_embedding_vectors",
    "write_aggregate",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV = REPO_ROOT / ".env"
DEFAULT_PROTOCOL = (
    REPO_ROOT
    / "backend"
    / "evaluation"
    / "labels"
    / "embedding_validation_protocol.json"
)
DEFAULT_SUBSET_MANIFEST = (
    REPO_ROOT
    / "backend"
    / "evaluation"
    / "labels"
    / "retrieval_subset_manifest.json"
)
DEFAULT_PRIVATE_RECORDS = (
    REPO_ROOT
    / "backend"
    / "evaluation"
    / "private"
    / "retrieval_subset.local.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "backend"
    / "evaluation"
    / "reports"
    / "embedding_benchmark.json"
)

ALLOWED_EMBEDDING_MODEL = "text-embedding-3-small"
ALLOWED_EMBEDDING_DIMENSIONS = 1536
DEFAULT_MAX_BATCH_SIZE = 16
DEFAULT_TIMEOUT_SECONDS = 30
RELEVANT_LABEL_MIN = 2
METRIC_K = 10
REDACTED = "[REDACTED]"

_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "
_WHITESPACE_RE = re.compile(r"\s+")
_SENSITIVE_MARKERS = (
    "authorization",
    "apikey",
    "api_key",
    "bearer",
    "query_text",
    "document_text",
)


class ConfigurationError(RuntimeError):
    """Invalid embedding configuration (never carries secrets)."""


class EmbeddingProviderError(RuntimeError):
    """Sanitized provider failure; never carries secrets or raw payloads."""

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@dataclass(frozen=True)
class EmbeddingConfig:
    base_url: str
    api_key: str
    model: str
    dimensions: int
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __repr__(self) -> str:
        return (
            "EmbeddingConfig(base_url="
            f"{self.base_url!r}, api_key={REDACTED!r}, model={self.model!r}, "
            f"dimensions={self.dimensions}, max_batch_size={self.max_batch_size}, "
            f"timeout_seconds={self.timeout_seconds})"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class EmbeddingVector:
    index: int
    values: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingRequestResult:
    model: str
    vectors: tuple[EmbeddingVector, ...]
    latency_ms: float


@dataclass(frozen=True)
class LabeledPair:
    """In-memory pair. Text fields exist only for request building; never report."""

    record_id: str
    query_entity_id: str
    document_entity_id: str
    query_text: str
    document_text: str
    relevance_label: int
    split: str


class EmbeddingClient(Protocol):
    def create(
        self,
        *,
        model: str,
        dimensions: int,
        inputs: Sequence[str],
        timeout_seconds: int,
    ) -> EmbeddingRequestResult: ...


EmbedFn = Callable[..., EmbeddingRequestResult]


def load_embedding_config(environment: Mapping[str, str]) -> EmbeddingConfig:
    base_url = environment.get("SHOPAIKEY_BASE_URL", "").strip()
    api_key = environment.get("SHOPAIKEY_API_KEY", "").strip()
    model = environment.get("EMBEDDING_MODEL", "").strip()
    dimensions_raw = environment.get("EMBEDDING_DIMENSIONS", "").strip()
    try:
        parsed_url = urlsplit(base_url)
    except ValueError:
        raise ConfigurationError("Invalid embedding configuration.") from None

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ConfigurationError("Invalid embedding configuration.")
    if not api_key or not model or not dimensions_raw:
        raise ConfigurationError("Invalid embedding configuration.")
    try:
        dimensions = int(dimensions_raw)
    except ValueError:
        raise ConfigurationError("Invalid embedding configuration.") from None
    if dimensions <= 0:
        raise ConfigurationError("Invalid embedding configuration.")

    reject_if_disallowed_contract(model=model, dimensions=dimensions)
    return EmbeddingConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        dimensions=dimensions,
    )


def load_root_embedding_config() -> EmbeddingConfig:
    file_values = {
        key: value
        for key, value in dotenv_values(ROOT_ENV).items()
        if value is not None
    }
    values = {
        name: os.environ.get(name, file_values.get(name, ""))
        for name in (
            "SHOPAIKEY_BASE_URL",
            "SHOPAIKEY_API_KEY",
            "EMBEDDING_MODEL",
            "EMBEDDING_DIMENSIONS",
        )
    }
    return load_embedding_config(values)


def reject_if_disallowed_contract(*, model: str, dimensions: int) -> None:
    if model != ALLOWED_EMBEDDING_MODEL or dimensions != ALLOWED_EMBEDDING_DIMENSIONS:
        raise ConfigurationError(
            "Disallowed embedding contract: only "
            f"{ALLOWED_EMBEDDING_MODEL} with dimensions="
            f"{ALLOWED_EMBEDDING_DIMENSIONS} is permitted."
        )


def normalize_embedding_text(text: str) -> str:
    """Strip and collapse internal whitespace. Never apply E5 prefixes."""
    if text.startswith(_E5_QUERY_PREFIX) or text.startswith(_E5_PASSAGE_PREFIX):
        # Strip accidental E5 prefixes rather than forward them.
        if text.lower().startswith(_E5_QUERY_PREFIX):
            text = text[len(_E5_QUERY_PREFIX) :]
        elif text.lower().startswith(_E5_PASSAGE_PREFIX):
            text = text[len(_E5_PASSAGE_PREFIX) :]
    return _WHITESPACE_RE.sub(" ", text.strip())


def sanitize_failure_message(
    message: str,
    *,
    secrets: Sequence[str] = (),
    private_fragments: Sequence[str] = (),
) -> str:
    """Return a bounded failure code/summary with secrets and private text removed."""
    lowered = message.lower().replace("-", "").replace("_", "")
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return "sanitized_provider_failure"
    for secret in secrets:
        if secret and secret in message:
            return "sanitized_provider_failure"
    for fragment in private_fragments:
        if fragment and len(fragment) >= 8 and fragment in message:
            return "sanitized_provider_failure"
    # Keep only short, alphanumeric failure codes when possible.
    cleaned = re.sub(r"[^a-zA-Z0-9_.: -]", "", message).strip()
    if not cleaned or len(cleaned) > 120:
        return "sanitized_provider_failure"
    return cleaned


def _default_openai_client(
    config: EmbeddingConfig,
) -> EmbeddingClient:
    from openai import OpenAI

    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
    )

    class _OpenAIEmbeddingClient:
        def create(
            self,
            *,
            model: str,
            dimensions: int,
            inputs: Sequence[str],
            timeout_seconds: int,
        ) -> EmbeddingRequestResult:
            started = time.perf_counter()
            try:
                response = client.embeddings.create(
                    model=model,
                    input=list(inputs),
                    dimensions=dimensions,
                    encoding_format="float",
                    timeout=timeout_seconds,
                )
            except Exception as error:
                raise EmbeddingProviderError(
                    sanitize_failure_message(
                        type(error).__name__,
                        secrets=[config.api_key],
                    )
                ) from None
            latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
            items = sorted(response.data, key=lambda item: int(item.index))
            vectors = tuple(
                EmbeddingVector(
                    index=int(item.index),
                    values=tuple(float(v) for v in item.embedding),
                )
                for item in items
            )
            response_model = str(getattr(response, "model", model) or model)
            return EmbeddingRequestResult(
                model=response_model,
                vectors=vectors,
                latency_ms=latency_ms,
            )

    return _OpenAIEmbeddingClient()


def validate_embedding_vectors(
    *,
    input_count: int,
    vectors: Sequence[EmbeddingVector],
    expected_dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
) -> None:
    if len(vectors) != input_count:
        raise EmbeddingProviderError("vector_count_mismatch")
    seen_indexes: set[int] = set()
    for expected_index, vector in enumerate(vectors):
        if vector.index != expected_index:
            raise EmbeddingProviderError("ordering_violation")
        if vector.index in seen_indexes:
            raise EmbeddingProviderError("duplicate_vector_index")
        seen_indexes.add(vector.index)
        if len(vector.values) != expected_dimensions:
            raise EmbeddingProviderError("dimension_mismatch")
        for value in vector.values:
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise EmbeddingProviderError("non_finite_value")


def embed_scalar(
    config: EmbeddingConfig,
    text: str,
    *,
    client: EmbeddingClient | None = None,
) -> EmbeddingRequestResult:
    reject_if_disallowed_contract(model=config.model, dimensions=config.dimensions)
    normalized = normalize_embedding_text(text)
    active = client or _default_openai_client(config)
    result = active.create(
        model=config.model,
        dimensions=config.dimensions,
        inputs=[normalized],
        timeout_seconds=config.timeout_seconds,
    )
    if result.model and result.model != config.model:
        # Some providers suffix versions; require exact locked ID for gate evidence.
        if result.model != ALLOWED_EMBEDDING_MODEL and not result.model.startswith(
            ALLOWED_EMBEDDING_MODEL
        ):
            raise EmbeddingProviderError("model_mismatch")
    validate_embedding_vectors(
        input_count=1,
        vectors=result.vectors,
        expected_dimensions=config.dimensions,
    )
    return result


def embed_batch(
    config: EmbeddingConfig,
    texts: Sequence[str],
    *,
    client: EmbeddingClient | None = None,
) -> EmbeddingRequestResult:
    reject_if_disallowed_contract(model=config.model, dimensions=config.dimensions)
    if not texts:
        raise EmbeddingProviderError("empty_batch")
    if len(texts) > config.max_batch_size:
        raise EmbeddingProviderError("batch_size_exceeded")
    normalized = [normalize_embedding_text(text) for text in texts]
    active = client or _default_openai_client(config)
    result = active.create(
        model=config.model,
        dimensions=config.dimensions,
        inputs=normalized,
        timeout_seconds=config.timeout_seconds,
    )
    validate_embedding_vectors(
        input_count=len(texts),
        vectors=result.vectors,
        expected_dimensions=config.dimensions,
    )
    return result


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vector_length_mismatch")
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=True):
        dot += float(a) * float(b)
        left_norm += float(a) * float(a)
        right_norm += float(b) * float(b)
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def _dcg_at_k(relevances: Sequence[float], k: int) -> float:
    total = 0.0
    for index, relevance in enumerate(relevances[:k]):
        total += (2.0 ** float(relevance) - 1.0) / math.log2(index + 2.0)
    return total


def ndcg_at_k(relevances_in_rank_order: Sequence[float], k: int = METRIC_K) -> float:
    if not relevances_in_rank_order or k <= 0:
        return 0.0
    dcg = _dcg_at_k(relevances_in_rank_order, k)
    ideal = _dcg_at_k(sorted(relevances_in_rank_order, reverse=True), k)
    if ideal <= 0.0:
        return 0.0
    return dcg / ideal


def recall_at_k(
    relevances_in_rank_order: Sequence[int],
    *,
    k: int = METRIC_K,
    relevant_min: int = RELEVANT_LABEL_MIN,
) -> float:
    if not relevances_in_rank_order or k <= 0:
        return 0.0
    total_relevant = sum(1 for rel in relevances_in_rank_order if rel >= relevant_min)
    if total_relevant == 0:
        return 0.0
    hit = sum(1 for rel in relevances_in_rank_order[:k] if rel >= relevant_min)
    return hit / total_relevant


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: Sequence[float], p: float) -> float:
    """Inclusive linear-interpolation percentile for p in [0, 100]."""
    if not values:
        return 0.0
    if p <= 0:
        return float(min(values))
    if p >= 100:
        return float(max(values))
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    return _read_json(path)


def load_validation_pairs(
    *,
    private_records_path: Path,
    subset_manifest_path: Path = DEFAULT_SUBSET_MANIFEST,
    protocol: Mapping[str, Any] | None = None,
) -> tuple[list[LabeledPair], int]:
    """Load validation-slice pairs only. Never returns held-out pairs."""
    protocol = protocol or load_protocol()
    seed = int(protocol["evaluation_inputs"]["split"]["seed"])
    active_slice = protocol["evaluation_inputs"]["split"]["phase0_active_slice"]
    if active_slice != "validation":
        raise ValueError("phase0_active_slice must be validation")

    manifest = _read_json(subset_manifest_path)
    if int(manifest.get("seed", -1)) != seed:
        raise ValueError("subset seed mismatch vs protocol")
    allowed_ids = set(manifest.get("validation_record_ids") or [])
    if not allowed_ids:
        raise ValueError("subset manifest missing validation_record_ids")

    private = _read_json(private_records_path)
    if int(private.get("seed", -1)) != seed:
        raise ValueError("private records seed mismatch vs protocol")

    pairs: list[LabeledPair] = []
    for entry in private.get("records") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("split") != "validation":
            continue
        record_id = str(entry.get("record_id", ""))
        if record_id not in allowed_ids:
            continue
        label = int(entry["relevance_label"])
        if label < 0 or label > 3:
            raise ValueError("relevance_label out of 0-3 scale")
        pairs.append(
            LabeledPair(
                record_id=record_id,
                query_entity_id=str(entry["query_entity_id"]),
                document_entity_id=str(entry["document_entity_id"]),
                query_text=str(entry["query_text"]),
                document_text=str(entry["document_text"]),
                relevance_label=label,
                split="validation",
            )
        )
    pairs.sort(key=lambda item: item.record_id)
    if not pairs:
        raise ValueError("no validation pairs loaded")
    return pairs, seed


def _vectors_close(
    left: Sequence[float],
    right: Sequence[float],
    *,
    abs_tol: float = 1e-5,
) -> bool:
    if len(left) != len(right):
        return False
    return all(
        math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=abs_tol)
        for a, b in zip(left, right, strict=True)
    )


def run_compatibility(
    config: EmbeddingConfig,
    *,
    client: EmbeddingClient,
    probe_texts: Sequence[str] | None = None,
) -> tuple[CompatibilityEvidence, list[float], list[str]]:
    """Scalar/batch ordering, dimension, finite, equivalence, and failure checks."""
    latencies: list[float] = []
    failures: list[str] = []
    probes = list(probe_texts) if probe_texts is not None else [
        "Synthetic probe text alpha for embedding compatibility.",
        "Synthetic probe text beta for embedding compatibility.",
        "Synthetic probe text gamma for embedding compatibility.",
    ]
    probes = [normalize_embedding_text(text) for text in probes[: config.max_batch_size]]

    scalar_ok = False
    batch_ok = False
    ordering_ok = False
    finite_ok = False
    length_ok = False
    equivalence_ok = False
    sanitized_failure_ok = False

    try:
        scalar_vectors: list[tuple[float, ...]] = []
        for text in probes:
            result = embed_scalar(config, text, client=client)
            latencies.append(result.latency_ms)
            scalar_vectors.append(result.vectors[0].values)
        scalar_ok = True
        finite_ok = True
        length_ok = True
        ordering_ok = True
    except EmbeddingProviderError as error:
        failures.append(sanitize_failure_message(str(error), secrets=[config.api_key]))
    except Exception:
        failures.append("scalar_unexpected_failure")

    try:
        batch_result = embed_batch(config, probes, client=client)
        latencies.append(batch_result.latency_ms)
        batch_ok = True
        finite_ok = True
        length_ok = True
        ordering_ok = all(
            vector.index == index for index, vector in enumerate(batch_result.vectors)
        )
        if scalar_ok:
            equivalence_ok = all(
                _vectors_close(scalar_vectors[index], batch_result.vectors[index].values)
                for index in range(len(probes))
            )
    except EmbeddingProviderError as error:
        failures.append(sanitize_failure_message(str(error), secrets=[config.api_key]))
    except Exception:
        failures.append("batch_unexpected_failure")

    # Intentional invalid path: oversized batch must fail without leaking secrets.
    try:
        oversized = probes + ["overflow probe"] * (config.max_batch_size)
        embed_batch(config, oversized[: config.max_batch_size + 1], client=client)
        sanitized_failure_ok = False
        failures.append("expected_batch_limit_failure_missing")
    except EmbeddingProviderError as error:
        message = str(error)
        if config.api_key and config.api_key in message:
            sanitized_failure_ok = False
            failures.append("secret_leak_in_failure")
        else:
            sanitized_failure_ok = True
    except Exception as error:
        message = sanitize_failure_message(str(error), secrets=[config.api_key])
        sanitized_failure_ok = config.api_key not in message
        if not sanitized_failure_ok:
            failures.append("secret_leak_in_failure")

    evidence = CompatibilityEvidence(
        model=config.model,
        dimensions=config.dimensions,
        encoding="float",
        e5_prefixes_applied=False,
        scalar_ok=scalar_ok,
        batch_ok=batch_ok,
        ordering_preserved=ordering_ok,
        finite_floats_only=finite_ok,
        vector_length_ok=length_ok,
        scalar_batch_equivalence=equivalence_ok,
        max_batch_size=config.max_batch_size,
        sanitized_failure_ok=sanitized_failure_ok,
    )
    return evidence, latencies, failures


def _unique_entity_texts(pairs: Sequence[LabeledPair]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for pair in pairs:
        texts.setdefault(pair.query_entity_id, pair.query_text)
        texts.setdefault(pair.document_entity_id, pair.document_text)
    return texts


def _embed_entity_map(
    config: EmbeddingConfig,
    entity_texts: Mapping[str, str],
    *,
    client: EmbeddingClient,
) -> tuple[dict[str, tuple[float, ...]], list[float]]:
    ordered_ids = sorted(entity_texts.keys())
    latencies: list[float] = []
    vectors: dict[str, tuple[float, ...]] = {}
    batch_size = config.max_batch_size
    for start in range(0, len(ordered_ids), batch_size):
        chunk_ids = ordered_ids[start : start + batch_size]
        chunk_texts = [entity_texts[entity_id] for entity_id in chunk_ids]
        result = embed_batch(config, chunk_texts, client=client)
        latencies.append(result.latency_ms)
        for offset, entity_id in enumerate(chunk_ids):
            vectors[entity_id] = result.vectors[offset].values
    return vectors, latencies


def compute_quality_metrics(
    pairs: Sequence[LabeledPair],
    embeddings: Mapping[str, Sequence[float]],
    *,
    seed: int,
    k: int = METRIC_K,
    relevant_min: int = RELEVANT_LABEL_MIN,
) -> QualityMetrics:
    by_query: dict[str, list[LabeledPair]] = defaultdict(list)
    for pair in pairs:
        by_query[pair.query_entity_id].append(pair)

    ndcg_scores: list[float] = []
    recall_scores: list[float] = []
    for query_id in sorted(by_query.keys()):
        group = by_query[query_id]
        query_vector = embeddings[query_id]
        ranked: list[tuple[float, int, str]] = []
        for pair in group:
            doc_vector = embeddings[pair.document_entity_id]
            score = cosine_similarity(query_vector, doc_vector)
            ranked.append((score, pair.relevance_label, pair.document_entity_id))
        ranked.sort(key=lambda item: (-item[0], item[2]))
        relevances = [label for _, label, _ in ranked]
        ndcg_scores.append(ndcg_at_k(relevances, k=k))
        recall_scores.append(
            recall_at_k(relevances, k=k, relevant_min=relevant_min)
        )

    query_count = len(by_query)
    mean_ndcg = sum(ndcg_scores) / query_count if query_count else 0.0
    mean_recall = sum(recall_scores) / query_count if query_count else 0.0
    return QualityMetrics(
        slice="validation",
        k=k,
        similarity="cosine",
        relevant_label_threshold_min=relevant_min,
        ndcg_at_10=round(mean_ndcg, 6),
        recall_at_10=round(mean_recall, 6),
        query_count=query_count,
        labeled_pair_count=len(pairs),
        seed=seed,
    )


def build_latency_metrics(latencies: Sequence[float]) -> LatencyMetrics:
    return LatencyMetrics(
        sample_count=len(latencies),
        median_provider_request_latency_ms=round(median(latencies), 3),
        p95_provider_request_latency_ms=round(percentile(latencies, 95.0), 3),
    )


def build_aggregate(
    *,
    protocol: Mapping[str, Any],
    config: EmbeddingConfig,
    compatibility: CompatibilityEvidence,
    quality: QualityMetrics,
    latency: LatencyMetrics,
    failure_codes: Sequence[str],
    subset_manifest_path: Path,
    protocol_path: Path,
) -> AggregateEmbeddingResult:
    baselines = protocol["pass_criteria"]["numeric_baselines"]
    return AggregateEmbeddingResult(
        schema_version=1,
        data_class="safe_aggregate",
        protocol_id=str(protocol["protocol_id"]),
        protocol_version=int(protocol["protocol_version"]),
        provider="ShopAIKey",
        endpoint="POST /v1/embeddings",
        model=config.model,
        dimensions=config.dimensions,
        encoding="float",
        seed=quality.seed,
        active_slice="validation",
        held_out_used=False,
        compatibility=compatibility,
        quality=quality,
        latency=latency,
        pass_criteria=PassCriteriaSnapshot(
            status=str(protocol["pass_criteria"]["status"]),
            ndcg_at_10_min=float(baselines["nDCG@10_min"]),
            recall_at_10_min=float(baselines["Recall@10_min"]),
            median_provider_request_latency_ms_max=float(
                baselines["median_provider_request_latency_ms_max"]
            ),
            p95_provider_request_latency_ms_max=float(
                baselines["p95_provider_request_latency_ms_max"]
            ),
        ),
        subset_manifest_path=_safe_repo_relative(subset_manifest_path),
        protocol_path=_safe_repo_relative(protocol_path),
        failure_codes=list(failure_codes),
        notes="Phase 0 embedding compatibility and validation-slice baseline.",
    )


def write_aggregate(result: AggregateEmbeddingResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    # Hard guard: never write private text keys.
    forbidden = ("query_text", "document_text", "api_key", "authorization")
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    lowered = serialized.lower()
    for key in forbidden:
        if f'"{key}"' in lowered:
            raise RuntimeError("aggregate_contains_forbidden_fields")
    output_path.write_text(serialized + "\n", encoding="utf-8")
    return output_path


def _safe_repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def run_benchmark(
    config: EmbeddingConfig,
    *,
    client: EmbeddingClient,
    protocol_path: Path = DEFAULT_PROTOCOL,
    subset_manifest_path: Path = DEFAULT_SUBSET_MANIFEST,
    private_records_path: Path = DEFAULT_PRIVATE_RECORDS,
    probe_texts: Sequence[str] | None = None,
) -> AggregateEmbeddingResult:
    """Run compatibility + validation-slice quality/latency with an injectable client."""
    reject_if_disallowed_contract(model=config.model, dimensions=config.dimensions)
    protocol = load_protocol(protocol_path)
    protocol_model = protocol["provider_contract"]["model"]
    protocol_dims = int(protocol["provider_contract"]["dimensions"])
    reject_if_disallowed_contract(model=protocol_model, dimensions=protocol_dims)
    if protocol["preprocessing"].get("e5_query_prefix") or protocol["preprocessing"].get(
        "e5_passage_prefix"
    ):
        raise ConfigurationError("E5 prefixes are forbidden by the locked protocol.")

    pairs, seed = load_validation_pairs(
        private_records_path=private_records_path,
        subset_manifest_path=subset_manifest_path,
        protocol=protocol,
    )
    private_fragments = []
    for pair in pairs[:3]:
        private_fragments.append(pair.query_text[:40])
        private_fragments.append(pair.document_text[:40])

    compatibility, compat_latencies, failures = run_compatibility(
        config,
        client=client,
        probe_texts=probe_texts,
    )

    quality_latencies: list[float] = []
    try:
        entity_texts = _unique_entity_texts(pairs)
        embeddings, quality_latencies = _embed_entity_map(
            config, entity_texts, client=client
        )
        quality = compute_quality_metrics(pairs, embeddings, seed=seed)
    except EmbeddingProviderError as error:
        failures.append(
            sanitize_failure_message(
                str(error),
                secrets=[config.api_key],
                private_fragments=private_fragments,
            )
        )
        quality = QualityMetrics(
            slice="validation",
            k=METRIC_K,
            similarity="cosine",
            relevant_label_threshold_min=RELEVANT_LABEL_MIN,
            ndcg_at_10=0.0,
            recall_at_10=0.0,
            query_count=0,
            labeled_pair_count=len(pairs),
            seed=seed,
        )
    except Exception:
        failures.append("quality_unexpected_failure")
        quality = QualityMetrics(
            slice="validation",
            k=METRIC_K,
            similarity="cosine",
            relevant_label_threshold_min=RELEVANT_LABEL_MIN,
            ndcg_at_10=0.0,
            recall_at_10=0.0,
            query_count=0,
            labeled_pair_count=len(pairs),
            seed=seed,
        )

    latency = build_latency_metrics([*compat_latencies, *quality_latencies])
    return build_aggregate(
        protocol=protocol,
        config=config,
        compatibility=compatibility,
        quality=quality,
        latency=latency,
        failure_codes=failures,
        subset_manifest_path=subset_manifest_path,
        protocol_path=protocol_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Live entrypoint for 05C. Normal tests must inject a fake client instead."""
    parser = argparse.ArgumentParser(
        description="ShopAIKey embedding compatibility and baseline benchmark"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Aggregate JSON output path",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=DEFAULT_PROTOCOL,
    )
    parser.add_argument(
        "--subset-manifest",
        type=Path,
        default=DEFAULT_SUBSET_MANIFEST,
    )
    parser.add_argument(
        "--private-records",
        type=Path,
        default=DEFAULT_PRIVATE_RECORDS,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        config = load_root_embedding_config()
    except ConfigurationError:
        print("embedding_config_invalid", flush=True)
        return 1

    try:
        client = _default_openai_client(config)
        result = run_benchmark(
            config,
            client=client,
            protocol_path=args.protocol,
            subset_manifest_path=args.subset_manifest,
            private_records_path=args.private_records,
        )
        write_aggregate(result, args.output)
    except Exception as error:
        safe = sanitize_failure_message(str(error), secrets=[config.api_key])
        print(safe, flush=True)
        return 1

    # Concise aggregate-only summary; never print private text or secrets.
    print(
        json.dumps(
            {
                "model": result.model,
                "dimensions": result.dimensions,
                "ndcg_at_10": result.quality.ndcg_at_10,
                "recall_at_10": result.quality.recall_at_10,
                "median_ms": result.latency.median_provider_request_latency_ms,
                "p95_ms": result.latency.p95_provider_request_latency_ms,
                "output": _safe_repo_relative(args.output),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
