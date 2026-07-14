"""Unit tests for Job extraction contracts and structured JD service.

Covers Plan 5 §7.1 / §7.4. Schema tests cover exact Pydantic contracts.
Service tests are fake-invoker only — never call the live ShopAIKey provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from inspect import signature
from pathlib import Path
from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from app.db.models.jobs import JOB_JD_QUALITIES
from app.schemas.jobs import (
    JobPostExtraction,
    JobSeniority,
    JobSkill,
    JobWorkMode,
    parse_job_post_extraction,
)
from app.schemas.skills import SkillRef
from app.services.jd_extraction import (
    EXTRACTION_SCHEMA_STRATEGY,
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    FAILURE_PROVIDER_ERROR,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    STRUCTURED_OUTPUT_METHOD,
    STRUCTURED_OUTPUT_STRICT,
    ExtractedJobPost,
    ExtractedJobSkillItem,
    JdExtractionError,
    ShopAIKeyStructuredJdInvoker,
    classify_provider_error,
    extract_job_post_from_text,
    extracted_to_job_post,
)
from app.services.provider_retry import (
    MAX_PROVIDER_RETRIES,
    ProviderRetryError,
    invoke_with_provider_retry,
)
from app.services.skill_normalization import SkillNormalizer
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"

_SKILL_REF_FIELDS = frozenset(
    {"canonical_key", "display_name", "aliases", "category"}
)
_JOB_SKILL_FIELDS = frozenset({"skill", "confidence", "evidence"})
_JOB_POST_EXTRACTION_FIELDS = frozenset(
    {
        "title",
        "company",
        "summary",
        "responsibilities",
        "required_skills",
        "preferred_skills",
        "seniority",
        "min_experience_years",
        "max_experience_years",
        "location",
        "work_mode",
        "extraction_confidence",
    }
)


def _skill_ref(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "canonical_key": "python",
        "display_name": "Python",
        "aliases": ["python3"],
        "category": "language",
    }
    base.update(overrides)
    return base


def _job_skill(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "skill": _skill_ref(),
        "confidence": 0.9,
        "evidence": ["Required: 3+ years Python"],
    }
    base.update(overrides)
    return base


def _extraction(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services"],
        "required_skills": [_job_skill()],
        "preferred_skills": [],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return base


def test_job_skill_exact_fields() -> None:
    skill = JobSkill.model_validate(_job_skill())
    assert set(JobSkill.model_fields) == _JOB_SKILL_FIELDS
    assert set(skill.model_dump()) == _JOB_SKILL_FIELDS
    assert set(skill.skill.model_dump()) == _SKILL_REF_FIELDS
    assert isinstance(skill.skill, SkillRef)


def test_job_post_extraction_exact_fields() -> None:
    doc = JobPostExtraction.model_validate(_extraction())
    assert set(JobPostExtraction.model_fields) == _JOB_POST_EXTRACTION_FIELDS
    assert set(doc.model_dump()) == _JOB_POST_EXTRACTION_FIELDS


def test_valid_document_round_trip() -> None:
    payload = _extraction(
        preferred_skills=[
            _job_skill(
                skill=_skill_ref(
                    canonical_key="fastapi",
                    display_name="FastAPI",
                    aliases=[],
                    category=None,
                ),
                evidence=["Nice to have FastAPI"],
            )
        ]
    )
    doc = parse_job_post_extraction(payload)
    dumped = doc.model_dump(mode="json")
    again = parse_job_post_extraction(dumped)
    assert again.model_dump(mode="json") == dumped
    assert set(dumped) == _JOB_POST_EXTRACTION_FIELDS
    assert "jd_quality" not in dumped
    assert "aliases" not in dumped
    assert "relationships" not in dumped
    assert dumped["preferred_skills"][0]["skill"]["aliases"] == []


def test_jd_quality_cannot_appear_on_extraction() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(jd_quality="full"))
    serialized = JobPostExtraction.model_validate(_extraction()).model_dump(
        mode="json"
    )
    assert "jd_quality" not in serialized
    assert set(serialized.keys()).isdisjoint(JOB_JD_QUALITIES)


def test_nullable_title_company_location_and_experience() -> None:
    doc = JobPostExtraction.model_validate(
        _extraction(
            title=None,
            company=None,
            location=None,
            min_experience_years=None,
            max_experience_years=None,
        )
    )
    assert doc.title is None
    assert doc.company is None
    assert doc.location is None
    assert doc.min_experience_years is None
    assert doc.max_experience_years is None


def test_summary_required_string_and_empty_lists_valid() -> None:
    doc = JobPostExtraction.model_validate(
        _extraction(
            summary="",
            responsibilities=[],
            required_skills=[],
            preferred_skills=[],
        )
    )
    assert doc.summary == ""
    assert doc.responsibilities == []
    assert doc.required_skills == []
    assert doc.preferred_skills == []


def test_summary_null_rejected() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(summary=None))


def test_seniority_and_work_mode_enum_values() -> None:
    assert set(get_args(JobSeniority)) == {
        "intern",
        "junior",
        "mid",
        "senior",
        "lead",
        "unknown",
    }
    assert set(get_args(JobWorkMode)) == {
        "remote",
        "hybrid",
        "onsite",
        "unknown",
    }
    for value in get_args(JobSeniority):
        JobPostExtraction.model_validate(_extraction(seniority=value))
    for value in get_args(JobWorkMode):
        JobPostExtraction.model_validate(_extraction(work_mode=value))


def test_rejects_bad_seniority_and_work_mode() -> None:
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(seniority="principal"))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(work_mode="wfh"))


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_bounds_accepted(confidence: float) -> None:
    skill = JobSkill.model_validate(_job_skill(confidence=confidence))
    doc = JobPostExtraction.model_validate(
        _extraction(extraction_confidence=confidence)
    )
    assert skill.confidence == confidence
    assert doc.extraction_confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(confidence=confidence))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(
            _extraction(extraction_confidence=confidence)
        )


def test_evidence_is_list_of_strings() -> None:
    skill = JobSkill.model_validate(
        _job_skill(evidence=["snippet A", "snippet B"])
    )
    assert skill.evidence == ["snippet A", "snippet B"]
    empty = JobSkill.model_validate(_job_skill(evidence=[]))
    assert empty.evidence == []


def test_evidence_rejects_non_string_items() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=[{"text": "x"}]))
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(evidence=[1, 2]))


def test_nested_skill_ref_validated() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(
            _job_skill(skill=_skill_ref(extra_field="nope"))
        )
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(skill="python"))


def test_all_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        JobSkill.model_validate(_job_skill(weight=1.0))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(jd_quality="full"))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(aliases=["x"]))
    with pytest.raises(ValidationError):
        JobPostExtraction.model_validate(_extraction(relationships=["..."]))


# ---------------------------------------------------------------------------
# Structured JD extraction service (fake invoker only)
# ---------------------------------------------------------------------------


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _valid_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python"],
            },
            {
                "name": "React.js",
                "confidence": 0.7,
                "evidence": ["Nice to have React.js"],
            },
        ],
        "preferred_skills": [
            {
                "name": "FastAPI",
                "confidence": 0.6,
                "evidence": ["Preferred: FastAPI"],
            }
        ],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


class FakeJdInvoker:
    """Scripted invoker: returns payloads or raises in order."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedJobPost | dict[str, Any]:
        self.calls.append(
            {
                "is_repair": is_repair,
                "message_count": len(list(messages)),
            }
        )
        if not self.script:
            raise RuntimeError("fake invoker script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("fake error")
        return item


class APITimeoutError(Exception):
    """Named like provider APITimeoutError for classify_provider_error coverage."""


class RateLimitError(Exception):
    status_code = 429


class AuthError(Exception):
    """Non-retryable provider-style failure."""


def test_strict_json_schema_strategy_constants() -> None:
    assert EXTRACTION_SCHEMA_STRATEGY == "strict_json_schema"
    assert STRUCTURED_OUTPUT_METHOD == "json_schema"
    assert STRUCTURED_OUTPUT_STRICT is True
    assert MAX_PROVIDER_RETRIES == 1


def test_shopaikey_jd_invoker_uses_with_structured_output() -> None:
    fake_model = MagicMock()
    bound = MagicMock()
    fake_model.with_structured_output.return_value = bound
    bound.invoke.return_value = _valid_extracted()

    invoker = ShopAIKeyStructuredJdInvoker(model=fake_model)
    assert invoker.model_name
    fake_model.with_structured_output.assert_called_once()
    kwargs = fake_model.with_structured_output.call_args
    assert kwargs.kwargs.get("method") == "json_schema"
    assert kwargs.kwargs.get("strict") is True
    assert kwargs.args[0] is ExtractedJobPost or (
        kwargs.kwargs.get("schema") is ExtractedJobPost
    )

    result = invoker.invoke_structured([MagicMock()])
    assert isinstance(result, ExtractedJobPost)
    assert result.title == "Backend Engineer"


def test_valid_fake_response_normalizes_skills_and_preserves_evidence() -> None:
    invoker = FakeJdInvoker([_valid_extracted()])
    outcome = extract_job_post_from_text(
        "Synthetic JD text about Python and FastAPI.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.schema_repairs_used == 0
    assert outcome.provider_retries_used == 0
    assert len(invoker.calls) == 1
    assert invoker.calls[0]["is_repair"] is False

    doc = outcome.extraction
    assert isinstance(doc, JobPostExtraction)
    assert doc.title == "Backend Engineer"
    req_keys = {s.skill.canonical_key for s in doc.required_skills}
    assert "python" in req_keys
    assert "react" in req_keys  # React.js alias via SkillNormalizer
    pref = doc.preferred_skills[0]
    assert pref.skill.canonical_key == "fastapi"
    assert pref.skill.display_name == "FastAPI"
    assert pref.evidence == ["Preferred: FastAPI"]
    # LLM never supplies aliases on free-text path; normalizer fills seed aliases.
    assert "python3" in doc.required_skills[0].skill.aliases or doc.required_skills[
        0
    ].skill.canonical_key == "python"
    assert "jd_quality" not in doc.model_dump(mode="json")


def test_exactly_one_schema_repair_then_success() -> None:
    invoker = FakeJdInvoker(
        [
            ValidationError.from_exception_data(
                "ExtractedJobPost",
                [{"type": "missing", "loc": ("summary",), "input": {}}],
            ),
            _valid_extracted(),
        ]
    )
    outcome = extract_job_post_from_text(
        "JD text for repair path.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.schema_repairs_used == 1
    assert len(invoker.calls) == 2
    assert invoker.calls[0]["is_repair"] is False
    assert invoker.calls[1]["is_repair"] is True
    assert outcome.extraction.summary


def test_schema_repair_exhausted_fails() -> None:
    bad = ValidationError.from_exception_data(
        "ExtractedJobPost",
        [{"type": "missing", "loc": ("summary",), "input": {}}],
    )
    invoker = FakeJdInvoker([bad, bad])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD text for exhausted repair.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    assert len(invoker.calls) == 2
    assert "secret" not in ei.value.message.lower()
    assert "JD TEXT" not in ei.value.message


def test_exactly_one_timeout_retry_then_success() -> None:
    invoker = FakeJdInvoker([APITimeoutError("timeout"), _valid_extracted()])
    outcome = extract_job_post_from_text(
        "JD text for timeout retry.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.provider_retries_used == 1
    assert len(invoker.calls) == 2
    assert outcome.extraction.title == "Backend Engineer"


def test_timeout_retry_exhausted() -> None:
    invoker = FakeJdInvoker([APITimeoutError("t1"), APITimeoutError("t2")])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD text for timeout exhaustion.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_PROVIDER_TIMEOUT
    assert len(invoker.calls) == 2
    assert "t1" not in ei.value.message  # sanitized: type name only


def test_rate_limit_retry_once() -> None:
    invoker = FakeJdInvoker([RateLimitError("rate"), _valid_extracted()])
    outcome = extract_job_post_from_text(
        "JD text for rate limit retry.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.provider_retries_used == 1
    assert classify_provider_error(RateLimitError("x")) == FAILURE_PROVIDER_RATE_LIMIT


def test_non_retryable_provider_error() -> None:
    invoker = FakeJdInvoker([AuthError("nope")])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD text for non-retryable provider error.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_PROVIDER_ERROR
    assert len(invoker.calls) == 1
    assert ei.value.message == "provider error: AuthError"


def test_extra_fields_and_evidence_shape_rejected_then_repair() -> None:
    """Invalid extra fields on LLM payload trigger repair; valid second call wins."""
    invoker = FakeJdInvoker(
        [
            {
                "title": "X",
                "company": None,
                "summary": "s",
                "responsibilities": [],
                "required_skills": [],
                "preferred_skills": [],
                "seniority": "mid",
                "min_experience_years": None,
                "max_experience_years": None,
                "location": None,
                "work_mode": "remote",
                "extraction_confidence": 0.5,
                "jd_quality": "full",  # forbidden extra
            },
            _valid_extracted(),
        ]
    )
    outcome = extract_job_post_from_text(
        "JD text with bad extra field first.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.schema_repairs_used == 1
    assert "jd_quality" not in outcome.extraction.model_dump(mode="json")


def test_whitespace_only_skill_name_raises_for_repair() -> None:
    """Blank skill names must not be dropped; they fail validation/normalization."""
    extracted = _valid_extracted(
        required_skills=[
            ExtractedJobSkillItem(name="   ", confidence=0.5, evidence=[]),
            ExtractedJobSkillItem(
                name="Python",
                confidence=0.9,
                evidence=["Python required"],
            ),
        ],
        preferred_skills=[],
    )
    with pytest.raises(ValueError):
        extracted_to_job_post(extracted, _normalizer())


def test_blank_skill_name_uses_schema_repair_then_exhausts() -> None:
    blank = _valid_extracted(
        required_skills=[
            ExtractedJobSkillItem(name="  \t  ", confidence=0.5, evidence=["x"]),
        ],
        preferred_skills=[],
    )
    invoker = FakeJdInvoker([blank, blank])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD with blank skill names.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    assert len(invoker.calls) == 2
    assert invoker.calls[0]["is_repair"] is False
    assert invoker.calls[1]["is_repair"] is True
    assert "secret" not in ei.value.message.lower()


def test_out_of_range_skill_confidence_uses_schema_repair_then_exhausts() -> None:
    bad = _valid_extracted(
        required_skills=[
            ExtractedJobSkillItem(
                name="Python",
                confidence=1.5,
                evidence=["Required Python"],
            ),
        ],
        preferred_skills=[],
    )
    invoker = FakeJdInvoker([bad, bad])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD with out-of-range skill confidence.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    assert len(invoker.calls) == 2
    assert invoker.calls[1]["is_repair"] is True


def test_out_of_range_extraction_confidence_uses_schema_repair_then_exhausts() -> None:
    bad = _valid_extracted(extraction_confidence=-0.1)
    invoker = FakeJdInvoker([bad, bad])
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD with out-of-range extraction confidence.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_INVALID_STRUCTURED_OUTPUT
    assert len(invoker.calls) == 2
    assert invoker.calls[1]["is_repair"] is True


def test_out_of_range_skill_confidence_then_repair_success() -> None:
    bad = _valid_extracted(
        required_skills=[
            ExtractedJobSkillItem(
                name="Python",
                confidence=2.0,
                evidence=["Required Python"],
            ),
        ],
        preferred_skills=[],
    )
    invoker = FakeJdInvoker([bad, _valid_extracted()])
    outcome = extract_job_post_from_text(
        "JD repair after bad skill confidence.",
        invoker=invoker,
        normalizer=_normalizer(),
    )
    assert outcome.schema_repairs_used == 1
    assert 0.0 <= outcome.extraction.extraction_confidence <= 1.0
    for skill in outcome.extraction.required_skills:
        assert 0.0 <= skill.confidence <= 1.0


def test_shared_provider_retry_owner_retries_once() -> None:
    attempts = {"n": 0}

    def _flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise APITimeoutError("once")
        return "ok"

    result, retries = invoke_with_provider_retry(_flaky)
    assert result == "ok"
    assert retries == 1
    assert attempts["n"] == 2

    with pytest.raises(ProviderRetryError) as ei:
        invoke_with_provider_retry(lambda: (_ for _ in ()).throw(AuthError("x")))
    assert ei.value.code == FAILURE_PROVIDER_ERROR


def test_provider_retry_rejects_max_retries_override() -> None:
    """Public API must not accept a max_retries override above the hard cap."""
    params = signature(invoke_with_provider_retry).parameters
    assert "max_retries" not in params
    assert MAX_PROVIDER_RETRIES == 1


def test_provider_retry_hard_cap_two_attempts_on_timeout() -> None:
    attempts = {"n": 0}

    def _always_timeout() -> str:
        attempts["n"] += 1
        raise APITimeoutError(f"t{attempts['n']}")

    with pytest.raises(ProviderRetryError) as ei:
        invoke_with_provider_retry(_always_timeout)
    assert ei.value.code == FAILURE_PROVIDER_TIMEOUT
    assert attempts["n"] == 2  # initial + exactly one retry


def test_provider_retry_hard_cap_two_attempts_on_rate_limit() -> None:
    attempts = {"n": 0}

    def _always_rate() -> str:
        attempts["n"] += 1
        raise RateLimitError("rate")

    with pytest.raises(ProviderRetryError) as ei:
        invoke_with_provider_retry(_always_rate)
    assert ei.value.code == FAILURE_PROVIDER_RATE_LIMIT
    assert attempts["n"] == 2


def test_jd_timeout_exhaustion_never_exceeds_two_provider_calls() -> None:
    invoker = FakeJdInvoker(
        [APITimeoutError("t1"), APITimeoutError("t2"), APITimeoutError("t3")]
    )
    with pytest.raises(JdExtractionError) as ei:
        extract_job_post_from_text(
            "JD timeout hard cap.",
            invoker=invoker,
            normalizer=_normalizer(),
        )
    assert ei.value.code == FAILURE_PROVIDER_TIMEOUT
    assert len(invoker.calls) == 2
