"""Fail-closed PDF layout extraction tests (Plan 4 task 02A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.services.pdf_text import (
    DEFAULT_MAX_PDF_PAGES,
    PdfTextError,
    PdfTextErrorCode,
    extract_pdf_text,
    usable_character_count,
)
from tests.fixtures.cv_pdfs import (
    build_multipage_text_pdf,
    build_synthetic_image_only_pdf,
    build_synthetic_text_pdf,
    write_bytes,
)

# Contact-like sentinels must never appear in exception surfaces.
_EMAIL_SENTINEL = "leakage.probe@example.com"
_PHONE_SENTINEL = "+1 555-010-9988"


def test_default_max_pages_matches_typed_settings_floor() -> None:
    assert DEFAULT_MAX_PDF_PAGES == 10


def test_usable_character_count_ignores_whitespace_only() -> None:
    assert usable_character_count("") == 0
    assert usable_character_count(" \n\t  ") == 0
    assert usable_character_count("a b") == 2


def test_valid_text_pdf_reports_page_count_and_usable_text() -> None:
    probe = "Experience Python FastAPI Engineer"
    data = build_synthetic_text_pdf(probe)
    result = extract_pdf_text(data)
    assert result.page_count == 1
    assert result.usable_character_count > 0
    assert usable_character_count(result.text) == result.usable_character_count
    # Layout extraction should surface the synthetic probe body.
    assert "Experience" in result.text or "Python" in result.text or "Engineer" in result.text


def test_image_only_pdf_exact_no_extractable_text_code() -> None:
    data = build_synthetic_image_only_pdf()
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(data)
    assert exc_info.value.code is PdfTextErrorCode.NO_EXTRACTABLE_TEXT
    assert str(exc_info.value) == "NO_EXTRACTABLE_TEXT"
    assert exc_info.value.code.value == "NO_EXTRACTABLE_TEXT"


def test_whitespace_only_text_maps_to_no_extractable_text() -> None:
    data = build_synthetic_text_pdf("   \t  ")
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(data)
    assert exc_info.value.code is PdfTextErrorCode.NO_EXTRACTABLE_TEXT


def test_malformed_pdf_parse_failed_stable_code() -> None:
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(b"this is not a pdf document at all")
    assert exc_info.value.code is PdfTextErrorCode.PDF_PARSE_FAILED
    assert str(exc_info.value) == "PDF_PARSE_FAILED"
    assert _EMAIL_SENTINEL not in str(exc_info.value)
    assert _EMAIL_SENTINEL not in repr(exc_info.value)


def test_over_page_limit_fails_closed() -> None:
    data = build_multipage_text_pdf(page_count=11, line="OverLimitPage")
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(data, max_pages=10)
    assert exc_info.value.code is PdfTextErrorCode.PAGE_LIMIT_EXCEEDED
    assert str(exc_info.value) == "PAGE_LIMIT_EXCEEDED"


def test_exact_max_pages_is_allowed() -> None:
    data = build_multipage_text_pdf(page_count=10, line="BoundaryPage")
    result = extract_pdf_text(data, max_pages=10)
    assert result.page_count == 10
    assert result.usable_character_count > 0


def test_custom_max_pages_respected() -> None:
    data = build_multipage_text_pdf(page_count=3, line="Triple")
    result = extract_pdf_text(data, max_pages=3)
    assert result.page_count == 3
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(data, max_pages=2)
    assert exc_info.value.code is PdfTextErrorCode.PAGE_LIMIT_EXCEEDED


def test_extract_from_path(tmp_path: Path) -> None:
    path = write_bytes(
        tmp_path / "cv.pdf",
        build_synthetic_text_pdf("PathBasedExtraction Skills Education"),
    )
    result = extract_pdf_text(path)
    assert result.page_count == 1
    assert result.usable_character_count > 0


def test_missing_path_is_invalid_source(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.pdf"
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(missing)
    assert exc_info.value.code is PdfTextErrorCode.INVALID_SOURCE


def test_invalid_max_pages_rejected() -> None:
    data = build_synthetic_text_pdf("Ok")
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(data, max_pages=0)
    assert exc_info.value.code is PdfTextErrorCode.INVALID_SOURCE


def test_exception_surfaces_never_embed_document_text() -> None:
    secret = f"SECRET_CV_BODY {_EMAIL_SENTINEL} {_PHONE_SENTINEL}"
    # Force parse failure with secret-bearing garbage that is not a PDF.
    blob = secret.encode("utf-8") * 20
    with pytest.raises(PdfTextError) as exc_info:
        extract_pdf_text(blob)
    surface = f"{exc_info.value!s}|{exc_info.value!r}|{exc_info.value.args!r}"
    assert secret not in surface
    assert _EMAIL_SENTINEL not in surface
    assert _PHONE_SENTINEL not in surface
    assert "SECRET_CV_BODY" not in surface


def test_no_provider_path_on_failure_is_code_gated() -> None:
    """Callers must treat any PdfTextError as blocking provider invocation."""
    provider_called = False

    def fake_provider(_text: str) -> None:
        nonlocal provider_called
        provider_called = True

    for payload in (
        build_synthetic_image_only_pdf(),
        b"not-a-pdf",
        build_multipage_text_pdf(page_count=12),
    ):
        provider_called = False
        try:
            result = extract_pdf_text(payload, max_pages=10)
        except PdfTextError:
            # Fail-closed: do not call provider.
            pass
        else:
            # Success path would call provider; not expected for these payloads.
            fake_provider(result.text)
        assert provider_called is False
