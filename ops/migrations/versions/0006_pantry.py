"""Reviewed pantry ingredients, separate from recipe ingredients."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pantry_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("canonical", sa.String(200), nullable=False, unique=True),
        sa.Column("quantity", sa.String(80)),
        sa.Column("unit", sa.String(80)),
        sa.Column("notes", sa.Text()),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade():
    op.drop_table("pantry_item")
