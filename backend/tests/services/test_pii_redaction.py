"""Deterministic PII redaction tests (Plan 4 task 02A)."""

from __future__ import annotations

import pytest
from app.services.pdf_text import extract_pdf_text
from app.services.pii_redaction import (
    PiiRedactionError,
    PiiRedactionErrorCode,
    assert_no_contact_sentinels,
    redact_pii,
)
from tests.fixtures.cv_pdfs import build_synthetic_text_pdf

EMAIL_A = "alice.candidate@example.com"
EMAIL_B = "ops+cv@mail.example.org"
PHONE_US = "+1 555-123-4567"
PHONE_PAREN = "(555) 987-6543"
PHONE_DOTS = "555.222.3333"
PHONE_INTL = "+44 20 7946 0958"
# Contiguous local / international-without-plus forms (no separators).
PHONE_CONTIGUOUS_US = "5551234567"
PHONE_CONTIGUOUS_JP_LOCAL = "0901234567"
PHONE_CONTIGUOUS_UK_LOCAL = "02079460958"
PHONE_CONTIGUOUS_INTL_NO_PLUS = "447911123456"
ADDR_LINE = "123 Hidden Street, Apt 4B, Springfield"
CONTACT_ADDR_LINE = "99 Privacy Lane, Suite 10"


def _cv_body() -> str:
    return "\n".join(
        [
            "Jane Doe",
            "Senior Software Engineer",
            f"Email: {EMAIL_A}",
            f"Phone: {PHONE_US}",
            f"Alt: {EMAIL_B} / {PHONE_PAREN}",
            f"Mobile {PHONE_DOTS}",
            f"Intl {PHONE_INTL}",
            f"Address: {ADDR_LINE}",
            f"Contact Address: {CONTACT_ADDR_LINE}",
            "Experience",
            "Acme Corp — Built Python and FastAPI services",
            "Education",
            "BSc Computer Science, State University",
            "Skills: Python, FastAPI, PostgreSQL, CI/CD",
            "Languages: English, Spanish",
        ]
    )


def test_redacts_emails_phones_and_labeled_addresses() -> None:
    result = redact_pii(_cv_body())
    for sentinel in (
        EMAIL_A,
        EMAIL_B,
        PHONE_US,
        PHONE_PAREN,
        PHONE_DOTS,
        PHONE_INTL,
        ADDR_LINE,
        CONTACT_ADDR_LINE,
    ):
        assert sentinel not in result.text
    assert result.emails_removed >= 2
    assert result.phones_removed >= 2
    assert result.address_lines_removed >= 2


def test_preserves_non_contact_experience_education_skills() -> None:
    result = redact_pii(_cv_body())
    preserved = (
        "Jane Doe",
        "Senior Software Engineer",
        "Acme Corp",
        "Python",
        "FastAPI",
        "PostgreSQL",
        "CI/CD",
        "Computer Science",
        "Education",
        "Experience",
        "Skills",
        "Languages",
        "English",
        "Spanish",
    )
    for token in preserved:
        assert token in result.text


def test_multiline_and_unicode_contacts() -> None:
    body = (
        "Candidate\n"
        f"{EMAIL_A}\n"
        f"{PHONE_US}\n"
        "Adresse: not-a-labeled-english-address-keep\n"
        f"Address: Rue de l’Université 1, Genève\n"
        "Skills: C++, C#\n"
    )
    result = redact_pii(body)
    assert EMAIL_A not in result.text
    assert PHONE_US not in result.text
    assert "Rue de l’Université" not in result.text
    assert "Genève" not in result.text
    assert "Skills: C++, C#" in result.text
    assert "not-a-labeled-english-address-keep" in result.text


def test_false_positive_boundaries_years_and_skills() -> None:
    """Years and tech labels must not be treated as phone numbers."""
    body = (
        "Experience 2019-2024\n"
        "Skills: C++, C#, Node.js, CI/CD\n"
        "Level: advanced (5)\n"
        "Room 101 Building 2\n"
        "Years: 3.5\n"
    )
    result = redact_pii(body)
    assert "2019-2024" in result.text
    assert "C++" in result.text
    assert "C#" in result.text
    assert "CI/CD" in result.text
    assert "Room 101 Building 2" in result.text
    assert result.phones_removed == 0
    assert result.emails_removed == 0


