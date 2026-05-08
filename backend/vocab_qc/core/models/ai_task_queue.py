"""AI 任务队列模型: 持久化 Gateway 异步任务，支持提交/轮询解耦和重启恢复."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from vocab_qc.core.db import Base


class AiTaskStatus(str, Enum):
    """AI 任务状态机: pending → submitted → completed / failed."""

    PENDING = "pending"        # 已入队，尚未提交到 Gateway
    SUBMITTED = "submitted"    # 已提交，gateway_task_no 已获得
    POLLING = "polling"        # 正在被 polling worker 处理（短暂锁定态）
    COMPLETED = "completed"    # Gateway 返回 COMPLETED，result_data 已填充
    FAILED = "failed"          # 重试耗尽或 Gateway 返回 FAILED
    CANCELLED = "cancelled"    # 手动取消


class AiTaskQueue(Base):
    """AI Gateway 异步任务队列.

    用于持久化 task_no，解耦提交与轮询，支持重启后恢复未完成的任务。
    """

    __tablename__ = "ai_task_queue"
    __table_args__ = (
        Index("ix_aitq_status_created", "status", "created_at"),
        Index("ix_aitq_batch_key", "batch_key"),
        Index("ix_aitq_task_no", "gateway_task_no", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 批次关联
    batch_key: Mapped[str] = mapped_column(String(100), nullable=False)
    content_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=True,
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False)  # generation / qc_layer2
    dimension: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Gateway 交互
    gateway_task_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    submit_body: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AiTaskStatus.PENDING.value,
    )
    result_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 重试 & 轮询计数
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    poll_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 时间戳
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关联元数据（用于监控和审计）
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    word_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("words.id", ondelete="SET NULL"), nullable=True,
    )
    package_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("packages.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AiTaskQueue id={self.id} batch_key={self.batch_key!r} "
            f"status={self.status} task_no={self.gateway_task_no!r}>"
        )
