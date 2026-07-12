"""Versioned Job embedding text and locked ShopAIKey embedding adapter.

Owns:

- deterministic Job representation builder (title, summary, responsibilities,
  required skills, preferred skills only)
- shared whitespace normalization and E5-prefix stripping
- locked ``text-embedding-3-small`` / 1536 / float contract validation
- injectable production adapter with batch size ≤ 16, one transient retry,
  ordered finite-vector validation, and secret-safe failures

Phase 0 evaluation reuses the shared primitives from this module so production
and diagnostics do not diverge on contract rules.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, cast, runtime_checkable

from app.config import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    REDACTED,
    Settings,
)
from app.schemas.job_post import JobPostExtraction, JobSkill

# ---------------------------------------------------------------------------
# Locked contract constants
# ---------------------------------------------------------------------------

JOB_TEXT_REPRESENTATION_VERSION: Final[str] = "job_embedding_text_v1"
DEFAULT_MAX_BATCH_SIZE: Final[int] = 16
DEFAULT_TIMEOUT_SECONDS: Final[int] = 30
MAX_TRANSIENT_RETRIES: Final[int] = 1
EMBEDDING_ENCODING: Final[str] = "float"

_E5_QUERY_PREFIX: Final[str] = "query: "
_E5_PASSAGE_PREFIX: Final[str] = "passage: "
_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_SENSITIVE_MARKERS: Final[tuple[str, ...]] = (
    "authorization",
    "apikey",
    "api_key",
    "bearer",
    "query_text",
    "document_text",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EmbeddingConfigurationError(RuntimeError):
    """Invalid embedding configuration (never carries secrets)."""


class EmbeddingProviderError(RuntimeError):
    """Sanitized provider/validation failure; never carries secrets or raw text.

    ``str(error)`` is a stable alphanumeric code only.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"EmbeddingProviderError(code={self.code!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


class JobEmbeddingErrorCode(StrEnum):
    """Stable production failure codes for Job embedding operations."""

    TIMEOUT = "embedding_timeout"
    RATE_LIMIT = "embedding_rate_limit"
    CANCELLED = "embedding_cancelled"
    PROVIDER_ERROR = "embedding_provider_error"
    CONFIG = "embedding_config_error"
    MODEL_MISMATCH = "model_mismatch"
    VECTOR_COUNT_MISMATCH = "vector_count_mismatch"
    ORDERING_VIOLATION = "ordering_violation"
    DIMENSION_MISMATCH = "dimension_mismatch"
    NON_FINITE_VALUE = "non_finite_value"
    EMPTY_BATCH = "empty_batch"
    BATCH_SIZE_EXCEEDED = "batch_size_exceeded"
    DUPLICATE_VECTOR_INDEX = "duplicate_vector_index"


class JobEmbeddingError(Exception):
    """Sanitized Job embedding failure (code-only str/repr; no chained secrets)."""

    def __init__(self, code: JobEmbeddingErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"JobEmbeddingError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One embedding vector with its input-order index."""

    index: int
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class JobEmbeddingFields:
    """Minimal Job surface for embedding text (no salary/URL/HTML/match)."""

    title: str | None = None
    summary: str = ""
    responsibilities: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class JobEmbeddingResult:
    """Ordered validated vectors plus version/model/dimension identity."""

    vectors: tuple[EmbeddingVector, ...]
    model: str
    dimensions: int
    representation_version: str
    encoding: str = EMBEDDING_ENCODING

    @property
    def identity(self) -> dict[str, object]:
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "representation_version": self.representation_version,
            "encoding": self.encoding,
        }


IsCancelledFn = Callable[[], bool]
EmbeddingsFactory = Callable[..., "EmbeddingsClientLike"]


@runtime_checkable
class EmbeddingsClientLike(Protocol):
    """Minimal OpenAIEmbeddings surface used by the production adapter."""

    def embed_documents(
        self,
        texts: list[str],
        chunk_size: int | None = None,
        **kwargs: object,
    ) -> list[list[float]]: ...


# ---------------------------------------------------------------------------
# Shared contract primitives (also consumed by Phase 0 benchmark)
# ---------------------------------------------------------------------------


def reject_if_disallowed_contract(*, model: str, dimensions: int) -> None:
    """Fail closed unless the locked model and dimension pair is requested."""
    if model != ALLOWED_EMBEDDING_MODEL or dimensions != ALLOWED_EMBEDDING_DIMENSIONS:
        raise EmbeddingConfigurationError(
            "Disallowed embedding contract: only "
            f"{ALLOWED_EMBEDDING_MODEL} with dimensions="
            f"{ALLOWED_EMBEDDING_DIMENSIONS} is permitted."
        )


