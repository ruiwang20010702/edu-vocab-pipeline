"""Prompt 模型."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from vocab_qc.core.db import Base


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        Index(
            "uq_prompts_active_dim",
            "category",
            "dimension",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # generation / qa
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)  # chunk / sentence / mnemonic_*
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="gemini-3-flash-preview|efficiency")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_api_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ai_api_base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="1")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="file", server_default="file")
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"<Prompt id={self.id} name={self.name!r} dim={self.dimension}>"
