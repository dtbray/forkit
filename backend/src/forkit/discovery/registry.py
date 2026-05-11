"""Adapter registry — maps adapter_kind to SiteAdapter class.

ADR-002 Section 7.2.
"""

from __future__ import annotations

from ..models.discovery_site import DiscoverySite
from .adapters.base import SiteAdapter
from .adapters.google_cse import GoogleCseAdapter
from .adapters.html_scrape import HtmlScrapeAdapter

ADAPTERS: dict[str, type[SiteAdapter]] = {
    "html_scrape": HtmlScrapeAdapter,
    "google_cse": GoogleCseAdapter,
}


def get_adapter(site: DiscoverySite) -> SiteAdapter:
    """Return an instantiated SiteAdapter for the given site.

    Raises ValueError if site.adapter_kind is not registered.
    """
    cls = ADAPTERS.get(site.adapter_kind)
    if cls is None:
        raise ValueError(
            f"Unknown adapter kind {site.adapter_kind!r} for site {site.slug!r}. "
            f"Registered kinds: {list(ADAPTERS)}"
        )
    return cls(site)
