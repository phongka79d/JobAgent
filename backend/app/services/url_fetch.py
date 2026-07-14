"""Bounded HTTP/HTTPS Job Description text acquisition (Plan 5 §7.2).

Ownership
---------
* Scheme allowlist: ``http`` and ``https`` only.
* Controlled download timeout and streamed body size from settings
  (``URL_FETCH_TIMEOUT_SECONDS``, ``URL_MAX_RESPONSE_MB``).
* One wall-clock timeout covers the complete request plus streamed-body read.
* Request-level ``follow_redirects=False`` (3xx treated as unavailable).
* MIME allowlist: ``text/html`` and ``text/plain`` after stripping charset
  parameters.
* Plain-text decode of the body; HTML main text via pinned Trafilatura.
* Admission: reject only absent or whitespace-only (``strip()`` empty) text;
  every other non-empty result is accepted unchanged (no length/keyword/
  contact heuristics — quality classification is later).
* Stable paste-text fallback messages for unsupported/unavailable/empty paths.

No cookies, authentication headers, browser/JS renderer, site scrapers, SSRF
or redirect validation, persistence, providers, or graph behavior. Never log
response headers or a full source document.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.settings import Settings, get_settings

# Stable application failure codes for URL acquisition.
URL_UNSUPPORTED_SCHEME: Final[str] = "URL_UNSUPPORTED_SCHEME"
URL_UNSUPPORTED_CONTENT_TYPE: Final[str] = "URL_UNSUPPORTED_CONTENT_TYPE"
URL_FETCH_TIMEOUT: Final[str] = "URL_FETCH_TIMEOUT"
URL_FETCH_UNAVAILABLE: Final[str] = "URL_FETCH_UNAVAILABLE"
URL_RESPONSE_TOO_LARGE: Final[str] = "URL_RESPONSE_TOO_LARGE"
URL_EMPTY_TEXT: Final[str] = "URL_EMPTY_TEXT"

# Single user-facing paste instruction for every acquisition failure.
PASTE_JD_FALLBACK_MESSAGE: Final[str] = (
    "Unable to obtain job description text from the URL. "
    "Please paste the job description text instead."
)

ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})
ALLOWED_MIME_TYPES: Final[frozenset[str]] = frozenset({"text/html", "text/plain"})
MIME_TEXT_HTML: Final[str] = "text/html"
MIME_TEXT_PLAIN: Final[str] = "text/plain"

_STREAM_CHUNK: Final[int] = 64 * 1024
_DEFAULT_CHARSET: Final[str] = "utf-8"


@dataclass(frozen=True, slots=True)
class UrlFetchResult:
    """Outcome of one constrained URL-to-text acquisition attempt.

    On success ``text`` is non-None and ``failure_code`` is None.
    On failure ``text`` is None, ``failure_code`` is set, and
    ``paste_fallback_message`` is the stable paste-text instruction.
    """

    text: str | None
    failure_code: str | None

    @property
    def ok(self) -> bool:
        """True when admitted JD text was obtained."""
        return self.failure_code is None and self.text is not None

    @property
    def paste_fallback_message(self) -> str | None:
        """Stable paste instruction on failure; None on success."""
        if self.ok:
            return None
        return PASTE_JD_FALLBACK_MESSAGE


def _failure(code: str) -> UrlFetchResult:
    return UrlFetchResult(text=None, failure_code=code)


def _success(text: str) -> UrlFetchResult:
    return UrlFetchResult(text=text, failure_code=None)


def is_admitted_text(text: str | None) -> bool:
    """Return True when text is present and not whitespace-only after strip.

    Approved admission predicate only — no length, keyword, or contact check.
    """
    return text is not None and text.strip() != ""


def base_mime_type(content_type: str | None) -> str:
    """Return the MIME type without parameters (charset ignored)."""
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def charset_from_content_type(content_type: str | None) -> str | None:
    """Extract an optional charset parameter; does not affect MIME allowlisting."""
    if not content_type:
        return None
    parts = content_type.split(";")
    for part in parts[1:]:
        token = part.strip()
        if token.lower().startswith("charset="):
            value = token.split("=", 1)[1].strip().strip("\"'")
            return value or None
    return None


def decode_body(raw: bytes, content_type: str | None) -> str:
    """Decode response bytes using charset when present, else UTF-8."""
    encoding = charset_from_content_type(content_type) or _DEFAULT_CHARSET
    try:
        return raw.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return raw.decode(_DEFAULT_CHARSET, errors="replace")


def extract_html_main_text(html: str) -> str | None:
    """Extract main document text via pinned Trafilatura (no network).

    Raised extractor errors become a null result so callers return the stable
    paste-text failure path without leaking exception details.
    """
    try:
        return trafilatura.extract(html)
    except Exception:
        return None


def validate_url_scheme(url: str) -> str | None:
    """Return failure code when scheme is not http/https; else None."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return URL_UNSUPPORTED_SCHEME
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return URL_UNSUPPORTED_SCHEME
    if not parsed.netloc:
        return URL_UNSUPPORTED_SCHEME
    return None


