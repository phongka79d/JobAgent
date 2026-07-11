"""Focused pypdf normal/layout extraction benchmark recorder (Phase 0).

Loads fixtures from the frozen safe manifest and resolves bytes via an ignored
private path mapping. Records aggregate metrics only — never raw document text.
OCR and alternate parsers are intentionally out of scope.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pypdf import PdfReader

from evaluation.pdf_benchmark_schema import (
    AggregateBenchmarkResult,
    AggregateSummary,
    BenchmarkRecord,
    ExtractionOutcome,
    ModeSummary,
    ParserMode,
)

# Re-export schema symbols for a single import surface.
__all__ = [
    "AggregateBenchmarkResult",
    "AggregateSummary",
    "BenchmarkRecord",
    "DEFAULT_FROZEN_MANIFEST",
    "DEFAULT_OUTPUT",
    "DEFAULT_PRIVATE_MANIFEST",
    "ExtractionOutcome",
    "FixtureResolutionError",
    "ModeSummary",
    "ParserMode",
    "build_aggregate",
    "classify_outcome",
    "concise_summary_lines",
    "extract_with_mode",
    "load_frozen_fixture_entries",
    "load_private_path_mapping",
    "main",
    "resolve_fixture_paths",
    "run_benchmark",
    "run_from_manifests",
    "run_single",
    "write_aggregate",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FROZEN_MANIFEST = (
    REPO_ROOT / "backend" / "evaluation" / "fixtures" / "pdf_fixture_manifest.json"
)
DEFAULT_PRIVATE_MANIFEST = (
    REPO_ROOT / "backend" / "evaluation" / "private" / "pdf_manifest.local.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "backend"
    / "evaluation"
    / "reports"
    / "pdf_extraction_benchmark.json"
)

PYPDF_MODE_MAP: Mapping[str, Literal["plain", "layout"]] = {
    "normal": "plain",
    "layout": "layout",
}


class FixtureResolutionError(RuntimeError):
    """Raised when a frozen fixture cannot be resolved to a local PDF path."""


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def load_frozen_fixture_entries(manifest_path: Path) -> list[dict[str, Any]]:
    payload = _read_json(manifest_path)
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError(f"frozen manifest has no fixtures: {manifest_path}")
    ordered: list[dict[str, Any]] = []
    for entry in fixtures:
        if not isinstance(entry, dict):
            raise ValueError("fixture entry must be an object")
        fixture_id = entry.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("fixture entry missing fixture_id")
        ordered.append(entry)
    return ordered


def load_private_path_mapping(private_manifest_path: Path) -> dict[str, Path]:
    """Map fixture_id -> absolute PDF path from the ignored private manifest."""
    if not private_manifest_path.is_file():
        raise FixtureResolutionError(
            f"private path mapping missing: {private_manifest_path}"
        )
    payload = _read_json(private_manifest_path)
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list):
        raise FixtureResolutionError("private manifest fixtures must be a list")
    mapping: dict[str, Path] = {}
    for entry in fixtures:
        if not isinstance(entry, dict):
            continue
        fixture_id = entry.get("fixture_id")
        local_path = entry.get("local_path")
        if not isinstance(fixture_id, str) or not isinstance(local_path, str):
            continue
        if local_path in {"", "SET_IN_IGNORED_COPY"}:
            continue
        resolved = Path(local_path)
        if not resolved.is_absolute():
            resolved = (REPO_ROOT / local_path).resolve()
        mapping[fixture_id] = resolved
    if not mapping:
        raise FixtureResolutionError(
            f"private path mapping empty or unresolved: {private_manifest_path}"
        )
    return mapping


def resolve_fixture_paths(
    frozen_entries: Sequence[Mapping[str, Any]],
    path_mapping: Mapping[str, Path],
) -> list[tuple[str, Path]]:
    """Resolve frozen fixture IDs in deterministic manifest order."""
    resolved: list[tuple[str, Path]] = []
    for entry in frozen_entries:
        fixture_id = str(entry["fixture_id"])
        path = path_mapping.get(fixture_id)
        if path is None:
            raise FixtureResolutionError(
                f"no private path mapping for fixture_id={fixture_id}"
            )
        if not path.is_file():
            raise FixtureResolutionError(
                f"mapped PDF missing for fixture_id={fixture_id}"
            )
        resolved.append((fixture_id, path))
    return resolved


def classify_outcome(extracted_character_count: int) -> ExtractionOutcome:
    """Map usable character yield to the explicit Phase 0 outcome contract."""
    if extracted_character_count > 0:
        return ExtractionOutcome.EXTRACTED_TEXT
    return ExtractionOutcome.NO_EXTRACTABLE_TEXT


def extract_with_mode(pdf_path: Path, parser_mode: ParserMode) -> tuple[int, int, int]:
    """Run one pypdf extraction mode. Returns (page_count, char_count, elapsed_ms).

    Timing bounds enclose open + page iteration + extract_text only.
    Never returns document text.
    """
    extraction_mode = PYPDF_MODE_MAP[parser_mode.value]
    started = time.perf_counter()
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text(extraction_mode=extraction_mode) or ""
        chunks.append(text)
    joined = "".join(chunks)
    # Usable text = non-whitespace characters only for zero-yield mapping.
    usable = "".join(ch for ch in joined if not ch.isspace())
    character_count = len(usable)
    elapsed_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
    return page_count, character_count, elapsed_ms


def run_single(
    fixture_id: str,
    pdf_path: Path,
    parser_mode: ParserMode,
) -> BenchmarkRecord:
    """Single consistent extraction path for both normal and layout modes."""
    try:
        page_count, character_count, elapsed_ms = extract_with_mode(
            pdf_path, parser_mode
        )
        outcome = classify_outcome(character_count)
        return BenchmarkRecord(
            fixture_id=fixture_id,
            page_count=page_count,
            parser_mode=parser_mode,
            extracted_character_count=character_count,
            elapsed_milliseconds=elapsed_ms,
            outcome=outcome,
        )
    except Exception:
        return BenchmarkRecord(
            fixture_id=fixture_id,
            page_count=0,
            parser_mode=parser_mode,
            extracted_character_count=0,
            elapsed_milliseconds=0,
            outcome=ExtractionOutcome.EXTRACTION_ERROR,
        )


def run_benchmark(
    fixture_paths: Sequence[tuple[str, Path]],
    modes: Sequence[ParserMode] = (
        ParserMode.NORMAL,
        ParserMode.LAYOUT,
    ),
) -> list[BenchmarkRecord]:
    """Deterministic order: fixtures as provided, then modes (normal, layout)."""
    records: list[BenchmarkRecord] = []
    for fixture_id, pdf_path in fixture_paths:
        for mode in modes:
            records.append(run_single(fixture_id, pdf_path, mode))
    return records


def build_summary(
    records: Sequence[BenchmarkRecord],
    fixture_ids: Sequence[str],
    modes: Sequence[ParserMode],
) -> AggregateSummary:
    by_mode: list[ModeSummary] = []
    for mode in modes:
        mode_records = [r for r in records if r.parser_mode == mode]
        by_mode.append(
            ModeSummary(
                parser_mode=mode,
                record_count=len(mode_records),
                extracted_text_count=sum(
                    1
                    for r in mode_records
                    if r.outcome == ExtractionOutcome.EXTRACTED_TEXT
                ),
                no_extractable_text_count=sum(
                    1
                    for r in mode_records
                    if r.outcome == ExtractionOutcome.NO_EXTRACTABLE_TEXT
                ),
                extraction_error_count=sum(
                    1
                    for r in mode_records
                    if r.outcome == ExtractionOutcome.EXTRACTION_ERROR
                ),
                total_extracted_characters=sum(
                    r.extracted_character_count for r in mode_records
                ),
                total_elapsed_milliseconds=sum(
                    r.elapsed_milliseconds for r in mode_records
                ),
            )
        )
    return AggregateSummary(
        fixture_count=len(fixture_ids),
        record_count=len(records),
        fixture_ids_in_order=list(fixture_ids),
        modes_in_order=list(modes),
        by_mode=by_mode,
    )


def build_aggregate(
    *,
    records: Sequence[BenchmarkRecord],
    fixture_ids: Sequence[str],
    modes: Sequence[ParserMode],
    frozen_manifest_path: Path,
    path_mapping_source: str,
    manifest_id: str | None,
) -> AggregateBenchmarkResult:
    return AggregateBenchmarkResult(
        schema_version=1,
        data_class="safe_aggregate",
        manifest_id=manifest_id,
        frozen_manifest_path=_safe_repo_relative(frozen_manifest_path),
        path_mapping_source=path_mapping_source,
        parser_library="pypdf",
        parser_modes=list(modes),
        ocr_used=False,
        alternate_parser_used=False,
        records=list(records),
        summary=build_summary(records, fixture_ids, modes),
    )


def _safe_repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        # Outside repo (e.g. temp test paths): basename only, no personal paths.
        return path.name


def write_aggregate(result: AggregateBenchmarkResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    _assert_no_raw_text_fields(payload)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _assert_no_raw_text_fields(payload: Any) -> None:
    banned = {
        "text",
        "raw_text",
        "document_text",
        "extracted_text",
        "content",
        "page_text",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in banned:
                raise ValueError(f"raw text field forbidden in aggregate: {key}")
            _assert_no_raw_text_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_raw_text_fields(item)


def concise_summary_lines(result: AggregateBenchmarkResult) -> list[str]:
    """Report-ready lines with IDs and counts only (no document text)."""
    lines = [
        f"manifest_id={result.manifest_id or 'none'}",
        f"fixture_count={result.summary.fixture_count}",
        f"record_count={result.summary.record_count}",
        f"modes={','.join(m.value for m in result.parser_modes)}",
        f"ocr_used={result.ocr_used}",
        f"alternate_parser_used={result.alternate_parser_used}",
    ]
    for mode_summary in result.summary.by_mode:
        lines.append(
            "mode={mode} records={n} extracted={e} no_text={z} errors={err} "
            "chars={c} elapsed_ms={ms}".format(
                mode=mode_summary.parser_mode.value,
                n=mode_summary.record_count,
                e=mode_summary.extracted_text_count,
                z=mode_summary.no_extractable_text_count,
                err=mode_summary.extraction_error_count,
                c=mode_summary.total_extracted_characters,
                ms=mode_summary.total_elapsed_milliseconds,
            )
        )
    return lines


def run_from_manifests(
    *,
    frozen_manifest_path: Path = DEFAULT_FROZEN_MANIFEST,
    private_manifest_path: Path = DEFAULT_PRIVATE_MANIFEST,
    output_path: Path | None = DEFAULT_OUTPUT,
    path_mapping: Mapping[str, Path] | None = None,
) -> AggregateBenchmarkResult:
    frozen_entries = load_frozen_fixture_entries(frozen_manifest_path)
    frozen_payload = _read_json(frozen_manifest_path)
    manifest_id = frozen_payload.get("manifest_id")
    if manifest_id is not None and not isinstance(manifest_id, str):
        manifest_id = None

    if path_mapping is None:
        mapping = load_private_path_mapping(private_manifest_path)
        mapping_source = _safe_repo_relative(private_manifest_path)
    else:
        mapping = dict(path_mapping)
        mapping_source = "explicit_path_mapping"

    fixture_paths = resolve_fixture_paths(frozen_entries, mapping)
    modes = (ParserMode.NORMAL, ParserMode.LAYOUT)
    records = run_benchmark(fixture_paths, modes=modes)
    fixture_ids = [fixture_id for fixture_id, _ in fixture_paths]
    aggregate = build_aggregate(
        records=records,
        fixture_ids=fixture_ids,
        modes=modes,
        frozen_manifest_path=frozen_manifest_path,
        path_mapping_source=mapping_source,
        manifest_id=manifest_id,
    )
    if output_path is not None:
        write_aggregate(aggregate, output_path)
    return aggregate


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run focused pypdf normal/layout extraction benchmark. "
            "Emits aggregate metrics only; never prints document text."
        )
    )
    parser.add_argument(
        "--frozen-manifest",
        type=Path,
        default=DEFAULT_FROZEN_MANIFEST,
        help="Path to frozen safe fixture manifest JSON",
    )
    parser.add_argument(
        "--private-manifest",
        type=Path,
        default=DEFAULT_PRIVATE_MANIFEST,
        help="Ignored private path-mapping manifest (fixture_id -> local_path)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Aggregate JSON output path under evaluation reports",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print concise aggregate summary lines (no document text)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        result = run_from_manifests(
            frozen_manifest_path=args.frozen_manifest,
            private_manifest_path=args.private_manifest,
            output_path=args.output,
        )
    except (FixtureResolutionError, OSError, ValueError) as exc:
        print(f"benchmark_failed: {exc}", file=sys.stderr)
        return 1

    if args.print_summary:
        for line in concise_summary_lines(result):
            print(line)
    else:
        print(
            f"wrote_aggregate records={result.summary.record_count} "
            f"path={_safe_repo_relative(args.output)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
