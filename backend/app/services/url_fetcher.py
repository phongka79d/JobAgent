"""Bounded, SSRF-safe HTTP retrieval for a single public JD URL.

Uses the pure URL policy module for every URL and DNS answer, connects only to
vetted addresses (no hostname re-resolution on the wire), manually follows at
most three redirects, streams at most the configured body ceiling, and accepts
only ``text/html`` / ``text/plain``. Ambient proxies, cookies, authentication,
and browser or scripted-render paths are disabled. Failures expose stable codes only.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

import httpcore
import httpx

from app.config import Settings
from app.security.url_policy import (
    MAX_REDIRECTS,
    ParsedPublicUrl,
    UrlPolicyError,
    UrlPolicyErrorCode,
    parse_public_http_url,
    resolve_redirect_url,
    validate_resolved_addresses,
)


class _HttpcoreResponseStream(httpx.SyncByteStream):
    """Adapt an httpcore response stream to httpx without buffering the body."""

    def __init__(self, stream: object) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        yield from self._stream  # type: ignore[misc]

    def close(self) -> None:
        closer = getattr(self._stream, "close", None)
        if callable(closer):
            closer()

# Locked media types (parameters such as charset are stripped before compare).
ALLOWED_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"text/html", "text/plain"})

_REDIRECT_STATUS: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})
_CHUNK_SIZE: Final[int] = 64 * 1024


class UrlFetchErrorCode(StrEnum):
    """Stable, non-sensitive URL fetch failure codes."""

    URL_BLOCKED = "URL_BLOCKED"
    URL_INVALID = "URL_INVALID"
    URL_UNAVAILABLE = "URL_UNAVAILABLE"
    URL_TIMEOUT = "URL_TIMEOUT"
    URL_REDIRECT_LIMIT = "URL_REDIRECT_LIMIT"
    URL_RESPONSE_TOO_LARGE = "URL_RESPONSE_TOO_LARGE"
    URL_UNSUPPORTED_MEDIA_TYPE = "URL_UNSUPPORTED_MEDIA_TYPE"


class UrlFetchError(Exception):
    """Sanitized URL fetch failure (code-only str/repr; no URL/DNS/body)."""

    def __init__(self, code: UrlFetchErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"UrlFetchError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@dataclass(frozen=True, slots=True)
class UrlFetchResult:
    """Controlled fetch outcome for the JD acquisition boundary.

    ``body`` is bounded response bytes. ``media_type`` is an approved type
    without parameters. ``source_url`` is the final credential-free public URL
    after redirects (safe display/storage metadata — never includes DNS detail).
    """

    body: bytes
    media_type: str
    source_url: str
    status_code: int
    # Peer addresses actually used for TCP connect (test/observability only;
    # never log alongside secrets; empty when a custom transport omits them).
    connected_addresses: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class DnsResolver(Protocol):
    """Resolve a hostname to IP address strings (A/AAAA). No filtering here."""

    def resolve(self, host: str) -> Sequence[str]: ...


TransportFactory = Callable[[str], httpx.BaseTransport]


class SystemDnsResolver:
    """``getaddrinfo``-based resolver returning unique A/AAAA string forms."""

    def resolve(self, host: str) -> Sequence[str]:
        try:
            infos = socket.getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM,
            )
        except OSError:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE) from None
        addresses: list[str] = []
        seen: set[str] = set()
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            raw = sockaddr[0]
            if not isinstance(raw, str):
                continue
            if raw not in seen:
                seen.add(raw)
                addresses.append(raw)
        if not addresses:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE)
        return addresses


class _BoundIPBackend(httpcore.NetworkBackend):
    """TCP backend that always dials a single pre-vetted IP address."""

    def __init__(self, connect_ip: str, connected: list[str]) -> None:
        self._connect_ip = connect_ip
        self._connected = connected
        self._inner = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object | None = None,
    ) -> httpcore.NetworkStream:
        self._connected.append(self._connect_ip)
        return self._inner.connect_tcp(
            self._connect_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,  # type: ignore[arg-type]
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object | None = None,
    ) -> httpcore.NetworkStream:
        raise UrlFetchError(UrlFetchErrorCode.URL_BLOCKED)

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


class BoundIPTransport(httpx.BaseTransport):
    """httpx transport that binds TCP to *connect_ip* while keeping Host/SNI."""

    def __init__(self, connect_ip: str, *, verify: bool | str = True) -> None:
        self.connect_ip = connect_ip
        self.connected_addresses: list[str] = []
        ssl_context = httpx.create_ssl_context(verify=verify)
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            network_backend=_BoundIPBackend(connect_ip, self.connected_addresses),
            max_connections=1,
            max_keepalive_connections=0,
            retries=0,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.SyncByteStream)
        req = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        try:
            resp = self._pool.handle_request(req)
        except httpcore.TimeoutException:
            raise UrlFetchError(UrlFetchErrorCode.URL_TIMEOUT) from None
        except httpcore.NetworkError:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE) from None
        except UrlFetchError:
            raise
        except Exception:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE) from None

        return httpx.Response(
            status_code=resp.status,
            headers=resp.headers,
            stream=_HttpcoreResponseStream(resp.stream),
            extensions=resp.extensions,
        )

    def close(self) -> None:
        self._pool.close()


def default_transport_factory(connect_ip: str) -> httpx.BaseTransport:
    """Production transport: dial only *connect_ip*, verify TLS for Host/SNI."""
    return BoundIPTransport(connect_ip, verify=True)


def parse_media_type(content_type: str | None) -> str | None:
    """Extract the essence media type (lowercase) without parameters."""
    if content_type is None:
        return None
    cleaned = content_type.strip()
    if not cleaned:
        return None
    essence = cleaned.split(";", 1)[0].strip().lower()
    return essence or None


def _policy_to_fetch_error(exc: UrlPolicyError) -> UrlFetchError:
    if exc.code is UrlPolicyErrorCode.URL_INVALID:
        return UrlFetchError(UrlFetchErrorCode.URL_INVALID)
    return UrlFetchError(UrlFetchErrorCode.URL_BLOCKED)


def _map_httpx_error(exc: BaseException) -> UrlFetchError:
    if isinstance(exc, UrlFetchError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return UrlFetchError(UrlFetchErrorCode.URL_TIMEOUT)
    if isinstance(exc, (httpx.TransportError, httpx.HTTPError)):
        return UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE)
    return UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE)


class UrlFetcher:
    """Single controlled URL downloader with injected DNS/transport seams."""

    def __init__(
        self,
        *,
        timeout_seconds: int,
        max_response_bytes: int,
        resolver: DnsResolver | None = None,
        transport_factory: TransportFactory | None = None,
        max_redirects: int = MAX_REDIRECTS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._resolver: DnsResolver = resolver if resolver is not None else SystemDnsResolver()
        self._transport_factory: TransportFactory = (
            transport_factory
            if transport_factory is not None
            else default_transport_factory
        )

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        resolver: DnsResolver | None = None,
        transport_factory: TransportFactory | None = None,
    ) -> UrlFetcher:
        """Build a fetcher from typed root URL timeout/body settings."""
        max_bytes = settings.url_max_response_mb * 1024 * 1024
        return cls(
            timeout_seconds=settings.url_fetch_timeout_seconds,
            max_response_bytes=max_bytes,
            resolver=resolver,
            transport_factory=transport_factory,
        )

    def fetch(self, url: str) -> UrlFetchResult:
        """Fetch one public URL under the security and size contract.

        Raises ``UrlFetchError`` with a stable code on any policy, network,
        redirect, media-type, size, or timeout failure. Never returns partial
        content that violated the policy.
        """
        deadline = time.monotonic() + float(self._timeout_seconds)
        try:
            current = parse_public_http_url(url)
        except UrlPolicyError as exc:
            raise _policy_to_fetch_error(exc) from None

        redirects_followed = 0
        connected: list[str] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UrlFetchError(UrlFetchErrorCode.URL_TIMEOUT)

            vetted = self._vetted_addresses(current)
            connect_ip = vetted[0]
            transport = self._transport_factory(connect_ip)
            try:
                response = self._send(
                    current,
                    transport=transport,
                    timeout=remaining,
                )
                if isinstance(transport, BoundIPTransport):
                    connected.extend(transport.connected_addresses)
                else:
                    # Custom transports: record the intended vetted peer.
                    connected.append(connect_ip)

                # Capture headers/status before body read; close on all paths.
                status_code = response.status_code
                location = response.headers.get("location")
                content_type = response.headers.get("content-type")

                if status_code in _REDIRECT_STATUS:
                    response.close()
                    if redirects_followed >= self._max_redirects:
                        raise UrlFetchError(UrlFetchErrorCode.URL_REDIRECT_LIMIT)
                    if not location:
                        raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE)
                    try:
                        current = resolve_redirect_url(current, location)
                    except UrlPolicyError as exc:
                        raise _policy_to_fetch_error(exc) from None
                    redirects_followed += 1
                    continue

                if status_code < 200 or status_code >= 300:
                    response.close()
                    raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE)

                media_type = parse_media_type(content_type)
                if media_type not in ALLOWED_MEDIA_TYPES:
                    response.close()
                    raise UrlFetchError(UrlFetchErrorCode.URL_UNSUPPORTED_MEDIA_TYPE)

                body = self._read_body(response, deadline=deadline)
                return UrlFetchResult(
                    body=body,
                    media_type=media_type,
                    source_url=current.normalized,
                    status_code=status_code,
                    connected_addresses=tuple(connected),
                )
            except UrlFetchError:
                raise
            except UrlPolicyError as exc:
                raise _policy_to_fetch_error(exc) from None
            except Exception as exc:
                raise _map_httpx_error(exc) from None
            finally:
                close = getattr(transport, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

    def _vetted_addresses(self, parsed: ParsedPublicUrl) -> tuple[str, ...]:
        if parsed.host_is_ip:
            try:
                return validate_resolved_addresses(parsed.literal_addresses)
            except UrlPolicyError as exc:
                raise _policy_to_fetch_error(exc) from None
        try:
            resolved = self._resolver.resolve(parsed.host)
        except UrlFetchError:
            raise
        except Exception:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE) from None
        try:
            return validate_resolved_addresses(list(resolved))
        except UrlPolicyError as exc:
            raise _policy_to_fetch_error(exc) from None

    def _send(
        self,
        parsed: ParsedPublicUrl,
        *,
        transport: httpx.BaseTransport,
        timeout: float,
    ) -> httpx.Response:
        # trust_env=False: ignore HTTP(S)_PROXY / environment cookies.
        # No auth, no cookies jar, no automatic redirects.
        headers: dict[str, str] = {
            "Accept": "text/html, text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": "JobAgentURLFetcher/1.0",
        }
        try:
            with httpx.Client(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(timeout),
                headers=headers,
                cookies=httpx.Cookies(),
            ) as client:
                # stream=True so we can enforce the body ceiling incrementally.
                request = client.build_request("GET", parsed.normalized)
                return client.send(request, stream=True)
        except UrlFetchError:
            raise
        except Exception as exc:
            raise _map_httpx_error(exc) from None

    def _read_body(self, response: httpx.Response, *, deadline: float) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes(chunk_size=_CHUNK_SIZE):
                if time.monotonic() > deadline:
                    raise UrlFetchError(UrlFetchErrorCode.URL_TIMEOUT)
                if not chunk:
                    continue
                total += len(chunk)
                if total > self._max_response_bytes:
                    raise UrlFetchError(UrlFetchErrorCode.URL_RESPONSE_TOO_LARGE)
                chunks.append(chunk)
        except UrlFetchError:
            raise
        except httpx.TimeoutException:
            raise UrlFetchError(UrlFetchErrorCode.URL_TIMEOUT) from None
        except Exception:
            raise UrlFetchError(UrlFetchErrorCode.URL_UNAVAILABLE) from None
        finally:
            response.close()
        return b"".join(chunks)


__all__ = [
    "ALLOWED_MEDIA_TYPES",
    "BoundIPTransport",
    "DnsResolver",
    "SystemDnsResolver",
    "TransportFactory",
    "UrlFetchError",
    "UrlFetchErrorCode",
    "UrlFetchResult",
    "UrlFetcher",
    "default_transport_factory",
    "parse_media_type",
]
