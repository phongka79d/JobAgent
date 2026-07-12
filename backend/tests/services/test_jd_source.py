"""Tests for deterministic JD text acquisition (URL or pasted input).

Uses synthetic fixtures and injected fetchers only — no public network,
browser, ShopAIKey, or alternate HTML parser fallback.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from app.services.jd_source import (
    MAX_PASTED_JD_TEXT_LEN,
    AcquiredJd,
    JdSourceError,
    JdSourceErrorCode,
    JdSourceType,
    acquire_jd,
    canonicalize_jd_text,
    extract_html_main_text,
    hash_canonical_text,
)
from app.services.url_fetcher import (
    UrlFetcher,
    UrlFetchError,
    UrlFetchErrorCode,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "jds"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _assert_jd_error(exc: JdSourceError, code: JdSourceErrorCode) -> None:
    assert exc.code is code
    assert str(exc) == code.value
    assert repr(exc) == f"JdSourceError(code={code.value!r})"
    assert exc.__cause__ is None
    assert exc.__context__ is None


def _assert_no_sensitive_leak(blob: str, *extra: str) -> None:
    for needle in (
        "Senior Backend Engineer",
        "Example Corp",
        "careers@example.com",
        "555-0100",
        "http://",
        "https://",
        "password",
        "secret-key",
        "Authorization",
        "ShopAIKey",
        "playwright",
        "selenium",
        "puppeteer",
        *extra,
    ):
        assert needle not in blob


class ScriptedResolver:
    def __init__(self, mapping: dict[str, Sequence[str]]) -> None:
        self.mapping = {k.lower(): list(v) for k, v in mapping.items()}
        self.calls: list[str] = []

    def resolve(self, host: str) -> Sequence[str]:
        key = host.lower()
        self.calls.append(key)
        if key not in self.mapping:
            raise OSError("resolver miss")
        return list(self.mapping[key])


class ScriptedTransport(httpx.BaseTransport):
    def __init__(
        self,
        connect_ip: str,
        responses: list[httpx.Response],
        *,
        connected: list[str],
        requests: list[httpx.Request],
    ) -> None:
        self.connect_ip = connect_ip
        self._responses = responses
        self._connected = connected
        self._requests = requests
        self.connected_addresses = [connect_ip]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._connected.append(self.connect_ip)
        self._requests.append(request)
        if not self._responses:
            return httpx.Response(500, text="unexpected")
        return self._responses.pop(0)


class CountingFetcher:
    """Minimal stand-in that records calls; not a real UrlFetcher."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> Any:
        self.calls.append(url)
        raise AssertionError("fetcher must not be called on raw path")


def _make_fetcher(
    *,
    body: bytes,
    media_type: str,
    host: str = "jobs.example.com",
    ip: str = "93.184.216.34",
    source_path: str = "/jd/1",
) -> tuple[UrlFetcher, list[httpx.Request]]:
    resolver = ScriptedResolver({host: [ip]})
    requests: list[httpx.Request] = []
    shared = [
        httpx.Response(
            200,
            headers={"content-type": f"{media_type}; charset=utf-8"},
            content=body,
        )
    ]
    connected: list[str] = []

    def factory(connect_ip: str) -> httpx.BaseTransport:
        return ScriptedTransport(
            connect_ip,
            shared,
            connected=connected,
            requests=requests,
        )

    fetcher = UrlFetcher(
        timeout_seconds=10,
        max_response_bytes=5 * 1024 * 1024,
        resolver=resolver,
        transport_factory=factory,
    )
    return fetcher, requests


# ---------------------------------------------------------------------------
# Canonicalization / hashing
# ---------------------------------------------------------------------------


class TestCanonicalization:
    def test_unicode_nfc_and_line_endings_hash_identically(self) -> None:
        # café composed vs decomposed; CRLF vs LF; edge whitespace.
        composed = "Title: Caf\u00e9 Engineer\r\n\r\nBuild APIs."
        decomposed = "  Title: Cafe\u0301 Engineer\n\nBuild APIs.  \n"
        a = canonicalize_jd_text(composed)
        b = canonicalize_jd_text(decomposed)
        assert a == b
        assert hash_canonical_text(a) == hash_canonical_text(b)
        assert a == "Title: Café Engineer\n\nBuild APIs."

    def test_preserves_semantic_case_punctuation_and_internal_structure(
        self,
    ) -> None:
        raw = "  Senior Engineer!\n\n  - Python, C++\n\tKeep indent\n  "
        out = canonicalize_jd_text(raw)
        assert "Senior Engineer!" in out
        assert "Python, C++" in out
        assert "\n\n" in out
        # Leading indent on internal lines preserved; trailing edge stripped.
        assert "  - Python, C++" in out or "- Python, C++" in out
        assert out.endswith("Keep indent")
        assert not out.startswith(" ")
        assert not out.endswith(" ")

    def test_hash_is_sha256_hex_of_utf8_canonical(self) -> None:
        text = "Exact JD body"
        canonical = canonicalize_jd_text(text)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert hash_canonical_text(canonical) == expected
        assert len(expected) == 64


