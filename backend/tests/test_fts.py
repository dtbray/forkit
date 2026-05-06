"""Tests for FTS5 virtual table and trigger-based content sync."""

from __future__ import annotations

import json

from sqlalchemy import text

from forkit.models import Ingredient, Recipe


def _insert_recipe(db_session, title: str, source_url: str, ingredients: list[str]) -> Recipe:
    """Helper: create a recipe with inline ingredient rows."""
    recipe = Recipe(
        title=title,
        source_url=source_url,
        instructions=json.dumps(["Step 1"]),
    )
    for pos, raw in enumerate(ingredients):
        recipe.ingredients.append(
            Ingredient(
                position=pos,
                raw_text=raw,
                item=raw.split()[-1],  # rough item extraction for test data
            )
        )
    db_session.add(recipe)
    db_session.commit()
    return recipe


def test_fts_match_title(db_session):
    """FTS5 MATCH on 'chocolate' returns the recipe inserted by trigger."""
    recipe = _insert_recipe(
        db_session,
        title="Chocolate Chip Cookies",
        source_url="https://example.com/choc-chip",
        ingredients=["2 cups all-purpose flour", "1 cup chocolate chips"],
    )

    rows = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'chocolate'")
    ).fetchall()

    recipe_ids = [r[0] for r in rows]
    assert recipe.id in recipe_ids, "Expected FTS hit for 'chocolate' in title/ingredients"


def test_fts_match_ingredient(db_session):
    """FTS5 MATCH on 'flour' returns the recipe via ingredient trigger."""
    recipe = _insert_recipe(
        db_session,
        title="Chocolate Chip Cookies",
        source_url="https://example.com/choc-chip-flour",
        ingredients=["2 cups all-purpose flour", "1 cup chocolate chips"],
    )

    rows = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'flour'")
    ).fetchall()

    recipe_ids = [r[0] for r in rows]
    assert recipe.id in recipe_ids, "Expected FTS hit for 'flour' in ingredient_text"


def test_fts_no_match_absent_term(db_session):
    """FTS5 MATCH on 'zucchini' returns no results for this recipe."""
    recipe = _insert_recipe(
        db_session,
        title="Chocolate Chip Cookies",
        source_url="https://example.com/choc-chip-nozucchini",
        ingredients=["2 cups all-purpose flour", "1 cup chocolate chips"],
    )

    rows = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'zucchini'")
    ).fetchall()

    recipe_ids = [r[0] for r in rows]
    assert recipe.id not in recipe_ids, "Did not expect FTS hit for 'zucchini'"
    assert len(recipe_ids) == 0, "FTS index should be empty for 'zucchini'"


def test_fts_update_triggers_resync(db_session):
    """Updating a recipe title re-syncs the FTS index via the au trigger."""
    recipe = _insert_recipe(
        db_session,
        title="Vanilla Cake",
        source_url="https://example.com/vanilla-cake",
        ingredients=["2 cups sugar"],
    )

    # Confirm 'vanilla' is found before update
    rows_before = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'vanilla'")
    ).fetchall()
    assert recipe.id in [r[0] for r in rows_before]

    # Update title
    recipe.title = "Lemon Drizzle Cake"
    db_session.commit()

    # 'vanilla' should no longer match
    rows_after_vanilla = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'vanilla'")
    ).fetchall()
    assert recipe.id not in [r[0] for r in rows_after_vanilla]

    # 'lemon' should now match
    rows_lemon = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'lemon'")
    ).fetchall()
    assert recipe.id in [r[0] for r in rows_lemon]


def test_fts_delete_trigger_removes_row(db_session):
    """Deleting a recipe removes it from the FTS index."""
    recipe = _insert_recipe(
        db_session,
        title="Garlic Bread",
        source_url="https://example.com/garlic-bread",
        ingredients=["4 cloves garlic"],
    )
    recipe_id = recipe.id

    rows_before = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'garlic'")
    ).fetchall()
    assert recipe_id in [r[0] for r in rows_before]

    db_session.delete(recipe)
    db_session.commit()

    rows_after = db_session.execute(
        text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH 'garlic'")
    ).fetchall()
    assert recipe_id not in [r[0] for r in rows_after]
