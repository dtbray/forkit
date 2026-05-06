from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .ingredient import Ingredient
    from .tag import Tag


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Recipe(Base):
    __tablename__ = "recipe"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid4_str)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hero_image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    yield_text: Mapped[str | None] = mapped_column(String, nullable=True)
    # ISO 8601 duration strings e.g. "PT30M"
    prep_time: Mapped[str | None] = mapped_column(String, nullable=True)
    cook_time: Mapped[str | None] = mapped_column(String, nullable=True)
    total_time: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON-encoded list of step strings
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    cuisine: Mapped[str | None] = mapped_column(String, nullable=True)
    meal_type: Mapped[str | None] = mapped_column(String, nullable=True)
    cook_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_cooked: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_viewed: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # "jsonld", "adapter:<name>", "llm", "manual", "vision"
    parser_source: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    ingredients: Mapped[list[Ingredient]] = relationship(
        "Ingredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="Ingredient.position",
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary="recipe_tag",
        back_populates="recipes",
    )

    __table_args__ = (
        UniqueConstraint("source_url", name="uq_recipe_source_url"),
    )
