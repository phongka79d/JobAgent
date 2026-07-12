"""Fake/socket-blocked tests for versioned Job embeddings (Plan 5 03B).

Never opens a provider network connection. Never logs API keys or raw Job text
into durable exception/repr surfaces.
"""

from __future__ import annotations

import hashlib
import math
import socket
from collections.abc import Sequence
from typing import Any

import pytest
from app.config import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    REDACTED,
    Settings,
    load_settings,
)
from app.schemas.candidate import SkillRef, SkillStatus
from app.schemas.job_post import (
    EmploymentType,
    JdQuality,
    JobPostExtraction,
    JobSeniority,
    JobSkill,
    JobWorkMode,
)
from app.services.embeddings import (
    DEFAULT_MAX_BATCH_SIZE,
    JOB_TEXT_REPRESENTATION_VERSION,
    MAX_TRANSIENT_RETRIES,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingVector,
    JobEmbeddingError,
    JobEmbeddingErrorCode,
    JobEmbeddingFields,
    JobEmbeddingService,
    build_job_embedding_text,
    classify_embedding_failure,
    is_transient_embedding_failure,
    normalize_embedding_text,
    reject_if_disallowed_contract,
    sanitize_failure_message,
    validate_embedding_vectors,
)

SENTINEL_API_KEY = "sentinel-embedding-service-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-embedding-never-emit"
SENTINEL_BASE_URL = "https://provider.example/v1"
PRIVATE_JOB_MARKER = "PRIVATE_JOB_TEXT_MUST_NOT_APPEAR"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _unit_vector_from_text(text: str, dimensions: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(block), 4):
            if len(values) >= dimensions:
                break
            chunk = int.from_bytes(block[index : index + 4], "big")
            values.append((chunk / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class FakeEmbeddingsClient:
    """Injectable OpenAIEmbeddings stand-in; never uses the network."""

    def __init__(
        self,
        *,
        dimensions: int = ALLOWED_EMBEDDING_DIMENSIONS,
        fail_on_call: BaseException | None = None,
        fail_sequence: list[BaseException] | None = None,
        wrong_count: bool = False,
        wrong_dimensions: bool = False,
        non_finite: bool = False,
        permute_order: bool = False,
        empty_response: bool = False,
    ) -> None:
        self.dimensions = dimensions
        self.fail_on_call = fail_on_call
        self.fail_sequence = list(fail_sequence or [])
        self.wrong_count = wrong_count
        self.wrong_dimensions = wrong_dimensions
        self.non_finite = non_finite
        self.permute_order = permute_order
        self.empty_response = empty_response
        self.calls: list[list[str]] = []
        self.kwargs_log: list[dict[str, Any]] = []

    def embed_documents(
        self,
        texts: list[str],
        chunk_size: int | None = None,
        **kwargs: object,
    ) -> list[list[float]]:
        del chunk_size
        self.calls.append(list(texts))
        self.kwargs_log.append(dict(kwargs))
        if self.fail_sequence:
            raise self.fail_sequence.pop(0)
        if self.fail_on_call is not None:
            raise self.fail_on_call
        if self.empty_response:
            return []
        rows: list[list[float]] = []
        for index, text in enumerate(texts):
            dim = 8 if self.wrong_dimensions else self.dimensions
            values = _unit_vector_from_text(text, dim)
            if self.non_finite and index == 0:
                values[0] = float("nan")
            rows.append(values)
        if self.wrong_count and rows:
            rows = rows[:-1]
        if self.permute_order and len(rows) > 1:
            rows = list(reversed(rows))
        return rows


class RecordingFactory:
    def __init__(self, template: FakeEmbeddingsClient | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.template = template or FakeEmbeddingsClient()

    def __call__(self, **kwargs: object) -> FakeEmbeddingsClient:
        self.calls.append(dict(kwargs))
        return self.template


def _settings(**overrides: str) -> Settings:
    environ = {
        "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
        "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
        "SHOPAIKEY_BASE_URL": SENTINEL_BASE_URL,
        "EMBEDDING_MODEL": ALLOWED_EMBEDDING_MODEL,
        "EMBEDDING_DIMENSIONS": str(ALLOWED_EMBEDDING_DIMENSIONS),
        **overrides,
    }
    return load_settings(environ=environ)


def _skill(name: str) -> JobSkill:
    return JobSkill(
        skill=SkillRef(
            canonical_key=name.lower().replace(" ", "_"),
            display_name=name,
            status=SkillStatus.PROVISIONAL,
            confidence=0.9,
        ),
        confidence=0.8,
        evidence=["seen in JD"],
    )


def _extraction(**overrides: object) -> JobPostExtraction:
    base: dict[str, object] = {
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "summary": "Build reliable APIs",
        "responsibilities": ["Design services", "Own on-call"],
        "required_skills": [_skill("Python"), _skill("FastAPI")],
        "preferred_skills": [_skill("Kubernetes")],
        "seniority": JobSeniority.MID,
        "min_experience_years": 3.0,
        "max_experience_years": 6.0,
        "location": "Remote",
        "work_mode": JobWorkMode.REMOTE,
        "employment_type": EmploymentType.FULL_TIME,
        "education_requirements": ["BS Computer Science"],
        "language_requirements": ["English"],
        "salary_text": "$150,000 - $180,000",
        "job_family": "Software Engineering",
        "extraction_confidence": 0.9,
        "jd_quality": JdQuality.FULL,
    }
    base.update(overrides)
    return JobPostExtraction.model_validate(base)


def _service(
    factory: RecordingFactory | None = None,
    *,
    is_cancelled: Any = None,
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
) -> tuple[JobEmbeddingService, RecordingFactory]:
    recording = factory or RecordingFactory()
    service = JobEmbeddingService.from_settings(
        _settings(),
        embeddings_factory=recording,
        is_cancelled=is_cancelled,
        max_batch_size=max_batch_size,
    )
    return service, recording


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("network socket opened during embedding tests")

    monkeypatch.setattr(socket, "socket", _blocked)


# ---------------------------------------------------------------------------
# Representation builder
# ---------------------------------------------------------------------------


def test_job_text_source_order_and_excludes_non_embedding_fields(
    block_sockets: None,
) -> None:
    del block_sockets
    job = _extraction(
        title="Title A",
        summary="Summary B",
        responsibilities=["Resp C", "Resp D"],
        required_skills=[_skill("ReqSkill")],
        preferred_skills=[_skill("PrefSkill")],
        salary_text="$999999",
        company="SecretCo",
        location="https://internal.example/jd",
    )
    text = build_job_embedding_text(job)
    assert text == normalize_embedding_text(
        "Title A\nSummary B\nResp C, Resp D\nReqSkill\nPrefSkill"
    )
    assert "SecretCo" not in text
    assert "$999999" not in text
    assert "https://" not in text
    assert "Software Engineering" not in text
    assert "BS Computer Science" not in text
    assert "English" not in text
    assert "seen in JD" not in text
    assert not text.lower().startswith("query:")
    assert not text.lower().startswith("passage:")


def test_job_text_deterministic_and_versioned(block_sockets: None) -> None:
    del block_sockets
    fields = JobEmbeddingFields(
        title="  Eng  ",
        summary="  line   one  ",
        responsibilities=("Do  work",),
        required_skills=("Python",),
        preferred_skills=(),
    )
    first = build_job_embedding_text(fields)
    second = build_job_embedding_text(fields)
    assert first == second
    assert first == "Eng line one Do work Python"
    service, _ = _service()
    assert service.representation_version == JOB_TEXT_REPRESENTATION_VERSION


def test_job_text_strips_accidental_e5_prefixes(block_sockets: None) -> None:
    del block_sockets
    fields = JobEmbeddingFields(
        title="query: Real Title",
        summary="passage: Real Summary",
        responsibilities=(),
        required_skills=(),
        preferred_skills=(),
    )
    text = build_job_embedding_text(fields)
    assert not text.lower().startswith("query:")
    assert "Real Title" in text
    assert "Real Summary" in text


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


def test_normalize_and_allowlist_shared_with_benchmark(block_sockets: None) -> None:
    del block_sockets
    assert normalize_embedding_text("  a   b  ") == "a b"
    assert normalize_embedding_text("query: hello") == "hello"
    assert normalize_embedding_text("passage: world") == "world"
    with pytest.raises(EmbeddingConfigurationError):
        reject_if_disallowed_contract(model="other", dimensions=1536)
    with pytest.raises(EmbeddingConfigurationError):
        reject_if_disallowed_contract(
            model=ALLOWED_EMBEDDING_MODEL, dimensions=768
        )


def test_validate_vectors_boundaries(block_sockets: None) -> None:
    del block_sockets
    good = tuple(0.01 for _ in range(ALLOWED_EMBEDDING_DIMENSIONS))
    validate_embedding_vectors(
        input_count=1, vectors=(EmbeddingVector(index=0, values=good),)
    )
    with pytest.raises(EmbeddingProviderError, match="ordering_violation"):
        validate_embedding_vectors(
            input_count=1, vectors=(EmbeddingVector(index=1, values=good),)
        )
    with pytest.raises(EmbeddingProviderError, match="dimension_mismatch"):
        validate_embedding_vectors(
            input_count=1,
            vectors=(EmbeddingVector(index=0, values=(0.1, 0.2)),),
        )
    bad = list(good)
    bad[0] = float("nan")
    with pytest.raises(EmbeddingProviderError, match="non_finite_value"):
        validate_embedding_vectors(
            input_count=1,
            vectors=(EmbeddingVector(index=0, values=tuple(bad)),),
        )


# ---------------------------------------------------------------------------
# Service: scalar / batch / order / identity
# ---------------------------------------------------------------------------


def test_from_settings_locked_construction_kwargs(block_sockets: None) -> None:
    del block_sockets
    service, factory = _service()
    kwargs = service.model_construction_kwargs()
    assert kwargs["model"] == ALLOWED_EMBEDDING_MODEL
    assert kwargs["dimensions"] == ALLOWED_EMBEDDING_DIMENSIONS
    assert kwargs["base_url"] == SENTINEL_BASE_URL
    assert kwargs["api_key"] == SENTINEL_API_KEY
    assert kwargs["chunk_size"] == DEFAULT_MAX_BATCH_SIZE
    assert kwargs["max_retries"] == 0
    assert kwargs["check_embedding_ctx_length"] is False
    assert SENTINEL_API_KEY not in repr(service)
    assert SENTINEL_API_KEY not in str(service)
    assert REDACTED in repr(service)
    assert factory.calls == []


def test_embed_job_scalar_identity_and_dimensions(block_sockets: None) -> None:
    del block_sockets
    service, factory = _service()
    result = service.embed_job(_extraction())
    assert result.model == ALLOWED_EMBEDDING_MODEL
    assert result.dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert result.representation_version == JOB_TEXT_REPRESENTATION_VERSION
    assert result.encoding == "float"
    assert len(result.vectors) == 1
    assert result.vectors[0].index == 0
    assert len(result.vectors[0].values) == ALLOWED_EMBEDDING_DIMENSIONS
    assert all(math.isfinite(v) for v in result.vectors[0].values)
    assert len(factory.calls) == 1
    assert factory.calls[0]["model"] == ALLOWED_EMBEDDING_MODEL
    assert factory.calls[0]["dimensions"] == ALLOWED_EMBEDDING_DIMENSIONS
    # Normalized job text reached the fake (no E5 / no salary).
    sent = factory.template.calls[0][0]
    assert "Backend Engineer" in sent
    assert "$150,000" not in sent
    assert not sent.lower().startswith("query:")


def test_embed_jobs_batch_preserves_order_1_to_16(block_sockets: None) -> None:
    del block_sockets
    service, factory = _service()
    jobs = [
        JobEmbeddingFields(title=f"Job {index}", summary=f"S{index}")
        for index in range(1, 5)
    ]
    result = service.embed_jobs(jobs)
    assert [vector.index for vector in result.vectors] == [0, 1, 2, 3]
    texts = factory.template.calls[0]
    assert len(texts) == 4
    # Distinct titles => distinct deterministic vectors.
    assert result.vectors[0].values != result.vectors[1].values
    for vector in result.vectors:
        assert len(vector.values) == ALLOWED_EMBEDDING_DIMENSIONS


def test_batch_size_boundaries(block_sockets: None) -> None:
    del block_sockets
    service, _ = _service(max_batch_size=2)
    with pytest.raises(JobEmbeddingError) as empty:
        service.embed_texts([])
    assert empty.value.code == JobEmbeddingErrorCode.EMPTY_BATCH
    with pytest.raises(JobEmbeddingError) as oversized:
        service.embed_texts(["a", "b", "c"])
    assert oversized.value.code == JobEmbeddingErrorCode.BATCH_SIZE_EXCEEDED
    # Construction cannot raise max batch above 16.
    with pytest.raises(JobEmbeddingError) as config:
        JobEmbeddingService(
            base_url=SENTINEL_BASE_URL,
            api_key=SENTINEL_API_KEY,
            max_batch_size=17,
        )
    assert config.value.code == JobEmbeddingErrorCode.CONFIG


def test_mismatched_response_count_dimensions_non_finite(
    block_sockets: None,
) -> None:
    del block_sockets
    for kwargs, code in (
        ({"wrong_count": True}, JobEmbeddingErrorCode.VECTOR_COUNT_MISMATCH),
        ({"wrong_dimensions": True}, JobEmbeddingErrorCode.DIMENSION_MISMATCH),
        ({"non_finite": True}, JobEmbeddingErrorCode.NON_FINITE_VALUE),
        ({"empty_response": True}, JobEmbeddingErrorCode.VECTOR_COUNT_MISMATCH),
    ):
        client = FakeEmbeddingsClient(**kwargs)
        service, _ = _service(RecordingFactory(client))
        with pytest.raises(JobEmbeddingError) as raised:
            service.embed_texts(["alpha", "beta"], client=client)
        assert raised.value.code == code
        assert SENTINEL_API_KEY not in str(raised.value)
        assert raised.value.__cause__ is None


def test_permute_order_detected_via_content_when_indexes_rebuilt(
    block_sockets: None,
) -> None:
    """Adapter rebuilds indexes 0..n-1 from row order; swapped rows change mapping."""
    del block_sockets
    client = FakeEmbeddingsClient(permute_order=True)
    service, _ = _service(RecordingFactory(client))
    texts = ["alpha unique", "beta unique"]
    # Scalar baselines.
    scalar_a = service.embed_texts([texts[0]], client=FakeEmbeddingsClient())
    scalar_b = service.embed_texts([texts[1]], client=FakeEmbeddingsClient())
    batch = service.embed_texts(texts, client=client)
    # Permuted fake returns reversed embeddings; index 0 no longer matches scalar A.
    assert batch.vectors[0].values == scalar_b.vectors[0].values
    assert batch.vectors[1].values == scalar_a.vectors[0].values


# ---------------------------------------------------------------------------
# Retry / cancellation / secret safety
# ---------------------------------------------------------------------------


def test_one_transient_retry_on_timeout_then_success(block_sockets: None) -> None:
    del block_sockets
    client = FakeEmbeddingsClient(
        fail_sequence=[TimeoutError("provider timed out")]
    )
    service, _ = _service(RecordingFactory(client))
    result = service.embed_texts(["probe"], client=client)
    assert len(result.vectors) == 1
    assert len(client.calls) == 2  # fail once, retry once


def test_transient_retry_budget_exhausted(block_sockets: None) -> None:
    del block_sockets
    client = FakeEmbeddingsClient(
        fail_sequence=[
            TimeoutError("t1"),
            TimeoutError("t2"),
        ]
    )
    service, _ = _service(RecordingFactory(client))
    with pytest.raises(JobEmbeddingError) as raised:
        service.embed_texts(["probe"], client=client)
    assert raised.value.code == JobEmbeddingErrorCode.TIMEOUT
    assert len(client.calls) == MAX_TRANSIENT_RETRIES + 1
    assert SENTINEL_API_KEY not in str(raised.value)
    assert PRIVATE_JOB_MARKER not in str(raised.value)


def test_rate_limit_is_transient(block_sockets: None) -> None:
    del block_sockets
    assert is_transient_embedding_failure(JobEmbeddingErrorCode.RATE_LIMIT)
    assert is_transient_embedding_failure(JobEmbeddingErrorCode.TIMEOUT)
    assert not is_transient_embedding_failure(JobEmbeddingErrorCode.PROVIDER_ERROR)
    assert classify_embedding_failure(TimeoutError()) == JobEmbeddingErrorCode.TIMEOUT

    class RateLimitError(Exception):
        pass

    assert (
        classify_embedding_failure(RateLimitError("429 rate limit"))
        == JobEmbeddingErrorCode.RATE_LIMIT
    )


def test_cancellation_fails_closed(block_sockets: None) -> None:
    del block_sockets
    cancelled = {"value": True}
    service, _ = _service(is_cancelled=lambda: cancelled["value"])
    with pytest.raises(JobEmbeddingError) as raised:
        service.embed_texts(["probe"])
    assert raised.value.code == JobEmbeddingErrorCode.CANCELLED


def test_errors_and_repr_hide_secrets_and_input_text(block_sockets: None) -> None:
    del block_sockets
    client = FakeEmbeddingsClient(
        fail_on_call=RuntimeError(
            f"Authorization: Bearer {SENTINEL_API_KEY} body={PRIVATE_JOB_MARKER}"
        )
    )
    service, _ = _service(RecordingFactory(client))
    with pytest.raises(JobEmbeddingError) as raised:
        service.embed_texts([PRIVATE_JOB_MARKER], client=client)
    rendered = str(raised.value)
    assert SENTINEL_API_KEY not in rendered
    assert PRIVATE_JOB_MARKER not in rendered
    assert rendered == JobEmbeddingErrorCode.PROVIDER_ERROR.value
    assert SENTINEL_API_KEY not in repr(service)
    sanitized = sanitize_failure_message(
        f"Authorization Bearer {SENTINEL_API_KEY}",
        secrets=[SENTINEL_API_KEY],
        private_fragments=[PRIVATE_JOB_MARKER],
    )
    assert SENTINEL_API_KEY not in sanitized


def test_disallowed_model_cannot_be_constructed(block_sockets: None) -> None:
    del block_sockets
    with pytest.raises(JobEmbeddingError) as raised:
        JobEmbeddingService(
            base_url=SENTINEL_BASE_URL,
            api_key=SENTINEL_API_KEY,
            model="text-embedding-3-large",
            dimensions=ALLOWED_EMBEDDING_DIMENSIONS,
        )
    assert raised.value.code == JobEmbeddingErrorCode.CONFIG


def test_zero_network_for_required_path(block_sockets: None) -> None:
    del block_sockets
    service, _ = _service()
    jobs: Sequence[JobEmbeddingFields] = (
        JobEmbeddingFields(title="One", summary="A"),
        JobEmbeddingFields(title="Two", summary="B"),
    )
    result = service.embed_jobs(jobs)
    assert len(result.vectors) == 2
    assert result.identity["model"] == ALLOWED_EMBEDDING_MODEL
    assert result.identity["dimensions"] == ALLOWED_EMBEDDING_DIMENSIONS
    assert result.identity["representation_version"] == JOB_TEXT_REPRESENTATION_VERSION
