from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .recipe import Recipe


class Ingredient(Base):
    __tablename__ = "ingredient"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[str] = mapped_column(
        String, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    item: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalized token for Pantry Match (P2)
    canonical_token: Mapped[str | None] = mapped_column(String, nullable=True)

    recipe: Mapped[Recipe] = relationship("Recipe", back_populates="ingredients")

    __table_args__ = (
        UniqueConstraint("recipe_id", "position", name="uq_ingredient_recipe_position"),
        Index("ix_ingredient_recipe_id", "recipe_id"),
        Index("ix_ingredient_canonical_token", "canonical_token"),
    )
