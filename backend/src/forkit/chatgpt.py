"""Official Sign in with ChatGPT OSS flow and protected rotating credentials.

Login runs on the browser's computer; self-hosted installs transfer this file via
SSH. No Codex tokens, client secrets, API keys or backend-api endpoints are used.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import secrets
import shlex
import stat
import subprocess
import tempfile
import time
import uuid
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

ISSUER = "https://auth.openai.com"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


class ConnectionError(RuntimeError):
    """A redacted, user-actionable connection error."""


def save_credentials(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temp:
        os.chmod(temp.name, 0o600)
        json.dump(value, temp)
        temp.flush()
        os.fsync(temp.fileno())
    Path(temp.name).replace(path)


def read_credentials(path: Path) -> dict:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ConnectionError("ChatGPT credential file must be private (0600)")
    value = json.loads(path.read_text())
    if (
        value.get("issuer") != ISSUER
        or not value.get("client_id", "").startswith("oaiapp_")
        or not value.get("subject")
        or not value.get("access_token")
        or "chatgpt.tokens.use.direct" not in value.get("scopes", [])
    ):
        raise ConnectionError("Reconnect ChatGPT with permission to use your plan")
    return value


@contextmanager
def credential_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def verify_identity(token: str, client_id: str, nonce: str | None = None) -> dict:
    jwks = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json", timeout=10)
    key = jwks.get_signing_key_from_jwt(token)
    identity = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=client_id,
        options={"require": ["sub", "exp", "iat"]},
        leeway=5,
    )
    if not identity["sub"] or (nonce is not None and identity.get("nonce") != nonce):
        raise ConnectionError("ChatGPT identity could not be verified")
    return identity


def apply_tokens(value: dict, tokens: dict) -> dict:
    scopes = tokens.get("scope", " ".join(value.get("scopes", []))).split()
    if "chatgpt.tokens.use.direct" not in scopes or not tokens.get("access_token"):
        raise ConnectionError("ChatGPT plan permission was not granted")
    return {
        **value,
        **{k: tokens[k] for k in ["access_token", "refresh_token", "id_token"] if k in tokens},
        "scopes": scopes,
        "expires_at": time.time() + int(tokens["expires_in"]),
        "saved_at": time.time(),
    }


def access_credentials(path: Path) -> dict:
    with credential_lock(path):
        value = read_credentials(path)
        if float(value.get("expires_at", 0)) > time.time() + 60:
            return value
        if not value.get("refresh_token"):
            raise ConnectionError("ChatGPT connection expired. Please reconnect.")
        try:
            response = httpx.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": value["client_id"],
                    "refresh_token": value["refresh_token"],
                    "resource": RESOURCE,
                },
                timeout=20,
                follow_redirects=False,
            )
            response.raise_for_status()
            tokens = response.json()
            if not tokens.get("refresh_token"):
                raise ConnectionError("ChatGPT renewal did not return rotating credentials")
            if tokens.get("id_token"):
                identity = verify_identity(tokens["id_token"], value["client_id"])
                if identity["sub"] != value["subject"]:
                    raise ConnectionError("ChatGPT account changed; reconnect explicitly")
            updated = apply_tokens(value, tokens)
            save_credentials(path, updated)
            return updated
        except (httpx.HTTPError, ValueError, KeyError, jwt.PyJWTError) as exc:
            raise ConnectionError("ChatGPT connection needs renewal. Please reconnect.") from exc


def account_models(value: dict) -> list[dict]:
    try:
        response = httpx.get(
            RESOURCE + "/models",
            headers={"Authorization": "Bearer " + value["access_token"]},
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        return [
            {"slug": item["slug"], "display_name": item["display_name"]}
            for item in response.json()["models"]
            if item.get("visibility") == "list"
        ]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise ConnectionError("Could not load your ChatGPT models. Try reconnecting.") from exc


def login(path: Path, port: int = 1455) -> None:
    previous = read_credentials(path) if path.exists() else {}
    host_file = path.with_name("host-id")
    if not host_file.exists():
        save_credentials(host_file, {"id": "urn:uuid:" + str(uuid.uuid4())})
    host_id = json.loads(host_file.read_text())["id"]
    state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    callback: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Callback contains a code: never log the URL.

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/auth/callback":
                self.send_error(404)
                return
            params = parse_qs(parsed.query)
            if params.get("state") != [state]:
                self.send_error(400, "Invalid sign-in state")
                return
            callback.update({k: v[0] for k, v in params.items() if len(v) == 1})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Return to your terminal to finish connecting Forkit.")

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        params = {
            "client_id": previous.get("client_id", "dynamic_agent_client"),
            "ext_agent_host_id": host_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if not previous:
            params["agent_name_hint"] = "Forkit"
        url = ISSUER + "/api/accounts/authorize?" + urlencode(params)
        print("Open this URL on THIS computer (not your phone):\n" + url, flush=True)
        webbrowser.open(url)
        deadline = time.monotonic() + 600
        server.timeout = 1
        while not callback and time.monotonic() < deadline:
            server.handle_request()
    if callback.get("error") or not callback.get("code"):
        raise ConnectionError("Sign-in cancelled, expired, or plan access was not granted")
    client_id = callback.get("client_id", previous.get("client_id", ""))
    if not client_id.startswith("oaiapp_") or (previous and client_id != previous["client_id"]):
        raise ConnectionError("Unexpected ChatGPT client registration")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": callback["code"],
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "resource": RESOURCE,
        },
        timeout=30,
        follow_redirects=False,
    )
    response.raise_for_status()
    tokens = response.json()
    identity = verify_identity(tokens["id_token"], client_id, nonce)
    if previous and identity["sub"] != previous["subject"]:
        raise ConnectionError("Account changed; use a new credential path to link another account")
    value = apply_tokens(
        {
            **previous,
            "issuer": ISSUER,
            "subject": identity["sub"],
            "client_id": client_id,
            "ext_agent_host_id": host_id,
        },
        tokens,
    )
    save_credentials(path, value)
    print("ChatGPT connected. Protected credentials saved; no API key is needed.")


def install_on_lab(path: Path, host: str, identity: Path) -> None:
    """Explicit helper option: transfer via existing SSH, never through browser storage."""
    if (
        not host
        or host.startswith("-")
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.@:-"
            for c in host
        )
    ):
        raise ConnectionError("Invalid SSH host")
    value = read_credentials(path)
    installer = (
        "import json,os,pathlib,sys,uuid; "
        "p=pathlib.Path('/opt/homelab/forkit/data/chatgpt'); "
        "p.mkdir(mode=0o700,parents=True,exist_ok=True); os.chmod(p,0o700); os.chown(p,1000,1000); "
        "h=p/'host-id'; "
        "host=json.loads(h.read_text()) if h.exists() else {'id':'urn:uuid:'+str(uuid.uuid4())}; "
        "os.umask(0o077); h.write_text(json.dumps(host)); os.chown(h,1000,1000); "
        "v=json.load(sys.stdin); v['ext_agent_host_id']=host['id']; "
        "t=p/'credentials.json.partial'; t.write_text(json.dumps(v)); "
        "os.chmod(t,0o600); os.chown(t,1000,1000); t.replace(p/'credentials.json')"
    )
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(identity.expanduser()),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            host,
            "sudo -n incus exec forkit -- python3 -c " + shlex.quote(installer),
        ],
        input=json.dumps(value),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise ConnectionError(
            "SSH installation failed; keep the private file and follow setup instructions"
        )
    print("ChatGPT connection installed on the lab. Choose a photo model in Forkit Pantry.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials", type=Path, default=Path.home() / ".config/forkit/chatgpt.json"
    )
    parser.add_argument("--port", type=int, default=1455)
    parser.add_argument(
        "--install-host", help="Optional existing SSH host owning the lab's forkit Incus guest"
    )
    parser.add_argument("--identity", type=Path, default=Path.home() / ".ssh/homelab_ed25519")
    args = parser.parse_args()
    try:
        login(args.credentials.expanduser(), args.port)
        if args.install_host:
            install_on_lab(args.credentials.expanduser(), args.install_host, args.identity)
    except (
        ConnectionError,
        OSError,
        subprocess.SubprocessError,
        httpx.HTTPError,
        ValueError,
        KeyError,
        jwt.PyJWTError,
    ):
        print("Could not complete ChatGPT sign-in. Retry or check the connection setup guide.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
