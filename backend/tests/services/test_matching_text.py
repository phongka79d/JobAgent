"""Fake/socket-blocked tests for versioned Candidate embedding text (Plan 6 01A).

Never opens a provider network connection. Never logs API keys, contact PII, or
raw CV/source text into durable exception/repr surfaces.
"""

from __future__ import annotations

import math
import socket
from typing import Any

import pytest
from app.config import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    Settings,
    load_settings,
)
from app.schemas.candidate import (
    CandidateProfile,
    CandidateSkill,
    ExperienceItem,
    SkillProficiency,
    SkillRef,
    SkillSource,
    SkillStatus,
)
from app.schemas.matching import (
    CANDIDATE_TEXT_REPRESENTATION_VERSION,
    CandidateEmbeddingError,
    CandidateEmbeddingErrorCode,
    CandidateEmbeddingFields,
)
from app.schemas.preferences import JobPreferences, TargetSeniority, WorkMode
from app.services.embeddings import (
    JOB_TEXT_REPRESENTATION_VERSION,
    JobEmbeddingFields,
    JobEmbeddingService,
    build_job_embedding_text,
    normalize_embedding_text,
)
from app.services.matching_text import (
    MAX_CANDIDATE_EMBEDDING_TEXT_LEN,
    build_candidate_embedding_text,
    candidate_fields_from_profile,
    embed_candidate,
    redact_candidate_embedding_text,
)
from app.services.pii_redaction import PiiRedactionError, PiiRedactionErrorCode
from tests.services.test_embeddings import FakeEmbeddingsClient, RecordingFactory

SENTINEL_API_KEY = "sentinel-candidate-embed-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-candidate-never-emit"
SENTINEL_BASE_URL = "https://provider.example/v1"
CONTACT_EMAIL = "candidate.private@example.com"
CONTACT_PHONE = "+1 555-123-4567"
RAW_CV_MARKER = "RAW_CV_BODY_MUST_NOT_APPEAR"
STORAGE_PATH_MARKER = "C:/files/active/cv-secret.pdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings() -> Settings:
    return load_settings(
        environ={
            "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
            "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
            "SHOPAIKEY_BASE_URL": SENTINEL_BASE_URL,
            "EMBEDDING_MODEL": ALLOWED_EMBEDDING_MODEL,
            "EMBEDDING_DIMENSIONS": str(ALLOWED_EMBEDDING_DIMENSIONS),
        }
    )


def _service(
    factory: RecordingFactory | None = None,
) -> tuple[JobEmbeddingService, RecordingFactory]:
    recording = factory or RecordingFactory()
    service = JobEmbeddingService.from_settings(
        _settings(),
        embeddings_factory=recording,
    )
    return service, recording


def _skill(
    name: str,
    *,
    status: SkillStatus = SkillStatus.VERIFIED,
    excluded: bool = False,
    canonical_key: str | None = None,
) -> CandidateSkill:
    key = canonical_key or name.lower().replace(" ", "_")
    return CandidateSkill(
        skill=SkillRef(
            canonical_key=key,
            display_name=name,
            status=status,
            confidence=0.9,
            evidence=["seen on CV"],
        ),
        proficiency=SkillProficiency.ADVANCED,
        years=None,
        source=SkillSource.CV,
        excluded=excluded,
        evidence=[],
    )


