from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .recipe import Recipe


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    recipes: Mapped[list[Recipe]] = relationship(
        "Recipe",
        secondary="recipe_tag",
        back_populates="tags",
    )

    __table_args__ = (UniqueConstraint("name", name="uq_tag_name"),)
