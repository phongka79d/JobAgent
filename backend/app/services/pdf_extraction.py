"""Sole production owner for pypdf digital-text extraction and quality rules.

Ownership
---------
* Pinned ``pypdf`` digital-text extraction only (normal + layout modes).
* Profession-neutral meaningful-text threshold and normalization.
* Stable ``NO_EXTRACTABLE_TEXT`` when neither mode yields meaningful text.
* Page count and malformed-PDF failures for upload validation.

OCR, alternate PDF parsers, and remote text services are never imported or
called. Raw extracted text is transient service data: callers must not log,
persist, serialize into public contracts, chat rows, tool logs, checkpoints,
Agent context, or Neo4j.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Final

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

# --- Profession-neutral meaningful-text rule (single definition) ---

MIN_NON_WHITESPACE_CHARS: Final[int] = 80

MEANINGFUL_TEXT_RULE: Final[str] = (
    "After Unicode NFKC and whitespace normalization, text is meaningful when "
    f"non-whitespace character count >= {MIN_NON_WHITESPACE_CHARS} and at least "
    "one Unicode letter or number is present. Image-only, empty, punctuation-only, "
    "and below-threshold digital text map to NO_EXTRACTABLE_TEXT. OCR is never used."
)

# Stable application failure codes (attachment/service layer).
NO_EXTRACTABLE_TEXT: Final[str] = "NO_EXTRACTABLE_TEXT"
MALFORMED_PDF: Final[str] = "MALFORMED_PDF"

_PdfSource = Path | str | bytes | BinaryIO


class PdfMalformedError(ValueError):
    """Raised when pypdf cannot open or parse the PDF for page/text extraction."""

    failure_code: str = MALFORMED_PDF

    def __init__(self, message: str = "PDF is malformed or unreadable") -> None:
        super().__init__(message)
        self.failure_code = MALFORMED_PDF


@dataclass(frozen=True, slots=True)
class PdfTextExtraction:
    """Transient digital-text extraction outcome for one PDF.

    ``normal_text`` / ``layout_text`` are service-private. Do not log, persist,
    or return them from public HTTP/tool contracts.
    """

    page_count: int
    normal_text: str
    layout_text: str
    normal_is_meaningful: bool
    layout_is_meaningful: bool

    @property
    def has_meaningful_text(self) -> bool:
        """True when either documented pypdf mode yields meaningful text."""
        return self.normal_is_meaningful or self.layout_is_meaningful

    @property
    def failure_code(self) -> str | None:
        """``NO_EXTRACTABLE_TEXT`` when quality fails; otherwise ``None``."""
        if self.has_meaningful_text:
            return None
        return NO_EXTRACTABLE_TEXT

    @property
    def preferred_text(self) -> str | None:
        """Layout text when meaningful; else normal; else ``None``.

        Plan 4 production pipeline prefers layout extraction; Phase 0 gate
        still accepts either mode via :attr:`has_meaningful_text`.
        """
        if self.layout_is_meaningful:
            return self.layout_text
        if self.normal_is_meaningful:
            return self.normal_text
        return None


def normalize_whitespace(text: str) -> str:
    """Apply NFKC and collapse whitespace for measurement/rule evaluation."""
    normalized = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", normalized).strip()


def non_whitespace_count(text: str) -> int:
    """Count non-whitespace characters in ``text``."""
    return sum(1 for ch in text if not ch.isspace())


def is_meaningful_text(text: str) -> bool:
    """Apply the owned minimum-text/quality rule for extractable CV text."""
    normalized = normalize_whitespace(text)
    if non_whitespace_count(normalized) < MIN_NON_WHITESPACE_CHARS:
        return False
    return any(character.isalnum() for character in normalized)


def measure(text: str) -> tuple[int, int]:
    """Return ``(normalized_length, non_whitespace_count)`` after ws normalize."""
    normalized = normalize_whitespace(text)
    return len(normalized), non_whitespace_count(normalized)


def _open_reader(source: _PdfSource) -> PdfReader:
    """Open a :class:`PdfReader` from path, bytes, or binary stream."""
    try:
        if isinstance(source, (bytes, bytearray)):
            return PdfReader(BytesIO(bytes(source)), strict=False)
        if isinstance(source, (str, Path)):
            return PdfReader(str(source), strict=False)
        # BinaryIO / file-like
        return PdfReader(source, strict=False)
    except (PdfReadError, PdfStreamError, OSError, ValueError, TypeError) as exc:
        raise PdfMalformedError(
            f"PDF is malformed or unreadable: {exc}"
        ) from exc


def parse_page_count(source: _PdfSource) -> int:
    """Return PDF page count for upload validation (before final row/file).

    Raises:
        PdfMalformedError: when the PDF cannot be opened or pages cannot be read.
    """
    reader = _open_reader(source)
    try:
        return len(reader.pages)
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        raise PdfMalformedError(
            f"PDF page count unavailable: {exc}"
        ) from exc


def extract_modes(source: _PdfSource) -> tuple[str, str, int]:
    """Return ``(normal_text, layout_text, page_count)`` using pypdf only.

    Raises:
        PdfMalformedError: when the PDF cannot be opened or text cannot be read.
    """
    reader = _open_reader(source)
    try:
        page_count = len(reader.pages)
        normal_parts: list[str] = []
        layout_parts: list[str] = []
        for page in reader.pages:
            normal_parts.append(page.extract_text() or "")
            layout_parts.append(page.extract_text(extraction_mode="layout") or "")
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        raise PdfMalformedError(
            f"PDF text extraction failed: {exc}"
        ) from exc
    return "\n".join(normal_parts), "\n".join(layout_parts), page_count


def extract_pdf_text(source: _PdfSource) -> PdfTextExtraction:
    """Extract normal + layout text and apply the meaningful-text rule.

    Does not enforce ``MAX_PDF_PAGES`` (upload service owns that decision using
    :func:`parse_page_count` / :attr:`PdfTextExtraction.page_count`).
    Never calls OCR or any alternate parser.

    Raises:
        PdfMalformedError: unreadable / malformed PDF.
    """
    normal, layout, pages = extract_modes(source)
    return PdfTextExtraction(
        page_count=pages,
        normal_text=normal,
        layout_text=layout,
        normal_is_meaningful=is_meaningful_text(normal),
        layout_is_meaningful=is_meaningful_text(layout),
    )
