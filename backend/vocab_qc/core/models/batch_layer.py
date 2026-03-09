"""批次模型: ReviewBatch."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vocab_qc.core.db import Base


class ReviewBatch(Base):
    """审核批次。"""

    __tablename__ = "review_batches"
    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'completed')", name="ck_review_batches_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ReviewBatch id={self.id} user={self.user_id} status={self.status}>"
