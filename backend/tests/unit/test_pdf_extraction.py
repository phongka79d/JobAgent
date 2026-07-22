"""Unit tests for the sole pypdf extraction / meaningful-text owner (Plan 4 §7.4)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from app.services import pdf_extraction
from app.services.pdf_extraction import (
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


def _digital_text_pdf(*lines: str) -> bytes:
    """Build a tiny synthetic Helvetica PDF without adding a fixture dependency."""
    operators = ["BT", "/F1 10 Tf", "50 740 Td"]
    for index, line in enumerate(lines):
        if index:
            operators.append("0 -14 Td")
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        operators.append(f"({escaped}) Tj")
    operators.append("ET")
    stream = "\n".join(operators).encode("ascii")
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    )
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(payload)


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


@pytest.mark.parametrize(
    "text",
    (
        "Campaign planning audience research content performance budget allocation "
        "customer retention brand positioning channel measurement partner outreach",
        "Revenue forecasting cash flow reconciliation audit preparation portfolio "
        "review variance reporting regulatory controls and financial planning",
        "Patient coordination clinical documentation care planning safety review "
        "community outreach scheduling quality improvement and service continuity",
        "Supplier coordination inventory planning route scheduling contract review "
        "process improvement workforce allocation and operational risk management",
    ),
)
def test_marker_free_professions_pass_both_real_pypdf_modes(text: str) -> None:
    assert all(
        marker not in text.casefold()
        for marker in ("email", "engineer", "developer", "python", "skills")
    )
    normal, layout, pages = extract_modes(_digital_text_pdf(text))
    assert pages == 1
    assert is_meaningful_text(normal) is True
    assert is_meaningful_text(layout) is True


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
    too_short = "Brand planning and content"
    assert len(too_short.replace(" ", "")) < MIN_NON_WHITESPACE_CHARS
    assert is_meaningful_text(too_short) is False

    profession_neutral = (
        "Brand strategy, campaign planning, audience research, content performance, "
        "budget ownership, revenue forecasting, and customer retention. " * 3
    )
    assert all(
        marker not in profession_neutral.casefold()
        for marker in ("email", "engineer", "python", "skills")
    )
    assert is_meaningful_text(profession_neutral) is True

    assert is_meaningful_text("!" * MIN_NON_WHITESPACE_CHARS) is False
    assert is_meaningful_text("\uff11" * MIN_NON_WHITESPACE_CHARS) is True


def test_preferred_text_prefers_layout_when_both_meaningful() -> None:
    result = PdfTextExtraction(
        page_count=1,
        normal_text="normal " * 40 + "email name experience engineer skills python",
        layout_text="layout " * 40 + "email name experience engineer skills python",
        normal_is_meaningful=True,
        layout_is_meaningful=True,
    )
    assert result.preferred_text is not None
    assert result.preferred_text.startswith("layout")


def test_preferred_text_falls_back_to_normal() -> None:
    result = PdfTextExtraction(
        page_count=1,
        normal_text="normal " * 40 + "email name experience engineer skills python",
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


def test_meaningful_rule_has_no_profession_marker_families() -> None:
    assert MIN_NON_WHITESPACE_CHARS == 80
    assert not hasattr(pdf_extraction, "IDENTITY_MARKERS")
    assert not hasattr(pdf_extraction, "EXPERIENCE_MARKERS")
    assert not hasattr(pdf_extraction, "SKILLS_MARKERS")
    lowered_rule = pdf_extraction.MEANINGFUL_TEXT_RULE.casefold()
    for forbidden in ("identity marker", "experience marker", "skills marker"):
        assert forbidden not in lowered_rule
