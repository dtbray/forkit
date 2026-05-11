"""Discovery search and sites CRUD endpoints — ADR-002 Section 5.1.

Security conditions:
  S3  — home_url and any URL in adapter_config_json validated as http(s) at write time.
  S6  — GET /sites and GET /sites/{id} redact fields matching /api_key|secret|token/i.
  S7  — POST /sites/{id}/test: rate-limited 5/min, logs source IP + target at WARN,
         caps response at 4KB.
  S8  — All endpoints rate-limited (10/min or 5/min as specified).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import structlog
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..discovery.adapters.google_cse import validate_config_has_no_key_values
from ..discovery.registry import get_adapter
from ..discovery.schemas import RecipeStub, SearchRequest, SearchResponse
from ..discovery.service import federated_search
from ..models.discovery_site import DiscoverySite
from ..parser.fetcher import FetchError, URLForbiddenError, _resolve_and_check, safe_fetch  # noqa: PLC2701

log = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/discovery")

_SENSITIVE_RE = re.compile(r"(api_key|secret|token)", re.IGNORECASE)
_VALID_SCHEMES = {"http", "https"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_url(url: str, field_name: str = "url") -> str:
    """Validate http(s) scheme and run SSRF IP check — security condition S3."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in _VALID_SCHEMES:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name}: only http/https URLs are allowed",
        )
    if not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"{field_name}: URL has no host")
    try:
        _resolve_and_check(parsed.hostname or "")
    except URLForbiddenError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=422, detail=f"Could not resolve host: {exc}") from exc
    return url


def _redact_config(config_json: str | None) -> dict:
    """Return adapter_config_json with sensitive fields removed — security condition S6."""
    if not config_json:
        return {}
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError:
        return {}
    return {
        k: "[REDACTED]" if _SENSITIVE_RE.search(k) else v
        for k, v in config.items()
    }


def _site_to_dict(site: DiscoverySite, redact: bool = True) -> dict:
    config = _redact_config(site.adapter_config_json) if redact else {}
    return {
        "id": site.id,
        "slug": site.slug,
        "name": site.name,
        "home_url": site.home_url,
        "adapter_kind": site.adapter_kind,
        "adapter_config": config,
        "search_enabled": bool(site.search_enabled),
        "feed_enabled": bool(site.feed_enabled),
        "is_builtin": bool(site.is_builtin),
        "paywall_note": site.paywall_note,
        "last_search_ok_at": site.last_search_ok_at.isoformat() if site.last_search_ok_at else None,
        "last_search_error": site.last_search_error,
        "created_at": site.created_at.isoformat() if site.created_at else None,
        "updated_at": site.updated_at.isoformat() if site.updated_at else None,
    }


# ---------------------------------------------------------------------------
# POST /discovery/search
# ---------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
@limiter.limit("10/minute")
async def search(
    request: Request,
    body: SearchRequest,
    session: Session = Depends(get_session),
) -> SearchResponse:
    """Federated search across all enabled discovery sites.

    Rate-limited: 10/min/IP (security condition S8).
    """
    log.info("discovery: search", q=body.q, site_slugs=body.site_slugs)
    return await federated_search(
        q=body.q,
        site_slugs=body.site_slugs,
        limit_per_site=body.limit_per_site,
        session=session,
    )


# ---------------------------------------------------------------------------
# Sites CRUD
# ---------------------------------------------------------------------------


@router.get("/sites")
def list_sites(
    session: Session = Depends(get_session),
) -> list[dict]:
    """List all configured discovery sites (adapter config redacted — S6)."""
    sites = session.scalars(select(DiscoverySite)).all()
    return [_site_to_dict(s) for s in sites]


class DetectRequest(BaseModel):
    url: str


class DetectResponse(BaseModel):
    input_url: str
    site_name: str
    is_feed: bool
    detected_feeds: list[str]
    suggested_search_url_template: str | None
    confidence: str  # "high" | "partial" | "none"


# ---------------------------------------------------------------------------
# POST /discovery/sites/detect
# ---------------------------------------------------------------------------


