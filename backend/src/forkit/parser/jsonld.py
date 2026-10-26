"""JSON-LD recipe extractor.

Extraction order:
1. extruct — pulls all JSON-LD from the page; look for @type matching "Recipe".
2. recipe-scrapers — fallback if extruct finds nothing useful.

Returns a dict conforming to the normalizer's expected keys, or None.
"""

from __future__ import annotations

import json
import re
from typing import Any

import extruct
import structlog

log = structlog.get_logger()

_RECIPE_TYPE_RE = re.compile(r"\bRecipe\b", re.IGNORECASE)


def _is_recipe_type(type_value: Any) -> bool:
    """Accept both string and list @type values."""
    if isinstance(type_value, str):
        return bool(_RECIPE_TYPE_RE.search(type_value))
    if isinstance(type_value, list):
        return any(
            isinstance(t, str) and _RECIPE_TYPE_RE.search(t) for t in type_value
        )
    return False


def _coerce_to_list(value: Any) -> list[str]:
    """Coerce a JSON-LD value that may be a string or list to list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def _extract_instruction_text(step: Any) -> str | None:
    """Extract text from a HowToStep or plain string."""
    if isinstance(step, str):
        return step.strip() or None
    if isinstance(step, dict):
        # HowToStep / HowToSection
        step_type = step.get("@type", "")
        if isinstance(step_type, str) and "HowToSection" in step_type:
            # Recurse into itemListElement
            items = step.get("itemListElement", [])
            if not isinstance(items, list):
                items = [items]
            return "\n".join(filter(None, (_extract_instruction_text(item) for item in items))) or None
        return (
            step.get("text")
            or step.get("name")
            or step.get("description")
        )
    return None


def _jsonld_to_raw(data: dict[str, Any]) -> dict[str, Any]:
    """Map a raw JSON-LD Recipe object to our internal raw dict format."""
    ingredients = _coerce_to_list(data.get("recipeIngredient"))

    raw_instructions = data.get("recipeInstructions", [])
    if isinstance(raw_instructions, str):
        # Some sites encode instructions as a plain string
        instructions = [raw_instructions.strip()] if raw_instructions.strip() else []
    else:
        steps = _coerce_to_list(raw_instructions) if isinstance(raw_instructions, list) else []
        # Handle both plain strings and HowToStep dicts
        instructions = []
        for item in (raw_instructions if isinstance(raw_instructions, list) else [raw_instructions]):
            text = _extract_instruction_text(item)
            if text:
                instructions.append(text)

    # Time fields
    def _time(key: str) -> str | None:
        val = data.get(key)
        return str(val).strip() if val else None

    image_val = data.get("image")
    image_url: str | None = None
    if isinstance(image_val, str):
        image_url = image_val
    elif isinstance(image_val, dict):
        image_url = image_val.get("url")
    elif isinstance(image_val, list) and image_val:
        first = image_val[0]
        image_url = first if isinstance(first, str) else (first.get("url") if isinstance(first, dict) else None)

    return {
        "title": data.get("name", ""),
        "description": data.get("description"),
        "ingredients": ingredients,
        "instructions": instructions,
        "image_url": image_url,
        "total_time": _time("totalTime"),
        "prep_time": _time("prepTime"),
        "cook_time": _time("cookTime"),
        "yield_text": data.get("recipeYield")
        if isinstance(data.get("recipeYield"), str)
        else (str(data["recipeYield"][0]) if isinstance(data.get("recipeYield"), list) and data["recipeYield"] else None),
        "cuisine": (
            data["recipeCuisine"]
            if isinstance(data.get("recipeCuisine"), str)
            else (
                data["recipeCuisine"][0]
                if isinstance(data.get("recipeCuisine"), list) and data["recipeCuisine"]
                else None
            )
        ),
    }


def _try_extruct(html: str, url: str) -> dict[str, Any] | None:
    """Attempt extraction via extruct JSON-LD."""
    try:
        data = extruct.extract(
            html,
            base_url=url,
            syntaxes=["json-ld"],
            uniform=True,
        )
    except Exception as exc:
        log.debug("extruct failed", url=url, error=str(exc))
        return None

    for item in data.get("json-ld", []):
        if not isinstance(item, dict):
            continue
        if _is_recipe_type(item.get("@type")):
            log.debug("extruct found Recipe JSON-LD", url=url)
            return _jsonld_to_raw(item)

        # Check @graph entries
        for graph_item in item.get("@graph", []):
            if isinstance(graph_item, dict) and _is_recipe_type(graph_item.get("@type")):
                log.debug("extruct found Recipe in @graph", url=url)
                return _jsonld_to_raw(graph_item)

    return None


def _try_recipe_scrapers(html: str, url: str) -> dict[str, Any] | None:
    """Fallback: recipe-scrapers library."""
    try:
        from recipe_scrapers import scrape_html

        scraper = scrape_html(html, org_url=url)
        title = scraper.title()
        if not title:
            return None

        try:
            ingredients = scraper.ingredients()
        except Exception:
            ingredients = []

        try:
            instruction_text = scraper.instructions()
            instructions = [s.strip() for s in instruction_text.splitlines() if s.strip()]
        except Exception:
            instructions = []

        try:
            image_url = scraper.image()
        except Exception:
            image_url = None

        def _safe(fn):  # type: ignore[no-untyped-def]
            try:
                return fn()
            except Exception:
                return None

        log.debug("recipe-scrapers succeeded", url=url)
        return {
            "title": title,
            "description": _safe(scraper.description),
            "ingredients": ingredients,
            "instructions": instructions,
            "image_url": image_url,
            "total_time": _safe(lambda: f"PT{scraper.total_time()}M") if _safe(scraper.total_time) else None,
            "prep_time": _safe(lambda: f"PT{scraper.prep_time()}M") if _safe(scraper.prep_time) else None,
            "cook_time": _safe(lambda: f"PT{scraper.cook_time()}M") if _safe(scraper.cook_time) else None,
            "yield_text": _safe(scraper.yields),
            "cuisine": _safe(scraper.cuisine),
        }
    except Exception as exc:
        log.debug("recipe-scrapers failed", url=url, error=str(exc))
        return None


def extract_jsonld(html: str, url: str, *, schema_only: bool = False) -> dict[str, Any] | None:
    """Extract a recipe dict from HTML.

    Tries extruct first, falls back to recipe-scrapers.
    Returns None if neither strategy finds a recipe.
    """
    result = _try_extruct(html, url)
    if result is not None:
        return result

    return None if schema_only else _try_recipe_scrapers(html, url)
