"""Feed inbox API — Phase 2 Feed Subscriber.

Endpoints:
  GET  /api/feed/inbox          — returns unpromoted, undismissed feed items
  POST /api/feed/promote        — ingest a feed item URL into the recipe vault
  POST /api/feed/dismiss        — dismiss a feed item from the inbox

Security:
  - Rate limits: promote 10/min, dismiss 30/min
  - promote calls ingest_url() directly (no HTTP self-call)
  - Input validated at boundary (Pydantic)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models.discovery_site import DiscoverySite
from ..models.feed_item import FeedItem
from ..services.ingest import ingest_url

log = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class FeedItemOut(BaseModel):
    id: str
    site_id: str
    site_name: str
    entry_guid: str
    url: str
    title: str
    summary: str | None
    published_at: datetime | None
    ingested: bool
    dismissed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InboxResponse(BaseModel):
    items: list[FeedItemOut]
    page: int
    limit: int
    total: int
    pages: int


class PromoteRequest(BaseModel):
    feed_item_id: str

    @field_validator("feed_item_id")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("feed_item_id must not be empty")
        return v


class PromoteResponse(BaseModel):
    feed_item_id: str
    recipe_id: str
    already_existed: bool


class DismissRequest(BaseModel):
    feed_item_id: str

    @field_validator("feed_item_id")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("feed_item_id must not be empty")
        return v


class DismissResponse(BaseModel):
    feed_item_id: str
    dismissed: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/feed/inbox", response_model=InboxResponse)
async def get_inbox(
    page: int = 1,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> Any:
    """Return unpromoted, undismissed feed items ordered by published_at desc
    (falls back to created_at desc for items with no published_at).
    Includes site name.
    """
    if page < 1:
        page = 1
    if limit < 1 or limit > 200:
        limit = 50

    offset = (page - 1) * limit

    # Count total for pagination
    from sqlalchemy import func

    count_stmt = select(func.count(FeedItem.id)).where(
        FeedItem.ingested == 0,
        FeedItem.dismissed == 0,
    )
    total: int = session.scalar(count_stmt) or 0

    # Fetch page — order by published_at desc nulls last, then created_at desc
    from sqlalchemy import case, nullslast

    order_col = case(
        (FeedItem.published_at.is_not(None), FeedItem.published_at),
        else_=FeedItem.created_at,
    )

    stmt = (
        select(FeedItem)
        .where(
            FeedItem.ingested == 0,
            FeedItem.dismissed == 0,
        )
        .order_by(order_col.desc())
        .offset(offset)
        .limit(limit)
    )

    items = list(session.scalars(stmt).all())

    # Batch-load site names
    site_ids = {item.site_id for item in items}
    sites: dict[str, str] = {}
    if site_ids:
        site_rows = session.scalars(
            select(DiscoverySite).where(DiscoverySite.id.in_(site_ids))
        ).all()
        sites = {s.id: s.name for s in site_rows}

    out_items = [
        FeedItemOut(
            id=item.id,
            site_id=item.site_id,
            site_name=sites.get(item.site_id, "Unknown"),
            entry_guid=item.entry_guid,
            url=item.url,
            title=item.title,
            summary=item.summary,
            published_at=item.published_at,
            ingested=bool(item.ingested),
            dismissed=bool(item.dismissed),
            created_at=item.created_at,
        )
        for item in items
    ]

    import math
    pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    return InboxResponse(items=out_items, page=page, limit=limit, total=total, pages=pages)


@router.post("/feed/promote", response_model=PromoteResponse)
@limiter.limit("10/minute")
async def promote_feed_item(
    request: Request,
    body: PromoteRequest,
    session: Session = Depends(get_session),
) -> Any:
    """Ingest a feed item's URL into the recipe vault.

    Calls ingest_url() directly — no HTTP self-call.
    Marks feed_item.ingested=1, ingested_at=now, recipe_id=result.id.
    Idempotent: if feed_item is already ingested, returns the existing recipe_id.
    """
    from datetime import timezone

    item = session.get(FeedItem, body.feed_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="feed_item not found")

    # Idempotent: already ingested
    if item.ingested and item.recipe_id:
        return PromoteResponse(
            feed_item_id=item.id,
            recipe_id=item.recipe_id,
            already_existed=True,
        )

    already_existed = False
    recipe_id: str

    try:
        result = await ingest_url(item.url, session)
        recipe_id = result["recipe_id"]
    except HTTPException as exc:
        if exc.status_code == 409:
            # Already in vault — mark ingested and return existing id
            detail = exc.detail
            if isinstance(detail, dict):
                recipe_id = detail.get("recipe_id", "")
            else:
                recipe_id = ""
            already_existed = True
        else:
            raise

    now = datetime.now(timezone.utc)
    item.ingested = 1
    item.ingested_at = now
    item.recipe_id = recipe_id
    try:
        session.add(item)
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("feed promote: failed to update feed_item", feed_item_id=item.id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to update feed item") from exc

    log.info("feed promote: done", feed_item_id=item.id, recipe_id=recipe_id)

    return PromoteResponse(
        feed_item_id=item.id,
        recipe_id=recipe_id,
        already_existed=already_existed,
    )


@router.post("/feed/dismiss", response_model=DismissResponse)
@limiter.limit("30/minute")
async def dismiss_feed_item(
    request: Request,
    body: DismissRequest,
    session: Session = Depends(get_session),
) -> Any:
    """Dismiss a feed item from the inbox (sets dismissed=1)."""
    item = session.get(FeedItem, body.feed_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="feed_item not found")

    item.dismissed = 1
    try:
        session.add(item)
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("feed dismiss: failed", feed_item_id=item.id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to dismiss feed item") from exc

    log.info("feed dismiss: done", feed_item_id=item.id)

    return DismissResponse(feed_item_id=item.id, dismissed=True)
