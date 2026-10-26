import base64
import io
import json
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from PIL import Image

from forkit import chatgpt
from forkit.api.pantry import limiter
from forkit.config import get_settings
from forkit.db import get_session
from forkit.main import app
from forkit.models import Ingredient, Recipe
from forkit.services import pantry


@pytest.fixture
def client(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "forkit_chatgpt_credentials_path", str(tmp_path / "connection.json")
    )
    limiter.reset()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.pop(get_session, None)


def credentials():
    return {
        "issuer": chatgpt.ISSUER,
        "subject": "household-owner",
        "client_id": "oaiapp_test",
        "access_token": "test-access",
        "refresh_token": "test-refresh",
        "model": "vision-test",
        "scopes": ["chatgpt.tokens.use.direct"],
        "expires_at": time.time() + 3600,
    }


def photo():
    image = Image.new("RGB", (20, 10), "red")
    exif = Image.Exif()
    exif[270] = "private camera metadata"
    output = io.BytesIO()
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


def test_text_review_commit_duplicates_and_remove(client):
    response = client.post(
        "/api/pantry/preview/text",
        json={"text": "2 eggs next item 400 g tomatoes, diced; milk and spinach"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["name"] for i in items] == ["eggs", "tomatoes", "milk", "spinach"]
    assert items[1]["notes"] == "diced"
    assert client.get("/api/pantry").json()["items"] == []
    # Review can remove mistaken candidates and correct names/amounts.
    items = items[:2]
    items[0]["quantity"] = "3"
    body = {"source": "text", "items": items}
    assert client.post("/api/pantry/items", json=body).json() == {"added": 2, "already_present": 0}
    body["items"][0]["quantity"] = "100"
    assert client.post("/api/pantry/items", json=body).json() == {"added": 0, "already_present": 2}
    saved = client.get("/api/pantry").json()["items"]
    assert saved[0]["quantity"] == "3"
    assert client.delete("/api/pantry/items/" + str(saved[0]["id"])).status_code == 204
    assert len(client.get("/api/pantry").json()["items"]) == 1


def test_invalid_review_is_atomic(client):
    for data in [
        {"source": "text", "items": [{"name": "rice"}, {"name": "   "}]},
        {"source": "audio", "items": [{"name": "rice"}]},
        {"source": "photo", "items": [{"name": "rice", "unexpected": True}]},
    ]:
        assert client.post("/api/pantry/items", json=data).status_code == 422
    assert client.get("/api/pantry").json()["items"] == []
    assert client.post("/api/pantry/preview/text", json={"text": "123"}).status_code == 422


def test_matching_has_no_fuzzy_false_positives_or_assumed_staples(client, db_session):
    recipe = Recipe(
        title="White bean rice", source_url="https://example.com/rice", instructions="[]"
    )
    recipe.ingredients = [
        Ingredient(position=i, raw_text=name, item=name)
        for i, name in enumerate(["rice", "white beans", "salt"])
    ]
    db_session.add(recipe)
    db_session.commit()
    client.post(
        "/api/pantry/items",
        json={"source": "text", "items": [{"name": "Rice"}, {"name": "white wine"}]},
    )
    result = client.get("/api/pantry/recipes").json()["recipes"][0]
    assert result["matched"] == ["rice"]
    assert result["missing"] == ["white beans", "salt"]


def test_photo_requires_connection_and_valid_bounded_image(client):
    assert not client.get("/api/pantry/capabilities").json()["chatgpt_connected"]
    assert (
        client.post(
            "/api/pantry/preview/photo", content=b"x", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/pantry/preview/photo", content=b"x", headers={"Content-Type": "image/jpeg"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/pantry/preview/photo", content=photo(), headers={"Content-Type": "image/jpeg"}
        ).status_code
        == 503
    )
    assert (
        client.post(
            "/api/pantry/preview/photo",
            content=b"x" * (8 * 1024 * 1024 + 1),
            headers={"Content-Type": "image/jpeg"},
        ).status_code
        == 413
    )
    assert client.get("/api/pantry").json()["items"] == []


def test_photo_uses_chatgpt_plan_stream_strips_metadata_and_requires_completion(
    client, monkeypatch
):
    path = Path(get_settings().forkit_chatgpt_credentials_path)
    chatgpt.save_credentials(path, credentials())
    complete = True
    actual_client = httpx.AsyncClient

    def provider(request):
        assert request.url == chatgpt.RESOURCE + "/responses"
        payload = json.loads(request.content)
        assert payload["store"] is False and payload["stream"] is True
        assert "max_output_tokens" not in payload
        assert request.headers["Authorization"] == "Bearer test-access"
        image_data = payload["input"][0]["content"][1]["image_url"].split(",")[1]
        with Image.open(io.BytesIO(base64.b64decode(image_data))) as image:
            assert not image.getexif()
        events = [
            {
                "type": "response.output_text.delta",
                "delta": json.dumps(
                    {
                        "items": [
                            {
                                "name": "tomatoes",
                                "quantity": None,
                                "unit": None,
                                "notes": "Check variety",
                            }
                        ]
                    }
                ),
            }
        ]
        if complete:
            events.append({"type": "response.completed"})
        else:
            events.append({"type": "response.failed"})
        return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events))

    monkeypatch.setattr(
        pantry.httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(provider), **kwargs),
    )
    response = client.post(
        "/api/pantry/preview/photo", content=photo(), headers={"Content-Type": "image/jpeg"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["name"] == "tomatoes"
    assert client.get("/api/pantry").json()["items"] == []
    complete = False
    assert (
        client.post(
            "/api/pantry/preview/photo", content=photo(), headers={"Content-Type": "image/jpeg"}
        ).status_code
        == 502
    )
    assert client.get("/api/pantry").json()["items"] == []


def test_identity_validation_and_rotating_credentials(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = {
        "sub": "owner",
        "iss": chatgpt.ISSUER,
        "aud": "oaiapp_test",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "nonce": "expected",
    }
    with patch.object(jwt.PyJWKClient, "get_signing_key_from_jwt") as key:
        key.return_value.key = private.public_key()
        token = jwt.encode(identity, private, algorithm="RS256")
        assert chatgpt.verify_identity(token, "oaiapp_test", "expected")["sub"] == "owner"
        for changes in [{"iss": "https://attacker.invalid"}, {"aud": "oaiapp_other"}, {"exp": 1}]:
            bad = jwt.encode({**identity, **changes}, private, algorithm="RS256")
            with pytest.raises(jwt.PyJWTError):
                chatgpt.verify_identity(bad, "oaiapp_test", "expected")
        with pytest.raises(chatgpt.ConnectionError):
            chatgpt.verify_identity(token, "oaiapp_test", "wrong")
    path = tmp_path / "credentials.json"
    value = credentials()
    value["expires_at"] = 0
    chatgpt.save_credentials(path, value)
    assert path.stat().st_mode & 0o777 == 0o600
    with patch.object(
        chatgpt.httpx,
        "post",
        return_value=httpx.Response(
            200,
            json={
                "access_token": "replacement-access",
                "refresh_token": "replacement-refresh",
                "expires_in": 3600,
                "scope": "chatgpt.tokens.use.direct",
            },
            request=httpx.Request("POST", chatgpt.TOKEN_URL),
        ),
    ) as renew:
        assert chatgpt.access_credentials(path)["access_token"] == "replacement-access"
        assert chatgpt.access_credentials(path)["refresh_token"] == "replacement-refresh"
        assert renew.call_count == 1
    path.chmod(0o644)
    with pytest.raises(chatgpt.ConnectionError):
        chatgpt.read_credentials(path)


def test_lab_install_never_puts_tokens_in_ssh_arguments(tmp_path):
    path = tmp_path / "credentials.json"
    chatgpt.save_credentials(path, credentials())
    with patch.object(chatgpt.subprocess, "run") as transfer:
        transfer.return_value.returncode = 0
        chatgpt.install_on_lab(path, "ansible@192.168.1.153", tmp_path / "key")
        call = transfer.call_args
        assert "test-access" not in " ".join(call.args[0])
        assert json.loads(call.kwargs["input"])["access_token"] == "test-access"
        assert "StrictHostKeyChecking=yes" in call.args[0]
        with pytest.raises(chatgpt.ConnectionError):
            chatgpt.install_on_lab(path, "-oProxyCommand=bad", tmp_path / "key")
        with pytest.raises(chatgpt.ConnectionError):
            chatgpt.install_on_lab(path, "attacker@example.com", tmp_path / "key")
        assert transfer.call_count == 1
