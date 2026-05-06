from sqlalchemy import Column, ForeignKey, String, Integer, Table

from .base import Base

recipe_tag = Table(
    "recipe_tag",
    Base.metadata,
    Column(
        "recipe_id",
        String,
        ForeignKey("recipe.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tag.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
)
