"""Grounded optional-contact extraction contracts."""

from __future__ import annotations

from app.services.cv_chunk_contracts import CanonicalChunk
from app.services.cv_contact_contracts import (
    ExtractedContactFact,
    validate_and_project_contact_facts,
)
from pydantic import ValidationError


def _fact(kind: str, value: str, evidence: str, ordinal: int) -> ExtractedContactFact:
    return ExtractedContactFact(
        kind=kind, value=value, evidence=evidence, source_chunk_ordinal=ordinal
    )  # type: ignore[arg-type]


def _project(*facts: ExtractedContactFact):
    return validate_and_project_contact_facts(
        facts,
        [
            CanonicalChunk(
                ordinal=0,
                text=(
                    "Phone +1 (202) 555-0147; email PERSON@Example.TEST; "
                    "other@example.test; GitHub https://github.com/synthetic-user "
                    "and https://github.com/other-user"
                ),
            ),
            CanonicalChunk(
                ordinal=1,
                text="Alternative +1 303 555 0199",
            ),
        ],
    )


def test_contact_fact_is_strict() -> None:
    try:
        ExtractedContactFact.model_validate(
            {
                "kind": "email",
                "value": "x@y.test",
                "evidence": "x@y.test",
                "source_chunk_ordinal": "0",
            }
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("source ordinals must be strict integers")


def test_contacts_preserve_source_order_display_values_and_normalize_duplicates() -> (
    None
):
    accepted = _project(
        _fact("email", " PERSON@Example.TEST ", "email PERSON@Example.TEST", 0),
        _fact("phone", "+1 202 555 0147", "Phone +1 (202) 555-0147", 0),
        _fact(
            "github_url",
            "https://github.com/synthetic-user",
            "GitHub https://github.com/synthetic-user",
            0,
        ),
        _fact("email", "person@example.test", "PERSON@Example.TEST", 0),
    )
    assert accepted.phone == "+1 202 555 0147"
    assert accepted.email == "PERSON@Example.TEST"
    assert accepted.github_url == "https://github.com/synthetic-user"
    assert accepted.warnings == ()


def test_distinct_contacts_become_ambiguous_in_stable_kind_order() -> None:
    accepted = _project(
        _fact("email", "PERSON@Example.TEST", "PERSON@Example.TEST", 0),
        _fact("email", "other@example.test", "other@example.test", 0),
        _fact("phone", "+1 (202) 555-0147", "Phone +1 (202) 555-0147", 0),
        _fact("phone", "+1 303 555 0199", "Alternative +1 303 555 0199", 1),
        _fact(
            "github_url",
            "https://github.com/synthetic-user",
            "https://github.com/synthetic-user",
            0,
        ),
        _fact(
            "github_url",
            "https://github.com/other-user",
            "https://github.com/other-user",
            0,
        ),
    )
    assert accepted.phone is None
    assert accepted.email is None
    assert accepted.github_url is None
    assert accepted.warnings == (
        "ambiguous_contact:phone",
        "ambiguous_contact:email",
        "ambiguous_contact:github_url",
    )


def test_missing_evidence_invalid_ordinal_and_username_inference_are_dropped() -> None:
    accepted = _project(
        _fact("email", "person@example.test", "not present", 0),
        _fact("phone", "+12025550147", "+12025550147", 99),
        _fact("github_url", "synthetic-user", "synthetic-user", 0),
    )
    assert accepted.phone is None
    assert accepted.email is None
    assert accepted.github_url is None
    assert accepted.warnings == ()


def test_malformed_email_phone_bounds_and_repo_or_non_github_are_dropped() -> None:
    accepted = _project(
        _fact("email", "broken.example.test", "broken.example.test", 0),
        _fact("phone", "123456", "123456", 0),
        _fact(
            "github_url",
            "https://github.com/synthetic-user/repo",
            "https://github.com/synthetic-user/repo",
            0,
        ),
        _fact(
            "github_url",
            "https://example.test/synthetic-user",
            "https://example.test/synthetic-user",
            0,
        ),
    )
    assert accepted.phone is None
    assert accepted.email is None
    assert accepted.github_url is None
