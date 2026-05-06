"""Tests for SQLAlchemy models: insert, retrieve, relationships."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from forkit.models import Ingredient, Recipe, Tag


def test_recipe_insert_and_retrieve(db_session):
    """A Recipe inserted via ORM is retrievable with correct field values."""
    recipe = Recipe(
        title="Chocolate Chip Cookies",
        source_url="https://example.com/chocolate-chip-cookies",
        instructions=json.dumps(["Mix dry ingredients", "Add wet ingredients", "Bake at 375F"]),
        cook_count=3,
        rating=5,
        cuisine="American",
        meal_type="dessert",
        parser_source="jsonld",
        parser_confidence=0.95,
    )
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.get(Recipe, recipe.id)
    assert fetched is not None
    assert fetched.title == "Chocolate Chip Cookies"
    assert fetched.source_url == "https://example.com/chocolate-chip-cookies"
    assert fetched.cook_count == 3
    assert fetched.rating == 5
    assert fetched.cuisine == "American"
    assert fetched.meal_type == "dessert"
    assert fetched.parser_source == "jsonld"
    assert fetched.parser_confidence == pytest.approx(0.95)
    assert fetched.view_count == 0
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_recipe_with_ingredients(db_session):
    """Ingredients are inserted and retrievable via relationship."""
    recipe = Recipe(
        title="Pancakes",
        source_url="https://example.com/pancakes",
        instructions=json.dumps(["Mix", "Pour", "Flip"]),
    )
    ing1 = Ingredient(
        recipe=recipe,
        position=0,
        raw_text="2 cups all-purpose flour",
        qty="2",
        unit="cups",
        item="all-purpose flour",
        canonical_token="flour",
    )
    ing2 = Ingredient(
        recipe=recipe,
        position=1,
        raw_text="1 tsp baking powder",
        qty="1",
        unit="tsp",
        item="baking powder",
        canonical_token="baking powder",
    )
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.get(Recipe, recipe.id)
    assert fetched is not None
    assert len(fetched.ingredients) == 2
    assert fetched.ingredients[0].raw_text == "2 cups all-purpose flour"
    assert fetched.ingredients[0].canonical_token == "flour"
    assert fetched.ingredients[1].item == "baking powder"


def test_recipe_with_tags(db_session):
    """Tags are associated and retrievable via relationship."""
    tag_dessert = Tag(name="dessert")
    tag_quick = Tag(name="quick")
    recipe = Recipe(
        title="Brownies",
        source_url="https://example.com/brownies",
        instructions=json.dumps(["Mix", "Bake"]),
        tags=[tag_dessert, tag_quick],
    )
    db_session.add(recipe)
    db_session.commit()

    fetched = db_session.get(Recipe, recipe.id)
    assert fetched is not None
    tag_names = {t.name for t in fetched.tags}
    assert "dessert" in tag_names
    assert "quick" in tag_names


def test_ingredient_cascade_delete(db_session):
    """Deleting a Recipe cascades to its Ingredients."""
    recipe = Recipe(
        title="Soup",
        source_url="https://example.com/soup",
        instructions=json.dumps(["Boil water"]),
    )
    ing = Ingredient(
        recipe=recipe,
        position=0,
        raw_text="1 onion",
        item="onion",
        canonical_token="onion",
    )
    db_session.add(recipe)
    db_session.commit()

    recipe_id = recipe.id
    db_session.delete(recipe)
    db_session.commit()

    remaining = db_session.query(Ingredient).filter_by(recipe_id=recipe_id).all()
    assert remaining == []


import pytest  # noqa: E402 — placed here to avoid shadowing builtins at top
