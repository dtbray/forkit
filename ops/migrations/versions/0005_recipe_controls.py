"""Persistent favorites and explicit deletion suppression."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "recipe",
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_table(
        "deleted_recipe",
        sa.Column("source_url", sa.String(), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("deleted_recipe")
    op.drop_column("recipe", "favorite")
