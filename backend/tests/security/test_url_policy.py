"""Injected unit tests for pure DNS/IP/URL policy (no network I/O)."""

from __future__ import annotations

import ipaddress

import pytest
from app.security.url_policy import (
    ParsedPublicUrl,
    UrlPolicyError,
    UrlPolicyErrorCode,
    is_blocked_hostname,
    is_forbidden_ip,
    normalize_ip,
    parse_public_http_url,
    resolve_redirect_url,
    validate_resolved_addresses,
)


def _assert_code_only(exc: UrlPolicyError, code: UrlPolicyErrorCode) -> None:
    assert exc.code is code
    assert str(exc) == code.value
    assert repr(exc) == f"UrlPolicyError(code={code.value!r})"
    assert exc.__cause__ is None
    assert exc.__context__ is None
    # Failures must not echo raw URL/DNS detail.
    blob = f"{exc!s}{exc!r}{exc.code}"
    assert "http" not in blob.lower() or "URL_" in blob
    assert "127.0.0.1" not in blob
    assert "localhost" not in blob
    assert "password" not in blob


class TestParsePublicHttpUrl:
    def test_allows_public_https_hostname(self) -> None:
        parsed = parse_public_http_url("https://jobs.example.com/careers/123")
        assert parsed.scheme == "https"
        assert parsed.host == "jobs.example.com"
        assert parsed.port == 443
        assert parsed.path == "/careers/123"
        assert parsed.host_is_ip is False
        assert parsed.literal_addresses == ()
        assert parsed.normalized == "https://jobs.example.com/careers/123"

    def test_allows_public_ipv4_literal(self) -> None:
        parsed = parse_public_http_url("http://93.184.216.34/jd")
        assert parsed.host_is_ip is True
        assert parsed.literal_addresses == ("93.184.216.34",)
        assert parsed.normalized == "http://93.184.216.34/jd"

    def test_allows_public_ipv6_literal(self) -> None:
        # 2001:4860:4860::8888 is a public Google DNS address.
        parsed = parse_public_http_url("https://[2001:4860:4860::8888]/")
        assert parsed.host_is_ip is True
        assert parsed.host == "2001:4860:4860::8888"
        assert "2001:4860:4860::8888" in parsed.normalized

    def test_rejects_credentials(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            parse_public_http_url("https://user:secret@jobs.example.com/x")
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_userinfo_without_password(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            parse_public_http_url("https://user@jobs.example.com/x")
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_non_http_schemes(self) -> None:
        for raw in (
            "ftp://files.example.com/a",
            "file:///etc/passwd",
            "gopher://example.com/",
            "javascript:alert(1)",
        ):
            with pytest.raises(UrlPolicyError) as ei:
                parse_public_http_url(raw)
            assert ei.value.code in {
                UrlPolicyErrorCode.URL_INVALID,
                UrlPolicyErrorCode.URL_BLOCKED,
            }
            _assert_code_only(ei.value, ei.value.code)

    def test_rejects_localhost_names(self) -> None:
        for raw in (
            "http://localhost/jd",
            "http://LOCALHOST/jd",
            "http://localhost.localdomain/",
            "http://app.localhost/",
            "http://metadata.google.internal/",
            "http://metadata/",
        ):
            with pytest.raises(UrlPolicyError) as ei:
                parse_public_http_url(raw)
            _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_loopback_literals(self) -> None:
        for raw in (
            "http://127.0.0.1/",
            "http://127.0.0.2:8080/x",
            "http://[::1]/",
        ):
            with pytest.raises(UrlPolicyError) as ei:
                parse_public_http_url(raw)
            _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_private_and_link_local_literals(self) -> None:
        for raw in (
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://169.254.1.1/",
            "http://169.254.169.254/latest/meta-data",
            "http://[fe80::1]/",
            "http://[fc00::1]/",
            "http://0.0.0.0/",
            "http://[::]/",
        ):
            with pytest.raises(UrlPolicyError) as ei:
                parse_public_http_url(raw)
            _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_ipv4_mapped_loopback(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            parse_public_http_url("http://[::ffff:127.0.0.1]/")
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_rejects_empty_and_blank(self) -> None:
        for raw in ("", "   ", "\t"):
            with pytest.raises(UrlPolicyError) as ei:
                parse_public_http_url(raw)
            _assert_code_only(ei.value, UrlPolicyErrorCode.URL_INVALID)

    def test_preserves_query_drops_fragment(self) -> None:
        parsed = parse_public_http_url(
            "https://jobs.example.com/a?q=1#section"
        )
        assert parsed.query == "q=1"
        assert parsed.normalized == "https://jobs.example.com/a?q=1"
        assert "#" not in parsed.normalized


class TestForbiddenIpClasses:
    @pytest.mark.parametrize(
        "raw",
        [
            "127.0.0.1",
            "10.1.2.3",
            "172.16.5.5",
            "192.168.0.10",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "255.255.255.255",
            "::1",
            "fe80::1",
            "fc00::abcd",
            "ff02::1",
            "::",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
            "fd00:ec2::254",
        ],
    )
    def test_forbidden(self, raw: str) -> None:
        assert is_forbidden_ip(raw) is True

    @pytest.mark.parametrize(
        "raw",
        [
            "93.184.216.34",
            "8.8.8.8",
            "1.1.1.1",
            "2001:4860:4860::8888",
        ],
    )
    def test_allowed_public(self, raw: str) -> None:
        assert is_forbidden_ip(raw) is False

    def test_normalize_ipv4_mapped(self) -> None:
        ip = normalize_ip("::ffff:8.8.8.8")
        assert isinstance(ip, ipaddress.IPv4Address)
        assert str(ip) == "8.8.8.8"


class TestValidateResolvedAddresses:
    def test_all_public_ok(self) -> None:
        vetted = validate_resolved_addresses(["8.8.8.8", "1.1.1.1"])
        assert vetted == ("8.8.8.8", "1.1.1.1")

    def test_mixed_safe_and_forbidden_fails(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            validate_resolved_addresses(["8.8.8.8", "127.0.0.1"])
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_empty_fails(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            validate_resolved_addresses([])
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_all_private_fails(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            validate_resolved_addresses(["10.0.0.1", "192.168.0.1"])
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_metadata_v6_fails(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            validate_resolved_addresses(["fd00:ec2::254"])
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_dedupes_addresses(self) -> None:
        vetted = validate_resolved_addresses(["8.8.8.8", "8.8.8.8"])
        assert vetted == ("8.8.8.8",)

    def test_error_has_no_address_leak(self) -> None:
        with pytest.raises(UrlPolicyError) as ei:
            validate_resolved_addresses(["10.0.0.99"])
        text = f"{ei.value!s}{ei.value!r}"
        assert "10.0.0.99" not in text


class TestRedirectResolution:
    def test_absolute_redirect_revalidated(self) -> None:
        current = parse_public_http_url("https://jobs.example.com/a")
        nxt = resolve_redirect_url(current, "https://cdn.example.com/b")
        assert nxt.host == "cdn.example.com"
        assert nxt.path == "/b"

    def test_relative_redirect(self) -> None:
        current = parse_public_http_url("https://jobs.example.com/a/b")
        nxt = resolve_redirect_url(current, "../c")
        assert nxt.normalized == "https://jobs.example.com/c"

    def test_redirect_to_localhost_blocked(self) -> None:
        current = parse_public_http_url("https://jobs.example.com/a")
        with pytest.raises(UrlPolicyError) as ei:
            resolve_redirect_url(current, "http://127.0.0.1/secret")
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)

    def test_redirect_with_credentials_blocked(self) -> None:
        current = parse_public_http_url("https://jobs.example.com/a")
        with pytest.raises(UrlPolicyError) as ei:
            resolve_redirect_url(current, "https://u:p@evil.example.com/")
        _assert_code_only(ei.value, UrlPolicyErrorCode.URL_BLOCKED)


class TestBlockedHostnames:
    def test_matrix(self) -> None:
        assert is_blocked_hostname("localhost") is True
        assert is_blocked_hostname("metadata.google.internal") is True
        assert is_blocked_hostname("jobs.example.com") is False
        assert is_blocked_hostname("app.localhost") is True


class TestParsedPublicUrlShape:
    def test_frozen_dataclass(self) -> None:
        parsed = parse_public_http_url("https://example.com/")
        assert isinstance(parsed, ParsedPublicUrl)
        with pytest.raises(AttributeError):
            parsed.host = "other"  # type: ignore[misc]
