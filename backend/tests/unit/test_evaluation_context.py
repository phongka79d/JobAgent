"""Unit tests for pure evaluation context hashing and currentness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextError,
    EvaluationContextFacts,
    canonical_evaluation_context_bytes,
    derive_evaluation_currentness,
    evaluation_context_hash,
)

_TS = datetime(2020, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_matching_contract_invalidates_pre_skill_normalization_results() -> None:
    assert MATCHING_CONTRACT_VERSION == "match_v3"


def _facts(**overrides: object) -> EvaluationContextFacts:
    base: dict[str, object] = {
        "job_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "job_revision": _TS,
        "active_attachment_id": "11111111-2222-4333-8444-555555555555",
        "cv_source_hash": "cvhash-aaa",
        "profile_revision": _TS,
        "preferences_revision": _TS,
        "matching_contract_version": MATCHING_CONTRACT_VERSION,
    }
    base.update(overrides)
    return EvaluationContextFacts(**base)  # type: ignore[arg-type]


def test_canonical_bytes_stable_and_sorted() -> None:
    facts = _facts()
    a = canonical_evaluation_context_bytes(facts)
    b = canonical_evaluation_context_bytes(facts)
    assert a == b
    assert a == (
        b'{"active_attachment_id":"11111111-2222-4333-8444-555555555555",'
        b'"cv_source_hash":"cvhash-aaa",'
        b'"job_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",'
        b'"job_revision":"2020-01-01T12:00:00+00:00",'
        b'"matching_contract_version":"match_v3",'
        b'"preferences_revision":"2020-01-01T12:00:00+00:00",'
        b'"profile_revision":"2020-01-01T12:00:00+00:00"}'
    )
    digest = evaluation_context_hash(facts)
    assert digest == evaluation_context_hash(facts)
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_same_facts_same_hash_independent_of_construction_order() -> None:
    first = evaluation_context_hash(_facts())
    second = evaluation_context_hash(
        EvaluationContextFacts(
            matching_contract_version=MATCHING_CONTRACT_VERSION,
            preferences_revision=_TS,
            profile_revision=_TS,
            cv_source_hash="cvhash-aaa",
            active_attachment_id="11111111-2222-4333-8444-555555555555",
            job_revision=_TS,
            job_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        )
    )
    assert first == second


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_id", "bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        ("job_revision", _TS + timedelta(seconds=1)),
        ("active_attachment_id", "99999999-2222-4333-8444-555555555555"),
        ("cv_source_hash", "cvhash-bbb"),
        ("profile_revision", _TS + timedelta(days=1)),
        ("preferences_revision", _TS + timedelta(hours=1)),
        ("matching_contract_version", "match_v4"),
    ],
)
def test_each_revision_fact_changes_hash(field: str, value: object) -> None:
    baseline = evaluation_context_hash(_facts())
    changed = evaluation_context_hash(_facts(**{field: value}))
    assert changed != baseline


def test_naive_datetime_rejected() -> None:
    with pytest.raises(EvaluationContextError, match="timezone-aware"):
        canonical_evaluation_context_bytes(
            _facts(job_revision=datetime(2020, 1, 1, 12, 0, 0))
        )


def test_empty_string_fields_rejected() -> None:
    with pytest.raises(EvaluationContextError, match="job_id"):
        evaluation_context_hash(_facts(job_id=""))
    with pytest.raises(EvaluationContextError, match="cv_source_hash"):
        evaluation_context_hash(_facts(cv_source_hash="  "))


def test_client_fields_do_not_participate_in_hash_api() -> None:
    """Context facts accept only server revision fields (no client extras)."""
    with pytest.raises(TypeError):
        EvaluationContextFacts(  # type: ignore[call-arg]
            job_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            job_revision=_TS,
            active_attachment_id="11111111-2222-4333-8444-555555555555",
            cv_source_hash="cvhash-aaa",
            profile_revision=_TS,
            preferences_revision=_TS,
            client_score=0.99,
        )


def test_derive_currentness_none_current_stale() -> None:
    assert (
        derive_evaluation_currentness(
            has_any_row=False, has_exact_context_hash=False
        )
        == "none"
    )
    assert (
        derive_evaluation_currentness(
            has_any_row=True, has_exact_context_hash=True
        )
        == "current"
    )
    assert (
        derive_evaluation_currentness(
            has_any_row=False, has_exact_context_hash=True
        )
        == "current"
    )
    assert (
        derive_evaluation_currentness(
            has_any_row=True, has_exact_context_hash=False
        )
        == "stale"
    )
