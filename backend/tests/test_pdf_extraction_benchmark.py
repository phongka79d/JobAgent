"""Focused tests for the pypdf normal/layout benchmark recorder (04B).

Uses only synthetic PDFs built in-process. Private corpus is never required.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from evaluation.benchmark_pdf_extraction import (
    AggregateBenchmarkResult,
    BenchmarkRecord,
    ExtractionOutcome,
    FixtureResolutionError,
    ParserMode,
    build_aggregate,
    classify_outcome,
    load_frozen_fixture_entries,
    resolve_fixture_paths,
    run_benchmark,
    run_from_manifests,
    run_single,
    write_aggregate,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Synthetic PDF builders (no private corpus, no third-party PDF writer)
# ---------------------------------------------------------------------------


def _build_pdf(content_stream: bytes) -> bytes:
    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        (
            b"4 0 obj\n<< /Length %d >>\nstream\n" % len(content_stream)
            + content_stream
            + b"endstream\nendobj\n"
        ),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def build_synthetic_text_pdf(text: str = "SyntheticProbeText") -> bytes:
    escaped = (
        text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET\n".encode("latin-1")
    return _build_pdf(stream)


def build_synthetic_image_only_pdf() -> bytes:
    """Page with an empty content stream (no text operators)."""
    return _build_pdf(b"")


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def write_frozen_manifest(path: Path, fixture_ids: list[tuple[str, str]]) -> Path:
    """fixture_ids: list of (fixture_id, fixture_kind)."""
    fixtures = [
        {
            "fixture_id": fixture_id,
            "fixture_kind": kind,
            "data_class": "synthetic",
            "page_count": 1,
            "sha256": "0" * 64,
            "benchmark_status": "FROZEN",
        }
        for fixture_id, kind in fixture_ids
    ]
    payload = {
        "manifest_version": 1,
        "manifest_id": "synthetic_pdf_fixture_test_v1",
        "data_class": "safe_aggregate",
        "recorded_before_benchmark": True,
        "fixtures": fixtures,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_private_mapping(
    path: Path, mapping: dict[str, Path], repo_root: Path
) -> Path:
    fixtures = []
    for fixture_id, pdf_path in mapping.items():
        try:
            rel = pdf_path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = str(pdf_path.resolve())
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "local_path": rel,
                "fixture_kind": "digital",
            }
        )
    payload = {
        "manifest_version": 1,
        "data_class": "local_private",
        "fixtures": fixtures,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


REQUIRED_RECORD_FIELDS = {
    "fixture_id",
    "page_count",
    "parser_mode",
    "extracted_character_count",
    "elapsed_milliseconds",
    "outcome",
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_benchmark_record_schema_requires_all_plan_fields() -> None:
    record = BenchmarkRecord(
        fixture_id="synthetic_pdf_001",
        page_count=1,
        parser_mode=ParserMode.NORMAL,
        extracted_character_count=12,
        elapsed_milliseconds=3,
        outcome=ExtractionOutcome.EXTRACTED_TEXT,
    )
    payload = record.model_dump()
    assert REQUIRED_RECORD_FIELDS.issubset(payload.keys())
    assert payload["parser_mode"] == "normal"
    assert "text" not in payload
    assert "extracted_text" not in payload


def test_benchmark_record_rejects_raw_text_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BenchmarkRecord(
            fixture_id="x",
            page_count=1,
            parser_mode=ParserMode.LAYOUT,
            extracted_character_count=0,
            elapsed_milliseconds=1,
            outcome=ExtractionOutcome.NO_EXTRACTABLE_TEXT,
            extracted_text="secret document body",  # type: ignore[call-arg]
        )


def test_classify_outcome_maps_zero_usable_text() -> None:
    assert classify_outcome(0) == ExtractionOutcome.NO_EXTRACTABLE_TEXT
    assert classify_outcome(1) == ExtractionOutcome.EXTRACTED_TEXT


# ---------------------------------------------------------------------------
# Synthetic text / image-only / malformed
# ---------------------------------------------------------------------------


def test_both_modes_run_through_one_path_on_synthetic_text(
    tmp_path: Path,
) -> None:
    pdf_path = write_bytes(tmp_path / "text.pdf", build_synthetic_text_pdf())
    records = run_benchmark(
        [("synthetic_text_001", pdf_path)],
        modes=(ParserMode.NORMAL, ParserMode.LAYOUT),
    )
    assert len(records) == 2
    assert [r.parser_mode for r in records] == [
        ParserMode.NORMAL,
        ParserMode.LAYOUT,
    ]
    for record in records:
        assert record.fixture_id == "synthetic_text_001"
        assert record.page_count == 1
        assert record.extracted_character_count > 0
        assert record.elapsed_milliseconds >= 0
        assert record.outcome == ExtractionOutcome.EXTRACTED_TEXT
        assert REQUIRED_RECORD_FIELDS.issubset(record.model_dump().keys())


def test_image_only_fixture_yields_no_extractable_text_both_modes(
    tmp_path: Path,
) -> None:
    pdf_path = write_bytes(
        tmp_path / "image_only.pdf", build_synthetic_image_only_pdf()
    )
    records = run_benchmark(
        [("synthetic_image_only_001", pdf_path)],
        modes=(ParserMode.NORMAL, ParserMode.LAYOUT),
    )
    assert len(records) == 2
    for record in records:
        assert record.extracted_character_count == 0
        assert record.outcome == ExtractionOutcome.NO_EXTRACTABLE_TEXT
        assert record.page_count == 1


def test_image_only_exact_outcome_code_normal_and_layout(
    tmp_path: Path,
) -> None:
    """04D: exact outcome code + zero usable chars for both parser modes."""
    pdf_path = write_bytes(
        tmp_path / "image_only_exact.pdf", build_synthetic_image_only_pdf()
    )
    for mode in (ParserMode.NORMAL, ParserMode.LAYOUT):
        record = run_single("synthetic_image_only_exact", pdf_path, mode)
        assert record.outcome is ExtractionOutcome.NO_EXTRACTABLE_TEXT
        assert record.outcome.value == "NO_EXTRACTABLE_TEXT"
        assert record.extracted_character_count == 0
        assert record.parser_mode is mode
        assert record.page_count == 1


def test_image_only_repeated_runs_stable_exact_code(tmp_path: Path) -> None:
    """04D: repeated image-only runs reproducibly yield the exact failure code."""
    pdf_path = write_bytes(
        tmp_path / "image_only_repeat.pdf", build_synthetic_image_only_pdf()
    )
    for _ in range(3):
        for mode in (ParserMode.NORMAL, ParserMode.LAYOUT):
            record = run_single("synthetic_image_only_repeat", pdf_path, mode)
            assert record.outcome == ExtractionOutcome.NO_EXTRACTABLE_TEXT
            assert record.extracted_character_count == 0


def test_frozen_image_only_fixture_exact_code_both_modes_when_present() -> None:
    """04D: frozen private image-only fixture (when available) both modes exact code."""
    private_pdf = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "private"
        / "pdfs"
        / "pdf_image_only_001.pdf"
    )
    if not private_pdf.is_file():
        pytest.skip("frozen private image-only fixture not present locally")

    for mode in (ParserMode.NORMAL, ParserMode.LAYOUT):
        record = run_single("pdf_image_only_001", private_pdf, mode)
        assert record.outcome.value == "NO_EXTRACTABLE_TEXT"
        assert record.extracted_character_count == 0
        assert record.page_count >= 1
        assert record.outcome != ExtractionOutcome.EXTRACTION_ERROR
        assert record.outcome != ExtractionOutcome.EXTRACTED_TEXT

    # Repeated dual-mode runs remain stable.
    for _ in range(3):
        for mode in (ParserMode.NORMAL, ParserMode.LAYOUT):
            record = run_single("pdf_image_only_001", private_pdf, mode)
            assert record.outcome == ExtractionOutcome.NO_EXTRACTABLE_TEXT
            assert record.extracted_character_count == 0


def test_malformed_input_maps_to_extraction_error(tmp_path: Path) -> None:
    bad_path = write_bytes(tmp_path / "bad.pdf", b"this is not a pdf")
    record = run_single("malformed_001", bad_path, ParserMode.NORMAL)
    assert record.outcome == ExtractionOutcome.EXTRACTION_ERROR
    assert record.extracted_character_count == 0
    assert record.fixture_id == "malformed_001"
    assert record.parser_mode == ParserMode.NORMAL


def test_deterministic_fixture_and_mode_ordering(tmp_path: Path) -> None:
    a = write_bytes(tmp_path / "a.pdf", build_synthetic_text_pdf("AlphaText"))
    b = write_bytes(tmp_path / "b.pdf", build_synthetic_text_pdf("BetaText"))
    records = run_benchmark(
        [("fixture_a", a), ("fixture_b", b)],
        modes=(ParserMode.NORMAL, ParserMode.LAYOUT),
    )
    ordered = [(r.fixture_id, r.parser_mode.value) for r in records]
    assert ordered == [
        ("fixture_a", "normal"),
        ("fixture_a", "layout"),
        ("fixture_b", "normal"),
        ("fixture_b", "layout"),
    ]


# ---------------------------------------------------------------------------
# Manifest loading (no hardcoded personal paths)
# ---------------------------------------------------------------------------


def test_loads_fixtures_from_frozen_manifest_and_path_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evaluation import benchmark_pdf_extraction as mod

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    pdf_dir = tmp_path / "backend" / "evaluation" / "private" / "pdfs"
    text_pdf = write_bytes(pdf_dir / "syn_text.pdf", build_synthetic_text_pdf())
    image_pdf = write_bytes(
        pdf_dir / "syn_image.pdf", build_synthetic_image_only_pdf()
    )
    frozen = write_frozen_manifest(
        tmp_path / "backend" / "evaluation" / "fixtures" / "frozen.json",
        [
            ("syn_text_001", "digital"),
            ("syn_image_001", "image_only"),
        ],
    )
    private = write_private_mapping(
        tmp_path / "backend" / "evaluation" / "private" / "map.json",
        {
            "syn_text_001": text_pdf,
            "syn_image_001": image_pdf,
        },
        repo_root=tmp_path,
    )
    out = tmp_path / "backend" / "evaluation" / "reports" / "out.json"

    result = run_from_manifests(
        frozen_manifest_path=frozen,
        private_manifest_path=private,
        output_path=out,
    )

    assert result.manifest_id == "synthetic_pdf_fixture_test_v1"
    assert result.summary.fixture_count == 2
    assert result.summary.record_count == 4
    assert result.ocr_used is False
    assert result.alternate_parser_used is False
    assert out.is_file()

    dumped = json.loads(out.read_text(encoding="utf-8"))
    assert dumped["data_class"] == "safe_aggregate"
    for record in dumped["records"]:
        assert REQUIRED_RECORD_FIELDS.issubset(record.keys())
        for banned in ("text", "raw_text", "document_text", "extracted_text", "content"):
            assert banned not in record

    text_records = [
        r for r in result.records if r.fixture_id == "syn_text_001"
    ]
    image_records = [
        r for r in result.records if r.fixture_id == "syn_image_001"
    ]
    assert all(r.outcome == ExtractionOutcome.EXTRACTED_TEXT for r in text_records)
    assert all(
        r.outcome == ExtractionOutcome.NO_EXTRACTABLE_TEXT for r in image_records
    )


def test_missing_path_mapping_raises(tmp_path: Path) -> None:
    frozen = write_frozen_manifest(
        tmp_path / "frozen.json",
        [("missing_001", "digital")],
    )
    entries = load_frozen_fixture_entries(frozen)
    with pytest.raises(FixtureResolutionError):
        resolve_fixture_paths(entries, {})


def test_aggregate_schema_validation_round_trip(tmp_path: Path) -> None:
    pdf_path = write_bytes(tmp_path / "t.pdf", build_synthetic_text_pdf())
    records = run_benchmark([("syn_001", pdf_path)])
    aggregate = build_aggregate(
        records=records,
        fixture_ids=["syn_001"],
        modes=(ParserMode.NORMAL, ParserMode.LAYOUT),
        frozen_manifest_path=tmp_path / "frozen.json",
        path_mapping_source="explicit_path_mapping",
        manifest_id="test",
    )
    out = tmp_path / "agg.json"
    write_aggregate(aggregate, out)
    reloaded = AggregateBenchmarkResult.model_validate_json(
        out.read_text(encoding="utf-8")
    )
    assert reloaded.summary.record_count == 2
    assert reloaded.parser_library == "pypdf"


# ---------------------------------------------------------------------------
# OCR / fallback dependency and raw-text leakage searches
# ---------------------------------------------------------------------------


def test_no_ocr_or_fallback_parser_dependencies_in_source() -> None:
    evaluation_dir = Path(__file__).resolve().parents[1] / "evaluation"
    sources = [
        evaluation_dir / "benchmark_pdf_extraction.py",
        evaluation_dir / "pdf_benchmark_schema.py",
    ]
    banned_imports = (
        r"\bpdfminer\b",
        r"\bpdfplumber\b",
        r"\bfitz\b",
        r"\bpymupdf\b",
        r"\bpytesseract\b",
        r"\btesseract\b",
        r"\bocrmypdf\b",
        r"\beasyocr\b",
        r"\bpaddleocr\b",
        r"\bpdf2image\b",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    for pattern in banned_imports:
        assert (
            re.search(pattern, combined) is None
        ), f"banned dependency pattern: {pattern}"
    assert "from pypdf" in combined or "import pypdf" in combined
    assert "ocr_used" in combined
    assert "NO_EXTRACTABLE_TEXT" in combined


def test_pyproject_pins_pypdf_without_ocr_stack() -> None:
    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert "pypdf" in pyproject
    for banned in (
        "pdfminer",
        "pdfplumber",
        "pymupdf",
        "pytesseract",
        "ocrmypdf",
        "easyocr",
        "paddleocr",
    ):
        assert banned not in pyproject


def test_aggregate_json_contains_no_raw_document_snippets(
    tmp_path: Path,
) -> None:
    sentinel = "UniquePrivateBodyNeverInReportsXYZ"
    pdf_path = write_bytes(
        tmp_path / "private_like.pdf", build_synthetic_text_pdf(sentinel)
    )
    records = run_benchmark([("syn_private_like", pdf_path)])
    aggregate = build_aggregate(
        records=records,
        fixture_ids=["syn_private_like"],
        modes=(ParserMode.NORMAL, ParserMode.LAYOUT),
        frozen_manifest_path=tmp_path / "f.json",
        path_mapping_source="explicit_path_mapping",
        manifest_id=None,
    )
    out = tmp_path / "safe.json"
    write_aggregate(aggregate, out)
    raw = out.read_text(encoding="utf-8")
    assert sentinel not in raw
    assert "UniquePrivate" not in raw
