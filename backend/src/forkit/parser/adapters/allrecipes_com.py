"""Per-site adapter for allrecipes.com.

AllRecipes publishes structured JSON-LD but also has robust support in
recipe-scrapers.  This adapter uses `recipe-scrapers` `scrape_html()` as
the canonical parse path, giving us a single code path that handles both
their JSON-LD and any site-specific HTML structure changes.
"""

from __future__ import annotations

from typing import Any

import structlog

from . import register

log = structlog.get_logger()


@register(hosts=["allrecipes.com", "www.allrecipes.com"])
def parse(html: str, url: str) -> dict[str, Any] | None:
    """Parse an AllRecipes page into a raw recipe dict."""
    try:
        from recipe_scrapers import scrape_html

        scraper = scrape_html(html, org_url=url)

        def _safe(fn: Any) -> Any:
            try:
                return fn()
            except Exception:
                return None

        title = _safe(scraper.title)
        if not title:
            log.debug("allrecipes adapter: no title found", url=url)
            return None

        ingredients: list[str] = _safe(scraper.ingredients) or []

        instruction_text: str = _safe(scraper.instructions) or ""
        instructions: list[str] = [
            s.strip() for s in instruction_text.splitlines() if s.strip()
        ]

        total_time_min = _safe(scraper.total_time)
        prep_time_min = _safe(scraper.prep_time)
        cook_time_min = _safe(scraper.cook_time)

        log.debug(
            "allrecipes adapter: parsed",
            url=url,
            title=title,
            ingredient_count=len(ingredients),
            step_count=len(instructions),
        )

        return {
            "title": title,
            "description": _safe(scraper.description),
            "ingredients": ingredients,
            "instructions": instructions,
            "image_url": _safe(scraper.image),
            "total_time": f"PT{total_time_min}M" if total_time_min else None,
            "prep_time": f"PT{prep_time_min}M" if prep_time_min else None,
            "cook_time": f"PT{cook_time_min}M" if cook_time_min else None,
            "yield_text": _safe(scraper.yields),
            "cuisine": _safe(scraper.cuisine),
        }
    except Exception as exc:
        log.warning("allrecipes adapter failed", url=url, error=str(exc))
        return None
