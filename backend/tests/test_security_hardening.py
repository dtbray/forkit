"""Regression coverage for static containment and actual bounded outbound reads."""

import socket
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from forkit import main
from forkit.parser import fetcher


@pytest.mark.parametrize("path", ["%2e%2e/secret.txt", "escape/secret.txt"])
def test_static_cannot_escape_packaged_root(tmp_path, monkeypatch, path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("SPA")
    (tmp_path / "secret.txt").write_text("outside")
    (static / "escape").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(main, "_static_dir", static)
    with TestClient(main.app) as client:
        assert client.get("/" + path).status_code == 404
        assert client.get("/recipes/123").text == "SPA"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "::1", "::ffff:192.168.1.1", "100.64.0.1", "64:ff9b::7f00:1", "2002:7f00:1::"],
)
def test_all_dns_answers_are_validated(monkeypatch, address):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, 443)),
        ],
    )
    with pytest.raises(fetcher.URLForbiddenError):
        fetcher._resolve_and_check("publisher.test")


async def test_connection_dials_checked_literal_not_hostname(monkeypatch):
    monkeypatch.setattr(fetcher, "_resolve_and_check", lambda *a: ["93.184.216.34"])
    backend = fetcher._PublicNetworkBackend()
    backend.backend.connect_tcp = AsyncMock(return_value="stream")
    assert await backend.connect_tcp("publisher.test", 443) == "stream"
    assert backend.backend.connect_tcp.call_args.args == ("93.184.216.34", 443)


class Chunks(httpx.AsyncByteStream):
    def __init__(self):
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for _ in range(100):
            self.reads += 1
            yield b"x" * 65536

    async def aclose(self):
        self.closed = True


async def test_body_cap_stops_network_stream_early(monkeypatch):
    stream = Chunks()
    monkeypatch.setattr(
        fetcher,
        "_PublicTransport",
        lambda: httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
    )
    with pytest.raises(fetcher.FetchError, match="exceeded"):
        await fetcher.safe_fetch("https://publisher.test/", max_bytes=65536)
    assert stream.reads == 2
    assert stream.closed


async def test_redirect_cookies_are_not_forwarded(monkeypatch):
    seen = []

    def respond(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "/recipe", "Set-Cookie": "track=1"})
        return httpx.Response(200, content=b"ok")

    monkeypatch.setattr(fetcher, "_PublicTransport", lambda: httpx.MockTransport(respond))
    assert await fetcher.safe_fetch("https://publisher.test/") == b"ok"
    assert "cookie" not in seen[1].headers


async def test_redirect_to_private_host_rechecks_at_connect(monkeypatch):
    class ConnectionTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.url.host == "publisher.test":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
            await fetcher._PublicNetworkBackend().connect_tcp(request.url.host, 80)
            pytest.fail("private connection was allowed")

    monkeypatch.setattr(fetcher, "_PublicTransport", ConnectionTransport)
    with pytest.raises(fetcher.URLForbiddenError):
        await fetcher.safe_fetch("https://publisher.test/")


async def test_compression_cannot_bypass_memory_bound(monkeypatch):
    stream = Chunks()

    def respond(request):
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)

    monkeypatch.setattr(fetcher, "_PublicTransport", lambda: httpx.MockTransport(respond))
    with pytest.raises(fetcher.FetchError, match="encoding"):
        await fetcher.safe_fetch("https://publisher.test/")
    assert stream.reads == 0
    assert stream.closed


def test_spa_index_symlink_cannot_escape_packaged_root(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("outside")
    (static / "index.html").symlink_to(secret)
    monkeypatch.setattr(main, "_static_dir", static)
    with TestClient(main.app) as client:
        assert client.get("/recipes/123").status_code == 404
