"""HtmlScrapeAdapter — CSS-selector-based search result scraper.

ADR-002 Section 7.3.

Security conditions enforced:
  S1  — all outbound HTTP via safe_fetch(), never raw httpx.
  S3  — thumbnail_url and result url validated to http(s) scheme only.
  S4  — {q} URL-encoded with urllib.parse.quote_plus before substitution.
  S5  — title and description sanitized with bleach.clean(tags=[], strip=True).
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import quote_plus, urljoin, urlparse

import bleach
import structlog
from selectolax.parser import HTMLParser

from ...models.discovery_site import DiscoverySite
from ...parser.fetcher import FetchError, URLForbiddenError, safe_fetch
from ..schemas import RecipeStub, SourceSite
from .base import SiteAdapter

log = structlog.get_logger()

_VALID_SCHEMES = {"http", "https"}
_TRACKING_PARAMS = re.compile(
    r"(utm_\w+|fbclid|gclid|mc_eid|ref|source|campaign)=[^&]*&?",
    re.IGNORECASE,
)


def _safe_url(raw: str, base: str | None = None) -> str | None:
    """Absolutify (if relative) and validate scheme. Returns None if invalid."""
    if not raw:
        return None
    url = raw.strip()
    if url.startswith("//"):
        url = "https:" + url
    if base and not urlparse(url).netloc:
        url = urljoin(base, url)
    parsed = urlparse(url)
    if parsed.scheme not in _VALID_SCHEMES:
        return None
    if not parsed.netloc:
        return None
    return url


def _sanitize(text: str | None) -> str | None:
    """Strip all HTML tags from a string — security condition S5."""
    if not text:
        return None
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True).strip()
    return cleaned or None


class HtmlScrapeAdapter(SiteAdapter):
    """Adapter that fetches a search URL and parses results via CSS selectors.

    adapter_config_json shape (ADR-002 Section 7.3):
    {
        "search_url_template": "https://www.seriouseats.com/search?q={q}",
        "result_selector": "article.search-result",
        "title_selector": "h2.title a",
        "link_selector": "h2.title a",
        "link_attr": "href",
        "thumbnail_selector": "img.thumbnail",
        "thumbnail_attr": "src",
        "description_selector": "p.summary",
        "url_must_contain": "/recipe"
    }
    """

    kind = "html_scrape"

    async def search(self, query: str, limit: int = 10) -> list[RecipeStub]:
        template = self.config.get("search_url_template", "")
        if not template:
            log.warning(
                "html_scrape: no search_url_template",
                site=self.site.slug,
            )
            return []

        # S4 — URL-encode query with quote_plus (mandatory security condition)
        encoded_q = quote_plus(query)
        search_url = template.replace("{q}", encoded_q)

        # Validate the constructed URL has a safe scheme (S3)
        parsed = urlparse(search_url)
        if parsed.scheme not in _VALID_SCHEMES:
            log.warning(
                "html_scrape: search_url scheme invalid",
                site=self.site.slug,
                url=search_url,
            )
            return []

        # S1 — use safe_fetch, never raw httpx
        try:
            html_bytes = await safe_fetch(search_url)
        except (FetchError, URLForbiddenError) as exc:
            log.warning(
                "html_scrape: fetch failed",
                site=self.site.slug,
                url=search_url,
                error=str(exc),
            )
            return []
        except Exception as exc:
            log.error(
                "html_scrape: unexpected fetch error",
                site=self.site.slug,
                url=search_url,
                error=str(exc),
            )
            return []

        html = html_bytes.decode("utf-8", errors="replace")
        return self._parse(html, search_url, limit)

    def _parse(self, html: str, search_url: str, limit: int) -> list[RecipeStub]:
        result_sel = self.config.get("result_selector", "")
        title_sel = self.config.get("title_selector", "")
        link_sel = self.config.get("link_selector", "")
        link_attr = self.config.get("link_attr", "href")
        thumb_sel = self.config.get("thumbnail_selector", "")
        thumb_attr = self.config.get("thumbnail_attr", "src")
        desc_sel = self.config.get("description_selector", "")
        url_must_contain = self.config.get("url_must_contain", "")

        tree = HTMLParser(html)
        stubs: list[RecipeStub] = []

        if result_sel:
            result_nodes = tree.css(result_sel)
        else:
            # Fallback: look for common recipe URL patterns
            result_nodes = tree.css("a[href]")

        for node in result_nodes:
            if len(stubs) >= limit:
                break

            # Extract link
            if link_sel:
                link_node = node.css_first(link_sel)
            else:
                link_node = node if node.tag == "a" else node.css_first("a")

            if link_node is None:
                continue

            raw_href = link_node.attributes.get(link_attr, "")
            url = _safe_url(raw_href, self.site.home_url)
            if not url:
                continue

            # Apply url_must_contain filter
            if url_must_contain and url_must_contain not in url:
                continue

            # Extract title — S5 sanitize
            if title_sel:
                title_node = node.css_first(title_sel)
                raw_title = title_node.text(strip=True) if title_node else link_node.text(strip=True)
            else:
                raw_title = link_node.text(strip=True)

            title = _sanitize(raw_title)
            if not title:
                continue

            # Extract thumbnail — S3 validate scheme
            thumbnail_url: str | None = None
            if thumb_sel:
                thumb_node = node.css_first(thumb_sel)
                if thumb_node:
                    raw_thumb = thumb_node.attributes.get(thumb_attr, "")
                    if not raw_thumb:
                        # Try data-src for lazy-loaded images
                        raw_thumb = thumb_node.attributes.get("data-src", "")
                    thumbnail_url = _safe_url(raw_thumb, self.site.home_url)

            # Extract description — S5 sanitize
            description: str | None = None
            if desc_sel:
                desc_node = node.css_first(desc_sel)
                if desc_node:
                    description = _sanitize(desc_node.text(strip=True))

            stubs.append(
                RecipeStub(
                    id="stub_" + str(uuid.uuid4()),
                    title=title,
                    url=url,
                    source_site=SourceSite(slug=self.site.slug, name=self.site.name),
                    thumbnail_url=thumbnail_url,
                    description=description,
                    origin="search",
                )
            )

        return stubs
