"""GoogleCseAdapter — Google Custom Search Engine adapter.

ADR-002 Section 7.4.

Security conditions enforced:
  S1  — outbound HTTP via safe_fetch(), never raw httpx.
  S3  — result URLs validated to http(s) scheme only.
  S5  — title and snippet sanitized via bleach.
  S6  — API key read from environment only; never stored in DB;
         adapter_config_json MUST NOT contain the key value.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from urllib.parse import quote_plus, urlparse

import bleach
import structlog

from ...parser.fetcher import FetchError, URLForbiddenError, safe_fetch
from ..schemas import RecipeStub, SourceSite
from .base import SiteAdapter

log = structlog.get_logger()

_VALID_SCHEMES = {"http", "https"}
_SENSITIVE_KEY_RE = re.compile(r"(api_key|secret|token)", re.IGNORECASE)

# Log-once guard: emit the "key missing" warning at most once per process
_warned_missing_key: set[str] = set()


def _sanitize(text: str | None) -> str | None:
    """Strip all HTML tags — security condition S5."""
    if not text:
        return None
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True).strip()
    return cleaned or None


def _safe_url(url: str) -> str | None:
    """Validate URL scheme is http(s) — security condition S3."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in _VALID_SCHEMES or not parsed.netloc:
        return None
    return url.strip()


def validate_config_has_no_key_values(config: dict) -> None:
    """Raise ValueError if config contains actual key/secret values.

    The config must reference env-var names, not the key values themselves.
    Security condition S6.
    """
    for key, value in config.items():
        if _SENSITIVE_KEY_RE.search(key) and key != "api_key_env":
            raise ValueError(
                f"adapter_config_json must not contain key field {key!r}. "
                "Store env-var name in 'api_key_env' instead."
            )
        # Heuristic: if a value looks like a real API key (>= 20 chars, no spaces),
        # reject it regardless of field name.
        if isinstance(value, str) and len(value) >= 20 and " " not in value and key != "cx":
            raise ValueError(
                f"adapter_config_json field {key!r} appears to contain a secret value. "
                "Use 'api_key_env' to reference an environment variable name."
            )


class GoogleCseAdapter(SiteAdapter):
    """Adapter that calls the Google Custom Search JSON API.

    adapter_config_json shape:
    {
        "api_key_env": "FORKIT_GOOGLE_CSE_API_KEY",
        "cx": "abc123:def456",
        "site_restrict": "epicurious.com"   (optional)
    }
    """

    kind = "google_cse"

    _CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    async def search(self, query: str, limit: int = 10) -> list[RecipeStub]:
        api_key_env = self.config.get("api_key_env", "FORKIT_GOOGLE_CSE_API_KEY")
        cx = self.config.get("cx", "")

        if not cx:
            log.warning("google_cse: no cx configured", site=self.site.slug)
            return []

        # S6 — API key from env only, never from DB
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            if api_key_env not in _warned_missing_key:
                log.warning(
                    "google_cse: API key env var not set — adapter inert",
                    site=self.site.slug,
                    env_var=api_key_env,
                )
                _warned_missing_key.add(api_key_env)
            return []

        # S4 — URL-encode the query
        encoded_q = quote_plus(query)
        num = min(limit, 10)  # CSE max is 10 per request

        url = (
            f"{self._CSE_ENDPOINT}"
            f"?q={encoded_q}"
            f"&cx={cx}"
            f"&key={api_key}"
            f"&num={num}"
        )

        site_restrict = self.config.get("site_restrict", "")
        if site_restrict:
            url += f"&siteSearch={quote_plus(site_restrict)}"

        # S1 — use safe_fetch
        try:
            body = await safe_fetch(url)
        except (FetchError, URLForbiddenError) as exc:
            log.warning(
                "google_cse: fetch failed",
                site=self.site.slug,
                error=str(exc),
            )
            return []
        except Exception as exc:
            log.error(
                "google_cse: unexpected fetch error",
                site=self.site.slug,
                error=str(exc),
            )
            return []

        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            log.warning("google_cse: invalid JSON response", site=self.site.slug, error=str(exc))
            return []

        items = data.get("items") or []
        stubs: list[RecipeStub] = []

        for item in items:
            raw_url = item.get("link", "")
            url_clean = _safe_url(raw_url)  # S3
            if not url_clean:
                continue

            # S5 — sanitize title and description
            title = _sanitize(item.get("title", ""))
            if not title:
                continue
            description = _sanitize(item.get("snippet", ""))

            # Thumbnail from pagemap
            thumbnail_url: str | None = None
            pagemap = item.get("pagemap") or {}
            cse_thumbs = pagemap.get("cse_thumbnail") or []
            if cse_thumbs:
                raw_thumb = cse_thumbs[0].get("src", "")
                thumbnail_url = _safe_url(raw_thumb)

            stubs.append(
                RecipeStub(
                    id="stub_" + str(uuid.uuid4()),
                    title=title,
                    url=url_clean,
                    source_site=SourceSite(slug=self.site.slug, name=self.site.name),
                    thumbnail_url=thumbnail_url,
                    description=description,
                    origin="search",
                )
            )

        return stubs
