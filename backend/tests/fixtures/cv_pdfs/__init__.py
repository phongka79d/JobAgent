"""Synthetic CV PDF builders for Plan 4 privacy-boundary tests.

All fixtures are built in-process. No private corpus or OCR stack is required.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "build_multipage_text_pdf",
    "build_synthetic_image_only_pdf",
    "build_synthetic_text_pdf",
    "write_bytes",
]


def _build_pdf(content_streams: list[bytes]) -> bytes:
    """Minimal valid PDF with one page per content stream (Helvetica text)."""
    if not content_streams:
        content_streams = [b""]

    n_pages = len(content_streams)
    # Object layout:
    # 1 Catalog, 2 Pages, 3..2+n Page, 3+n..2+2n Contents, last Font
    objects: list[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    kids = " ".join(f"{3 + i} 0 R" for i in range(n_pages))
    objects.append(
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>\nendobj\n".encode(
            "ascii"
        )
    )

    font_obj_num = 3 + 2 * n_pages
    for i, _stream in enumerate(content_streams):
        page_obj = 3 + i
        content_obj = 3 + n_pages + i
        objects.append(
            (
                f"{page_obj} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_obj} 0 R "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>\n"
                f"endobj\n"
            ).encode("ascii")
        )

    for i, stream in enumerate(content_streams):
        content_obj = 3 + n_pages + i
        objects.append(
            (
                f"{content_obj} 0 obj\n<< /Length {len(stream)} >>\nstream\n"
            ).encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        )

    objects.append(
        (
            f"{font_obj_num} 0 obj\n"
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
            "endobj\n"
        ).encode("ascii")
    )

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


def _escape_pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_stream(text: str, *, start_y: int = 720) -> bytes:
    """Build a simple multi-line Tj stream (latin-1 safe subset)."""
    lines = text.split("\n")
    parts: list[str] = [f"BT /F1 11 Tf 72 {start_y} Td"]
    for i, line in enumerate(lines):
        # Keep within PDF literal string / Helvetica latin-1.
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        escaped = _escape_pdf_string(safe)
        if i == 0:
            parts.append(f"({escaped}) Tj")
        else:
            parts.append(f"0 -14 Td ({escaped}) Tj")
    parts.append("ET")
    return ("\n".join(parts) + "\n").encode("latin-1")


def build_synthetic_text_pdf(text: str = "SyntheticProbeText") -> bytes:
    """One-page PDF whose layout extraction yields the given text."""
    return _build_pdf([_text_stream(text)])


def build_synthetic_image_only_pdf() -> bytes:
    """One-page PDF with an empty content stream (no text operators)."""
    return _build_pdf([b""])


def build_multipage_text_pdf(
    page_texts: list[str] | None = None,
    *,
    page_count: int | None = None,
    line: str = "PageBody",
) -> bytes:
    """Multi-page synthetic text PDF.

    Provide either ``page_texts`` or ``page_count`` (filled with ``line``).
    """
    if page_texts is None:
        if page_count is None:
            page_count = 1
        page_texts = [f"{line} {i + 1}" for i in range(page_count)]
    return _build_pdf([_text_stream(t) for t in page_texts])


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