def normalize_embedding_text(text: str) -> str:
    """Strip and collapse internal whitespace. Never apply E5 prefixes.

    Accidental leading ``query: `` / ``passage: `` tokens are stripped rather
    than forwarded to ShopAIKey.
    """
    cleaned = text
    lowered = cleaned.lower()
    if lowered.startswith(_E5_QUERY_PREFIX):
        cleaned = cleaned[len(_E5_QUERY_PREFIX) :]
    elif lowered.startswith(_E5_PASSAGE_PREFIX):
        cleaned = cleaned[len(_E5_PASSAGE_PREFIX) :]
    return _WHITESPACE_RE.sub(" ", cleaned.strip())


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
    cleaned = re.sub(r"[^a-zA-Z0-9_.: -]", "", message).strip()
    if not cleaned or len(cleaned) > 120:
        return "sanitized_provider_failure"
    return cleaned


def validate_embedding_vectors(
    *,
    input_count: int,
    vectors: Sequence[EmbeddingVector],
    expected_dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
) -> None:
    """Validate count, 0..n-1 order, exact dimensions, and finite floats."""
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


def vectors_from_ordered_rows(
    rows: Sequence[Sequence[float]],
    *,
    input_count: int | None = None,
    expected_dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
) -> tuple[EmbeddingVector, ...]:
    """Build indexed vectors from an ordered list of float rows and validate.

    ``input_count`` defaults to ``len(rows)``; pass the original request size to
    detect truncated or oversized provider responses.
    """
    expected = len(rows) if input_count is None else input_count
    if len(rows) != expected:
        raise EmbeddingProviderError("vector_count_mismatch")
    vectors = tuple(
        EmbeddingVector(index=index, values=tuple(float(v) for v in row))
        for index, row in enumerate(rows)
    )
    validate_embedding_vectors(
        input_count=expected,
        vectors=vectors,
        expected_dimensions=expected_dimensions,
    )
    return vectors


# ---------------------------------------------------------------------------
# Job representation builder
# ---------------------------------------------------------------------------


def _skill_display_name(skill: JobSkill | str) -> str:
    if isinstance(skill, str):
        return skill.strip()
    return skill.skill.display_name.strip()


def job_fields_from_extraction(job: JobPostExtraction) -> JobEmbeddingFields:
    """Project a validated Job extraction into embedding-only fields."""
    return JobEmbeddingFields(
        title=job.title,
        summary=job.summary,
        responsibilities=tuple(job.responsibilities),
        required_skills=tuple(
            _skill_display_name(item) for item in job.required_skills
        ),
        preferred_skills=tuple(
            _skill_display_name(item) for item in job.preferred_skills
        ),
    )


