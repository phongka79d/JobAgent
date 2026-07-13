#!/usr/bin/env python3
"""Phase 0 pypdf extraction gate for synthetic CV fixtures.

Single-purpose diagnostic: iterate committed fixtures, run pypdf normal and
layout extraction, apply the owned meaningful-text rule, and exit non-zero
when the aggregate threshold fails or the image-only fixture is accepted.

No OCR imports, subprocess OCR tools, remote OCR services, or alternate
parsers are used or permitted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import pypdf
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - environment setup
    print("PYPDF_COMPATIBILITY=FAIL", file=sys.stderr)
    print(f"ERROR=import_pypdf:{exc}", file=sys.stderr)
    raise SystemExit(2) from exc

# --- Owned feasibility rule (single location; reuse in production later) ---

MIN_NON_WHITESPACE_CHARS = 80

# Case-insensitive markers proving identity / experience / skills presence.
IDENTITY_MARKERS = (
    "email",
    "phone",
    "@",
    "name",
)
EXPERIENCE_MARKERS = (
    "experience",
    "engineer",
    "developer",
    "analyst",
    "worked",
    "senior",
    "staff",
    "platform",
)
SKILLS_MARKERS = (
    "skills",
    "python",
    "typescript",
    "sql",
    "react",
    "docker",
    "fastapi",
)

MEANINGFUL_TEXT_RULE = (
    "After whitespace normalization (collapse runs of whitespace, strip), text is "
    "meaningful when (1) non-whitespace character count >= "
    f"{MIN_NON_WHITESPACE_CHARS}, and (2) the lowercased text contains at least one "
    "identity marker "
    f"({', '.join(IDENTITY_MARKERS)}), one experience marker "
    f"({', '.join(EXPERIENCE_MARKERS)}), and one skills marker "
    f"({', '.join(SKILLS_MARKERS)}). Image-only / empty digital text maps to "
    "NO_EXTRACTABLE_TEXT. OCR is never used."
)

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
    return Path(__file__).resolve().parents[2]


def fixture_dir() -> Path:
    return repo_root() / "backend" / "tests" / "fixtures" / "cv"


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace only for measurement and rule evaluation."""
    return re.sub(r"\s+", " ", text or "").strip()


def non_whitespace_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def has_marker(text_lower: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text_lower for marker in markers)


def is_meaningful_text(text: str) -> bool:
    """Apply the owned minimum-text/quality rule for extractable CV text."""
    normalized = normalize_whitespace(text)
    if non_whitespace_count(normalized) < MIN_NON_WHITESPACE_CHARS:
        return False
    lower = normalized.lower()
    return (
        has_marker(lower, IDENTITY_MARKERS)
        and has_marker(lower, EXPERIENCE_MARKERS)
        and has_marker(lower, SKILLS_MARKERS)
    )


def extract_modes(path: Path) -> tuple[str, str, int]:
    """Return (normal_text, layout_text, page_count) using pypdf only."""
    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    normal_parts: list[str] = []
    layout_parts: list[str] = []
    for page in reader.pages:
        normal_parts.append(page.extract_text() or "")
        layout_parts.append(page.extract_text(extraction_mode="layout") or "")
    return "\n".join(normal_parts), "\n".join(layout_parts), page_count


def measure(text: str) -> tuple[int, int]:
    """Return (raw_char_len_after_ws_normalize, non_whitespace_count)."""
    normalized = normalize_whitespace(text)
    return len(normalized), non_whitespace_count(normalized)


def evaluate_digital(path: Path) -> dict:
    normal, layout, pages = extract_modes(path)
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
    normal, layout, pages = extract_modes(path)
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
        "status": "NO_EXTRACTABLE_TEXT" if no_text else "UNEXPECTED_TEXT",
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
    image_ok = image_row["status"] == "NO_EXTRACTABLE_TEXT"

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
