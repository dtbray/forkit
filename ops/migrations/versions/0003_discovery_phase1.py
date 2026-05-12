"""discovery_phase1: discovery_site and search_cache tables + builtin seed data

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10

"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # discovery_site
    # -------------------------------------------------------------------------
    op.create_table(
        "discovery_site",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("home_url", sa.Text(), nullable=False),
        sa.Column("adapter_kind", sa.String(), nullable=False),
        sa.Column("adapter_config_json", sa.Text(), nullable=True),
        sa.Column("search_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("feed_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_builtin", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paywall_note", sa.Text(), nullable=True),
        sa.Column("last_search_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_search_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_discovery_site_slug"),
    )
    op.create_index("ix_discovery_site_slug", "discovery_site", ["slug"], unique=True)
    op.create_index("ix_discovery_site_search_enabled", "discovery_site", ["search_enabled"])
    op.create_index("ix_discovery_site_feed_enabled", "discovery_site", ["feed_enabled"])

    # -------------------------------------------------------------------------
    # search_cache
    # -------------------------------------------------------------------------
    op.create_table(
        "search_cache",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("query_norm", sa.Text(), nullable=False),
        sa.Column("results_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "query_norm", name="uq_search_cache_site_query"),
    )
    op.create_index("ix_search_cache_expires_at", "search_cache", ["expires_at"])

    # -------------------------------------------------------------------------
    # Seed builtin sites
    # -------------------------------------------------------------------------
    _backend_src = str(Path(__file__).resolve().parents[4] / "backend" / "src")
    if _backend_src not in sys.path:
        sys.path.insert(0, _backend_src)

    from forkit.discovery.builtin_sites import BUILTIN_SITES  # noqa: PLC0415

    conn = op.get_bind()
    now = _utcnow_str()
    for site in BUILTIN_SITES:
        conn.execute(
            sa.text(
                "INSERT INTO discovery_site "
                "(id, slug, name, home_url, adapter_kind, adapter_config_json, "
                "search_enabled, feed_enabled, is_builtin, paywall_note, "
                "created_at, updated_at) "
                "VALUES (:id, :slug, :name, :home_url, :adapter_kind, :adapter_config_json, "
                ":search_enabled, :feed_enabled, :is_builtin, :paywall_note, "
                ":created_at, :updated_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "slug": site["slug"],
                "name": site["name"],
                "home_url": site["home_url"],
                "adapter_kind": site["adapter_kind"],
                "adapter_config_json": json.dumps(site.get("adapter_config_json") or {}),
                "search_enabled": 1 if site.get("search_enabled", True) else 0,
                "feed_enabled": 1 if site.get("feed_enabled", False) else 0,
                "is_builtin": 1,
                "paywall_note": site.get("paywall_note"),
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_search_cache_expires_at", table_name="search_cache")
    op.drop_table("search_cache")

    op.drop_index("ix_discovery_site_feed_enabled", table_name="discovery_site")
    op.drop_index("ix_discovery_site_search_enabled", table_name="discovery_site")
    op.drop_index("ix_discovery_site_slug", table_name="discovery_site")
    op.drop_table("discovery_site")