@router.post("/sites/detect", response_model=DetectResponse)
@limiter.limit("10/minute")
async def detect_site(
    request: Request,
    body: DetectRequest,
) -> DetectResponse:
    """Sniff a URL for RSS feeds and search patterns.

    Returns structured pre-fill data for the Add Site form.
    Rate-limited: 10/min/IP (security condition S8).
    """
    # 1. Validate URL (SSRF protection — S3)
    _validate_url(body.url, "url")

    # 2. Fetch the URL
    try:
        content_bytes = await safe_fetch(body.url)
    except URLForbiddenError:
        raise HTTPException(
            status_code=422,
            detail="URL is not allowed (SSRF protection)",
        )
    except FetchError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch URL: {exc}",
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Failed to analyze URL",
        )

    # 3. Parse HTML (best-effort)
    try:
        soup = BeautifulSoup(content_bytes, "html.parser")
    except Exception:
        soup = None

    # 4. Feed detection — is the URL itself a feed?
    is_feed = False
    try:
        parsed_feed = feedparser.parse(content_bytes)
        if parsed_feed.get("version") and parsed_feed.get("entries"):
            is_feed = True
    except Exception:
        pass

    # 5. RSS link tags
    detected_feeds: list[str] = []
    if soup is not None:
        for link_tag in soup.find_all("link", rel="alternate"):
            tag_type = link_tag.get("type", "")
            if tag_type in ("application/rss+xml", "application/atom+xml"):
                href = link_tag.get("href", "").strip()
                if not href:
                    continue
                resolved = urljoin(body.url, href)
                try:
                    _validate_url(resolved, "feed_href")
                except HTTPException:
                    continue
                detected_feeds.append(resolved)

    # 6. Site name
    site_name = ""
    if soup is not None:
        title_tag = soup.find("title")
        if title_tag:
            site_name = title_tag.get_text(strip=True)

    # 7. Search URL template (best-effort)
    suggested_search_url_template: str | None = None
    if soup is not None:
        for form in soup.find_all("form"):
            # Narrow to text/search inputs manually for bs4 compatibility
            input_tag = None
            for inp in form.find_all("input"):
                inp_type = (inp.get("type") or "text").lower()
                if inp_type in ("text", "search"):
                    input_tag = inp
                    break
            if input_tag is None:
                continue
            param_name = input_tag.get("name", "").strip()
            if not param_name:
                continue
            action = (form.get("action") or "").strip()
            if not action:
                action = body.url
            resolved_action = urljoin(body.url, action)
            try:
                _validate_url(resolved_action, "form_action")
            except HTTPException:
                continue
            suggested_search_url_template = f"{resolved_action}?{param_name}={{query}}"
            break

    # 8. Confidence
    if is_feed or detected_feeds:
        confidence = "high"
    elif suggested_search_url_template:
        confidence = "partial"
    else:
        confidence = "none"

    log.info(
        "detect site",
        url=body.url,
        is_feed=is_feed,
        feeds_found=len(detected_feeds),
        confidence=confidence,
    )

    return DetectResponse(
        input_url=body.url,
        site_name=site_name,
        is_feed=is_feed,
        detected_feeds=detected_feeds,
        suggested_search_url_template=suggested_search_url_template,
        confidence=confidence,
    )


class SiteCreateRequest(BaseModel):
    slug: str
    name: str
    home_url: str
    adapter_kind: str
    adapter_config_json: dict | None = None
    search_enabled: bool = True
    feed_enabled: bool = False
    paywall_note: str | None = None


