"""Acquire deterministic JD text from exactly one public URL or pasted raw text.

Batch01 (01B) boundary:

- Exactly one of ``url`` or ``raw_text`` is accepted.
- URL path uses the controlled (01A) fetcher only — never bypasses it.
- Raw path never calls the fetcher.
- ``text/plain`` bodies decode directly; ``text/html`` uses Trafilatura only
  (scripts/comments/metadata excluded). No browser, JavaScript, alternate
  parser, authenticated, or paywall fallback.
- Blank or failed HTML main-text extraction returns ``JD_TEXT_REQUIRED``.
- Canonical text normalizes Unicode (NFC), line endings, and edge whitespace
  while preserving semantic case, punctuation, and internal line structure.
- ``content_hash`` is SHA-256 of the UTF-8 canonical text.

Exception strings never embed raw JD text, response bodies, or unsafe URL
details.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import trafilatura

from app.services.url_fetcher import UrlFetcher, UrlFetchError, UrlFetchResult

# Reuse the public chat turn pasted-user-text ceiling (schemas.chat).
MAX_PASTED_JD_TEXT_LEN: Final[int] = 32_768

# Media types already approved by the (01A) fetcher.
_MEDIA_PLAIN: Final[str] = "text/plain"
_MEDIA_HTML: Final[str] = "text/html"


class JdSourceErrorCode(StrEnum):
    """Stable, non-sensitive JD source failure codes."""

    INVALID_INPUT = "INVALID_INPUT"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    JD_TEXT_REQUIRED = "JD_TEXT_REQUIRED"


class JdSourceType(StrEnum):
    """How the acquired JD content was supplied."""

    URL = "url"
    RAW_TEXT = "raw_text"


class JdSourceError(Exception):
    """Sanitized JD source failure (code-only str/repr; no raw content/URL)."""

    def __init__(self, code: JdSourceErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"JdSourceError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@dataclass(frozen=True, slots=True)
class AcquiredJd:
    """Typed acquired-JD object for later persistence/hash dedup.

    ``source_url`` is the credential-free public URL from the fetcher when the
    source was a URL; always ``None`` for raw pasted text. ``canonical_text``
    and ``content_hash`` are deterministic for equivalent content regardless of
    URL versus paste delivery after extraction.
    """

    source_type: JdSourceType
    canonical_text: str
    content_hash: str
    source_url: str | None = None


HtmlExtractor = Callable[[str], str | None]


def canonicalize_jd_text(text: str) -> str:
    """Return deterministic JD text for hashing and storage.

    Normalizes Unicode to NFC, converts CR/LF forms to ``\\n``, strips trailing
    horizontal whitespace on each line, and strips document-edge whitespace.
    Does **not** casefold, strip punctuation, or collapse internal blank lines
    or indentation.
    """
    if not isinstance(text, str):
        raise TypeError("jd text must be a string")
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def hash_canonical_text(canonical_text: str) -> str:
    """Return lowercase hex SHA-256 of UTF-8 ``canonical_text``."""
    if not isinstance(canonical_text, str):
        raise TypeError("canonical_text must be a string")
    digest = hashlib.sha256(canonical_text.encode("utf-8"))
    return digest.hexdigest()


def extract_html_main_text(html: str) -> str | None:
    """Extract main text from HTML via Trafilatura only.

    Excludes comments and metadata. Returns ``None`` when extraction fails or
    yields only blank content. Never falls back to a browser or alternate
    parser.
    """
    if not isinstance(html, str):
        return None
    if not html.strip():
        return None
    try:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            with_metadata=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            include_formatting=False,
            output_format="txt",
        )
    except Exception:
        return None
    if extracted is None:
        return None
    if not extracted.strip():
        return None
    return extracted


def _decode_plain_body(body: bytes) -> str:
    """Decode an approved ``text/plain`` body deterministically."""
    payload = body
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        # Deterministic fallback; latin-1 maps every byte.
        return payload.decode("latin-1")


def _decode_html_body(body: bytes) -> str:
    """Decode an approved ``text/html`` body for Trafilatura input."""
    payload = body
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("latin-1")


def _from_raw_text(raw_text: str) -> AcquiredJd:
    if not isinstance(raw_text, str):
        raise JdSourceError(JdSourceErrorCode.INVALID_INPUT)
    if len(raw_text) > MAX_PASTED_JD_TEXT_LEN:
        raise JdSourceError(JdSourceErrorCode.INPUT_TOO_LARGE)
    canonical = canonicalize_jd_text(raw_text)
    if not canonical:
        raise JdSourceError(JdSourceErrorCode.INVALID_INPUT)
    return AcquiredJd(
        source_type=JdSourceType.RAW_TEXT,
        canonical_text=canonical,
        content_hash=hash_canonical_text(canonical),
        source_url=None,
    )


def _text_from_fetch_result(
    result: UrlFetchResult,
    *,
    html_extractor: HtmlExtractor,
) -> str:
    media = result.media_type
    if media == _MEDIA_PLAIN:
        return _decode_plain_body(result.body)
    if media == _MEDIA_HTML:
        html = _decode_html_body(result.body)
        try:
            extracted = html_extractor(html)
        except JdSourceError:
            raise
        except Exception:
            # Extraction failure must not leak body text or stack detail.
            raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED) from None
        if extracted is None:
            raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED)
        if not isinstance(extracted, str) or not extracted.strip():
            raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED)
        return extracted
    # Fetcher should never return other types; fail closed without body detail.
    raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED)


def _from_url(
    url: str,
    *,
    fetcher: UrlFetcher,
    html_extractor: HtmlExtractor,
) -> AcquiredJd:
    if not isinstance(url, str) or not url.strip():
        raise JdSourceError(JdSourceErrorCode.INVALID_INPUT)
    try:
        fetch_result = fetcher.fetch(url)
    except UrlFetchError:
        # Preserve sanitized (01A) codes; never wrap with JD body/URL detail.
        raise
    except JdSourceError:
        raise
    except Exception:
        # Unexpected transport/programming errors must not leak content.
        raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED) from None

    raw_extracted = _text_from_fetch_result(
        fetch_result,
        html_extractor=html_extractor,
    )
    canonical = canonicalize_jd_text(raw_extracted)
    if not canonical:
        raise JdSourceError(JdSourceErrorCode.JD_TEXT_REQUIRED)
    return AcquiredJd(
        source_type=JdSourceType.URL,
        canonical_text=canonical,
        content_hash=hash_canonical_text(canonical),
        source_url=fetch_result.source_url,
    )


def acquire_jd(
    *,
    url: str | None = None,
    raw_text: str | None = None,
    fetcher: UrlFetcher | None = None,
    html_extractor: HtmlExtractor | None = None,
) -> AcquiredJd:
    """Acquire one JD from exactly one URL or raw-text input.

    Parameters
    ----------
    url:
        Public HTTP/HTTPS URL. When set, ``fetcher`` is required and the raw
        path is not used.
    raw_text:
        Pasted JD text (bounded by ``MAX_PASTED_JD_TEXT_LEN``). Never calls the
        fetcher.
    fetcher:
        Controlled (01A) ``UrlFetcher``. Required when ``url`` is provided.
    html_extractor:
        Optional injectable HTML main-text extractor (defaults to Trafilatura).
        Used only for approved ``text/html`` fetch results.

    Returns
    -------
    AcquiredJd
        Source type, optional safe source URL, canonical text, and content hash.

    Raises
    ------
    JdSourceError
        ``INVALID_INPUT`` when neither/both inputs are given, raw text is blank,
        or URL is empty; ``INPUT_TOO_LARGE`` when pasted text exceeds the chat
        ceiling; ``JD_TEXT_REQUIRED`` when HTML extraction is blank/failed
        (caller must ask the user to paste JD text).
    UrlFetchError
        Propagated unchanged from the (01A) fetcher on policy/network failures.
    """
    url_provided = url is not None
    raw_provided = raw_text is not None
    if url_provided == raw_provided:
        # Both or neither — strict one-of.
        raise JdSourceError(JdSourceErrorCode.INVALID_INPUT)

    extractor = html_extractor if html_extractor is not None else extract_html_main_text

    if raw_provided:
        # Raw path never touches the network/fetcher.
        assert raw_text is not None
        return _from_raw_text(raw_text)

    assert url is not None
    if fetcher is None:
        raise JdSourceError(JdSourceErrorCode.INVALID_INPUT)
    return _from_url(url, fetcher=fetcher, html_extractor=extractor)


__all__ = [
    "MAX_PASTED_JD_TEXT_LEN",
    "AcquiredJd",
    "HtmlExtractor",
    "JdSourceError",
    "JdSourceErrorCode",
    "JdSourceType",
    "acquire_jd",
    "canonicalize_jd_text",
    "extract_html_main_text",
    "hash_canonical_text",
]
