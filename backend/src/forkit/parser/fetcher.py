"""SSRF-safe HTTP fetcher (S1).

All outbound HTTP requests — page HTML and hero images — go through
`safe_fetch()`.  It enforces:

* Scheme allowlist: http / https only.
* DNS resolution + IP range check before each request hop.
* Manual redirect following so the IP is re-checked at every hop.
* 5-redirect maximum.
* 10-second per-request timeout.
* 5 MB response cap (streamed; aborts past limit).
* `trust_env=False` — no proxy env-var passthrough.
* Cookies dropped (no cookie jar, no state carried between hops).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Iterable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),  # loopback IPv4
    ipaddress.ip_network("::1/128"),  # loopback IPv6
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata (AWS IMDS)
    ipaddress.ip_network("fe80::/10"),  # link-local IPv6
    ipaddress.ip_network("10.0.0.0/8"),  # RFC-1918 private
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC-1918 private
    ipaddress.ip_network("fc00::/7"),  # unique-local IPv6
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("0.0.0.0/8"),  # unspecified
    ipaddress.ip_network("100.64.0.0/10"),  # shared address space (RFC-6598)
    # Azure IMDS — not covered by 169.254.0.0/16 due to the /32 boundary
    ipaddress.ip_network("168.63.129.16/32"),
    # Translation/tunnel ranges can embed otherwise blocked IPv4 destinations.
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("2001::/32"),
]

_FETCH_TIMEOUT = 10.0
_MAX_REDIRECTS = 5
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_USER_AGENT = "Forkit/0.1 (recipe importer)"


class SSRFBlockedError(Exception):
    """Base for all SSRF-guard rejections."""


class URLForbiddenError(SSRFBlockedError):
    """Raised when a URL or redirect target resolves to a blocked IP range."""


class FetchError(Exception):
    """Fetch failure, optionally carrying HTTP backoff information."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retry_after: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _resolve_and_check(host: str, port: int = 443) -> list[str]:
    """Check every A/AAAA result; return only literal addresses safe to dial."""
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host {host!r}: {exc}") from exc
    addresses = list(dict.fromkeys(result[4][0] for result in results))
    if not addresses:
        raise FetchError(f"No addresses returned for host {host!r}")
    for address in addresses:
        addr = ipaddress.ip_address(address)
        checked = addr.ipv4_mapped if isinstance(addr, ipaddress.IPv6Address) else None
        checked = checked or addr
        if not checked.is_global or any(checked in network for network in BLOCKED_NETWORKS):
            raise URLForbiddenError(f"Host {host!r} resolves to non-public address {addr}")
    return addresses


class _PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Pin validated addresses at TCP connection time; preserve original TLS SNI."""

    def __init__(self) -> None:
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[Any, ...]] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await asyncio.wait_for(
                asyncio.to_thread(_resolve_and_check, host, port),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise httpcore.ConnectTimeout("DNS resolution timed out") from exc
        last_error = None
        for address in addresses:
            try:
                return await self.backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("No validated destination addresses")

    async def sleep(self, seconds: float) -> None:
        await self.backend.sleep(seconds)


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: Any) -> None:
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


class _PublicTransport(httpx.AsyncBaseTransport):
    """HTTPX/httpcore adapter using public APIs and a constrained network backend."""

    def __init__(self) -> None:
        self.pool = httpcore.AsyncConnectionPool(network_backend=_PublicNetworkBackend())

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.pool.handle_async_request(
            httpcore.Request(
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
        )
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=_ResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self.pool.aclose()


async def safe_fetch(
    url: str,
    *,
    max_redirects: int = _MAX_REDIRECTS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    user_agent: str = _USER_AGENT,
    response_headers: dict[str, str] | None = None,
) -> bytes:
    """Fetch *url* with full SSRF protection. Returns response body bytes.

    Args:
        url: The URL to fetch.  Must use http or https scheme.
        max_redirects: Maximum number of redirect hops to follow.
        max_bytes: Abort and raise FetchError if response body exceeds this.

    Raises:
        URLForbiddenError: Scheme not allowed, or resolved IP is in a blocked range.
        FetchError: DNS failure, too many redirects, or response too large.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLForbiddenError(
            f"Scheme {parsed.scheme!r} is not allowed; only http and https are permitted"
        )

    hostname = parsed.hostname or ""
    if not hostname:
        raise URLForbiddenError("URL has no hostname")

    current_url = url
    hops = 0

    # follow_redirects=False so we can re-resolve the IP at each hop.
    # trust_env=False prevents HTTPS_PROXY / HTTP_PROXY passthrough.
    # Clear the cookie jar before each hop; never forward publisher cookies.
    async with httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=_FETCH_TIMEOUT,
        transport=_PublicTransport(),
    ) as client:
        while hops <= max_redirects:
            parsed = urlparse(current_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise URLForbiddenError("URL must use http or https and have a hostname")
            if parsed.username is not None or parsed.password is not None:
                raise URLForbiddenError("URL credentials are not permitted")
            # Streaming closes immediately on errors, caps decoded bytes, and drops cookies.
            client.cookies.clear()
            try:
                async with client.stream(
                    "GET",
                    current_url,
                    headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirect response missing Location header")
                        current_url = urljoin(current_url, location)
                        hops += 1
                        continue
                    if response.status_code >= 400:
                        raise FetchError(
                            f"HTTP {response.status_code} from {current_url!r}",
                            status_code=response.status_code,
                            retry_after=response.headers.get("retry-after"),
                        )
                    # Refuse encodings despite identity negotiation: decompression can
                    # allocate an unbounded output before a decoded-byte limit runs.
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise FetchError("Server ignored identity content encoding request")
                    if response_headers is not None:
                        response_headers.update(response.headers)
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        total += len(chunk)
                        if total > max_bytes:
                            raise FetchError(
                                f"Response from {current_url!r} exceeded {max_bytes} bytes cap"
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (
                httpcore.NetworkError,
                httpcore.TimeoutException,
                httpcore.ProtocolError,
                httpx.HTTPError,
            ) as exc:
                raise FetchError(f"Request failed for {current_url!r}: {exc}") from exc

    raise FetchError(f"Exceeded maximum of {max_redirects} redirects for {url!r}")