async def _read_stream_bounded(
    response: httpx.Response,
    max_bytes: int,
) -> bytes | None:
    """Read the response body while streaming; return None if over limit.

    Stops reading as soon as the cumulative size exceeds ``max_bytes`` so
    the client never buffers an unbounded body into memory.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes(chunk_size=_STREAM_CHUNK):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _build_client(
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.AsyncClient:
    """Create a fresh client: timeout only, no cookies or auth headers."""
    timeout = httpx.Timeout(timeout_seconds)
    # Intentionally no Authorization/Cookie headers and no shared cookie jar.
    # Redirects are also disabled at request level; client default matches.
    return httpx.AsyncClient(
        timeout=timeout,
        transport=transport,
        follow_redirects=False,
        headers={},
    )


async def _acquire_response_body(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
) -> UrlFetchResult | tuple[bytes, str | None, str]:
    """Perform one non-redirecting GET and stream a bounded body.

    Returns either an early failure result or ``(raw, content_type, mime)``.
    """
    # Request-level override: never follow redirects even if an injected client
    # was constructed with follow_redirects=True (avoids cookie/header leakage).
    async with client.stream("GET", url, follow_redirects=False) as response:
        if response.status_code < 200 or response.status_code >= 300:
            return _failure(URL_FETCH_UNAVAILABLE)

        content_type = response.headers.get("content-type")
        mime = base_mime_type(content_type)
        if mime not in ALLOWED_MIME_TYPES:
            return _failure(URL_UNSUPPORTED_CONTENT_TYPE)

        raw = await _read_stream_bounded(response, max_bytes)
        if raw is None:
            return _failure(URL_RESPONSE_TOO_LARGE)
        return raw, content_type, mime


async def fetch_url_text(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_seconds: float | None = None,
    max_response_mb: int | None = None,
) -> UrlFetchResult:
    """Fetch and acquire JD text from a public HTTP/HTTPS URL.

    Parameters
    ----------
    url:
        Candidate source URL (only ``http`` / ``https``).
    settings:
        Optional settings; used for timeout/size defaults when not overridden.
    client:
        Injected ``httpx.AsyncClient`` for tests; owns no auth/cookies.
    transport:
        Optional transport when constructing an ephemeral client (tests).
    timeout_seconds / max_response_mb:
        Explicit overrides for tests; otherwise settings values.

    Returns
    -------
    UrlFetchResult
        Admitted text on success, or failure with paste-text fallback message.
    """
    scheme_error = validate_url_scheme(url)
    if scheme_error is not None:
        return _failure(scheme_error)

    cfg = settings if settings is not None else get_settings()
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(cfg.URL_FETCH_TIMEOUT_SECONDS)
    )
    max_mb = (
        int(max_response_mb)
        if max_response_mb is not None
        else int(cfg.URL_MAX_RESPONSE_MB)
    )
    max_bytes = max_mb * 1024 * 1024

    owns_client = client is None
    active = client if client is not None else _build_client(timeout, transport)

    try:
        try:
            # Wall-clock budget for the full request + streamed body read.
            async with asyncio.timeout(timeout):
                outcome = await _acquire_response_body(active, url, max_bytes)
        except TimeoutError:
            return _failure(URL_FETCH_TIMEOUT)
        except httpx.TimeoutException:
            return _failure(URL_FETCH_TIMEOUT)
        except httpx.HTTPError:
            return _failure(URL_FETCH_UNAVAILABLE)
    finally:
        if owns_client:
            await active.aclose()

    if isinstance(outcome, UrlFetchResult):
        return outcome

    raw, content_type, mime = outcome
    decoded = decode_body(raw, content_type)

    if mime == MIME_TEXT_PLAIN:
        acquired: str | None = decoded
    else:
        acquired = extract_html_main_text(decoded)

    if not is_admitted_text(acquired):
        return _failure(URL_EMPTY_TEXT)

    # Admitted text is returned unchanged (including short/contact-only text).
    assert acquired is not None
    return _success(acquired)
