"""FeedItem ORM model — Phase 2 Feed Subscriber."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeedItem(Base):
    __tablename__ = "feed_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid4_str)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    entry_guid: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipe_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dismissed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("site_id", "entry_guid", name="uq_feed_item_site_guid"),
        Index("ix_feed_item_site_id", "site_id"),
        Index("ix_feed_item_ingested", "ingested"),
        Index("ix_feed_item_dismissed", "dismissed"),
        Index("ix_feed_item_published_at", "published_at"),
    )
