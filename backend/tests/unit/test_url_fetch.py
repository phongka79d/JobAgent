"""Unit tests for bounded URL→JD text acquisition (Plan 5 §7.2).

All HTTP uses ``httpx.MockTransport``; no public network access.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.services import url_fetch
from app.services.url_fetch import (
    ALLOWED_MIME_TYPES,
    ALLOWED_SCHEMES,
    PASTE_JD_FALLBACK_MESSAGE,
    URL_EMPTY_TEXT,
    URL_FETCH_TIMEOUT,
    URL_FETCH_UNAVAILABLE,
    URL_RESPONSE_TOO_LARGE,
    URL_UNSUPPORTED_CONTENT_TYPE,
    URL_UNSUPPORTED_SCHEME,
    UrlFetchResult,
    base_mime_type,
    charset_from_content_type,
    decode_body,
    fetch_url_text,
    is_admitted_text,
)

SERVICE_PATH = Path(url_fetch.__file__).resolve()
SOURCE = SERVICE_PATH.read_text(encoding="utf-8")

# Small synthetic HTML that Trafilatura 2.1.0 extracts main text from.
SAMPLE_HTML = (
    "<!DOCTYPE html><html><head><title>Role</title></head>"
    "<body><article><h1>Backend Engineer</h1>"
    "<p>Build APIs with Python and FastAPI for our platform team.</p>"
    "</article></body></html>"
)
SAMPLE_PLAIN = "Backend Engineer\nBuild APIs with Python and FastAPI."
CONTACT_ONLY = "Email: hiring@example.com\nPhone: 555-0100"
SHORT_TEXT = "Hi"


def _settings_like(
    *,
    timeout: int = 10,
    max_mb: int = 5,
) -> Any:
    """Minimal stand-in for Settings URL fields (no root .env load)."""

    class _S:
        URL_FETCH_TIMEOUT_SECONDS = timeout
        URL_MAX_RESPONSE_MB = max_mb

    return _S()


def _transport(
    handler: Any,
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _fetch(
    url: str,
    handler: Any,
    *,
    max_mb: int = 5,
    timeout: float = 10.0,
) -> UrlFetchResult:
    transport = _transport(handler)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        return await fetch_url_text(
            url,
            client=client,
            settings=_settings_like(timeout=int(timeout), max_mb=max_mb),
            max_response_mb=max_mb,
            timeout_seconds=timeout,
        )


# --- Scheme allowlist ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/jd",
        "file:///tmp/jd.html",
        "javascript:alert(1)",
        "data:text/plain,hello",
        "not-a-url",
        "",
        "http://",  # no netloc
    ],
)
async def test_unsupported_scheme_returns_paste_fallback(url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not fetch for scheme/url {url!r}")

    result = await _fetch(url or "http://", handler)
    assert result.ok is False
    assert result.failure_code == URL_UNSUPPORTED_SCHEME
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE
    assert result.text is None


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", sorted(ALLOWED_SCHEMES))
async def test_http_https_schemes_accepted(scheme: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SAMPLE_PLAIN.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    result = await _fetch(f"{scheme}://example.com/job", handler)
    assert result.ok is True
    assert result.text == SAMPLE_PLAIN
    assert result.failure_code is None
    assert result.paste_fallback_message is None


# --- Content-Type allowlist (charset ignored for allowlist) ---


@pytest.mark.parametrize(
    ("header", "expected_mime"),
    [
        ("text/html", "text/html"),
        ("text/plain", "text/plain"),
        ("text/html; charset=utf-8", "text/html"),
        ("text/plain; charset=ISO-8859-1", "text/plain"),
        ("TEXT/HTML;Charset=UTF-8", "text/html"),
        ("text/plain; charset=utf-8; format=flowed", "text/plain"),
    ],
)
def test_base_mime_ignores_charset_parameters(
    header: str, expected_mime: str
) -> None:
    assert base_mime_type(header) == expected_mime
    assert base_mime_type(header) in ALLOWED_MIME_TYPES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    [
        "text/html",
        "text/html; charset=utf-8",
        "text/html;charset=UTF-8",
    ],
)
async def test_html_content_types_accepted_with_charset(content_type: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SAMPLE_HTML.encode("utf-8"),
            headers={"content-type": content_type},
        )

    result = await _fetch("https://example.com/job", handler)
    assert result.ok is True
    assert result.text is not None
    assert "Backend Engineer" in result.text or "Python" in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "text/plain; charset=utf-8",
        "text/plain; charset=ISO-8859-1",
    ],
)
async def test_plain_content_types_accepted_with_charset(content_type: str) -> None:
    body = SAMPLE_PLAIN.encode("utf-8")
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    result = await _fetch("https://example.com/job.txt", handler)
    assert result.ok is True
    assert result.text is not None
    assert is_admitted_text(result.text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/pdf",
        "text/css",
        "multipart/form-data",
        "image/png",
        "",
    ],
)
async def test_unsupported_content_type_fails(content_type: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(200, content=b"{}", headers=headers)

    result = await _fetch("https://example.com/x", handler)
    assert result.ok is False
    assert result.failure_code == URL_UNSUPPORTED_CONTENT_TYPE
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


# --- Timeout / unavailable ---


@pytest.mark.asyncio
async def test_timeout_returns_stable_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    result = await _fetch("https://example.com/slow", handler)
    assert result.ok is False
    assert result.failure_code == URL_FETCH_TIMEOUT
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


class _DelayedStreamTransport(httpx.AsyncBaseTransport):
    """Transport that awaits before returning the body (wall-clock budget)."""

    def __init__(self, delay_seconds: float, body: bytes) -> None:
        self._delay_seconds = delay_seconds
        self._body = body

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(self._delay_seconds)
        return httpx.Response(
            200,
            content=self._body,
            headers={"content-type": "text/plain"},
            request=request,
        )


@pytest.mark.asyncio
async def test_wall_clock_timeout_covers_request_and_streamed_body() -> None:
    # A2: httpx per-op timeouts alone allowed a delayed stream (~0.085s) to
    # succeed under timeout_seconds=0.02. Wall-clock budget must fail it.
    transport = _DelayedStreamTransport(0.085, SAMPLE_PLAIN.encode("utf-8"))
    async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
        result = await fetch_url_text(
            "https://example.com/slow-stream",
            client=client,
            settings=_settings_like(timeout=10, max_mb=5),
            timeout_seconds=0.02,
            max_response_mb=5,
        )
    assert result.ok is False
    assert result.failure_code == URL_FETCH_TIMEOUT
    assert result.text is None
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_connect_error_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connect failure", request=request)

    result = await _fetch("https://example.com/down", handler)
    assert result.ok is False
    assert result.failure_code == URL_FETCH_UNAVAILABLE
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 400, 403, 404, 500, 502])
async def test_http_error_status_unavailable(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        headers: dict[str, str] = {"content-type": "text/plain"}
        if status in {301, 302, 303, 307, 308}:
            headers["location"] = "https://example.com/target"
        return httpx.Response(
            status,
            content=b"error",
            headers=headers,
        )

    result = await _fetch("https://example.com/missing", handler)
    assert result.ok is False
    assert result.failure_code == URL_FETCH_UNAVAILABLE


@pytest.mark.asyncio
async def test_redirect_not_followed_even_when_client_follows_redirects() -> None:
    """Request-level follow_redirects=False; 3xx = unavailable; no cookie leak."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={
                    "location": "https://example.com/target",
                    "set-cookie": "sid=secret",
                },
                content=b"",
            )
        return httpx.Response(
            200,
            content=SAMPLE_PLAIN.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    transport = _transport(handler)
    # Injected client intentionally follows redirects — production must override.
    async with httpx.AsyncClient(
        transport=transport,
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        result = await fetch_url_text(
            "https://example.com/start",
            client=client,
            settings=_settings_like(),
            timeout_seconds=10,
            max_response_mb=5,
        )

    assert result.ok is False
    assert result.failure_code == URL_FETCH_UNAVAILABLE
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE
    assert len(seen) == 1
    assert seen[0].url.path == "/start"
    header_names = {k.lower() for k in seen[0].headers.keys()}
    assert "cookie" not in header_names
    assert "authorization" not in header_names
    # No redirected hop, so no Set-Cookie from 302 can become Cookie outbound.
    assert "sid=secret" not in str(seen[0].headers).lower()


# --- Streamed size limit ---


@pytest.mark.asyncio
async def test_streamed_over_limit_fails_without_admitting_text() -> None:
    # 6 MiB > default 5 MB limit; body is large on the mock side, client must
    # stop once cumulative streamed bytes exceed the cap.
    oversize = b"x" * (6 * 1024 * 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=oversize,
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/huge", handler, max_mb=5)
    assert result.ok is False
    assert result.failure_code == URL_RESPONSE_TOO_LARGE
    assert result.text is None
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_body_at_limit_is_accepted() -> None:
    # Exactly 1 MiB with max_mb=1 must succeed (boundary).
    body = (b"Job role text with content. " * 40000)[: 1 * 1024 * 1024]
    assert len(body) == 1 * 1024 * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/plain; charset=utf-8"},
        )

    result = await _fetch("https://example.com/edge", handler, max_mb=1)
    assert result.ok is True
    assert result.text is not None
    assert len(result.text.encode("utf-8")) == len(body)


# --- Decoding / plain vs HTML ---


def test_decode_uses_charset_then_utf8_fallback() -> None:
    raw = "café".encode("latin-1")
    text = decode_body(raw, "text/plain; charset=iso-8859-1")
    assert "caf" in text
    assert charset_from_content_type("text/plain; charset=iso-8859-1") == "iso-8859-1"


@pytest.mark.asyncio
async def test_plain_text_bypasses_trafilatura(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> str:
        raise AssertionError("trafilatura must not run for text/plain")

    monkeypatch.setattr(url_fetch.trafilatura, "extract", boom)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SAMPLE_PLAIN.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/plain", handler)
    assert result.ok is True
    assert result.text == SAMPLE_PLAIN


@pytest.mark.asyncio
async def test_html_uses_trafilatura(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    real_extract = url_fetch.trafilatura.extract

    def wrapper(html: str, *a: Any, **k: Any) -> str | None:
        calls.append(html)
        return real_extract(html, *a, **k)

    monkeypatch.setattr(url_fetch.trafilatura, "extract", wrapper)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SAMPLE_HTML.encode("utf-8"),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    result = await _fetch("https://example.com/html", handler)
    assert result.ok is True
    assert len(calls) == 1
    assert result.text is not None
    assert is_admitted_text(result.text)


# --- Admission boundaries ---


@pytest.mark.parametrize(
    "text",
    [None, "", "   ", "\n\t  \n", "\u00a0"],
)
def test_admission_rejects_absent_or_whitespace_only(text: str | None) -> None:
    # \u00a0 is non-breaking space — str.strip() removes it in Python.
    assert is_admitted_text(text) is False


@pytest.mark.parametrize(
    "text",
    [SHORT_TEXT, CONTACT_ONLY, "x", "  has content  ", SAMPLE_PLAIN],
)
def test_admission_accepts_short_and_contact_only(text: str) -> None:
    assert is_admitted_text(text) is True


@pytest.mark.asyncio
async def test_whitespace_only_plain_returns_empty_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"   \n\t  ",
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/blank", handler)
    assert result.ok is False
    assert result.failure_code == URL_EMPTY_TEXT
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE


@pytest.mark.asyncio
async def test_empty_html_extraction_returns_empty_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(url_fetch.trafilatura, "extract", lambda *_a, **_k: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body></body></html>",
            headers={"content-type": "text/html"},
        )

    result = await _fetch("https://example.com/empty-html", handler)
    assert result.ok is False
    assert result.failure_code == URL_EMPTY_TEXT


@pytest.mark.asyncio
async def test_trafilatura_raised_error_becomes_paste_text_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: Any, **_k: Any) -> str:
        raise ValueError("extractor internal failure")

    monkeypatch.setattr(url_fetch.trafilatura, "extract", boom)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SAMPLE_HTML.encode("utf-8"),
            headers={"content-type": "text/html"},
        )

    result = await _fetch("https://example.com/bad-extract", handler)
    assert result.ok is False
    assert result.failure_code == URL_EMPTY_TEXT
    assert result.text is None
    assert result.paste_fallback_message == PASTE_JD_FALLBACK_MESSAGE
    # Sanitized: no extractor exception message in public fields.
    assert result.failure_code is not None
    assert "extractor internal" not in (result.paste_fallback_message or "")
    assert "ValueError" not in (result.paste_fallback_message or "")


@pytest.mark.asyncio
async def test_short_plain_text_succeeds_unchanged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=SHORT_TEXT.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/short", handler)
    assert result.ok is True
    assert result.text == SHORT_TEXT  # unchanged; no length heuristic


@pytest.mark.asyncio
async def test_contact_only_plain_succeeds_unchanged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=CONTACT_ONLY.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/contact", handler)
    assert result.ok is True
    assert result.text == CONTACT_ONLY


@pytest.mark.asyncio
async def test_admitted_text_preserves_internal_and_edge_whitespace() -> None:
    body = "  leading and trailing  \nline2"
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    result = await _fetch("https://example.com/ws", handler)
    assert result.ok is True
    assert result.text == body


# --- No auth/cookies; source hygiene ---


@pytest.mark.asyncio
async def test_request_has_no_authorization_or_cookie_headers() -> None:
    captured: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers)
        return httpx.Response(
            200,
            content=SAMPLE_PLAIN.encode("utf-8"),
            headers={"content-type": "text/plain"},
        )

    # Ephemeral client from the service (no injected client) — proves production path.
    transport = _transport(handler)
    result = await fetch_url_text(
        "https://example.com/job",
        transport=transport,
        settings=_settings_like(),
        timeout_seconds=10,
        max_response_mb=5,
    )
    assert result.ok is True
    assert len(captured) == 1
    header_names = {k.lower() for k in captured[0].keys()}
    assert "authorization" not in header_names
    assert "cookie" not in header_names
    # Assert captured request headers directly (no production hygiene helper).
    for name, value in captured[0].items():
        assert name.lower() not in {"authorization", "cookie"}
        assert "secret" not in value.lower()


def test_source_pins_and_forbids_browser_auth_and_full_body_logging() -> None:
    tree = ast.parse(SOURCE)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "trafilatura" in imported
    assert "httpx" in imported
    forbidden = {
        "selenium",
        "playwright",
        "pyppeteer",
        "scrapy",
        "beautifulsoup4",
        "bs4",
        "requests",
        "aiohttp",
    }
    assert imported.isdisjoint(forbidden)

    # No logging of full documents or secret header names in application code.
    assert "Authorization" not in SOURCE or "authorization" in SOURCE.lower()
    # Must not set Cookie / Authorization on outbound requests.
    assert "\"Authorization\"" not in SOURCE
    assert "'Authorization'" not in SOURCE
    assert "\"Cookie\"" not in SOURCE
    assert "'Cookie'" not in SOURCE
    # No logger.exception/info of response body variables as full dumps.
    assert "logger." not in SOURCE

    # Trafilatura pin is the only HTML extractor dependency surface in this module.
    assert "trafilatura" in SOURCE
    assert "URL_FETCH_TIMEOUT_SECONDS" in SOURCE
    assert "URL_MAX_RESPONSE_MB" in SOURCE
    assert "text/html" in SOURCE
    assert "text/plain" in SOURCE


def test_pyproject_pins_trafilatura_exactly() -> None:
    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "trafilatura==2.1.0" in pyproject


def test_module_is_single_purpose_and_under_line_budget() -> None:
    lines = SOURCE.splitlines()
    assert len(lines) < 300
    # No persistence / provider / graph imports.
    assert "sqlalchemy" not in SOURCE
    assert "neo4j" not in SOURCE
    assert "langchain" not in SOURCE
    assert "app.db" not in SOURCE
    assert "app.graph" not in SOURCE


def test_fetch_url_text_is_async_and_injectable() -> None:
    sig = inspect.signature(fetch_url_text)
    assert "client" in sig.parameters
    assert "transport" in sig.parameters
    assert inspect.iscoroutinefunction(fetch_url_text)
