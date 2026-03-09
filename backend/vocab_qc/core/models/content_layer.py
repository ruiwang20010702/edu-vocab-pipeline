"""内容层模型: ContentItem（含新增质检列）."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vocab_qc.core.db import Base
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS, ContentDimension, QcStatus

_VALID_DIMENSIONS = ("meaning", "phonetic", "syllable", "chunk", "sentence", *MNEMONIC_DIMENSIONS)


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            f"dimension IN ({', '.join(repr(d) for d in _VALID_DIMENSIONS)})",
            name="ck_content_items_dimension",
        ),
        Index("ix_content_items_word_dim", "word_id", "dimension"),
        Index("ix_content_items_word_meaning_dim", "word_id", "meaning_id", "dimension"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False, index=True)
    meaning_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meanings.id"), nullable=True, index=True)
    dimension: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_cn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 新增质检列
    qc_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=QcStatus.PENDING.value, server_default=QcStatus.PENDING.value, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_qc_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # 关系（字符串引用避免循环导入）
    word_rel: Mapped["Word"] = relationship("Word", back_populates="content_items")
    meaning_rel: Mapped[Optional["Meaning"]] = relationship("Meaning", back_populates="content_items")
    rule_results: Mapped[list["QcRuleResult"]] = relationship("QcRuleResult", back_populates="content_item_rel")
    review_items: Mapped[list["ReviewItem"]] = relationship("ReviewItem", back_populates="content_item_rel")

    @property
    def dimension_enum(self) -> ContentDimension:
        return ContentDimension(self.dimension)

    def __repr__(self) -> str:
        return f"<ContentItem id={self.id} dim={self.dimension} status={self.qc_status}>"
