"""POST /api/ingest — recipe ingestion endpoint (S7: rate-limited 10/min)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Ingredient, Recipe
from ..parser.fetcher import FetchError, URLForbiddenError, safe_fetch
from ..parser.ingredients import structure_ingredient
from ..parser.jsonld import extract_jsonld
from ..parser.normalizer import normalize

log = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class IngestRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url must not be empty")
        return v


class IngestResponse(BaseModel):
    recipe_id: str
    parser_source: str
    parser_confidence: float


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("10/minute")
async def ingest_recipe(
    request: Request,
    body: IngestRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Fetch a recipe URL, parse it, persist to DB, return the recipe ID.

    Rate limited to 10 requests/minute per IP (S7).
    SSRF-safe fetcher enforces scheme allowlist + IP blocklist (S1).
    HTML sanitized on store via bleach (S2).
    """
    log.info("ingest_recipe", url=body.url)

    # Step 1: Fetch
    try:
        html_bytes = await safe_fetch(body.url)
    except URLForbiddenError as exc:
        log.warning("ingest blocked url", url=body.url, reason=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FetchError as exc:
        log.warning("ingest fetch error", url=body.url, reason=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = html_bytes.decode("utf-8", errors="replace")

    # Step 2: JSON-LD extraction + adapter fallback
    raw = extract_jsonld(html, body.url)
    parser_source = "jsonld"

    if raw is None:
        # LLM fallback is v2 — return 422 with informative message
        log.info("ingest: no structured recipe found, LLM fallback not implemented in v1", url=body.url)
        raise HTTPException(
            status_code=422,
            detail="Could not extract a recipe from that URL. "
            "The page may not contain structured recipe data.",
        )

    # Step 3: Normalize (sanitize HTML, canonicalize times)
    normalized = normalize(raw)

    if not normalized.get("title"):
        raise HTTPException(
            status_code=422,
            detail="Extracted recipe has no title; cannot persist.",
        )

    # Step 4: Structure ingredients
    structured_ingredients = [
        structure_ingredient(ing) for ing in normalized.get("ingredients") or []
    ]

    # Step 5: Persist
    recipe_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    instructions_json = json.dumps(
        [
            {"step_number": i + 1, "text": step}
            for i, step in enumerate(normalized.get("instructions") or [])
        ]
    )

    recipe = Recipe(
        id=recipe_id,
        title=normalized["title"],
        description=normalized.get("description"),
        source_url=body.url,
        hero_image_path=None,  # image fetch is async post-ingest (future)
        yield_text=normalized.get("yield_text"),
        prep_time=normalized.get("prep_time"),
        cook_time=normalized.get("cook_time"),
        total_time=normalized.get("total_time"),
        cuisine=normalized.get("cuisine"),
        instructions=instructions_json,
        parser_source=parser_source,
        parser_confidence=1.0,
        created_at=now,
        updated_at=now,
    )

    session.add(recipe)

    for position, ing_dict in enumerate(structured_ingredients):
        ingredient = Ingredient(
            recipe_id=recipe_id,
            position=position,
            raw_text=ing_dict["raw_text"],
            qty=ing_dict.get("qty"),
            unit=ing_dict.get("unit"),
            item=ing_dict.get("item") or ing_dict["raw_text"],
            notes=ing_dict.get("notes"),
            canonical_token=ing_dict.get("canonical_token"),
        )
        session.add(ingredient)

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("ingest persist failed", recipe_id=recipe_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to persist recipe; please try again.",
        ) from exc

    log.info(
        "ingest complete",
        recipe_id=recipe_id,
        title=normalized["title"],
        parser_source=parser_source,
        ingredient_count=len(structured_ingredients),
    )

    return {
        "recipe_id": recipe_id,
        "parser_source": parser_source,
        "parser_confidence": 1.0,
    }
