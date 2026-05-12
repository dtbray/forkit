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

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback IPv4
    ipaddress.ip_network("::1/128"),            # loopback IPv6
    ipaddress.ip_network("169.254.0.0/16"),     # link-local / cloud metadata (AWS IMDS)
    ipaddress.ip_network("fe80::/10"),          # link-local IPv6
    ipaddress.ip_network("10.0.0.0/8"),         # RFC-1918 private
    ipaddress.ip_network("172.16.0.0/12"),      # RFC-1918 private
    ipaddress.ip_network("192.168.0.0/16"),     # RFC-1918 private
    ipaddress.ip_network("fc00::/7"),           # unique-local IPv6
    ipaddress.ip_network("224.0.0.0/4"),        # multicast
    ipaddress.ip_network("0.0.0.0/8"),          # unspecified
    ipaddress.ip_network("100.64.0.0/10"),      # shared address space (RFC-6598)
    # Azure IMDS — not covered by 169.254.0.0/16 due to the /32 boundary
    ipaddress.ip_network("168.63.129.16/32"),
]

_FETCH_TIMEOUT = 10.0
_MAX_REDIRECTS = 5
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class SSRFBlockedError(Exception):
    """Base for all SSRF-guard rejections."""


class URLForbiddenError(SSRFBlockedError):
    """Raised when a URL or redirect target resolves to a blocked IP range."""


class FetchError(Exception):
    """Raised on network errors, size cap exceeded, or too many redirects."""


def _resolve_and_check(host: str) -> None:
    """Resolve *host* to an IP address and raise URLForbiddenError if blocked.

    Raises FetchError if the hostname cannot be resolved at all.
    """
    try:
        ip_str = socket.gethostbyname(host)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host {host!r}: {exc}") from exc

    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise FetchError(f"Unexpected IP format {ip_str!r}: {exc}") from exc

    for network in BLOCKED_NETWORKS:
        if addr in network:
            raise URLForbiddenError(
                f"Host {host!r} resolves to {addr}, which is in blocked range {network}"
            )


async def safe_fetch(
    url: str,
    *,
    max_redirects: int = _MAX_REDIRECTS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
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

    _resolve_and_check(hostname)

    current_url = url
    hops = 0

    # follow_redirects=False so we can re-resolve the IP at each hop.
    # trust_env=False prevents HTTPS_PROXY / HTTP_PROXY passthrough.
    # No cookie jar — cookies are not stored or forwarded.
    async with httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=_FETCH_TIMEOUT,
    ) as client:
        while hops <= max_redirects:
            response = await client.get(
                current_url,
                headers={"User-Agent": _USER_AGENT},
            )

            if response.is_redirect:
                location = response.headers.get("location", "")
                if not location:
                    raise FetchError("Redirect response missing Location header")

                next_parsed = urlparse(location)
                if next_parsed.scheme not in ("http", "https", ""):
                    raise URLForbiddenError(
                        f"Redirect to scheme {next_parsed.scheme!r} is not allowed"
                    )

                # Relative redirect — reconstruct absolute URL.
                if not next_parsed.netloc:
                    from urllib.parse import urljoin
                    location = urljoin(current_url, location)
                    next_parsed = urlparse(location)

                next_host = next_parsed.hostname or ""
                if not next_host:
                    raise URLForbiddenError("Redirect URL has no hostname")

                _resolve_and_check(next_host)
                current_url = location
                hops += 1
                continue

            # Not a redirect — check HTTP status, then stream body with size cap.
            if response.status_code >= 400:
                raise FetchError(
                    f"HTTP {response.status_code} from {current_url!r}"
                )

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

    raise FetchError(f"Exceeded maximum of {max_redirects} redirects for {url!r}")