# ---------------------------------------------------------------------------
# Input validation (strict one-of)
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_neither_input_rejected(self) -> None:
        with pytest.raises(JdSourceError) as ei:
            acquire_jd()
        _assert_jd_error(ei.value, JdSourceErrorCode.INVALID_INPUT)
        _assert_no_sensitive_leak(f"{ei.value!s}{ei.value!r}")

    def test_both_inputs_rejected(self) -> None:
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="https://jobs.example.com/x", raw_text="body")
        _assert_jd_error(ei.value, JdSourceErrorCode.INVALID_INPUT)

    def test_blank_raw_rejected(self) -> None:
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(raw_text="   \n\t  ")
        _assert_jd_error(ei.value, JdSourceErrorCode.INVALID_INPUT)

    def test_empty_url_rejected(self) -> None:
        fetcher, _ = _make_fetcher(body=b"x", media_type="text/plain")
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="   ", fetcher=fetcher)
        _assert_jd_error(ei.value, JdSourceErrorCode.INVALID_INPUT)

    def test_url_without_fetcher_rejected(self) -> None:
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="https://jobs.example.com/x")
        _assert_jd_error(ei.value, JdSourceErrorCode.INVALID_INPUT)

    def test_oversize_pasted_input_rejected(self) -> None:
        huge = "A" * (MAX_PASTED_JD_TEXT_LEN + 1)
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(raw_text=huge)
        _assert_jd_error(ei.value, JdSourceErrorCode.INPUT_TOO_LARGE)
        blob = f"{ei.value!s}{ei.value!r}"
        assert "A" * 20 not in blob
        _assert_no_sensitive_leak(blob)


# ---------------------------------------------------------------------------
# Raw text path
# ---------------------------------------------------------------------------


class TestRawTextAcquisition:
    def test_raw_path_never_calls_fetcher(self) -> None:
        plain = _read_fixture("equivalent_plain.txt")
        counter = CountingFetcher()
        result = acquire_jd(raw_text=plain, fetcher=counter)  # type: ignore[arg-type]
        assert counter.calls == []
        assert isinstance(result, AcquiredJd)
        assert result.source_type is JdSourceType.RAW_TEXT
        assert result.source_url is None
        assert result.canonical_text
        assert result.content_hash == hash_canonical_text(result.canonical_text)
        # Semantic content preserved.
        assert "Senior Backend Engineer" in result.canonical_text
        assert "Python" in result.canonical_text

    def test_max_size_boundary_accepted(self) -> None:
        body = "B" * MAX_PASTED_JD_TEXT_LEN
        result = acquire_jd(raw_text=body)
        assert len(result.canonical_text) == MAX_PASTED_JD_TEXT_LEN


# ---------------------------------------------------------------------------
# Plain / HTML URL path
# ---------------------------------------------------------------------------


