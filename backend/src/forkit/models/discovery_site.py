"""DiscoverySite ORM model — ADR-002 Section 3.1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiscoverySite(Base):
    __tablename__ = "discovery_site"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid4_str)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    home_url: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String, nullable=False)
    adapter_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    feed_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paywall_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_search_ok_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_search_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_discovery_site_slug", "slug", unique=True),
        Index("ix_discovery_site_search_enabled", "search_enabled"),
        Index("ix_discovery_site_feed_enabled", "feed_enabled"),
    )
