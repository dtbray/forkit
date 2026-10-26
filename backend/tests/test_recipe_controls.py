"""Exercise the real HTTP mutation/search contract against a migrated database."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from forkit.db import get_session
from forkit.main import app
from forkit.models import DeletedRecipe, Ingredient, Recipe, Tag
from forkit.services.ingest import ingest_url


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def recipe(db_session):
    recipe = Recipe(
        title="Lemon pasta",
        source_url="https://example.com/pasta",
        instructions=json.dumps(["Cook"]),
        rating=5,
    )
    recipe.ingredients.append(Ingredient(position=0, raw_text="1 lemon", item="lemon"))
    recipe.tags.append(Tag(name="vegan"))
    db_session.add(recipe)
    db_session.commit()
    return recipe


def test_changes_persist_and_favorites_are_independent_of_rating(client, db_session, recipe):
    assert client.get("/api/recipes?favorite=true").json()["total"] == 0
    response = client.patch(
        f"/api/recipes/{recipe.id}",
        json={"favorite": True, "user_notes": "More lemon next time", "rating": 3},
    )
    assert response.status_code == 200
    db_session.expire_all()
    saved = client.get(f"/api/recipes/{recipe.id}").json()
    assert saved["favorite"] is True
    assert saved["user_notes"] == "More lemon next time"
    assert saved["rating"] == 3
    assert client.get("/api/recipes?favorite=true").json()["recipes"][0]["favorite"] is True
    assert client.get("/api/recipes?favorite=false").json()["total"] == 0
    assert (
        client.patch(
            f"/api/recipes/{recipe.id}", json={"rating": None, "user_notes": None}
        ).status_code
        == 200
    )
    db_session.expire_all()
    assert db_session.get(Recipe, recipe.id).rating is None


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 6},
        {"rating": True},
        {"favorite": None},
        {"favorite": "yes"},
        {"title": "unexpected"},
        {"user_notes": "x" * 100001},
    ],
)
def test_invalid_changes_rejected(client, recipe, body):
    assert client.patch(f"/api/recipes/{recipe.id}", json=body).status_code == 422


def test_delete_removes_recipe_relations_search_and_prevents_reimport(client, db_session, recipe):
    recipe_id, url = recipe.id, recipe.source_url
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404
    assert client.get("/api/recipes?q=lemon").json()["total"] == 0
    assert db_session.query(Ingredient).count() == 0
    assert db_session.execute(text("SELECT count(*) FROM recipe_tag")).scalar() == 0
    assert db_session.get(DeletedRecipe, url) is not None
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 404


@pytest.mark.asyncio
async def test_deleted_source_not_fetched(db_session):
    url = "https://example.com/deleted"
    db_session.add(DeletedRecipe(source_url=url))
    db_session.commit()
    with patch("forkit.services.ingest.safe_fetch", new_callable=AsyncMock) as fetch:
        with pytest.raises(HTTPException) as exc:
            await ingest_url(url, db_session)
        assert exc.value.status_code == 409
        fetch.assert_not_called()


@pytest.mark.parametrize("q", ['"', "(", "lemon OR", "lemon - pasta", "NEAR(lemon)", "title:lemon"])
def test_search_punctuation_cannot_trigger_fts_errors(client, recipe, q):
    assert client.get("/api/recipes", params={"q": q}).status_code == 200


def test_bounds_and_source_filters(client, recipe):
    for params in (
        {"limit": -1},
        {"limit": 201},
        {"offset": -1},
        {"q": "a" * 501},
        {"source": "%"},
    ):
        assert client.get("/api/recipes", params=params).status_code == 422
    assert client.get("/api/recipes?source=example.com&tag=vegan").json()["total"] == 1
    assert client.get("/api/recipes?source=other.example").json()["total"] == 0
    assert client.patch("/api/recipes/missing", json={"favorite": True}).status_code == 404


def test_upgrade_preserves_existing_recipe_and_rating(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'existing.sqlite'}")
    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[2] / "ops" / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "0004")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO recipe "
                "(id,title,source_url,instructions,rating,user_notes,created_at,updated_at) "
                "VALUES ('legacy','Soup','https://example.com/soup','[]',5,"
                "'Keep these notes',datetime('now'),datetime('now'))"
            )
        )
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT favorite,rating,user_notes FROM recipe WHERE id='legacy'")
        ).one()
        assert tuple(row) == (0, 5, "Keep these notes")
    engine.dispose()
