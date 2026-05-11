"""feed_items: feed_item table for Phase 2 Feed Subscriber

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_item",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("site_id", sa.String(), nullable=False),
        sa.Column("entry_guid", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipe_id", sa.String(), nullable=True),
        sa.Column("dismissed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "entry_guid", name="uq_feed_item_site_guid"),
        sa.ForeignKeyConstraint(["site_id"], ["discovery_site.id"], name="fk_feed_item_site"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], name="fk_feed_item_recipe"),
    )
    op.create_index("ix_feed_item_site_id", "feed_item", ["site_id"])
    op.create_index("ix_feed_item_ingested", "feed_item", ["ingested"])
    op.create_index("ix_feed_item_dismissed", "feed_item", ["dismissed"])
    op.create_index("ix_feed_item_published_at", "feed_item", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_feed_item_published_at", table_name="feed_item")
    op.drop_index("ix_feed_item_dismissed", table_name="feed_item")
    op.drop_index("ix_feed_item_ingested", table_name="feed_item")
    op.drop_index("ix_feed_item_site_id", table_name="feed_item")
    op.drop_table("feed_item")
