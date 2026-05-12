"""Adapter registry — maps adapter_kind to SiteAdapter class.

ADR-002 Section 7.2 / ADR-003 (dataset adapter).

The `dataset` adapter_kind is special: it is NOT site-bound (no per-row
DiscoverySite). It is a singleton over the local FTS5 corpus. The registry
exposes `get_dataset_adapter()` for callers that want the singleton, and
`ALLOWED_ADAPTER_KINDS` for API write-side allowlists.
"""

from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from ..models.discovery_site import DiscoverySite
from .adapters.base import SiteAdapter
from .adapters.feed import FeedAdapter
from .adapters.google_cse import GoogleCseAdapter
from .adapters.html_scrape import HtmlScrapeAdapter

# Site-bound adapters (instantiated per DiscoverySite row).
ADAPTERS: dict[str, type[SiteAdapter]] = {
    "html_scrape": HtmlScrapeAdapter,
    "google_cse": GoogleCseAdapter,
    "feed_only": FeedAdapter,
}

# All adapter_kind values that the API will accept on POST /discovery/sites.
# `dataset` is included here so the create_site endpoint accepts it, but its
# implementation is the singleton DatasetAdapter rather than a SiteAdapter.
ALLOWED_ADAPTER_KINDS: tuple[str, ...] = (
    "html_scrape",
    "google_cse",
    "feed_only",
    "dataset",
)


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


_dataset_adapter_singleton = None


def get_dataset_adapter():
    """Return the singleton DatasetAdapter over the local FTS5 corpus.

    Imported lazily so the dataset module is not loaded at import time of
    every site-bound adapter.
    """
    global _dataset_adapter_singleton
    if _dataset_adapter_singleton is None:
        from ..dataset.adapter import DatasetAdapter

        settings = get_settings()
        db_path = Path(settings.forkit_cache_dir) / "forkit_dataset.db"
        _dataset_adapter_singleton = DatasetAdapter(db_path)
    return _dataset_adapter_singleton
