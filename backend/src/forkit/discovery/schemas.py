"""Pydantic v2 schemas for Phase 1 discovery (federated search).

ADR-002 Section 4.

SECURITY NOTE (S10): Frontend must NOT render `description` as raw HTML.
Do NOT use {@html description} in any SvelteKit component — always render
description as plain text (e.g. inside a <p> or text node).  The field is
already server-side sanitized via bleach, but HTML injection via the
template engine would bypass that protection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceSite(BaseModel):
    slug: str
    name: str


class RecipeStub(BaseModel):
    """Unified result shape for both Phase 1 (search) and Phase 2 (feed) discovery.

    - `id` is transient for search results (generated per response, not stored).
    - `id` equals feed_item.id for feed-origin stubs.
    - `description` is sanitized server-side via bleach; do NOT render as HTML.
    """

    id: str
    title: str
    url: str
    source_site: SourceSite
    thumbnail_url: str | None = None
    description: str | None = None
    published_at: str | None = None
    already_in_collection: bool = False
    origin: Literal["search", "feed"] = "search"
    feed_item_id: str | None = None


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)
    site_slugs: list[str] | None = None
    limit_per_site: int = Field(default=10, ge=1, le=50)


class SiteSearchResult(BaseModel):
    slug: str
    count: int
    status: Literal["ok", "error", "timeout"]
    ms: int
    error: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[RecipeStub]
    site_results: list[SiteSearchResult]
    cached: bool
