"""Fail-closed pypdf layout text extraction for CV intake.

Reuses the locked Phase 0 semantics from
``evaluation/benchmark_pdf_extraction.py``:

- extraction mode is pypdf ``layout`` only (no OCR, no alternate parsers)
- usable text = non-whitespace characters only
- zero usable characters maps to exact code ``NO_EXTRACTABLE_TEXT``
- page count is reported; over-limit PDFs fail with a stable code

Exceptions expose only stable codes — never raw PDF text, paths, or stack
detail intended for external callers. Raw extracted text is returned only via
the internal ``PdfTextResult`` boundary for the next redaction step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Final, Literal

from pypdf import PdfReader

# Mirrors Settings.max_pdf_pages default (typed root contract MAX_PDF_PAGES).
DEFAULT_MAX_PDF_PAGES: Final[int] = 10

# Locked pypdf extraction mode (Phase 0 / Plan 4).
_EXTRACTION_MODE: Final[Literal["layout"]] = "layout"


class PdfTextErrorCode(StrEnum):
    """Stable, non-sensitive PDF text failure codes."""

    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    PDF_PARSE_FAILED = "PDF_PARSE_FAILED"
    INVALID_SOURCE = "INVALID_SOURCE"


class PdfTextError(Exception):
    """Sanitized PDF text failure (code-only str/repr; no document text)."""

    def __init__(self, code: PdfTextErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PdfTextError(code={self.code.value!r})"


@dataclass(frozen=True, slots=True)
class PdfTextResult:
    """Internal extraction result for the redaction boundary.

    ``text`` is raw layout-extracted text and must not leave the internal
    service pipeline unredacted. Public errors never embed this field.
    """

    page_count: int
    text: str
    usable_character_count: int


def usable_character_count(text: str) -> int:
    """Count non-whitespace characters (Phase 0 zero-yield contract)."""
    return sum(1 for ch in text if not ch.isspace())


def extract_pdf_text(
    source: bytes | Path | BinaryIO,
    *,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> PdfTextResult:
    """Extract layout text from a PDF and enforce the page/usable-text gates.

    Parameters
    ----------
    source:
        PDF bytes, a filesystem path, or a binary file object. Callers that
        open contained attachment paths must already own containment checks.
    max_pages:
        Inclusive upper bound on page count (typed settings default: 10).

    Returns
    -------
    PdfTextResult
        Page count, joined layout text, and usable character count when
        extraction succeeds and text is usable.

    Raises
    ------
    PdfTextError
        With a stable code for invalid source, parse failure, page limit, or
        zero usable digital text. Never embeds raw document content.
    """
    if max_pages < 1:
        raise PdfTextError(PdfTextErrorCode.INVALID_SOURCE)

    stream, owns_buffer = _open_source(source)
    try:
        try:
            reader = PdfReader(stream, strict=False)
        except PdfTextError:
            raise
        except Exception:
            raise PdfTextError(PdfTextErrorCode.PDF_PARSE_FAILED) from None

        try:
            if getattr(reader, "is_encrypted", False):
                # Encrypted PDFs are not supported; fail closed without probing.
                raise PdfTextError(PdfTextErrorCode.PDF_PARSE_FAILED)

            pages = reader.pages
            page_count = len(pages)
        except PdfTextError:
            raise
        except Exception:
            raise PdfTextError(PdfTextErrorCode.PDF_PARSE_FAILED) from None

        if page_count > max_pages:
            raise PdfTextError(PdfTextErrorCode.PAGE_LIMIT_EXCEEDED)

        try:
            chunks: list[str] = []
            for page in pages:
                page_text = page.extract_text(extraction_mode=_EXTRACTION_MODE)
                chunks.append(page_text if isinstance(page_text, str) else "")
            joined = "".join(chunks)
        except Exception:
            raise PdfTextError(PdfTextErrorCode.PDF_PARSE_FAILED) from None

        usable = usable_character_count(joined)
        if usable == 0:
            raise PdfTextError(PdfTextErrorCode.NO_EXTRACTABLE_TEXT)

        return PdfTextResult(
            page_count=page_count,
            text=joined,
            usable_character_count=usable,
        )
    finally:
        if owns_buffer:
            stream.close()


def _open_source(source: bytes | Path | BinaryIO) -> tuple[BinaryIO, bool]:
    """Return a readable binary stream and whether the caller should close it."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return BytesIO(bytes(source)), True
    if isinstance(source, Path):
        try:
            return source.open("rb"), True
        except OSError:
            raise PdfTextError(PdfTextErrorCode.INVALID_SOURCE) from None
    # BinaryIO-like: do not close caller-owned streams.
    read = getattr(source, "read", None)
    if not callable(read):
        raise PdfTextError(PdfTextErrorCode.INVALID_SOURCE)
    return source, False
