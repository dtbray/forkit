"""initial schema: recipe, ingredient, tag, recipe_tag, FTS5, triggers

Revision ID: 0001
Revises:
Create Date: 2026-05-03

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # recipe
    # ------------------------------------------------------------------
    op.create_table(
        "recipe",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("hero_image_path", sa.String(), nullable=True),
        sa.Column("yield_text", sa.String(), nullable=True),
        sa.Column("prep_time", sa.String(), nullable=True),
        sa.Column("cook_time", sa.String(), nullable=True),
        sa.Column("total_time", sa.String(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("cuisine", sa.String(), nullable=True),
        sa.Column("meal_type", sa.String(), nullable=True),
        sa.Column("cook_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_cooked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_viewed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parser_source", sa.String(), nullable=True),
        sa.Column("parser_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url", name="uq_recipe_source_url"),
    )

    # ------------------------------------------------------------------
    # tag
    # ------------------------------------------------------------------
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tag_name"),
    )

    # ------------------------------------------------------------------
    # ingredient
    # ------------------------------------------------------------------
    op.create_table(
        "ingredient",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipe_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("qty", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("item", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("canonical_token", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recipe_id", "position", name="uq_ingredient_recipe_position"
        ),
    )
    op.create_index("ix_ingredient_recipe_id", "ingredient", ["recipe_id"])
    op.create_index(
        "ix_ingredient_canonical_token", "ingredient", ["canonical_token"]
    )

    # ------------------------------------------------------------------
    # recipe_tag (association table)
    # ------------------------------------------------------------------
    op.create_table(
        "recipe_tag",
        sa.Column("recipe_id", sa.String(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("recipe_id", "tag_id"),
    )

    # ------------------------------------------------------------------
    # FTS5 virtual table
    # SQLAlchemy/Alembic does not know about FTS5; execute raw DDL.
    # The table aggregates searchable text from recipe + ingredients + tags.
    # content='' means external-content mode: the shadow tables hold only
    # the indexed tokens; triggers below keep them in sync.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE VIRTUAL TABLE recipe_fts USING fts5(
            recipe_id UNINDEXED,
            title,
            description,
            ingredient_text,
            tag_names,
            cuisine,
            tokenize='porter unicode61'
        )
        """
    )

    # ------------------------------------------------------------------
    # FTS5 sync triggers — recipe
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TRIGGER recipe_fts_ai AFTER INSERT ON recipe BEGIN
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            VALUES (
                new.id,
                new.title,
                COALESCE(new.description, ''),
                '',
                '',
                COALESCE(new.cuisine, '')
            );
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER recipe_fts_au AFTER UPDATE ON recipe BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = old.id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = new.id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER recipe_fts_ad AFTER DELETE ON recipe BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = old.id;
        END
        """
    )

    # ------------------------------------------------------------------
    # FTS5 sync triggers — ingredient
    # Refresh the full FTS row for the affected recipe when ingredients change.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TRIGGER ingredient_fts_ai AFTER INSERT ON ingredient BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = new.recipe_id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = new.recipe_id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER ingredient_fts_au AFTER UPDATE ON ingredient BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = new.recipe_id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = new.recipe_id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER ingredient_fts_ad AFTER DELETE ON ingredient BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = old.recipe_id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = old.recipe_id;
        END
        """
    )

    # ------------------------------------------------------------------
    # FTS5 sync triggers — recipe_tag
    # Refresh when tags are attached/detached.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TRIGGER recipe_tag_fts_ai AFTER INSERT ON recipe_tag BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = new.recipe_id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = new.recipe_id;
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER recipe_tag_fts_ad AFTER DELETE ON recipe_tag BEGIN
            DELETE FROM recipe_fts WHERE recipe_id = old.recipe_id;
            INSERT INTO recipe_fts(recipe_id, title, description, ingredient_text, tag_names, cuisine)
            SELECT
                r.id,
                r.title,
                COALESCE(r.description, ''),
                COALESCE((
                    SELECT GROUP_CONCAT(i.raw_text, ' ')
                    FROM ingredient i WHERE i.recipe_id = r.id
                ), ''),
                COALESCE((
                    SELECT GROUP_CONCAT(t.name, ' ')
                    FROM recipe_tag rt JOIN tag t ON t.id = rt.tag_id
                    WHERE rt.recipe_id = r.id
                ), ''),
                COALESCE(r.cuisine, '')
            FROM recipe r WHERE r.id = old.recipe_id;
        END
        """
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop triggers first (they reference the tables)
    for trigger in [
        "recipe_tag_fts_ad",
        "recipe_tag_fts_ai",
        "ingredient_fts_ad",
        "ingredient_fts_au",
        "ingredient_fts_ai",
        "recipe_fts_ad",
        "recipe_fts_au",
        "recipe_fts_ai",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")

    op.execute("DROP TABLE IF EXISTS recipe_fts")
    op.drop_table("recipe_tag")
    op.drop_index("ix_ingredient_canonical_token", table_name="ingredient")
    op.drop_index("ix_ingredient_recipe_id", table_name="ingredient")
    op.drop_table("ingredient")
    op.drop_table("tag")
    op.drop_table("recipe")
