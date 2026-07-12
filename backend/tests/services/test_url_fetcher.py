"""Injected DNS/transport tests for bounded SSRF-safe URL fetching.

All cases use fakes — no public network, no real DNS, no ambient proxies.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from app.config import load_settings
from app.services.url_fetcher import (
    ALLOWED_MEDIA_TYPES,
    UrlFetcher,
    UrlFetchError,
    UrlFetchErrorCode,
    UrlFetchResult,
    parse_media_type,
)


def _settings_env(tmp_path: Any, **overrides: str) -> dict[str, str]:
    base = {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://localhost:5173",
        "VITE_API_BASE_URL": "http://localhost:8000",
        "SQLITE_PATH": str(tmp_path / "db.sqlite"),
        "FILES_DIR": str(tmp_path / "files"),
        "NEO4J_URI": "bolt://invalid:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "secret",
        "SHOPAIKEY_BASE_URL": "https://example.invalid/v1",
        "SHOPAIKEY_API_KEY": "secret-key-value",
        "LLM_MODEL": "gpt-4o-mini",
        "LLM_TEMPERATURE": "0",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_DIMENSIONS": "1536",
        "MAX_PDF_SIZE_MB": "10",
        "MAX_PDF_PAGES": "10",
        "URL_FETCH_TIMEOUT_SECONDS": "10",
        "URL_MAX_RESPONSE_MB": "5",
        "TOOL_LOOP_LIMIT": "6",
    }
    base.update(overrides)
    return base


def _assert_fetch_code(exc: UrlFetchError, code: UrlFetchErrorCode) -> None:
    assert exc.code is code
    assert str(exc) == code.value
    assert repr(exc) == f"UrlFetchError(code={code.value!r})"
    assert exc.__cause__ is None
    assert exc.__context__ is None
    blob = f"{exc!s}{exc!r}"
    for needle in (
        "http://",
        "https://",
        "127.0.0.1",
        "localhost",
        "password",
        "secret-key",
        "Authorization",
        "PROXY",
        "8.8.8.8",
        "169.254.169.254",
        "Job description",
        "proxy-user",
    ):
        assert needle not in blob


class ScriptedResolver:
    """Hostname -> list of IP answers; supports per-call rebinding sequences."""

    def __init__(
        self,
        mapping: dict[str, Sequence[str]] | None = None,
        *,
        sequences: dict[str, list[Sequence[str]]] | None = None,
    ) -> None:
        self.mapping = {k.lower(): list(v) for k, v in (mapping or {}).items()}
        self.sequences = {
            k.lower(): [list(item) for item in seq]
            for k, seq in (sequences or {}).items()
        }
        self.calls: list[str] = []

    def resolve(self, host: str) -> Sequence[str]:
        key = host.lower()
        self.calls.append(key)
        if key in self.sequences and self.sequences[key]:
            return self.sequences[key].pop(0)
        if key not in self.mapping:
            raise OSError("resolver miss")
        return list(self.mapping[key])


class ScriptedTransport(httpx.BaseTransport):
    """Return canned responses; record connect_ip and request metadata."""

    def __init__(
        self,
        connect_ip: str,
        responses: list[httpx.Response],
        *,
        connected: list[str],
        requests: list[httpx.Request],
        error: Exception | None = None,
    ) -> None:
        self.connect_ip = connect_ip
        self._responses = responses
        self._connected = connected
        self._requests = requests
        self._error = error
        self.connected_addresses = [connect_ip]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self._connected.append(self.connect_ip)
        self._requests.append(request)
        if self._error is not None:
            raise self._error
        if not self._responses:
            return httpx.Response(500, text="unexpected")
        return self._responses.pop(0)


def _html_response(
    body: str = "<html><body>Engineer</body></html>",
    *,
    status: int = 200,
    content_type: str = "text/html; charset=utf-8",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    hdrs = {"content-type": content_type}
    if headers:
        hdrs.update(headers)
    return httpx.Response(status, headers=hdrs, content=body.encode("utf-8"))


def _plain_response(body: str = "Title: Engineer\n") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/plain; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def _redirect(location: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"location": location}, content=b"")


def _make_fetcher(
    *,
    resolver: ScriptedResolver,
    responses: list[httpx.Response],
    connected: list[str] | None = None,
    requests: list[httpx.Request] | None = None,
    timeout_seconds: int = 10,
    max_response_bytes: int = 5 * 1024 * 1024,
    max_redirects: int = 3,
    transport_error: Exception | None = None,
) -> tuple[UrlFetcher, list[str], list[httpx.Request]]:
    connected_list = connected if connected is not None else []
    request_list = requests if requests is not None else []
    # Shared queue so multi-hop redirects consume sequential responses.
    shared_responses = list(responses)

    def factory(connect_ip: str) -> httpx.BaseTransport:
        return ScriptedTransport(
            connect_ip,
            shared_responses,
            connected=connected_list,
            requests=request_list,
            error=transport_error,
        )

    fetcher = UrlFetcher(
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_response_bytes,
        resolver=resolver,
        transport_factory=factory,
        max_redirects=max_redirects,
    )
    return fetcher, connected_list, request_list


class TestUrlFetcherHappyPath:
    def test_allows_public_html_target(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["93.184.216.34"]})
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver,
            responses=[_html_response("Role: Backend Engineer")],
        )
        result = fetcher.fetch("https://jobs.example.com/jd/1")
        assert isinstance(result, UrlFetchResult)
        assert result.media_type == "text/html"
        assert b"Backend Engineer" in result.body
        assert result.source_url == "https://jobs.example.com/jd/1"
        assert result.connected_addresses
        assert all(addr == "93.184.216.34" for addr in result.connected_addresses)
        assert connected == ["93.184.216.34"]

    def test_allows_plain_text(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["1.1.1.1"]})
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[_plain_response("Plain JD text")],
        )
        result = fetcher.fetch("https://jobs.example.com/jd.txt")
        assert result.media_type == "text/plain"
        assert result.body == b"Plain JD text"

    def test_from_settings_uses_typed_ceilings(self, tmp_path: Any) -> None:
        settings = load_settings(
            environ=_settings_env(
                tmp_path,
                URL_FETCH_TIMEOUT_SECONDS="10",
                URL_MAX_RESPONSE_MB="5",
            )
        )
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        shared: list[httpx.Response] = [_html_response()]
        connected: list[str] = []

        def factory(connect_ip: str) -> httpx.BaseTransport:
            return ScriptedTransport(
                connect_ip, shared, connected=connected, requests=[]
            )

        fetcher = UrlFetcher.from_settings(
            settings, resolver=resolver, transport_factory=factory
        )
        assert fetcher._timeout_seconds == 10
        assert fetcher._max_response_bytes == 5 * 1024 * 1024
        result = fetcher.fetch("https://jobs.example.com/")
        assert result.media_type in ALLOWED_MEDIA_TYPES


class TestUrlFetcherPolicyFailures:
    def test_blocks_credentials_before_resolve(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        fetcher, _, _ = _make_fetcher(resolver=resolver, responses=[_html_response()])
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://user:password@jobs.example.com/x")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        assert resolver.calls == []

    def test_blocks_localhost_before_resolve(self) -> None:
        resolver = ScriptedResolver({})
        fetcher, _, _ = _make_fetcher(resolver=resolver, responses=[])
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("http://localhost/admin")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)

    def test_mixed_dns_answers_fail_before_content(self) -> None:
        resolver = ScriptedResolver(
            {"jobs.example.com": ["8.8.8.8", "127.0.0.1"]}
        )
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver,
            responses=[_html_response("should not be read")],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/jd")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        assert connected == []

    def test_private_only_dns_fails(self) -> None:
        resolver = ScriptedResolver({"internal.example.com": ["10.0.0.5"]})
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver, responses=[_html_response()]
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://internal.example.com/jd")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        assert connected == []

    def test_metadata_name_blocked(self) -> None:
        resolver = ScriptedResolver(
            {"metadata.google.internal": ["169.254.169.254"]}
        )
        fetcher, _, _ = _make_fetcher(resolver=resolver, responses=[])
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("http://metadata.google.internal/latest")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)


class TestUrlFetcherRedirects:
    def test_follows_up_to_three_redirects(self) -> None:
        resolver = ScriptedResolver(
            {
                "a.example.com": ["1.1.1.1"],
                "b.example.com": ["1.0.0.1"],
                "c.example.com": ["8.8.4.4"],
                "d.example.com": ["8.8.8.8"],
            }
        )
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                _redirect("https://b.example.com/2"),
                _redirect("https://c.example.com/3"),
                _redirect("https://d.example.com/4"),
                _html_response("final"),
            ],
        )
        result = fetcher.fetch("https://a.example.com/1")
        assert result.body == b"final"
        assert result.source_url == "https://d.example.com/4"
        assert connected == ["1.1.1.1", "1.0.0.1", "8.8.4.4", "8.8.8.8"]

    def test_fourth_redirect_rejected(self) -> None:
        resolver = ScriptedResolver(
            {
                "a.example.com": ["1.1.1.1"],
                "b.example.com": ["1.0.0.1"],
                "c.example.com": ["8.8.4.4"],
                "d.example.com": ["8.8.8.8"],
                "e.example.com": ["9.9.9.9"],
            }
        )
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                _redirect("https://b.example.com/2"),
                _redirect("https://c.example.com/3"),
                _redirect("https://d.example.com/4"),
                _redirect("https://e.example.com/5"),
                _html_response("too far"),
            ],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://a.example.com/1")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_REDIRECT_LIMIT)

    def test_redirect_to_private_blocked(self) -> None:
        resolver = ScriptedResolver({"a.example.com": ["1.1.1.1"]})
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver,
            responses=[_redirect("http://127.0.0.1/secret")],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://a.example.com/")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        assert connected == ["1.1.1.1"]

    def test_dns_rebinding_on_redirect_fails(self) -> None:
        """First hop public; second resolve returns private — fail closed."""
        resolver = ScriptedResolver(
            sequences={
                "rebind.example.com": [
                    ["8.8.8.8"],
                    ["127.0.0.1"],
                ]
            }
        )
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                _redirect("https://rebind.example.com/next"),
                _html_response("should not accept"),
            ],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://rebind.example.com/start")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        # First hop may connect; second must not accept content.
        assert connected == ["8.8.8.8"]


class TestUrlFetcherBodyAndMedia:
    def test_media_type_parameters_accepted_for_html(self) -> None:
        assert parse_media_type("text/html; charset=UTF-8") == "text/html"
        assert parse_media_type("text/plain;charset=iso-8859-1") == "text/plain"
        assert parse_media_type("application/json") == "application/json"
        assert parse_media_type(None) is None

    def test_rejects_disallowed_media_type(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                httpx.Response(
                    200,
                    headers={"content-type": "application/pdf"},
                    content=b"%PDF",
                )
            ],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/a.pdf")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_UNSUPPORTED_MEDIA_TYPE)

    def test_oversized_body_rejected(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        big = b"x" * 100
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                httpx.Response(
                    200,
                    headers={"content-type": "text/plain"},
                    content=big,
                )
            ],
            max_response_bytes=50,
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/big")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_RESPONSE_TOO_LARGE)

    def test_streaming_body_stops_at_ceiling(self) -> None:
        """Body delivered as chunked stream still enforces the byte ceiling."""
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})

        class ChunkedStream(httpx.SyncByteStream):
            def __iter__(self) -> Any:
                yield b"a" * 40
                yield b"b" * 40

            def close(self) -> None:
                return None

        response = httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=ChunkedStream(),
        )
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[response],
            max_response_bytes=50,
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/stream")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_RESPONSE_TOO_LARGE)


class TestUrlFetcherTimeoutsAndErrors:
    def test_transport_timeout_maps_to_stable_code(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[],
            transport_error=httpx.ConnectTimeout("slow"),
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_TIMEOUT)

    def test_http_error_status_unavailable(self) -> None:
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[
                httpx.Response(
                    503,
                    headers={"content-type": "text/plain"},
                    content=b"down",
                )
            ],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://jobs.example.com/")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_UNAVAILABLE)

    def test_resolver_failure_unavailable(self) -> None:
        class BoomResolver:
            def resolve(self, host: str) -> Sequence[str]:
                raise OSError("dns failed")

        fetcher = UrlFetcher(
            timeout_seconds=10,
            max_response_bytes=1024,
            resolver=BoomResolver(),
            transport_factory=lambda _ip: ScriptedTransport(
                _ip, [], connected=[], requests=[]
            ),
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch("https://missing.example.com/")
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_UNAVAILABLE)


class TestUrlFetcherNoLeakage:
    def test_failure_surfaces_have_no_secrets_or_url_detail(self) -> None:
        resolver = ScriptedResolver(
            {"jobs.example.com": ["8.8.8.8", "169.254.169.254"]}
        )
        fetcher, _, _ = _make_fetcher(
            resolver=resolver,
            responses=[_html_response("Job description SECRET_BODY")],
        )
        with pytest.raises(UrlFetchError) as ei:
            fetcher.fetch(
                "https://proxy-user:proxy-pass@jobs.example.com/path?token=abc"
            )
        _assert_fetch_code(ei.value, UrlFetchErrorCode.URL_BLOCKED)
        blob = f"{ei.value!s}{ei.value!r}{ei.value.code}"
        assert "proxy-pass" not in blob
        assert "token=abc" not in blob
        assert "SECRET_BODY" not in blob
        assert "169.254" not in blob

    def test_client_disables_trust_env_and_cookies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Factory path must not enable ambient proxy/cookie auth."""
        seen: dict[str, Any] = {}
        real_client = httpx.Client

        def tracking_client(*args: Any, **kwargs: Any) -> httpx.Client:
            seen.update(kwargs)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(
            "app.services.url_fetcher.httpx.Client", tracking_client
        )
        resolver = ScriptedResolver({"jobs.example.com": ["8.8.8.8"]})
        fetcher, _, _ = _make_fetcher(
            resolver=resolver, responses=[_html_response()]
        )
        fetcher.fetch("https://jobs.example.com/")
        assert seen.get("trust_env") is False
        assert seen.get("follow_redirects") is False
        assert seen.get("auth") is None

    def test_peer_stays_within_vetted_set(self) -> None:
        resolver = ScriptedResolver(
            {"jobs.example.com": ["93.184.216.34", "1.1.1.1"]}
        )
        fetcher, connected, _ = _make_fetcher(
            resolver=resolver, responses=[_html_response()]
        )
        result = fetcher.fetch("https://jobs.example.com/")
        # First vetted address is used; must remain in the validated set.
        assert set(result.connected_addresses) <= {"93.184.216.34", "1.1.1.1"}
        assert connected[0] == "93.184.216.34"


class TestNoSecondFetchStack:
    def test_module_does_not_import_requests_or_browser(self) -> None:
        import app.services.url_fetcher as mod

        src = open(mod.__file__, encoding="utf-8").read()
        assert "import requests" not in src
        assert "playwright" not in src.lower()
        assert "selenium" not in src.lower()
        assert "from selenium" not in src
        assert "import playwright" not in src
        assert "httpx" in src
