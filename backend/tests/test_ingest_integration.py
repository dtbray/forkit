"""Integration tests for POST /api/ingest — full pipeline."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from forkit.main import app
from forkit.db import get_session
from forkit.models import Ingredient, Recipe

# ---------------------------------------------------------------------------
# Minimal HTML fixture with valid JSON-LD Recipe schema
# ---------------------------------------------------------------------------
_JSONLD_HTML = """\
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Test Pasta",
  "description": "A simple pasta dish.",
  "recipeIngredient": ["200g spaghetti", "2 cloves garlic", "salt to taste"],
  "recipeInstructions": [
    {"@type": "HowToStep", "text": "Boil water."},
    {"@type": "HowToStep", "text": "Cook pasta for 10 minutes."},
    {"@type": "HowToStep", "text": "Serve hot."}
  ],
  "totalTime": "PT20M",
  "image": "https://example.com/pasta.jpg"
}
</script>
</head>
<body><h1>Test Pasta</h1></body>
</html>
"""

_RECIPE_URL = "https://recipes.example.com/test-pasta"
_IMAGE_URL = "https://example.com/pasta.jpg"


def _make_test_db():
    """Build an in-memory SQLite DB with all migrations applied."""
    import tempfile
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    _MIGRATIONS_DIR = _PROJECT_ROOT / "ops" / "migrations"

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()

    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn: object, _: object) -> None:
        cur = conn.cursor()  # type: ignore[union-attr]
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    return engine, db_path


@pytest.fixture()
def test_client_with_db():
    """TestClient with an isolated DB and mocked safe_fetch / image fetch."""
    engine, db_path = _make_test_db()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session():
        with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, SessionLocal

    app.dependency_overrides.clear()
    engine.dispose()
    try:
        os.unlink(db_path)
        for ext in ("-wal", "-shm"):
            side = db_path + ext
            if os.path.exists(side):
                os.unlink(side)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ingest_jsonld_success_full_pipeline(test_client_with_db):
    """POST /api/ingest with a valid JSON-LD page: 200, recipe persisted, ingredients written."""
    client, SessionLocal = test_client_with_db

    # Mock safe_fetch to return our HTML fixture; image fetch returns None (non-fatal)
    with (
        patch("forkit.api.ingest.safe_fetch", new=AsyncMock(return_value=_JSONLD_HTML.encode())),
        patch("forkit.api.ingest.fetch_and_store_image", new=AsyncMock(return_value=None)),
    ):
        resp = client.post("/api/ingest", json={"url": _RECIPE_URL})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "recipe_id" in data
    assert data["parser_source"] == "jsonld"
    assert data["parser_confidence"] == 1.0

    recipe_id = data["recipe_id"]

    # Verify DB row exists
    with SessionLocal() as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.title == "Test Pasta"
        assert recipe.source_url == _RECIPE_URL
        assert recipe.total_time == "PT20M"

        # Verify ingredients
        ingredients = (
            session.query(Ingredient)
            .filter_by(recipe_id=recipe_id)
            .order_by(Ingredient.position)
            .all()
        )
        assert len(ingredients) == 3
        assert ingredients[0].raw_text == "200g spaghetti"


def test_ingest_sets_hero_image_path_when_image_fetch_succeeds(test_client_with_db):
    """When image fetch succeeds, hero_image_path is written to the DB."""
    client, SessionLocal = test_client_with_db

    fake_image_path = "abc123/hero.webp"

    with (
        patch("forkit.api.ingest.safe_fetch", new=AsyncMock(return_value=_JSONLD_HTML.encode())),
        patch("forkit.api.ingest.fetch_and_store_image", new=AsyncMock(return_value=fake_image_path)),
    ):
        resp = client.post("/api/ingest", json={"url": _RECIPE_URL})

    assert resp.status_code == 200, resp.text
    recipe_id = resp.json()["recipe_id"]

    with SessionLocal() as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.hero_image_path == fake_image_path


def test_ingest_hero_image_null_when_image_fetch_fails(test_client_with_db):
    """When image fetch returns None, hero_image_path stays null (non-fatal)."""
    client, SessionLocal = test_client_with_db

    with (
        patch("forkit.api.ingest.safe_fetch", new=AsyncMock(return_value=_JSONLD_HTML.encode())),
        patch("forkit.api.ingest.fetch_and_store_image", new=AsyncMock(return_value=None)),
    ):
        resp = client.post("/api/ingest", json={"url": _RECIPE_URL})

    assert resp.status_code == 200, resp.text
    recipe_id = resp.json()["recipe_id"]

    with SessionLocal() as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.hero_image_path is None


def test_ingest_duplicate_returns_409(test_client_with_db):
    """POST /api/ingest with the same URL a second time returns 409 already_in_vault."""
    client, SessionLocal = test_client_with_db

    with (
        patch("forkit.api.ingest.safe_fetch", new=AsyncMock(return_value=_JSONLD_HTML.encode())),
        patch("forkit.api.ingest.fetch_and_store_image", new=AsyncMock(return_value=None)),
    ):
        first = client.post("/api/ingest", json={"url": _RECIPE_URL})
        assert first.status_code == 200, first.text
        first_recipe_id = first.json()["recipe_id"]

        second = client.post("/api/ingest", json={"url": _RECIPE_URL})

    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["detail"] == "already_in_vault"
    assert detail["recipe_id"] == first_recipe_id


def test_ingest_llm_fallback_called_when_no_jsonld(test_client_with_db):
    """When JSON-LD extraction returns None, LLM fallback is invoked."""
    client, SessionLocal = test_client_with_db

    plain_html = b"<html><body><p>Just some text, no recipe structured data.</p></body></html>"

    llm_result: dict[str, Any] = {
        "title": "LLM Pasta",
        "description": "An LLM-extracted pasta.",
        "ingredients": ["100g pasta", "olive oil"],
        "instructions": ["Boil pasta.", "Add oil."],
        "image_url": None,
        "total_time": "PT15M",
        "prep_time": None,
        "cook_time": None,
        "yield_text": "2 servings",
        "cuisine": "Italian",
    }

    llm_url = "https://recipes.example.com/plain-page"

    with (
        patch("forkit.api.ingest.safe_fetch", new=AsyncMock(return_value=plain_html)),
        patch("forkit.api.ingest.RoutedLLMProvider.extract_recipe", new=AsyncMock(return_value=llm_result)),
        patch("forkit.api.ingest.fetch_and_store_image", new=AsyncMock(return_value=None)),
    ):
        resp = client.post("/api/ingest", json={"url": llm_url})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["parser_source"] == "llm"

    with SessionLocal() as session:
        recipe = session.query(Recipe).filter_by(source_url=llm_url).first()
        assert recipe is not None
        assert recipe.title == "LLM Pasta"
        assert recipe.parser_source == "llm"