def _profile(**overrides: Any) -> CandidateProfile:
    base: dict[str, Any] = {
        "summary": "Backend engineer focused on APIs.",
        "current_title": "Senior Engineer",
        "total_experience_years": None,
        "skills": [
            _skill("Python"),
            _skill("FastAPI"),
            _skill("Secret Tool", status=SkillStatus.PROVISIONAL),
            _skill("Legacy Stack", excluded=True),
        ],
        "experiences": [
            ExperienceItem(title="Staff Backend Engineer", organization="Acme"),
            ExperienceItem(title="Backend Engineer", organization="Beta"),
            ExperienceItem(title=None, organization="NoTitleCo"),
        ],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return CandidateProfile.model_validate(base)


def _prefs(**overrides: Any) -> JobPreferences:
    data: dict[str, Any] = {
        "target_roles": ["Backend Engineer", "Platform Engineer"],
        "preferred_locations": ["Remote", "Berlin"],
        "acceptable_work_modes": [WorkMode.REMOTE, WorkMode.HYBRID],
        "target_seniority": [TargetSeniority.SENIOR, TargetSeniority.LEAD],
    }
    data.update(overrides)
    return JobPreferences.model_validate(data)


@pytest.fixture
def block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("network socket opened during matching text tests")

    monkeypatch.setattr(socket, "socket", _blocked)


# ---------------------------------------------------------------------------
# Representation builder
# ---------------------------------------------------------------------------


def test_candidate_text_source_order_and_exclusions(block_sockets: None) -> None:
    del block_sockets
    text = build_candidate_embedding_text(_profile(), _prefs())
    expected = normalize_embedding_text(
        "\n".join(
            [
                "Backend Engineer, Platform Engineer",
                "Backend engineer focused on APIs.",
                "Python, FastAPI",
                "Staff Backend Engineer, Backend Engineer",
                "Remote, Berlin, remote, hybrid, senior, lead",
            ]
        )
    )
    assert text == expected
    # Provisional / excluded skills never enter text.
    assert "Secret Tool" not in text
    assert "Legacy Stack" not in text
    # Non-representation profile fields never enter text.
    assert "Acme" not in text
    assert "Beta" not in text
    assert "Senior Engineer" not in text  # current_title is not a representation field
    assert "seen on CV" not in text
    assert STORAGE_PATH_MARKER not in text
    assert RAW_CV_MARKER not in text
    assert not text.lower().startswith("query:")
    assert not text.lower().startswith("passage:")


def test_candidate_text_byte_identical_for_equal_inputs(
    block_sockets: None,
) -> None:
    del block_sockets
    profile = _profile()
    prefs = _prefs()
    first = build_candidate_embedding_text(profile, prefs)
    second = build_candidate_embedding_text(profile, prefs)
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")
    fields = candidate_fields_from_profile(profile, prefs)
    assert build_candidate_embedding_text(fields) == first


def test_candidate_text_strips_accidental_e5_prefixes(block_sockets: None) -> None:
    del block_sockets
    fields = CandidateEmbeddingFields(
        target_roles=("query: Role",),
        summary="passage: Summary body",
        verified_skills=("Python",),
        experience_titles=("Engineer",),
        preferred_locations=(),
        acceptable_work_modes=(),
        target_seniority=(),
    )
    text = build_candidate_embedding_text(fields)
    assert not text.lower().startswith("query:")
    assert "Role" in text
    assert "Summary body" in text


def test_candidate_text_version_constant(block_sockets: None) -> None:
    del block_sockets
    assert CANDIDATE_TEXT_REPRESENTATION_VERSION == "candidate_embedding_text_v1"
    assert CANDIDATE_TEXT_REPRESENTATION_VERSION != JOB_TEXT_REPRESENTATION_VERSION


def test_candidate_fields_over_limit_raises_invalid_input_without_source(
    block_sockets: None,
) -> None:
    """Over-limit CandidateEmbeddingFields fail closed as code-only INVALID_INPUT."""
    del block_sockets
    sentinel = "OVER_LIMIT_SOURCE_MUST_NOT_LEAK_IN_EXCEPTION"
    # Exceed soft ceiling after normalize; builder must not truncate silently.
    summary = sentinel + ("x" * (MAX_CANDIDATE_EMBEDDING_TEXT_LEN + 1))
    fields = CandidateEmbeddingFields(summary=summary)
    with pytest.raises(CandidateEmbeddingError) as raised:
        build_candidate_embedding_text(fields)
    assert raised.value.code == CandidateEmbeddingErrorCode.INVALID_INPUT
    assert str(raised.value) == CandidateEmbeddingErrorCode.INVALID_INPUT.value
    assert sentinel not in str(raised.value)
    assert sentinel not in repr(raised.value)
    assert summary not in str(raised.value)
    assert summary not in repr(raised.value)
    assert raised.value.__cause__ is None


def test_job_embedding_text_unchanged_by_candidate_builder(
    block_sockets: None,
) -> None:
    del block_sockets
    job = JobEmbeddingFields(
        title="Title A",
        summary="Summary B",
        responsibilities=("Resp C", "Resp D"),
        required_skills=("ReqSkill",),
        preferred_skills=("PrefSkill",),
    )
    assert build_job_embedding_text(job) == normalize_embedding_text(
        "Title A\nSummary B\nResp C, Resp D\nReqSkill\nPrefSkill"
    )


# ---------------------------------------------------------------------------
# Redaction boundary
# ---------------------------------------------------------------------------


def test_redaction_removes_contact_before_provider(
    block_sockets: None,
) -> None:
    del block_sockets
    profile = _profile(
        summary=f"Engineer contact {CONTACT_EMAIL} phone {CONTACT_PHONE}"
    )
    plain = build_candidate_embedding_text(profile, _prefs())
    # Contact may still be present in pre-redaction assembly if summary holds it.
    redacted = redact_candidate_embedding_text(plain)
    assert CONTACT_EMAIL not in redacted
    assert CONTACT_PHONE not in redacted

    service, factory = _service()
    result = embed_candidate(profile, preferences=_prefs(), embedding_service=service)
    assert result.model == ALLOWED_EMBEDDING_MODEL
    assert result.dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert result.representation_version == CANDIDATE_TEXT_REPRESENTATION_VERSION
    assert result.encoding == "float"
    assert result.index == 0
    assert len(result.values) == ALLOWED_EMBEDDING_DIMENSIONS
    assert all(math.isfinite(v) for v in result.values)
    assert len(factory.calls) == 1
    assert factory.calls[0]["model"] == ALLOWED_EMBEDDING_MODEL
    assert factory.calls[0]["dimensions"] == ALLOWED_EMBEDDING_DIMENSIONS
    sent = factory.template.calls[0][0]
    assert CONTACT_EMAIL not in sent
    assert CONTACT_PHONE not in sent
    assert not sent.lower().startswith("query:")
    assert not sent.lower().startswith("passage:")


def test_redaction_failure_zero_provider_calls_and_no_source_text(
    block_sockets: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del block_sockets
    service, factory = _service()
    client = FakeEmbeddingsClient()
    factory.template = client

    def _boom(_text: str) -> object:
        raise PiiRedactionError(PiiRedactionErrorCode.REDACTION_FAILED)

    monkeypatch.setattr(
        "app.services.matching_text.redact_pii",
        _boom,
    )
    profile = _profile(summary=f"secret {CONTACT_EMAIL} {RAW_CV_MARKER}")
    with pytest.raises(CandidateEmbeddingError) as raised:
        embed_candidate(
            profile,
            preferences=_prefs(),
            embedding_service=service,
            client=client,
        )
    assert raised.value.code == CandidateEmbeddingErrorCode.REDACTION_FAILED
    assert str(raised.value) == CandidateEmbeddingErrorCode.REDACTION_FAILED.value
    assert CONTACT_EMAIL not in str(raised.value)
    assert CONTACT_EMAIL not in repr(raised.value)
    assert RAW_CV_MARKER not in str(raised.value)
    assert raised.value.__cause__ is None
    assert factory.calls == []
    assert client.calls == []


def test_equal_inputs_one_validated_vector(block_sockets: None) -> None:
    del block_sockets
    service, factory = _service()
    profile = _profile()
    prefs = _prefs()
    a = embed_candidate(profile, preferences=prefs, embedding_service=service)
    b = embed_candidate(profile, preferences=prefs, embedding_service=service)
    assert a.values == b.values
    assert len(a.values) == ALLOWED_EMBEDDING_DIMENSIONS
    assert a.identity["model"] == ALLOWED_EMBEDDING_MODEL
    assert a.identity["dimensions"] == ALLOWED_EMBEDDING_DIMENSIONS
    assert a.identity["representation_version"] == CANDIDATE_TEXT_REPRESENTATION_VERSION
    # Exactly one provider call per embed_candidate (scalar path).
    assert len(factory.template.calls) == 2
    for call in factory.template.calls:
        assert len(call) == 1


def test_provider_error_is_code_only(block_sockets: None) -> None:
    del block_sockets
    client = FakeEmbeddingsClient(
        fail_on_call=RuntimeError(
            f"Authorization: Bearer {SENTINEL_API_KEY} body={CONTACT_EMAIL}"
        )
    )
    service, _ = _service(RecordingFactory(client))
    with pytest.raises(CandidateEmbeddingError) as raised:
        embed_candidate(
            _profile(),
            preferences=_prefs(),
            embedding_service=service,
            client=client,
        )
    assert raised.value.code == CandidateEmbeddingErrorCode.PROVIDER_ERROR
    assert SENTINEL_API_KEY not in str(raised.value)
    assert CONTACT_EMAIL not in str(raised.value)
    assert raised.value.__cause__ is None


def test_errors_hide_secrets_and_source(block_sockets: None) -> None:
    del block_sockets
    err = CandidateEmbeddingError(CandidateEmbeddingErrorCode.REDACTION_FAILED)
    assert SENTINEL_API_KEY not in str(err)
    assert CONTACT_EMAIL not in repr(err)
    assert err.__cause__ is None
    assert err.__context__ is None
