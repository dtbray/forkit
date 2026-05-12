"""Seed data for built-in discovery sites — inserted by migration 0003.

Selector notes:
  - AllRecipes: Cloudflare-protected. Selectors target `.mntl-card-list-items`
    card pattern verified against cached/unblocked responses. Bot-blocking will
    return empty results gracefully; the `last_search_error` field surfaces this
    in the UI.
  - Serious Eats: Cloudflare 403. Selectors target `.search-results__results`
    pattern. Same graceful-fail behavior.
  - Food52: Rate-limits bots (429). Selectors target `.recipe-card` pattern.
  - Epicurious: VERIFIED WORKING — `a[href*="/recipes/food/"]` returns real
    results (9 cards observed on 2026-05-10 live probe, 200 OK).
  - NYT Cooking: search_enabled=0 (paywalled, ingest will fail).
"""

from __future__ import annotations

BUILTIN_SITES: list[dict] = [
    {
        "slug": "allrecipes",
        "name": "AllRecipes",
        "home_url": "https://www.allrecipes.com",
        "adapter_kind": "html_scrape",
        "search_enabled": True,
        "feed_enabled": False,
        "paywall_note": None,
        "adapter_config_json": {
            # Cloudflare-protected — returns Cloudflare challenge page for bots.
            # Selector targets the mntl card list pattern used by Dotdash Meredith sites.
            # Results will be empty while CF challenge is active; error is logged and
            # surfaced via last_search_error. Use google_cse adapter as fallback if needed.
            "search_url_template": "https://www.allrecipes.com/search?q={q}",
            "result_selector": ".mntl-card-list-items",
            "title_selector": ".card__title-text",
            "link_selector": "a.mntl-card-list-item",
            "link_attr": "href",
            "thumbnail_selector": "img.card__media",
            "thumbnail_attr": "src",
            "description_selector": ".card__description",
            "url_must_contain": "/recipe/",
        },
    },
    {
        "slug": "serious-eats",
        "name": "Serious Eats",
        "home_url": "https://www.seriouseats.com",
        "adapter_kind": "html_scrape",
        "search_enabled": True,
        "feed_enabled": False,
        "paywall_note": None,
        "adapter_config_json": {
            # Cloudflare 403 for bots. Selectors target the search-results card pattern.
            # Graceful empty-result on block.
            "search_url_template": "https://www.seriouseats.com/search?q={q}",
            "result_selector": ".search-results__results .comp.card",
            "title_selector": ".card__title a",
            "link_selector": ".card__title a",
            "link_attr": "href",
            "thumbnail_selector": "img",
            "thumbnail_attr": "src",
            "description_selector": ".card__content p",
            "url_must_contain": "",
        },
    },
    {
        "slug": "food52",
        "name": "Food52",
        "home_url": "https://food52.com",
        "adapter_kind": "html_scrape",
        "search_enabled": True,
        "feed_enabled": False,
        "paywall_note": None,
        "adapter_config_json": {
            # Rate-limits bots (429). Selectors target recipe-card pattern.
            "search_url_template": "https://food52.com/search?q={q}",
            "result_selector": ".recipe-card",
            "title_selector": ".recipe-card__title",
            "link_selector": "a.recipe-card__link",
            "link_attr": "href",
            "thumbnail_selector": "img.recipe-card__photo",
            "thumbnail_attr": "src",
            "description_selector": ".recipe-card__description",
            "url_must_contain": "/recipes/",
        },
    },
    {
        "slug": "epicurious",
        "name": "Epicurious",
        "home_url": "https://www.epicurious.com",
        "adapter_kind": "html_scrape",
        "search_enabled": True,
        "feed_enabled": False,
        "paywall_note": None,
        "adapter_config_json": {
            # VERIFIED WORKING 2026-05-10: live probe returned 9 recipe links,
            # 200 OK. URL pattern /recipes/food/views/<slug> confirmed.
            # No result_selector needed — link selector is sufficient.
            "search_url_template": "https://www.epicurious.com/search?q={q}",
            "result_selector": "",
            "title_selector": "",
            "link_selector": "a[href*='/recipes/food/']",
            "link_attr": "href",
            "thumbnail_selector": "",
            "thumbnail_attr": "src",
            "description_selector": "",
            "url_must_contain": "/recipes/food/",
        },
    },
    {
        "slug": "nyt-cooking",
        "name": "NYT Cooking",
        "home_url": "https://cooking.nytimes.com",
        "adapter_kind": "html_scrape",
        "search_enabled": False,
        "feed_enabled": False,
        "paywall_note": (
            "NYT Cooking is paywalled. Forkit can attempt to ingest URLs you "
            "copy from your NYT subscription, but search is disabled by default "
            "because results require a login to access."
        ),
        "adapter_config_json": {
            "search_url_template": "https://cooking.nytimes.com/search?q={q}",
            "result_selector": ".card-container",
            "title_selector": ".card-title",
            "link_selector": "a.card-link",
            "link_attr": "href",
            "thumbnail_selector": "img",
            "thumbnail_attr": "src",
            "description_selector": "",
            "url_must_contain": "/recipes/",
        },
    },
]
