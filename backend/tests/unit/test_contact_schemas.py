"""Pure syntax and normalization contracts for optional CV contacts."""

from __future__ import annotations

import pytest
from app.schemas.contact import (
    normalize_email,
    normalize_github_profile_url,
    normalize_phone,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" +1 (202) 555-0147 ", "+12025550147"),
        ("202.555.0147", "2025550147"),
    ],
)
def test_normalize_phone_retains_optional_plus_and_digits(
    value: str, expected: str
) -> None:
    assert normalize_phone(value) == expected


@pytest.mark.parametrize("value", ["123456", "+1234567890123456", "call-me"])
def test_normalize_phone_rejects_out_of_bounds_or_non_phone_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(value)


def test_normalize_email_casefolds_valid_bounded_address() -> None:
    assert normalize_email("  PERSON.Tag@Example.TEST ") == "person.tag@example.test"


@pytest.mark.parametrize("value", ["missing-at.example", "person@", "a b@example.test"])
def test_normalize_email_rejects_malformed_addresses(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(value)


def test_normalize_github_profile_url_accepts_one_profile_segment() -> None:
    assert (
        normalize_github_profile_url("https://www.github.com/synthetic-user/")
        == "https://github.com/synthetic-user"
    )


@pytest.mark.parametrize(
    "value",
    [
        "synthetic-user",
        "https://example.test/synthetic-user",
        "https://github.com/synthetic-user/repository",
        "https://github.com/synthetic-user?tab=repositories",
    ],
)
def test_normalize_github_profile_url_rejects_non_profile_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_github_profile_url(value)
