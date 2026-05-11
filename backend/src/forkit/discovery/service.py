"""Federated search orchestration — ADR-002 Section 5.1.

Security conditions enforced:
  S9  — query_norm = q.strip().lower()[:200]
  S10 — description is NOT rendered as HTML by callers; see schemas.py comment.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import bleach
import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.discovery_site import DiscoverySite
from ..models.recipe import Recipe
from ..models.search_cache import SearchCache
from .adapters.base import SiteAdapter
from .registry import get_adapter
from .schemas import RecipeStub, SearchResponse, SiteSearchResult

log = structlog.get_logger()

# Tracking/UTM params to strip from URLs during dedupe
_STRIP_PARAMS = re.compile(
    r"[?&](utm_\w+|fbclid|gclid|mc_eid|ref|source|campaign)=[^&]*",
    re.IGNORECASE,
)


def _canonicalize_url(url: str) -> str:
    """Lowercase host, strip tracking params — used for cross-site dedupe."""
    parsed = urlparse(url)
    normalized = parsed._replace(netloc=parsed.netloc.lower(), scheme=parsed.scheme.lower())
    canonical = normalized.geturl()
    # Strip tracking params
    canonical = re.sub(r"[?&](utm_\w+|fbclid|gclid|mc_eid)=[^&]*", "", canonical)
    # Clean up trailing ? or &
    canonical = re.sub(r"[?&]$", "", canonical)
    return canonical


def _sanitize(text: str | None) -> str | None:
    """Strip all HTML — security condition S5."""
    if not text:
        return None
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True).strip()
    return cleaned or None


async def _search_one(
    site: DiscoverySite,
    adapter: SiteAdapter,
    query: str,
    limit: int,
    timeout_sec: int,
) -> tuple[DiscoverySite, list[RecipeStub], str | None, int]:
    """Run a single-site search with timeout. Returns (site, stubs, error, elapsed_ms)."""
    start = time.monotonic()
    error: str | None = None
    stubs: list[RecipeStub] = []

    try:
        stubs = await asyncio.wait_for(
            adapter.search(query, limit),
            timeout=float(timeout_sec),
        )
    except asyncio.TimeoutError:
        error = "timeout"
        log.warning("discovery: search timeout", site=site.slug, timeout_sec=timeout_sec)
    except Exception as exc:
        error = str(exc)
        log.warning("discovery: search error", site=site.slug, error=error)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return site, stubs, error, elapsed_ms


async def federated_search(
    q: str,
    site_slugs: list[str] | None,
    limit_per_site: int,
    session: Session,
) -> SearchResponse:
    """Fan out search to all enabled sites and return a unified SearchResponse.

    Security condition S9: query_norm = q.strip().lower()[:200]
    """
    settings = get_settings()
    timeout_sec = settings.forkit_discovery_search_timeout_sec
    cache_ttl_min = settings.forkit_discovery_cache_ttl_min

    # S9 — normalize the query
    query_norm = q.strip().lower()[:200]

    # -------------------------------------------------------------------------
    # Load enabled sites
    # -------------------------------------------------------------------------
    stmt = select(DiscoverySite).where(DiscoverySite.search_enabled == 1)
    if site_slugs:
        stmt = stmt.where(DiscoverySite.slug.in_(site_slugs))

    sites: list[DiscoverySite] = list(session.scalars(stmt).all())

    if not sites:
        return SearchResponse(
            query=q,
            results=[],
            site_results=[],
            cached=False,
        )

    # -------------------------------------------------------------------------
    # Check cache for each site; separate cached vs uncached
    # -------------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    site_by_id: dict[str, DiscoverySite] = {s.id: s for s in sites}
    cached_results: dict[str, list[RecipeStub]] = {}
    uncached_sites: list[DiscoverySite] = []

    for site in sites:
        cache_row = session.scalar(
            select(SearchCache).where(
                SearchCache.site_id == site.id,
                SearchCache.query_norm == query_norm,
                SearchCache.expires_at > now,
            )
        )
        if cache_row is not None:
            try:
                stubs_data = json.loads(cache_row.results_json)
                stubs = [RecipeStub(**s) for s in stubs_data]
                cached_results[site.id] = stubs
            except Exception as exc:
                log.warning("discovery: cache parse error", site=site.slug, error=str(exc))
                uncached_sites.append(site)
        else:
            uncached_sites.append(site)

    # -------------------------------------------------------------------------
    # Fan out to uncached sites concurrently
    # -------------------------------------------------------------------------
    live_results: dict[str, list[RecipeStub]] = {}
    site_result_map: dict[str, SiteSearchResult] = {}

    # Build tasks
    tasks = []
    for site in uncached_sites:
        try:
            adapter = get_adapter(site)
        except ValueError as exc:
            log.warning("discovery: no adapter", site=site.slug, error=str(exc))
            site_result_map[site.id] = SiteSearchResult(
                slug=site.slug,
                count=0,
                status="error",
                ms=0,
                error=str(exc),
            )
            continue
        tasks.append((site, adapter))

    if tasks:
        coros = [
            _search_one(site, adapter, query_norm, limit_per_site, timeout_sec)
            for site, adapter in tasks
        ]
        task_results = await asyncio.gather(*coros, return_exceptions=True)

        for task_site_adapter, result in zip(tasks, task_results):
            site = task_site_adapter[0]
            if isinstance(result, Exception):
                site_result_map[site.id] = SiteSearchResult(
                    slug=site.slug, count=0, status="error", ms=0, error=str(result)
                )
                continue

            _, stubs, error, elapsed_ms = result

            # Update site health in DB
            if error:
                status: str = "timeout" if error == "timeout" else "error"
                try:
                    site.last_search_error = error
                    session.add(site)
                except Exception:
                    pass
            else:
                status = "ok"
                try:
                    site.last_search_ok_at = now
                    site.last_search_error = None
                    session.add(site)
                except Exception:
                    pass

            live_results[site.id] = stubs
            site_result_map[site.id] = SiteSearchResult(
                slug=site.slug,
                count=len(stubs),
                status=status,  # type: ignore[arg-type]
                ms=elapsed_ms,
                error=error,
            )

    # Add cached site results to site_result_map
    for site in sites:
        if site.id in cached_results:
            stubs = cached_results[site.id]
            site_result_map[site.id] = SiteSearchResult(
                slug=site.slug,
                count=len(stubs),
                status="ok",
                ms=0,
            )

    # -------------------------------------------------------------------------
    # Write live results to cache
    # -------------------------------------------------------------------------
    expires_at = now + timedelta(minutes=cache_ttl_min)
    for site_id, stubs in live_results.items():
        try:
            existing = session.scalar(
                select(SearchCache).where(
                    SearchCache.site_id == site_id,
                    SearchCache.query_norm == query_norm,
                )
            )
            if existing is not None:
                existing.results_json = json.dumps([s.model_dump() for s in stubs])
                existing.created_at = now
                existing.expires_at = expires_at
                session.add(existing)
            else:
                cache_row = SearchCache(
                    id=str(uuid.uuid4()),
                    site_id=site_id,
                    query_norm=query_norm,
                    results_json=json.dumps([s.model_dump() for s in stubs]),
                    created_at=now,
                    expires_at=expires_at,
                )
                session.add(cache_row)
        except Exception as exc:
            log.warning("discovery: cache write error", site_id=site_id, error=str(exc))

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.warning("discovery: db commit error", error=str(exc))

    # -------------------------------------------------------------------------
    # Merge all results (cached + live), dedupe by canonical URL
    # -------------------------------------------------------------------------
    all_site_stubs: dict[str, list[RecipeStub]] = {**cached_results, **live_results}

    # Round-robin interleave across sites
    site_queues: list[list[RecipeStub]] = [
        stubs for stubs in all_site_stubs.values() if stubs
    ]
    merged: list[RecipeStub] = []
    seen_urls: set[str] = set()

    max_len = max((len(q_) for q_ in site_queues), default=0)
    for i in range(max_len):
        for queue in site_queues:
            if i < len(queue):
                stub = queue[i]
                canonical = _canonicalize_url(stub.url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    # S5 — re-sanitize description before returning
                    stub.description = _sanitize(stub.description)
                    merged.append(stub)

    # -------------------------------------------------------------------------
    # Batch check already_in_collection
    # -------------------------------------------------------------------------
    if merged:
        urls_to_check = [s.url for s in merged]
        existing_urls: set[str] = set(
            session.scalars(
                select(Recipe.source_url).where(Recipe.source_url.in_(urls_to_check))
            ).all()
        )
        for stub in merged:
            stub.already_in_collection = stub.url in existing_urls

    any_cached = bool(cached_results) and not live_results

    return SearchResponse(
        query=q,
        results=merged,
        site_results=list(site_result_map.values()),
        cached=any_cached,
    )
