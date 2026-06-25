"""导出任务模型: 持久化异步 Excel 导出任务，触发/轮询解耦，避免同步导出撞超时."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vocab_qc.core.db import Base


class ExportJobStatus(str, Enum):
    """导出任务状态机: pending → running → completed / failed."""

    PENDING = "pending"      # 已入队，后台线程尚未开始
    RUNNING = "running"      # 后台线程正在构建 Excel
    COMPLETED = "completed"  # 文件已落盘，可下载
    FAILED = "failed"        # 构建异常或超时


# 终态集合：仅"未终态"视为进行中，用于并发去重与僵尸超时判断
EXPORT_TERMINAL_STATUSES = frozenset(
    {ExportJobStatus.COMPLETED.value, ExportJobStatus.FAILED.value}
)


class ExportJob(Base):
    """异步导出任务。

    点击导出 → 建任务(pending) → 后台线程跑 export_to_excel 落盘 → 前端轮询 → 完成下载。
    任务态存 DB、文件存容器本地盘；多 worker 下任一 worker 凭 DB+盘 提供状态/下载。
    """

    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ExportJobStatus.PENDING.value,
        server_default=ExportJobStatus.PENDING.value,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)  # 触发人 email（审计）

    # 完成后填充
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 时间戳（DB 存 UTC，与全库一致）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ExportJob id={self.id} status={self.status}>"