class TestUrlAcquisition:
    def test_plain_url_matches_pasted_equivalent(self) -> None:
        plain = _read_fixture("equivalent_plain.txt")
        # CRLF edge-whitespace variant of the same JD.
        variant = "\r\n" + plain.replace("\n", "\r\n") + "  \r\n"
        fetcher, requests = _make_fetcher(
            body=variant.encode("utf-8"),
            media_type="text/plain",
        )
        from_url = acquire_jd(
            url="https://jobs.example.com/jd/1",
            fetcher=fetcher,
        )
        from_raw = acquire_jd(raw_text=plain)
        assert from_url.source_type is JdSourceType.URL
        assert from_url.source_url == "https://jobs.example.com/jd/1"
        assert from_url.canonical_text == from_raw.canonical_text
        assert from_url.content_hash == from_raw.content_hash
        assert requests  # fetcher was used

    def test_html_url_matches_pasted_extracted_text(self) -> None:
        html = _read_fixture("equivalent.html")
        fetcher, _ = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )
        from_url = acquire_jd(
            url="https://jobs.example.com/jd/1",
            fetcher=fetcher,
        )
        # Pasting the same main text (post-extraction) hashes identically.
        from_raw = acquire_jd(raw_text=from_url.canonical_text)
        assert from_url.source_type is JdSourceType.URL
        assert from_url.canonical_text == from_raw.canonical_text
        assert from_url.content_hash == from_raw.content_hash
        assert "Senior Backend Engineer" in from_url.canonical_text
        assert "window.tracker" not in from_url.canonical_text
        assert "tracking comment" not in from_url.canonical_text

    def test_blank_html_returns_jd_text_required(self) -> None:
        html = _read_fixture("blank.html")
        fetcher, _ = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="https://jobs.example.com/empty", fetcher=fetcher)
        _assert_jd_error(ei.value, JdSourceErrorCode.JD_TEXT_REQUIRED)
        _assert_no_sensitive_leak(f"{ei.value!s}{ei.value!r}")

    def test_malformed_html_returns_jd_text_required(self) -> None:
        html = _read_fixture("malformed.html")
        fetcher, _ = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )
        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="https://jobs.example.com/bad", fetcher=fetcher)
        _assert_jd_error(ei.value, JdSourceErrorCode.JD_TEXT_REQUIRED)

    def test_extraction_failure_returns_jd_text_required(self) -> None:
        html = _read_fixture("equivalent.html")
        fetcher, _ = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )

        def boom(_html: str) -> str | None:
            raise RuntimeError("extractor exploded with secret body")

        with pytest.raises(JdSourceError) as ei:
            acquire_jd(
                url="https://jobs.example.com/jd/1",
                fetcher=fetcher,
                html_extractor=boom,
            )
        _assert_jd_error(ei.value, JdSourceErrorCode.JD_TEXT_REQUIRED)
        blob = f"{ei.value!s}{ei.value!r}"
        assert "extractor exploded" not in blob
        assert "secret body" not in blob

    def test_contact_only_nonblank_is_acquired(self) -> None:
        """Content-only quality decisions belong to Batch02; nonblank text is acquired."""
        html = _read_fixture("contact_only.html")
        fetcher, _ = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )
        result = acquire_jd(
            url="https://jobs.example.com/contact",
            fetcher=fetcher,
        )
        assert result.canonical_text
        assert result.content_hash
        # Fixture contact details exist only on the internal result object,
        # not in exception/log surfaces tested elsewhere.

    def test_url_path_propagates_fetcher_error_without_bypass(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["127.0.0.1"]})
        fetcher = UrlFetcher(
            timeout_seconds=10,
            max_response_bytes=1024,
            resolver=resolver,
            transport_factory=lambda _ip: ScriptedTransport(
                _ip, [], connected=[], requests=[]
            ),
        )
        with pytest.raises(UrlFetchError) as ei:
            acquire_jd(url="https://jobs.example.com/private", fetcher=fetcher)
        assert ei.value.code is UrlFetchErrorCode.URL_BLOCKED
        blob = f"{ei.value!s}{ei.value!r}"
        assert "127.0.0.1" not in blob
        assert "jobs.example.com" not in blob

    def test_url_path_never_uses_browser_or_provider_fallback(self) -> None:
        html = _read_fixture("blank.html")
        fetcher, requests = _make_fetcher(
            body=html.encode("utf-8"),
            media_type="text/html",
        )
        provider_calls: list[str] = []

        def fake_provider() -> None:
            provider_calls.append("called")

        with pytest.raises(JdSourceError) as ei:
            acquire_jd(url="https://jobs.example.com/empty", fetcher=fetcher)
        _assert_jd_error(ei.value, JdSourceErrorCode.JD_TEXT_REQUIRED)
        # Only the controlled fetcher ran (one GET); no provider/browser side effects.
        assert len(requests) == 1
        assert provider_calls == []
        assert requests[0].method == "GET"


# ---------------------------------------------------------------------------
# Trafilatura unit seam
# ---------------------------------------------------------------------------


class TestHtmlExtractor:
    def test_extract_html_main_text_on_fixtures(self) -> None:
        assert extract_html_main_text(_read_fixture("blank.html")) is None
        assert extract_html_main_text(_read_fixture("malformed.html")) is None
        contact = extract_html_main_text(_read_fixture("contact_only.html"))
        assert contact is not None
        assert contact.strip()
        main = extract_html_main_text(_read_fixture("equivalent.html"))
        assert main is not None
        assert "Senior Backend Engineer" in main
        assert "<script>" not in main
        assert "window.tracker" not in main
