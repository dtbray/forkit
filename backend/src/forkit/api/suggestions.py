"""GET /api/suggestions/tonight — recipe suggestion engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Recipe

log = structlog.get_logger()

router = APIRouter()


def _brief(r: Recipe) -> dict[str, Any]:
    return {
        "id": r.id,
        "title": r.title,
        "hero_image_path": r.hero_image_path,
        "total_time": r.total_time,
        "cuisine": r.cuisine,
        "cook_count": r.cook_count,
    }


def score_recipe(r: Recipe, now: datetime, max_cook: int) -> float:
    """Score a recipe for tonight's suggestion.

    Components:
    - recency (40%): inverse of days since last cooked — rewards variety
    - cook_norm (30%): log-normalized cook count — rewards trusted recipes
    - rating_norm (20%): normalized rating (1-5 → 0.2-1.0)
    - new_bonus (10%): flat bonus for recipes added in the last 7 days
    """
    if r.last_cooked:
        last_cooked_aware = r.last_cooked
        if last_cooked_aware.tzinfo is None:
            last_cooked_aware = last_cooked_aware.replace(tzinfo=timezone.utc)
        days_since = (now - last_cooked_aware).days
    else:
        days_since = 9999

    recency = 1.0 / (days_since + 1)
    cook_norm = math.log1p(r.cook_count) / math.log1p(max_cook)
    rating_norm = ((r.rating or 3) / 5)

    created_aware = r.created_at
    if created_aware is not None and created_aware.tzinfo is None:
        created_aware = created_aware.replace(tzinfo=timezone.utc)
    new_bonus = 0.1 if (created_aware and (now - created_aware).days <= 7) else 0.0

    return 0.4 * recency + 0.3 * cook_norm + 0.2 * rating_norm + new_bonus


@router.get("/suggestions/tonight")
async def suggestions_tonight(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return a ranked suggestion for tonight plus up to 3 alternates.

    Cold start (all cook_count == 0): sorts by created_at descending so
    newly added recipes surface first.
    """
    recipes = session.query(Recipe).all()
    if not recipes:
        return {"tonight": None, "alternates": [], "cold_start": True}

    now = datetime.now(timezone.utc)
    cold_start = all(r.cook_count == 0 for r in recipes)

    if cold_start:
        sorted_recipes = sorted(
            recipes,
            key=lambda r: r.created_at if r.created_at else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
    else:
        max_cook = max((r.cook_count for r in recipes), default=0) or 1
        sorted_recipes = sorted(recipes, key=lambda r: score_recipe(r, now, max_cook), reverse=True)

    tonight = sorted_recipes[0] if sorted_recipes else None
    alternates = sorted_recipes[1:4]

    return {
        "tonight": _brief(tonight) if tonight else None,
        "alternates": [_brief(r) for r in alternates],
        "cold_start": cold_start,
    }
