"""Per-site adapter for seriouseats.com.

Serious Eats uses a custom CMS but recipe-scrapers has dedicated support for
it.  We delegate entirely to `scrape_html()` for robustness.
"""

from __future__ import annotations

from typing import Any

import structlog

from . import register

log = structlog.get_logger()


@register(hosts=["seriouseats.com", "www.seriouseats.com"])
def parse(html: str, url: str) -> dict[str, Any] | None:
    """Parse a Serious Eats recipe page into a raw recipe dict."""
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
            log.debug("seriouseats adapter: no title found", url=url)
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
            "seriouseats adapter: parsed",
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
        log.warning("seriouseats adapter failed", url=url, error=str(exc))
        return None