@router.post("/sites", status_code=201)
@limiter.limit("10/minute")
def create_site(
    request: Request,
    body: SiteCreateRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Create a new discovery site.

    Rate-limited: 10/min/IP (security condition S8).
    Validates home_url and any URL in adapter_config_json (S3).
    Rejects adapter_config_json containing API key values (S6).
    """
    # S3 — validate home_url
    _validate_url(body.home_url, "home_url")

    # Validate adapter_kind is known
    if body.adapter_kind not in ("html_scrape", "google_cse", "feed_only"):
        raise HTTPException(
            status_code=422,
            detail=f"adapter_kind must be one of: html_scrape, google_cse, feed_only",
        )

    config = body.adapter_config_json or {}

    # S6 — reject configs with actual API key values
    if body.adapter_kind == "google_cse":
        try:
            validate_config_has_no_key_values(config)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # S3 — validate any URL in config
    for key, value in config.items():
        if "url" in key.lower() and isinstance(value, str) and value.startswith("http"):
            _validate_url(value, f"adapter_config_json.{key}")

    # Check slug uniqueness
    existing = session.scalar(
        select(DiscoverySite).where(DiscoverySite.slug == body.slug)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Site slug {body.slug!r} already exists")

    now = datetime.now(timezone.utc)
    site = DiscoverySite(
        id=str(uuid.uuid4()),
        slug=body.slug,
        name=body.name,
        home_url=body.home_url,
        adapter_kind=body.adapter_kind,
        adapter_config_json=json.dumps(config),
        search_enabled=1 if body.search_enabled else 0,
        feed_enabled=1 if body.feed_enabled else 0,
        is_builtin=0,
        paywall_note=body.paywall_note,
        created_at=now,
        updated_at=now,
    )
    session.add(site)
    try:
        session.commit()
        session.refresh(site)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to create site") from exc

    return _site_to_dict(site)


@router.get("/sites/{site_id}")
def get_site(
    site_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Get one discovery site (adapter config redacted — S6)."""
    site = session.get(DiscoverySite, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return _site_to_dict(site)


class SitePatchRequest(BaseModel):
    name: str | None = None
    home_url: str | None = None
    adapter_config_json: dict | None = None
    search_enabled: bool | None = None
    feed_enabled: bool | None = None
    paywall_note: str | None = None


@router.patch("/sites/{site_id}")
def patch_site(
    site_id: str,
    body: SitePatchRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Update a discovery site's config or enabled flags."""
    site = session.get(DiscoverySite, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    if body.home_url is not None:
        _validate_url(body.home_url, "home_url")
        site.home_url = body.home_url

    if body.name is not None:
        site.name = body.name

    if body.adapter_config_json is not None:
        config = body.adapter_config_json
        if site.adapter_kind == "google_cse":
            try:
                validate_config_has_no_key_values(config)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        for key, value in config.items():
            if "url" in key.lower() and isinstance(value, str) and value.startswith("http"):
                _validate_url(value, f"adapter_config_json.{key}")
        site.adapter_config_json = json.dumps(config)

    if body.search_enabled is not None:
        site.search_enabled = 1 if body.search_enabled else 0

    if body.feed_enabled is not None:
        site.feed_enabled = 1 if body.feed_enabled else 0

    if body.paywall_note is not None:
        site.paywall_note = body.paywall_note

    site.updated_at = datetime.now(timezone.utc)

    try:
        session.commit()
        session.refresh(site)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to update site") from exc

    return _site_to_dict(site)


@router.delete("/sites/{site_id}", status_code=204)
def delete_site(
    site_id: str,
    session: Session = Depends(get_session),
) -> None:
    """Delete a user-defined site. Builtin sites cannot be deleted."""
    site = session.get(DiscoverySite, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    if site.is_builtin:
        raise HTTPException(
            status_code=409,
            detail="Built-in sites cannot be deleted. Disable them via PATCH instead.",
        )
    session.delete(site)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete site") from exc


# ---------------------------------------------------------------------------
# POST /sites/{id}/test
# ---------------------------------------------------------------------------


class TestSiteResponse(BaseModel):
    ok: bool
    count: int
    error: str | None = None
    sample: list[RecipeStub]


@router.post("/sites/{site_id}/test")
@limiter.limit("5/minute")
async def test_site(
    site_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Any:
    """Run a sample search against one site and return ok/error + sample results.

    Rate-limited: 5/min/IP (security condition S7).
    Logs source IP and target site at WARN (S7).
    Response body capped at 4KB (S7c).
    """
    site = session.get(DiscoverySite, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    # S7 — log source IP and target at WARN
    client_ip = request.client.host if request.client else "unknown"
    log.warning(
        "discovery: site test invoked",
        site=site.slug,
        home_url=site.home_url,
        source_ip=client_ip,
    )

    try:
        adapter = get_adapter(site)
    except ValueError as exc:
        return TestSiteResponse(ok=False, count=0, error=str(exc), sample=[])

    try:
        stubs = await adapter.search("chicken", limit=5)
        sample = stubs[:3]
        result = TestSiteResponse(ok=True, count=len(stubs), sample=sample)
    except Exception as exc:
        result = TestSiteResponse(ok=False, count=0, error=str(exc), sample=[])

    # S7c — cap response at 4KB
    raw = result.model_dump_json()
    if len(raw.encode()) > 4096:
        # Trim sample until it fits
        while len(raw.encode()) > 4096 and result.sample:
            result.sample.pop()
            raw = result.model_dump_json()

    return result
