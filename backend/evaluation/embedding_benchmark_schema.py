"""Typed schemas for the focused ShopAIKey embedding benchmark (Phase 0).

Aggregate records intentionally exclude raw query/document text and secrets.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompatibilityEvidence(BaseModel):
    """Scalar/batch response-shape checks. No payload or text fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    dimensions: int = Field(ge=1)
    encoding: Literal["float"] = "float"
    e5_prefixes_applied: Literal[False] = False
    scalar_ok: bool
    batch_ok: bool
    ordering_preserved: bool
    finite_floats_only: bool
    vector_length_ok: bool
    scalar_batch_equivalence: bool
    max_batch_size: int = Field(ge=1)
    sanitized_failure_ok: bool


class QualityMetrics(BaseModel):
    """Validation-slice retrieval quality. Aggregate scores only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slice: Literal["validation"] = "validation"
    k: int = Field(ge=1)
    similarity: Literal["cosine"] = "cosine"
    relevant_label_threshold_min: int = Field(ge=0, le=3)
    ndcg_at_10: float = Field(ge=0.0, le=1.0)
    recall_at_10: float = Field(ge=0.0, le=1.0)
    query_count: int = Field(ge=0)
    labeled_pair_count: int = Field(ge=0)
    seed: int


class LatencyMetrics(BaseModel):
    """Provider request latency percentiles in milliseconds."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_count: int = Field(ge=0)
    median_provider_request_latency_ms: float = Field(ge=0.0)
    p95_provider_request_latency_ms: float = Field(ge=0.0)


class PassCriteriaSnapshot(BaseModel):
    """Pre-recorded baselines copied for comparison; not post-hoc edits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    ndcg_at_10_min: float
    recall_at_10_min: float
    median_provider_request_latency_ms_max: float
    p95_provider_request_latency_ms_max: float


class AggregateEmbeddingResult(BaseModel):
    """Machine-readable aggregate artifact (safe metrics only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    data_class: Literal["safe_aggregate"] = "safe_aggregate"
    protocol_id: str
    protocol_version: int
    provider: Literal["ShopAIKey"] = "ShopAIKey"
    endpoint: Literal["POST /v1/embeddings"] = "POST /v1/embeddings"
    model: str
    dimensions: int
    encoding: Literal["float"] = "float"
    seed: int
    active_slice: Literal["validation"] = "validation"
    held_out_used: Literal[False] = False
    compatibility: CompatibilityEvidence
    quality: QualityMetrics
    latency: LatencyMetrics
    pass_criteria: PassCriteriaSnapshot
    subset_manifest_path: str
    protocol_path: str
    failure_codes: list[str] = Field(default_factory=list)
    notes: str = ""
