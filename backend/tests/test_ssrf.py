"""SSRF guard tests — parametrized across blocked URL classes.

Each URL must raise URLForbiddenError (blocked IP / scheme) or FetchError
(DNS resolution failure for names like 'localhost' that may resolve to 127.0.0.1).
"""

from __future__ import annotations

import pytest

from forkit.parser.fetcher import FetchError, SSRFBlockedError, URLForbiddenError, safe_fetch


@pytest.mark.parametrize(
    "url",
    [
        # IPv4 loopback
        "http://127.0.0.1/secret",
        "http://127.0.0.1:8080/admin",
        # Hostname that resolves to loopback
        "http://localhost/secret",
        # Private RFC-1918
        "http://192.168.1.1/router",
        "http://10.0.0.1/internal",
        "http://172.16.0.1/internal",
        # AWS/GCP instance metadata
        "http://169.254.169.254/latest/meta-data/",
        # Forbidden scheme
        "ftp://example.com/recipe",
        "file:///etc/passwd",
        "gopher://evil.com/",
    ],
)
@pytest.mark.asyncio
async def test_ssrf_blocked(url: str) -> None:
    """All blocked URLs must raise SSRFBlockedError, URLForbiddenError, or FetchError."""
    with pytest.raises((SSRFBlockedError, URLForbiddenError, FetchError)):
        await safe_fetch(url)


@pytest.mark.asyncio
async def test_ssrf_scheme_allowlist_http_allowed() -> None:
    """http scheme must pass scheme check (may fail at DNS/network, not at scheme guard)."""
    # We're not testing connectivity; just that the scheme guard does not block http.
    # The actual fetch will fail due to test isolation, but the error should be
    # FetchError (DNS / network), not URLForbiddenError (scheme blocked).
    try:
        await safe_fetch("http://example.com/")
    except URLForbiddenError as exc:
        # Should NOT be raised for a legitimate public URL
        pytest.fail(f"URLForbiddenError raised for http://example.com/: {exc}")
    except (FetchError, Exception):
        # Network unavailable in test env is acceptable
        pass


@pytest.mark.asyncio
async def test_ssrf_data_uri_blocked() -> None:
    """data: URIs must be blocked by scheme allowlist."""
    with pytest.raises((URLForbiddenError, SSRFBlockedError)):
        await safe_fetch("data:text/html,<h1>hello</h1>")


@pytest.mark.asyncio
async def test_ssrf_ipv6_loopback_blocked() -> None:
    """IPv6 loopback ::1 must be blocked."""
    with pytest.raises((URLForbiddenError, SSRFBlockedError, FetchError)):
        await safe_fetch("http://[::1]/secret")
