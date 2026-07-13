"""Unit tests for the sole pypdf extraction / meaningful-text owner (Plan 4 §7.4)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from app.services import pdf_extraction
from app.services.pdf_extraction import (
    IDENTITY_MARKERS,
    MALFORMED_PDF,
    MIN_NON_WHITESPACE_CHARS,
    NO_EXTRACTABLE_TEXT,
    PdfMalformedError,
    PdfTextExtraction,
    extract_modes,
    extract_pdf_text,
    is_meaningful_text,
    measure,
    parse_page_count,
)

CV_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cv"

DIGITAL_FIXTURES = (
    "digital_cv_01.pdf",
    "digital_cv_02.pdf",
    "digital_cv_03.pdf",
    "digital_cv_04.pdf",
    "digital_cv_05.pdf",
)
IMAGE_ONLY = "image_only_cv.pdf"

# Phase 0 recorded page counts (all single-page fixtures).
EXPECTED_PAGES = 1


@pytest.fixture(params=DIGITAL_FIXTURES)
def digital_path(request: pytest.FixtureRequest) -> Path:
    path = CV_FIXTURES / request.param
    assert path.is_file(), f"missing fixture {path}"
    return path


def test_all_digital_fixtures_have_meaningful_text(digital_path: Path) -> None:
    result = extract_pdf_text(digital_path)
    assert result.page_count == EXPECTED_PAGES
    assert result.has_meaningful_text is True
    assert result.failure_code is None
    assert result.preferred_text is not None
    assert is_meaningful_text(result.preferred_text) is True
    # Either mode may pass; Phase 0 recorded both true for all digital fixtures.
    assert result.normal_is_meaningful or result.layout_is_meaningful


def test_digital_normal_and_layout_outcomes_match_gate(digital_path: Path) -> None:
    normal, layout, pages = extract_modes(digital_path)
    assert pages == EXPECTED_PAGES
    assert is_meaningful_text(normal) is True
    assert is_meaningful_text(layout) is True
    _, n_non_ws = measure(normal)
    _, l_non_ws = measure(layout)
    assert n_non_ws >= MIN_NON_WHITESPACE_CHARS
    assert l_non_ws >= MIN_NON_WHITESPACE_CHARS


def test_image_only_is_no_extractable_text() -> None:
    path = CV_FIXTURES / IMAGE_ONLY
    assert path.is_file()
    result = extract_pdf_text(path)
    assert result.page_count == EXPECTED_PAGES
    assert result.normal_is_meaningful is False
    assert result.layout_is_meaningful is False
    assert result.has_meaningful_text is False
    assert result.failure_code == NO_EXTRACTABLE_TEXT
    assert result.preferred_text is None
    _, n_non_ws = measure(result.normal_text)
    _, l_non_ws = measure(result.layout_text)
    assert n_non_ws == 0
    assert l_non_ws == 0


def test_parse_page_count_before_attachment_decision(digital_path: Path) -> None:
    """Upload layer can decide MAX_PDF_PAGES from page count alone."""
    pages = parse_page_count(digital_path)
    assert pages == EXPECTED_PAGES
    assert pages <= 10  # settings default MAX_PDF_PAGES


def test_malformed_bytes_raise_stable_code() -> None:
    with pytest.raises(PdfMalformedError) as exc_info:
        extract_pdf_text(b"not a pdf at all")
    assert exc_info.value.failure_code == MALFORMED_PDF


def test_malformed_empty_and_truncated_raise() -> None:
    with pytest.raises(PdfMalformedError):
        parse_page_count(b"")
    with pytest.raises(PdfMalformedError):
        extract_modes(b"%PDF-1.4\ntruncated garbage")


def test_meaningful_text_rule_thresholds() -> None:
    too_short = "email name experience engineer skills python"
    assert len(too_short.replace(" ", "")) < MIN_NON_WHITESPACE_CHARS
    assert is_meaningful_text(too_short) is False

    # Long enough non-ws but missing a marker family.
    long_no_skills = (
        "name contact email phone " + ("experience engineer developer " * 10)
    )
    assert is_meaningful_text(long_no_skills) is False

    long_ok = (
        "Candidate name email phone "
        + ("experience engineer developer senior " * 5)
        + ("skills python typescript sql react " * 3)
    )
    assert is_meaningful_text(long_ok) is True


def test_preferred_text_prefers_layout_when_both_meaningful() -> None:
    result = PdfTextExtraction(
        page_count=1,
        normal_text="normal " * 40
        + "email name experience engineer skills python",
        layout_text="layout " * 40
        + "email name experience engineer skills python",
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    assert result.preferred_text is not None
    assert result.preferred_text.startswith("layout")


def test_preferred_text_falls_back_to_normal() -> None:
    result = PdfTextExtraction(
        page_count=1,
        normal_text="normal " * 40
        + "email name experience engineer skills python",
        layout_text="x",
        normal_is_meaningful=True,
        layout_is_meaningful=False,
    )
    assert result.preferred_text is not None
    assert result.preferred_text.startswith("normal")


def test_module_source_has_no_ocr_or_alternate_parser() -> None:
    source = inspect.getsource(pdf_extraction)
    lowered = source.lower()
    for banned in (
        "tesseract",
        "easyocr",
        "paddleocr",
        "pytesseract",
        "ocrmypdf",
        "pdfminer",
        "pdfplumber",
        "fitz",
        "pymupdf",
        "pdfium",
        "subprocess",
    ):
        assert banned not in lowered, f"banned token present: {banned}"
    # OCR word may appear only in denial documentation.
    for line in source.splitlines():
        if "ocr" in line.lower():
            lowered_line = line.lower()
            assert any(
                deny in lowered_line
                for deny in (
                    "never",
                    "no ocr",
                    "without ocr",
                    "does not call ocr",
                    "not call ocr",
                    "not",
                )
            ), f"unexpected OCR reference: {line}"


def test_module_ast_only_imports_pypdf_for_parsing() -> None:
    path = Path(pdf_extraction.__file__).resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "pypdf" in imported
    for banned in ("subprocess", "pytesseract", "pdfminer", "fitz", "PIL", "cv2"):
        assert banned not in imported


def test_identity_marker_constants_match_phase0() -> None:
    assert MIN_NON_WHITESPACE_CHARS == 80
    assert "email" in IDENTITY_MARKERS
    assert "@" in IDENTITY_MARKERS
