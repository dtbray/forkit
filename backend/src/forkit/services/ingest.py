"""Ingest service — core recipe ingestion business logic.

Extracted from api/ingest.py so that both the HTTP endpoint and the future
Phase 2 inbox /promote endpoint can share the same code path without an
HTTP self-call (ADR-002 Section 5.2, alternative rejected).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import bleach
import structlog
from fastapi import HTTPException
from readability import Document
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm.anthropic import AnthropicProvider
from ..llm.base import LLMExtractionError
from ..llm.ollama import OllamaProvider
from ..llm.router import RoutedLLMProvider
from ..models import Ingredient, Recipe, Tag, recipe_tag
from ..parser.fetcher import FetchError, URLForbiddenError, safe_fetch
from ..parser.images import fetch_and_store_image
from ..parser.ingredients import structure_ingredient
from ..parser.jsonld import extract_jsonld
from ..parser.normalizer import normalize

log = structlog.get_logger()


def _extract_readable_text(html: str) -> str:
    doc = Document(html)
    content = doc.summary()
    return bleach.clean(content, tags=[], strip=True)


def _get_llm_provider(session: Session) -> RoutedLLMProvider:
    settings = get_settings()

    if settings.forkit_llm_primary == "ollama":
        primary: Any = OllamaProvider(
            base_url=settings.forkit_ollama_url,
            model=settings.forkit_ollama_model,
            timeout_sec=settings.forkit_llm_timeout_sec,
        )
    else:
        primary = AnthropicProvider(
            api_key=settings.forkit_anthropic_api_key.get_secret_value(),
            model=settings.forkit_anthropic_model,
            timeout_sec=settings.forkit_llm_timeout_sec,
        )

    fallback: Any = None
    if settings.forkit_llm_fallback == "anthropic":
        fallback = AnthropicProvider(
            api_key=settings.forkit_anthropic_api_key.get_secret_value(),
            model=settings.forkit_anthropic_model,
            timeout_sec=settings.forkit_llm_timeout_sec,
        )
    elif settings.forkit_llm_fallback == "ollama":
        fallback = OllamaProvider(
            base_url=settings.forkit_ollama_url,
            model=settings.forkit_ollama_model,
            timeout_sec=settings.forkit_llm_timeout_sec,
        )

    return RoutedLLMProvider(primary=primary, fallback=fallback, session=session)


async def ingest_url(url: str, session: Session) -> dict:
    """Fetch, parse, and persist a recipe URL. Returns dict with recipe_id,
    parser_source, parser_confidence.

    Raises HTTPException on duplicate (409), invalid URL (422), fetch error
    (400), or parse failure (422).

    This function is the single source of truth for recipe ingestion; both
    POST /api/ingest and (Phase 2) POST /api/discovery/inbox/{id}/promote
    call it directly — no HTTP self-call.
    """
    log.info("ingest_url", url=url)

    # --- Duplicate check ---------------------------------------------------
    existing = session.query(Recipe).filter_by(source_url=url).first()
    if existing is not None:
        log.info("ingest duplicate", url=url, recipe_id=existing.id)
        raise HTTPException(
            status_code=409,
            detail={"detail": "already_in_vault", "recipe_id": existing.id},
        )

    # --- Step 1: Fetch -----------------------------------------------------
    try:
        html_bytes = await safe_fetch(url)
    except URLForbiddenError as exc:
        log.warning("ingest blocked url", url=url, reason=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FetchError as exc:
        log.warning("ingest fetch error", url=url, reason=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = html_bytes.decode("utf-8", errors="replace")

    # --- Step 2: JSON-LD extraction → LLM fallback -------------------------
    raw = extract_jsonld(html, url)
    parser_source = "jsonld"
    parser_confidence = 1.0

    if raw is None:
        log.info("ingest: JSON-LD not found, trying LLM fallback", url=url)
        readable_text = _extract_readable_text(html)
        llm = _get_llm_provider(session)
        try:
            llm_result = await llm.extract_recipe(readable_text, source_url=url)
        except LLMExtractionError as exc:
            log.warning("ingest: LLM fallback failed", url=url, error=str(exc))
            raise HTTPException(
                status_code=422,
                detail="Could not extract a recipe from that URL. "
                "The page may not contain structured recipe data.",
            ) from exc
        raw = llm_result
        parser_source = "llm"
        parser_confidence = (
            float(raw.get("confidence", 0.7))
            if isinstance(raw.get("confidence"), (int, float))
            else 0.7
        )

    # --- Step 3: Normalize --------------------------------------------------
    normalized = normalize(raw)

    if not normalized.get("title"):
        raise HTTPException(
            status_code=422,
            detail="Extracted recipe has no title; cannot persist.",
        )

    # --- Step 4: Structure ingredients -------------------------------------
    structured_ingredients = [
        structure_ingredient(ing) for ing in normalized.get("ingredients") or []
    ]

    # --- Step 5: Persist ---------------------------------------------------
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
        source_url=url,
        hero_image_path=None,
        yield_text=normalized.get("yield_text"),
        prep_time=normalized.get("prep_time"),
        cook_time=normalized.get("cook_time"),
        total_time=normalized.get("total_time"),
        cuisine=normalized.get("cuisine"),
        instructions=instructions_json,
        parser_source=parser_source,
        parser_confidence=parser_confidence,
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

    # Tags
    for tag_name in raw.get("tags") or []:
        tag_name_clean = str(tag_name).lower().strip()
        if not tag_name_clean:
            continue
        tag = session.query(Tag).filter_by(name=tag_name_clean).first()
        if not tag:
            tag = Tag(name=tag_name_clean)
            session.add(tag)
            session.flush()
        session.execute(
            recipe_tag.insert().values(recipe_id=recipe_id, tag_id=tag.id)
        )

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("ingest persist failed", recipe_id=recipe_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to persist recipe; please try again.",
        ) from exc

    # --- Step 6: Image fetch (non-fatal) -----------------------------------
    settings = get_settings()
    image_url = normalized.get("image_url")
    if image_url:
        image_path = await fetch_and_store_image(image_url, settings.forkit_image_dir)
        if image_path:
            try:
                recipe_row = session.get(Recipe, recipe_id)
                if recipe_row is not None:
                    recipe_row.hero_image_path = image_path
                    session.commit()
            except Exception as exc:
                log.warning(
                    "ingest: failed to update hero_image_path",
                    recipe_id=recipe_id,
                    error=str(exc),
                )

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
        "parser_confidence": parser_confidence,
    }