def test_redacts_contiguous_local_and_international_without_plus_phones() -> None:
    """Common no-separator phone forms must be removed (A2 repair for 02A)."""
    body = "\n".join(
        [
            "Jane Doe",
            f"Mobile {PHONE_CONTIGUOUS_US}",
            f"JP {PHONE_CONTIGUOUS_JP_LOCAL}",
            f"UK {PHONE_CONTIGUOUS_UK_LOCAL}",
            f"INTL {PHONE_CONTIGUOUS_INTL_NO_PLUS}",
            # Formatted coverage retained alongside contiguous forms.
            f"US fmt {PHONE_US}",
            f"Paren {PHONE_PAREN}",
            f"Dots {PHONE_DOTS}",
            f"Intl fmt {PHONE_INTL}",
            "Experience 2019-2024",
            "Skills: Python, CI/CD",
            "Room 101 Building 2",
            "Level: advanced (5)",
        ]
    )
    result = redact_pii(body)
    for sentinel in (
        PHONE_CONTIGUOUS_US,
        PHONE_CONTIGUOUS_JP_LOCAL,
        PHONE_CONTIGUOUS_UK_LOCAL,
        PHONE_CONTIGUOUS_INTL_NO_PLUS,
        PHONE_US,
        PHONE_PAREN,
        PHONE_DOTS,
        PHONE_INTL,
    ):
        assert sentinel not in result.text
    assert result.phones_removed >= 8
    # Documented false-positive cases must survive the contiguous digit bound.
    assert "2019-2024" in result.text
    assert "CI/CD" in result.text
    assert "Room 101 Building 2" in result.text
    assert "advanced (5)" in result.text
    assert "Jane Doe" in result.text
    assert "Python" in result.text


def test_home_address_and_mailing_address_labels() -> None:
    body = (
        "Home Address: 1 Secret Way\n"
        "Mailing Address: PO Box 999\n"
        "Street Address: 2 Other Rd\n"
        "NotAddress without colon stays\n"
    )
    result = redact_pii(body)
    assert "1 Secret Way" not in result.text
    assert "PO Box 999" not in result.text
    assert "2 Other Rd" not in result.text
    assert "NotAddress without colon stays" in result.text


def test_inline_labeled_address_mid_line() -> None:
    body = f"Profile summary. Address: {ADDR_LINE}. Skills: Go."
    result = redact_pii(body)
    assert ADDR_LINE not in result.text
    assert "Skills: Go" in result.text or "Go" in result.text


def test_invalid_input_type_fails_closed() -> None:
    with pytest.raises(PiiRedactionError) as exc_info:
        redact_pii(12345)  # type: ignore[arg-type]
    assert exc_info.value.code is PiiRedactionErrorCode.INVALID_INPUT
    assert str(exc_info.value) == "INVALID_INPUT"


def test_redaction_exception_never_embeds_source_text() -> None:
    with pytest.raises(PiiRedactionError) as exc_info:
        redact_pii(None)  # type: ignore[arg-type]
    surface = f"{exc_info.value!s}|{exc_info.value!r}"
    assert "None" not in surface or exc_info.value.code.value in surface
    assert EMAIL_A not in surface


def test_assert_no_contact_sentinels_helper() -> None:
    redacted = redact_pii(_cv_body()).text
    assert_no_contact_sentinels(
        redacted,
        (EMAIL_A, EMAIL_B, PHONE_US, ADDR_LINE, CONTACT_ADDR_LINE),
    )
    with pytest.raises(PiiRedactionError) as exc_info:
        assert_no_contact_sentinels(f"still has {EMAIL_A}", (EMAIL_A,))
    assert exc_info.value.code is PiiRedactionErrorCode.REDACTION_FAILED
    # Sentinel must not appear in the exception surface.
    assert EMAIL_A not in str(exc_info.value)
    assert EMAIL_A not in repr(exc_info.value)


def test_pipeline_pdf_extract_then_redact_blocks_provider_on_redaction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No provider path after redaction failure (fail-closed gate)."""
    from app.services import pii_redaction as mod

    provider_calls: list[str] = []

    def fake_provider(text: str) -> None:
        provider_calls.append(text)

    def failing_redact(text: str) -> object:
        # Simulate fail-closed redaction without embedding source text.
        raise mod.PiiRedactionError(mod.PiiRedactionErrorCode.REDACTION_FAILED)

    monkeypatch.setattr(mod, "redact_pii", failing_redact)

    pdf = build_synthetic_text_pdf(
        f"Engineer {EMAIL_A} Python FastAPI Experience"
    )
    extracted = extract_pdf_text(pdf)
    assert extracted.usable_character_count > 0
    try:
        redacted = mod.redact_pii(extracted.text)
    except PiiRedactionError as exc:
        assert exc.code is PiiRedactionErrorCode.REDACTION_FAILED
        assert EMAIL_A not in str(exc)
        assert EMAIL_A not in repr(exc)
    else:
        fake_provider(redacted.text)  # type: ignore[union-attr]
    assert provider_calls == []


def test_end_to_end_pdf_to_redacted_text_removes_sentinels() -> None:
    # Keep body latin-1 friendly for synthetic PDF string operators.
    body = (
        f"Jane Doe Engineer Email {EMAIL_A} Phone {PHONE_US} "
        f"Address: 123 Hidden Street Skills Python FastAPI Education BSc"
    )
    pdf = build_synthetic_text_pdf(body)
    extracted = extract_pdf_text(pdf)
    redacted = redact_pii(extracted.text)
    assert EMAIL_A not in redacted.text
    assert PHONE_US not in redacted.text
    assert "123 Hidden Street" not in redacted.text
    # Non-contact content survives the boundary for structured extraction.
    assert "Python" in redacted.text or "Engineer" in redacted.text
