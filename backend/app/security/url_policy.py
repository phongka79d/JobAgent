"""Pure URL parser and DNS/IP policy for SSRF-safe public JD retrieval.

Validates scheme, credentials, hostnames, IP literals, and every DNS A/AAAA
answer (including IPv4-mapped IPv6). No network I/O lives here — callers
supply resolved addresses. Failures use stable sanitized codes only; raw URLs
and address details never appear in exception strings.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

# At most three redirect hops after the initial request (caller-enforced).
MAX_REDIRECTS: Final[int] = 3

_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

# Explicit localhost / cloud-metadata hostnames (case-insensitive match).
_BLOCKED_HOSTNAMES: Final[frozenset[str]] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)

# Trailing .localhost (RFC 6761) and common metadata DNS suffixes.
_BLOCKED_HOSTNAME_SUFFIXES: Final[tuple[str, ...]] = (
    ".localhost",
    ".localdomain",
    ".internal",
)

# Cloud metadata unicast addresses beyond generic private/link-local classes.
_METADATA_NETWORKS: Final[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)

_IPV4_MAPPED_PREFIX: Final[str] = "::ffff:"

_HOSTNAME_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))*$"
)


class UrlPolicyErrorCode(StrEnum):
    """Stable, non-sensitive URL policy failure codes."""

    URL_BLOCKED = "URL_BLOCKED"
    URL_INVALID = "URL_INVALID"


class UrlPolicyError(Exception):
    """Sanitized URL policy failure (code-only str/repr; no URL/DNS detail)."""

    def __init__(self, code: UrlPolicyErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"UrlPolicyError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@dataclass(frozen=True, slots=True)
class ParsedPublicUrl:
    """Credential-free HTTP(S) URL with discrete fields for safe fetching."""

    scheme: str
    host: str
    port: int
    path: str
    query: str
    # Reconstructable public form without userinfo/fragment.
    normalized: str
    # True when host is an IP literal (no DNS required).
    host_is_ip: bool
    # When host_is_ip, the single vetted address; otherwise empty until resolve.
    literal_addresses: tuple[str, ...]


def _blocked() -> UrlPolicyError:
    return UrlPolicyError(UrlPolicyErrorCode.URL_BLOCKED)


def _invalid() -> UrlPolicyError:
    return UrlPolicyError(UrlPolicyErrorCode.URL_INVALID)


def _require_valid_optional_port(parsed: SplitResult) -> int | None:
    """Return port or None; never surface raw port tokens in errors."""
    try:
        return parsed.port
    except ValueError:
        raise _invalid() from None


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def normalize_ip(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Parse an IP and collapse IPv4-mapped IPv6 to the embedded IPv4 address."""
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        ip = value
    else:
        try:
            ip = ipaddress.ip_address(value.strip())
        except ValueError as exc:
            raise _invalid() from exc
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_forbidden_ip(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True when the address is not a globally reachable public unicast IP.

    Blocks loopback, private, link-local, unspecified, multicast, reserved,
    documentation, shared (CGNAT), and cloud-metadata destinations for both
    IPv4 and IPv6, including IPv4-mapped IPv6 forms.
    """
    try:
        ip = normalize_ip(value)
    except UrlPolicyError:
        return True

    if not ip.is_global:
        return True

    for network in _METADATA_NETWORKS:
        if ip in network:
            return True

    # Defense in depth: explicit class checks even if is_global semantics change.
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    ):
        return True

    return False


def is_blocked_hostname(host: str) -> bool:
    """Return True for localhost / metadata-style hostnames (not IP literals)."""
    cleaned = host.strip().rstrip(".").lower()
    if not cleaned:
        return True
    if cleaned in _BLOCKED_HOSTNAMES:
        return True
    for suffix in _BLOCKED_HOSTNAME_SUFFIXES:
        if cleaned.endswith(suffix):
            return True
    return False


def _parse_host_as_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Try to interpret a URL host as an IP literal (bracket-stripped for IPv6)."""
    candidate = host.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        return normalize_ip(candidate)
    except UrlPolicyError:
        return None


def _validate_hostname_label(host: str) -> str:
    cleaned = host.strip().rstrip(".").lower()
    if not cleaned or len(cleaned) > 253:
        raise _invalid()
    if is_blocked_hostname(cleaned):
        raise _blocked()
    if not _HOSTNAME_RE.fullmatch(cleaned):
        # Allow underscore-free DNS names only; reject spaces/controls.
        raise _invalid()
    return cleaned


def parse_public_http_url(url: str) -> ParsedPublicUrl:
    """Parse and validate a credential-free public HTTP/HTTPS URL.

    Rejects non-HTTP(S) schemes, userinfo credentials, fragments used as
    authority tricks, localhost/metadata hostnames, and forbidden IP literals.
    """
    if not isinstance(url, str) or not url.strip():
        raise _invalid()

    cleaned = url.strip()
    # Reject embedded credentials early without relying solely on urlsplit.
    if "://" in cleaned:
        after_scheme = cleaned.split("://", 1)[1]
        authority = after_scheme.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if "@" in authority:
            raise _blocked()

    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise _invalid() from exc

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise _invalid()

    if parsed.username is not None or parsed.password is not None:
        raise _blocked()

    host = parsed.hostname
    if host is None or not str(host).strip():
        raise _invalid()

    port_value = _require_valid_optional_port(parsed)
    port = port_value if port_value is not None else _default_port(scheme)

    if port < 1 or port > 65535:
        raise _invalid()

    literal = _parse_host_as_ip(host)
    literal_addresses: tuple[str, ...] = ()
    host_is_ip = literal is not None

    if host_is_ip:
        assert literal is not None
        if is_forbidden_ip(literal):
            raise _blocked()
        host_for_url = str(literal)
        literal_addresses = (str(literal),)
        # Bracket IPv6 literals in netloc.
        if isinstance(literal, ipaddress.IPv6Address):
            netloc_host = f"[{host_for_url}]"
        else:
            netloc_host = host_for_url
    else:
        host_for_url = _validate_hostname_label(host)
        netloc_host = host_for_url

    default = _default_port(scheme)
    if port == default:
        netloc = netloc_host
    else:
        netloc = f"{netloc_host}:{port}"

    path = parsed.path if parsed.path else "/"
    query = parsed.query
    # Drop fragment from fetch target (not sent; never needed for JD body).
    normalized = urlunsplit((scheme, netloc, path, query, ""))

    return ParsedPublicUrl(
        scheme=scheme,
        host=host_for_url,
        port=port,
        path=path,
        query=query,
        normalized=normalized,
        host_is_ip=host_is_ip,
        literal_addresses=literal_addresses,
    )


def validate_resolved_addresses(addresses: Sequence[str]) -> tuple[str, ...]:
    """Validate every DNS answer; reject empty sets and any forbidden address.

    Mixed safe/forbidden answer sets fail closed before any connection.
    Returns the vetted address strings (normalized) on success.
    """
    if not addresses:
        raise _blocked()

    vetted: list[str] = []
    seen: set[str] = set()
    for raw in addresses:
        try:
            ip = normalize_ip(raw)
        except UrlPolicyError as exc:
            raise _blocked() from exc
        if is_forbidden_ip(ip):
            raise _blocked()
        text = str(ip)
        if text not in seen:
            seen.add(text)
            vetted.append(text)

    if not vetted:
        raise _blocked()
    return tuple(vetted)


def resolve_redirect_url(current: ParsedPublicUrl, location: str) -> ParsedPublicUrl:
    """Join a redirect Location against the current URL and re-apply policy."""
    if not isinstance(location, str) or not location.strip():
        raise _invalid()
    # urljoin handles absolute and relative Location values.
    joined = urljoin(current.normalized, location.strip())
    return parse_public_http_url(joined)


def addresses_for_connection(parsed: ParsedPublicUrl, resolved: Sequence[str]) -> tuple[str, ...]:
    """Return vetted addresses for *parsed*, using literals or DNS answers."""
    if parsed.host_is_ip:
        return validate_resolved_addresses(parsed.literal_addresses)
    return validate_resolved_addresses(resolved)


def filter_public_ips(addresses: Iterable[str]) -> tuple[str, ...]:
    """Return only globally safe addresses (does not fail on mixed sets).

    Prefer ``validate_resolved_addresses`` for the SSRF gate; this helper is
    for diagnostics/tests that need a pure filter without raising.
    """
    result: list[str] = []
    for raw in addresses:
        try:
            ip = normalize_ip(raw)
        except UrlPolicyError:
            continue
        if not is_forbidden_ip(ip):
            result.append(str(ip))
    return tuple(result)


__all__ = [
    "MAX_REDIRECTS",
    "ParsedPublicUrl",
    "UrlPolicyError",
    "UrlPolicyErrorCode",
    "addresses_for_connection",
    "filter_public_ips",
    "is_blocked_hostname",
    "is_forbidden_ip",
    "normalize_ip",
    "parse_public_http_url",
    "resolve_redirect_url",
    "validate_resolved_addresses",
]
