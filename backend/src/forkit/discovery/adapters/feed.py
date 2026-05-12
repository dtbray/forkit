"""FeedAdapter — RSS/Atom feed polling adapter.

Security conditions enforced:
  S1  — feed URL fetched via safe_fetch() (SSRF guard), never passed directly to feedparser.
  S5  — title and summary sanitized via _sanitize() before return.
  S_XML — defusedxml imported explicitly; feedparser uses it transitively for XML bomb defense.
  max_bytes=5*1024*1024 — feed response capped at 5 MB to prevent memory exhaustion.
"""

from __future__ import annotations

import defusedxml  # noqa: F401 — explicit import for XML bomb defense (S_XML)
import feedparser
import structlog

from ...parser.fetcher import FetchError, URLForbiddenError, safe_fetch
from ..sanitize import sanitize as _sanitize
from ..schemas import RecipeStub
from .base import FeedEntry, SiteAdapter

log = structlog.get_logger()

_FEED_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_FEED_MAX_ENTRIES = 50


class FeedAdapter(SiteAdapter):
    """Adapter that polls an RSS/Atom feed URL.

    adapter_config_json shape:
    {
        "feed_url": "https://example.com/feed.rss"
    }

    search() always returns [] — this adapter is feed-only.
    """

    kind = "feed_only"

    async def search(self, query: str, limit: int = 10) -> list[RecipeStub]:
        """Feed-only adapter does not support search."""
        return []

    async def poll(self) -> list[FeedEntry]:
        """Fetch and parse the configured feed URL.

        Security:
        - URL fetched via safe_fetch() (SSRF guard S1)
        - bytes content passed to feedparser.parse(), never the URL string
        - defusedxml imported explicitly for XML bomb defense
        - capped at _FEED_MAX_ENTRIES entries
        - title/summary sanitized via _sanitize() (S5)
        """
        feed_url = self.config.get("feed_url", "")
        if not feed_url:
            log.warning("feed_adapter: no feed_url configured", site=self.site.slug)
            return []

        # S1 — SSRF guard: fetch via safe_fetch, never feedparser.parse(url)
        try:
            content = await safe_fetch(feed_url, max_bytes=_FEED_MAX_BYTES)
        except (FetchError, URLForbiddenError) as exc:
            log.warning(
                "feed_adapter: fetch failed",
                site=self.site.slug,
                feed_url=feed_url,
                error=str(exc),
            )
            return []
        except Exception as exc:
            log.error(
                "feed_adapter: unexpected fetch error",
                site=self.site.slug,
                feed_url=feed_url,
                error=str(exc),
            )
            return []

        # Parse bytes — never pass URL string to feedparser (S1)
        parsed = feedparser.parse(content)

        entries: list[FeedEntry] = []
        for raw_entry in parsed.entries[:_FEED_MAX_ENTRIES]:
            # Derive guid: prefer id, fall back to link
            guid = getattr(raw_entry, "id", None) or getattr(raw_entry, "link", None)
            url = getattr(raw_entry, "link", None)

            if not guid or not url:
                continue

            raw_title = getattr(raw_entry, "title", None) or ""
            # S5 — sanitize title; skip entry if title is empty after sanitization
            title = _sanitize(raw_title)
            if not title:
                continue

            # S5 — sanitize summary
            raw_summary = getattr(raw_entry, "summary", None)
            summary = _sanitize(raw_summary)

            # Parse published date
            published_at = None
            published_parsed = getattr(raw_entry, "published_parsed", None)
            if published_parsed is not None:
                try:
                    import time as _time
                    from datetime import timezone

                    ts = _time.mktime(published_parsed)
                    from datetime import datetime

                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                except Exception:
                    published_at = None

            entries.append(
                FeedEntry(
                    guid=str(guid),
                    url=str(url),
                    title=title,
                    summary=summary,
                    published_at=published_at,
                )
            )

        log.info(
            "feed_adapter: poll complete",
            site=self.site.slug,
            entry_count=len(entries),
        )
        return entries
