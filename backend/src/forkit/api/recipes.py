"""GET /api/recipes — list and detail endpoints."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, text
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import DeletedRecipe, FeedItem, Recipe, Tag

log = structlog.get_logger()

router = APIRouter()
DbSession = Annotated[Session, Depends(get_session)]


def _image_variant(path: str | None, variant: str) -> str | None:
    if path and path.endswith("/hero.webp"):
        return str(PurePosixPath(path).with_name(f"{variant}.webp"))
    return path


def _recipe_brief(r: Recipe) -> dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "hero_image_path": r.hero_image_path,
        "thumb_image_path": _image_variant(r.hero_image_path, "thumb"),
        "medium_image_path": _image_variant(r.hero_image_path, "medium"),
        "favorite": r.favorite,
        "source_url": r.source_url,
        "tags": [t.name for t in r.tags],
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
        "thumb_image_path": _image_variant(r.hero_image_path, "thumb"),
        "medium_image_path": _image_variant(r.hero_image_path, "medium"),
        "favorite": r.favorite,
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
    session: DbSession,
    q: str | None = Query(default=None, max_length=500),
    favorite: bool | None = None,
    tag: str | None = None,
    cuisine: str | None = None,
    source: str | None = Query(default=None, max_length=253),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List recipes with optional filtering.

    - q: full-text search via FTS5
    - favorite: filter explicit saved favorite status
    - tag: filter by tag name
    - cuisine: partial match on cuisine field
    """
    query = session.query(Recipe).options(selectinload(Recipe.tags))

    if q:
        # Treat search as ordinary words, never as an unchecked FTS query language.
        terms = re.findall(r"[^\W_]+", q, re.UNICODE)
        if not terms:
            return {"recipes": [], "total": 0, "limit": limit, "offset": offset}
        fts_query = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
        # FTS5 match — get matching recipe IDs then filter
        fts_rows = session.execute(
            text("SELECT recipe_id FROM recipe_fts WHERE recipe_fts MATCH :q"),
            {"q": fts_query},
        ).fetchall()
        matched_ids = [row[0] for row in fts_rows]
        if not matched_ids:
            return {"recipes": [], "total": 0, "limit": limit, "offset": offset}
        query = query.filter(Recipe.id.in_(matched_ids))

    if favorite is not None:
        query = query.filter(Recipe.favorite == favorite)

    if source:
        # Only hostname filters; reject SQL wildcard characters and URL syntax.
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", source):
            raise HTTPException(status_code=422, detail="source must be a hostname")
        host = source.lower()
        query = query.filter(
            or_(
                Recipe.source_url.like(f"https://{host}/%"),
                Recipe.source_url.like(f"http://{host}/%"),
            )
        )

    if tag:
        query = query.join(Recipe.tags).filter(Tag.name == tag.lower().strip())

    if cuisine:
        query = query.filter(Recipe.cuisine.ilike(f"%{cuisine}%"))

    total = query.count()
    recipes = (
        query.order_by(Recipe.created_at.desc(), Recipe.id.desc()).offset(offset).limit(limit).all()
    )

    return {
        "recipes": [_recipe_brief(r) for r in recipes],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/recipes/{recipe_id}/cook")
async def mark_cooked(
    recipe_id: str,
    session: DbSession,
) -> dict[str, Any]:
    """Increment cook_count and set last_cooked to now."""
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    recipe.cook_count = (recipe.cook_count or 0) + 1
    recipe.last_cooked = datetime.now(UTC)
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
    session: DbSession,
) -> dict[str, Any]:
    """Return full recipe detail including ingredients and tags.

    Increments view_count and sets last_viewed.
    """
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    now = datetime.now(UTC)
    recipe.view_count = (recipe.view_count or 0) + 1
    recipe.last_viewed = now
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.warning("get_recipe: failed to update view_count", recipe_id=recipe_id, error=str(exc))

    return _recipe_full(recipe)


class RecipeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    favorite: bool | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    user_notes: str | None = Field(default=None, max_length=100_000)

    @field_validator("favorite")
    @classmethod
    def favorite_not_null(cls, value):
        if value is None:
            raise ValueError("favorite cannot be null")
        return value


@router.patch("/recipes/{recipe_id}")
async def update_recipe(recipe_id: str, body: RecipeUpdate, session: DbSession) -> dict[str, Any]:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(recipe, field, value)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("recipe update failed", recipe_id=recipe_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to save recipe.") from exc
    return _recipe_full(recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: str, session: DbSession) -> None:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found.")
    try:
        session.merge(DeletedRecipe(source_url=recipe.source_url))
        session.query(FeedItem).filter(FeedItem.recipe_id == recipe.id).update(
            {FeedItem.recipe_id: None, FeedItem.dismissed: 1}
        )
        session.delete(recipe)
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("recipe delete failed", recipe_id=recipe_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to delete recipe.") from exc
