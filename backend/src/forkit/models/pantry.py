"""Reviewed household ingredient availability; quantities are user supplied."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PantryItem(Base):
    __tablename__ = "pantry_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(80))
    unit: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
