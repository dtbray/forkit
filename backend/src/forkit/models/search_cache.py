"""SearchCache ORM model — ADR-002 Section 3.4."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchCache(Base):
    __tablename__ = "search_cache"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid4_str)
    site_id: Mapped[str] = mapped_column(String, nullable=False)
    query_norm: Mapped[str] = mapped_column(Text, nullable=False)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("site_id", "query_norm", name="uq_search_cache_site_query"),
        Index("ix_search_cache_expires_at", "expires_at"),
    )
