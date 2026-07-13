#!/usr/bin/env python3
"""Phase 0 pypdf extraction gate for synthetic CV fixtures.

Single-purpose diagnostic: iterate committed fixtures, run pypdf normal and
layout extraction via the production owner, apply the shared meaningful-text
rule, and exit non-zero when the aggregate threshold fails or the image-only
fixture is accepted.

No OCR imports, subprocess OCR tools, remote OCR services, or alternate
parsers are used or permitted. Quality constants and extraction live only in
``app.services.pdf_extraction``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the installable backend package is importable when the diagnostic is
# run from a checkout without relying on a pre-activated editable install.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    import pypdf
    from app.services.pdf_extraction import (
        MEANINGFUL_TEXT_RULE,
        NO_EXTRACTABLE_TEXT,
        PdfMalformedError,
        extract_modes,
        is_meaningful_text,
        measure,
    )
except ImportError as exc:  # pragma: no cover - environment setup
    print("PYPDF_COMPATIBILITY=FAIL", file=sys.stderr)
    print(f"ERROR=import_pypdf_or_owner:{exc}", file=sys.stderr)
    raise SystemExit(2) from exc

DIGITAL_FIXTURES = (
    "digital_cv_01.pdf",
    "digital_cv_02.pdf",
    "digital_cv_03.pdf",
    "digital_cv_04.pdf",
    "digital_cv_05.pdf",
)
IMAGE_ONLY_FIXTURE = "image_only_cv.pdf"
REQUIRED_DIGITAL_PASSES = 4


def repo_root() -> Path:
    return _REPO_ROOT


def fixture_dir() -> Path:
    return repo_root() / "backend" / "tests" / "fixtures" / "cv"


def evaluate_digital(path: Path) -> dict:
    try:
        normal, layout, pages = extract_modes(path)
    except PdfMalformedError as exc:
        return {
            "name": path.name,
            "kind": "digital",
            "pages": 0,
            "normal_non_ws": 0,
            "layout_non_ws": 0,
            "normal_norm_len": 0,
            "layout_norm_len": 0,
            "normal_ok": False,
            "layout_ok": False,
            "success": False,
            "status": "FAIL",
            "error": str(exc),
        }
    n_len, n_non_ws = measure(normal)
    l_len, l_non_ws = measure(layout)
    normal_ok = is_meaningful_text(normal)
    layout_ok = is_meaningful_text(layout)
    # Fixture succeeds when either documented pypdf mode yields meaningful text.
    success = normal_ok or layout_ok
    return {
        "name": path.name,
        "kind": "digital",
        "pages": pages,
        "normal_non_ws": n_non_ws,
        "layout_non_ws": l_non_ws,
        "normal_norm_len": n_len,
        "layout_norm_len": l_len,
        "normal_ok": normal_ok,
        "layout_ok": layout_ok,
        "success": success,
        "status": "PASS" if success else "FAIL",
    }


def evaluate_image_only(path: Path) -> dict:
    try:
        normal, layout, pages = extract_modes(path)
    except PdfMalformedError as exc:
        return {
            "name": path.name,
            "kind": "image_only",
            "pages": 0,
            "normal_non_ws": 0,
            "layout_non_ws": 0,
            "normal_norm_len": 0,
            "layout_norm_len": 0,
            "normal_ok": False,
            "layout_ok": False,
            "accepted": False,
            "status": NO_EXTRACTABLE_TEXT,
            "error": str(exc),
        }
    n_len, n_non_ws = measure(normal)
    l_len, l_non_ws = measure(layout)
    normal_ok = is_meaningful_text(normal)
    layout_ok = is_meaningful_text(layout)
    # Must not accept image-only as extractable.
    accepted = normal_ok or layout_ok
    no_text = (not normal_ok) and (not layout_ok)
    return {
        "name": path.name,
        "kind": "image_only",
        "pages": pages,
        "normal_non_ws": n_non_ws,
        "layout_non_ws": l_non_ws,
        "normal_norm_len": n_len,
        "layout_norm_len": l_len,
        "normal_ok": normal_ok,
        "layout_ok": layout_ok,
        "accepted": accepted,
        "status": NO_EXTRACTABLE_TEXT if no_text else "UNEXPECTED_TEXT",
    }


def format_digital_line(row: dict) -> str:
    return (
        f"{row['name']}: kind=digital pages={row['pages']} "
        f"normal_non_ws={row['normal_non_ws']} layout_non_ws={row['layout_non_ws']} "
        f"normal_ok={row['normal_ok']} layout_ok={row['layout_ok']} "
        f"result={row['status']}"
    )


def format_image_line(row: dict) -> str:
    return (
        f"{row['name']}: kind=image_only pages={row['pages']} "
        f"normal_non_ws={row['normal_non_ws']} layout_non_ws={row['layout_non_ws']} "
        f"normal_ok={row['normal_ok']} layout_ok={row['layout_ok']} "
        f"result={row['status']}"
    )


def main() -> int:
    base = fixture_dir()
    print(f"pypdf_version={pypdf.__version__}")
    print("meaningful_text_rule=" + MEANINGFUL_TEXT_RULE.replace("\n", " "))

    digital_rows: list[dict] = []
    for name in DIGITAL_FIXTURES:
        path = base / name
        if not path.is_file():
            print(f"ERROR=missing_fixture:{name}", file=sys.stderr)
            print("PYPDF_COMPATIBILITY=FAIL")
            return 1
        row = evaluate_digital(path)
        digital_rows.append(row)
        print(format_digital_line(row))

    image_path = base / IMAGE_ONLY_FIXTURE
    if not image_path.is_file():
        print(f"ERROR=missing_fixture:{IMAGE_ONLY_FIXTURE}", file=sys.stderr)
        print("PYPDF_COMPATIBILITY=FAIL")
        return 1
    image_row = evaluate_image_only(image_path)
    print(format_image_line(image_row))

    digital_passes = sum(1 for row in digital_rows if row["success"])
    digital_total = len(digital_rows)
    allowed_failures = [
        row["name"] for row in digital_rows if not row["success"]
    ]
    image_ok = image_row["status"] == NO_EXTRACTABLE_TEXT

    print(
        f"aggregate: digital_pass={digital_passes}/{digital_total} "
        f"required>={REQUIRED_DIGITAL_PASSES} "
        f"allowed_digital_failures={allowed_failures or 'none'} "
        f"image_only={image_row['status']}"
    )

    gate_pass = digital_passes >= REQUIRED_DIGITAL_PASSES and image_ok
    if gate_pass:
        print("PYPDF_COMPATIBILITY=PASS")
        return 0

    print("PYPDF_COMPATIBILITY=FAIL")
    if digital_passes < REQUIRED_DIGITAL_PASSES:
        print(
            f"FAIL_REASON=digital_below_threshold:{digital_passes}/{digital_total}",
            file=sys.stderr,
        )
    if not image_ok:
        print(
            f"FAIL_REASON=image_only_not_rejected:{image_row['status']}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