def _field_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _join_list(items: Sequence[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return ", ".join(cleaned)


def build_job_embedding_text(
    job: JobPostExtraction | JobEmbeddingFields,
) -> str:
    """Build versioned deterministic Job embedding text.

    Source order is fixed as: title, summary, responsibilities, required
    skills, preferred skills. Salary, company, location, raw HTML, source URL,
    quality labels, and match features are never included. No E5 prefixes are
    added.
    """
    fields = (
        job
        if isinstance(job, JobEmbeddingFields)
        else job_fields_from_extraction(job)
    )
    parts = [
        _field_text(fields.title),
        _field_text(fields.summary),
        _join_list(fields.responsibilities),
        _join_list(fields.required_skills),
        _join_list(fields.preferred_skills),
    ]
    # Preserve section order; empty sections collapse under whitespace normalize.
    assembled = "\n".join(parts)
    return normalize_embedding_text(assembled)


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


def classify_embedding_failure(exc: BaseException) -> JobEmbeddingErrorCode:
    """Map a provider/runtime exception to a stable sanitized code."""
    if isinstance(exc, JobEmbeddingError):
        return exc.code
    if isinstance(exc, EmbeddingProviderError):
        try:
            return JobEmbeddingErrorCode(exc.code)
        except ValueError:
            return JobEmbeddingErrorCode.PROVIDER_ERROR
    if isinstance(exc, EmbeddingConfigurationError):
        return JobEmbeddingErrorCode.CONFIG
    if isinstance(exc, TimeoutError):
        return JobEmbeddingErrorCode.TIMEOUT

    type_name = type(exc).__name__.lower()
    module_name = type(exc).__module__.lower()
    combined = f"{module_name}.{type_name}"

    if "cancel" in type_name or "cancelled" in type_name or "canceled" in type_name:
        return JobEmbeddingErrorCode.CANCELLED
    if "timeout" in type_name or "timeout" in combined:
        return JobEmbeddingErrorCode.TIMEOUT
    if "ratelimit" in type_name.replace("_", "") or "rate_limit" in type_name:
        return JobEmbeddingErrorCode.RATE_LIMIT

    try:
        message = str(exc).lower()
    except Exception:
        message = ""
    if "cancelled" in message or "canceled" in message:
        return JobEmbeddingErrorCode.CANCELLED
    if "timeout" in message or "timed out" in message or "deadline exceeded" in message:
        return JobEmbeddingErrorCode.TIMEOUT
    if (
        "rate limit" in message
        or "rate_limit" in message
        or "too many requests" in message
        or "429" in message
    ):
        return JobEmbeddingErrorCode.RATE_LIMIT
    return JobEmbeddingErrorCode.PROVIDER_ERROR


def is_transient_embedding_failure(code: JobEmbeddingErrorCode) -> bool:
    """True only for the single allowed retry class (timeout / rate limit)."""
    return code in {
        JobEmbeddingErrorCode.TIMEOUT,
        JobEmbeddingErrorCode.RATE_LIMIT,
    }


def _provider_error_to_job_error(exc: EmbeddingProviderError) -> JobEmbeddingError:
    try:
        return JobEmbeddingError(JobEmbeddingErrorCode(exc.code))
    except ValueError:
        return JobEmbeddingError(JobEmbeddingErrorCode.PROVIDER_ERROR)


# ---------------------------------------------------------------------------
# Production adapter
# ---------------------------------------------------------------------------


def _default_embeddings_factory(**kwargs: Any) -> EmbeddingsClientLike:
    """Construct live OpenAIEmbeddings. Tests inject fakes instead."""
    from langchain_openai import OpenAIEmbeddings

    # OpenAIEmbeddings accepts a wide keyword surface; kwargs are built only by
    # model_construction_kwargs (api_key/base_url/model/dimensions/...).
    return cast(EmbeddingsClientLike, OpenAIEmbeddings(**kwargs))


class JobEmbeddingService:
    """Injectable production adapter for locked ShopAIKey Job embeddings.

    Construction uses only typed settings / explicit kwargs. The embeddings
    factory is injectable so normal tests never open a network connection.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = ALLOWED_EMBEDDING_MODEL,
        dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        embeddings_factory: EmbeddingsFactory | None = None,
        is_cancelled: IsCancelledFn | None = None,
    ) -> None:
        if not base_url or not api_key:
            raise JobEmbeddingError(JobEmbeddingErrorCode.CONFIG)
        try:
            reject_if_disallowed_contract(model=model, dimensions=dimensions)
        except EmbeddingConfigurationError:
            raise JobEmbeddingError(JobEmbeddingErrorCode.CONFIG) from None
        if max_batch_size < 1 or max_batch_size > DEFAULT_MAX_BATCH_SIZE:
            raise JobEmbeddingError(JobEmbeddingErrorCode.CONFIG)
        if timeout_seconds <= 0:
            raise JobEmbeddingError(JobEmbeddingErrorCode.CONFIG)

        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._max_batch_size = max_batch_size
        self._timeout_seconds = timeout_seconds
        self._embeddings_factory: EmbeddingsFactory = (
            embeddings_factory or _default_embeddings_factory
        )
        self._is_cancelled = is_cancelled
        self._representation_version = JOB_TEXT_REPRESENTATION_VERSION

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        embeddings_factory: EmbeddingsFactory | None = None,
        is_cancelled: IsCancelledFn | None = None,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> JobEmbeddingService:
        """Build from typed root settings without reading root ``.env``."""
        return cls(
            base_url=settings.shopaikey_base_url,
            api_key=settings.shopaikey_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            max_batch_size=max_batch_size,
            timeout_seconds=timeout_seconds,
            embeddings_factory=embeddings_factory,
            is_cancelled=is_cancelled,
        )

    def __repr__(self) -> str:
        return (
            "JobEmbeddingService("
            f"base_url={self._base_url!r}, "
            f"api_key={REDACTED!r}, "
            f"model={self._model!r}, "
            f"dimensions={self._dimensions!r}, "
            f"max_batch_size={self._max_batch_size!r}, "
            f"timeout_seconds={self._timeout_seconds!r}, "
            f"representation_version={self._representation_version!r}, "
            f"encoding={EMBEDDING_ENCODING!r})"
        )

    __str__ = __repr__

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def max_batch_size(self) -> int:
        return self._max_batch_size

    @property
    def representation_version(self) -> str:
        return self._representation_version

    def model_construction_kwargs(self) -> dict[str, object]:
        """Return exact OpenAIEmbeddings kwargs for the locked contract."""
        return {
            "model": self._model,
            "dimensions": self._dimensions,
            "api_key": self._api_key,
            "base_url": self._base_url,
            "chunk_size": self._max_batch_size,
            # Application owns the single transient retry budget.
            "max_retries": 0,
            "request_timeout": float(self._timeout_seconds),
            # Avoid tiktoken-side token rechunking; batches are already ≤ 16.
            "check_embedding_ctx_length": False,
        }

    def build_client(self) -> EmbeddingsClientLike:
        """Construct the embeddings client via the injectable factory."""
        self._raise_if_cancelled()
        return self._embeddings_factory(**self.model_construction_kwargs())

    def build_job_text(self, job: JobPostExtraction | JobEmbeddingFields) -> str:
        """Public entry for the versioned Job representation builder."""
        return build_job_embedding_text(job)

    def embed_job(
        self,
        job: JobPostExtraction | JobEmbeddingFields,
        *,
        client: EmbeddingsClientLike | None = None,
    ) -> JobEmbeddingResult:
        """Embed one Job representation (scalar path)."""
        return self.embed_texts([build_job_embedding_text(job)], client=client)

    def embed_jobs(
        self,
        jobs: Sequence[JobPostExtraction | JobEmbeddingFields],
        *,
        client: EmbeddingsClientLike | None = None,
    ) -> JobEmbeddingResult:
        """Embed a batch of Jobs (1..max_batch_size), preserving input order."""
        texts = [build_job_embedding_text(job) for job in jobs]
        return self.embed_texts(texts, client=client)

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        client: EmbeddingsClientLike | None = None,
    ) -> JobEmbeddingResult:
        """Embed pre-built texts under the locked contract.

        Validates batch bounds, normalizes inputs (no E5 prefixes), preserves
        input/output order, and requires exactly 1536 finite floats per vector.
        """
        try:
            reject_if_disallowed_contract(
                model=self._model, dimensions=self._dimensions
            )
        except EmbeddingConfigurationError:
            raise JobEmbeddingError(JobEmbeddingErrorCode.CONFIG) from None

        if not texts:
            raise JobEmbeddingError(JobEmbeddingErrorCode.EMPTY_BATCH)
        if len(texts) > self._max_batch_size:
            raise JobEmbeddingError(JobEmbeddingErrorCode.BATCH_SIZE_EXCEEDED)

        normalized = [normalize_embedding_text(text) for text in texts]
        active = client or self.build_client()
        rows = self._embed_with_retry(active, normalized)
        try:
            vectors = vectors_from_ordered_rows(
                rows,
                input_count=len(normalized),
                expected_dimensions=self._dimensions,
            )
        except EmbeddingProviderError as exc:
            raise _provider_error_to_job_error(exc) from None

        return JobEmbeddingResult(
            vectors=vectors,
            model=self._model,
            dimensions=self._dimensions,
            representation_version=self._representation_version,
            encoding=EMBEDDING_ENCODING,
        )

    def _embed_with_retry(
        self,
        client: EmbeddingsClientLike,
        texts: list[str],
    ) -> list[list[float]]:
        attempts = 0
        last_code = JobEmbeddingErrorCode.PROVIDER_ERROR
        while attempts <= MAX_TRANSIENT_RETRIES:
            self._raise_if_cancelled()
            try:
                rows = client.embed_documents(texts)
            except JobEmbeddingError as exc:
                last_code = exc.code
                if (
                    attempts < MAX_TRANSIENT_RETRIES
                    and is_transient_embedding_failure(exc.code)
                ):
                    attempts += 1
                    continue
                raise
            except Exception as exc:
                last_code = classify_embedding_failure(exc)
                if (
                    attempts < MAX_TRANSIENT_RETRIES
                    and is_transient_embedding_failure(last_code)
                ):
                    attempts += 1
                    continue
                raise JobEmbeddingError(last_code) from None
            if not isinstance(rows, list):
                raise JobEmbeddingError(JobEmbeddingErrorCode.PROVIDER_ERROR)
            return rows
        raise JobEmbeddingError(last_code)

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled is not None and self._is_cancelled():
            raise JobEmbeddingError(JobEmbeddingErrorCode.CANCELLED)


__all__ = [
    "ALLOWED_EMBEDDING_DIMENSIONS",
    "ALLOWED_EMBEDDING_MODEL",
    "DEFAULT_MAX_BATCH_SIZE",
    "DEFAULT_TIMEOUT_SECONDS",
    "EMBEDDING_ENCODING",
    "JOB_TEXT_REPRESENTATION_VERSION",
    "MAX_TRANSIENT_RETRIES",
    "EmbeddingConfigurationError",
    "EmbeddingProviderError",
    "EmbeddingVector",
    "EmbeddingsClientLike",
    "EmbeddingsFactory",
    "IsCancelledFn",
    "JobEmbeddingError",
    "JobEmbeddingErrorCode",
    "JobEmbeddingFields",
    "JobEmbeddingResult",
    "JobEmbeddingService",
    "build_job_embedding_text",
    "classify_embedding_failure",
    "is_transient_embedding_failure",
    "job_fields_from_extraction",
    "normalize_embedding_text",
    "reject_if_disallowed_contract",
    "sanitize_failure_message",
    "validate_embedding_vectors",
    "vectors_from_ordered_rows",
]
