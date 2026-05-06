"""GET /api/recipes — list and detail endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Ingredient, Recipe, Tag

log = structlog.get_logger()

router = APIRouter()


def _recipe_brief(r: Recipe) -> dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "hero_image_path": r.hero_image_path,
        "cuisine": r.cuisine,
        "total_time": r.total_time,
        "rating": r.rating,
        "cook_count": r.cook_count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _recipe_full(r: Recipe) -> dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "source_url": r.source_url,
        "hero_image_path": r.hero_image_path,
        "yield_text": r.yield_text,
        "prep_time": r.prep_time,
        "cook_time": r.cook_time,
        "total_time": r.total_time,
        "cuisine": r.cuisine,
        "meal_type": r.meal_type,
        "instructions": r.instructions,
        "cook_count": r.cook_count,
        "last_cooked": r.last_cooked.isoformat() if r.last_cooked else None,
        "rating": r.rating,
        "user_notes": r.user_notes,
        "view_count": r.view_count,
        "last_viewed": r.last_viewed.isoformat() if r.last_viewed else None,
        "parser_source": r.parser_source,
        "parser_confidence": r.parser_confidence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        "ingredients": [
            {
                "id": ing.id,
                "position": ing.position,
                "raw_text": ing.raw_text,
                "qty": ing.qty,
                "unit": ing.unit,
                "item": ing.item,
                "notes": ing.notes,
                "canonical_token": ing.canonical_token,
            }
            for ing in sorted(r.ingredients, key=lambda i: i.position)
        ],
        "tags": [t.name for t in r.tags],
    }


@router.get("/recipes")
async def list_recipes(
    q: str | None = None,
    favorite: bool | None = None,
    tag: str | None = None,
    cuisine: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List recipes with optional filtering.

    - q: full-text search via FTS5
    - favorite: filter rating >= 4 (proxy for favorite)
    - tag: filter by tag name
    - cuisine: partial match on cuisine field
    """
    query = session.query(Recipe)

    if q:
        # FTS5 match — get matching recipe IDs then filter
        fts_rows = session.execute(
            text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH :q"),
            {"q": q},
        ).fetchall()
        matched_ids = [row[0] for row in fts_rows]
        if not matched_ids:
            return {"recipes": [], "total": 0, "limit": limit, "offset": offset}
        query = query.filter(Recipe.id.in_(matched_ids))

    if favorite is True:
        query = query.filter(Recipe.rating >= 4)

    if tag:
        query = query.join(Recipe.tags).filter(Tag.name == tag.lower().strip())

    if cuisine:
        query = query.filter(Recipe.cuisine.ilike(f"%{cuisine}%"))

    total = query.count()
    recipes = query.order_by(Recipe.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "recipes": [_recipe_brief(r) for r in recipes],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/recipes/{recipe_id}/cook")
async def mark_cooked(
    recipe_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Increment cook_count and set last_cooked to now."""
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    recipe.cook_count = (recipe.cook_count or 0) + 1
    recipe.last_cooked = datetime.now(timezone.utc)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("mark_cooked: commit failed", recipe_id=recipe_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update cook count.") from exc

    return {
        "cook_count": recipe.cook_count,
        "last_cooked": recipe.last_cooked.isoformat(),
    }


@router.get("/recipes/{recipe_id}")
async def get_recipe(
    recipe_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return full recipe detail including ingredients and tags.

    Increments view_count and sets last_viewed.
    """
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    now = datetime.now(timezone.utc)
    recipe.view_count = (recipe.view_count or 0) + 1
    recipe.last_viewed = now
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.warning("get_recipe: failed to update view_count", recipe_id=recipe_id, error=str(exc))

    return _recipe_full(recipe)
