"""Feed poller — polls all feed-enabled discovery sites and upserts feed_items.

Called by APScheduler every 60 minutes. Uses SessionLocal directly (not the
FastAPI get_session() dependency) so it can run outside the request/response cycle.

Security:
  - All network I/O delegated to FeedAdapter.poll() which uses safe_fetch() (S1)
  - Duplicate entries silently skipped via (site_id, entry_guid) unique constraint
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models.discovery_site import DiscoverySite
from ..models.feed_item import FeedItem
from .registry import get_adapter

log = structlog.get_logger()


async def poll_all_feeds(session_factory) -> None:  # type: ignore[type-arg]
    """Query all feed-enabled sites, poll each adapter, upsert feed_items.

    Uses session_factory() (SessionLocal) directly — not the FastAPI dependency.
    """
    session = session_factory()
    try:
        sites = list(
            session.scalars(
                select(DiscoverySite).where(DiscoverySite.feed_enabled == 1)
            ).all()
        )

        log.info("poller: starting poll cycle", site_count=len(sites))

        for site in sites:
            try:
                adapter = get_adapter(site)
            except ValueError as exc:
                log.warning("poller: no adapter for site", site=site.slug, error=str(exc))
                continue

            try:
                entries = await adapter.poll()
            except Exception as exc:
                log.warning("poller: poll failed", site=site.slug, error=str(exc))
                continue

            inserted = 0
            skipped = 0
            now = datetime.now(timezone.utc)

            for entry in entries:
                item = FeedItem(
                    id=str(uuid.uuid4()),
                    site_id=site.id,
                    entry_guid=entry.guid,
                    url=entry.url,
                    title=entry.title,
                    summary=entry.summary,
                    published_at=entry.published_at,
                    ingested=0,
                    dismissed=0,
                    created_at=now,
                )
                try:
                    session.add(item)
                    session.flush()
                    inserted += 1
                except IntegrityError:
                    session.rollback()
                    skipped += 1
                except Exception as exc:
                    session.rollback()
                    log.warning(
                        "poller: failed to insert feed_item",
                        site=site.slug,
                        guid=entry.guid,
                        error=str(exc),
                    )
                    skipped += 1

            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                log.warning("poller: commit failed", site=site.slug, error=str(exc))

            log.info(
                "poller: site poll done",
                site=site.slug,
                inserted=inserted,
                skipped=skipped,
            )

    finally:
        session.close()
