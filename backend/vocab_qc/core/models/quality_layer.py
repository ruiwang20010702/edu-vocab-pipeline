"""质量层模型: QcRun, QcRuleResult, RetryCounter, ReviewItem, AuditLogV2."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vocab_qc.core.db import Base


class QcRun(Base):
    """质检运行记录."""

    __tablename__ = "qc_runs"

    # TODO: 考虑迁移到 PostgreSQL 原生 UUID 类型（16字节 vs String(36) 的36字节）
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layer: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[str] = mapped_column(String(100), nullable=False, default="all")
    ai_strategy: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    rule_results: Mapped[list["QcRuleResult"]] = relationship(back_populates="run_rel")

    def __repr__(self) -> str:
        return f"<QcRun id={self.id} layer={self.layer} status={self.status}>"


class QcRuleResult(Base):
    """规则级质检结果（核心表）."""

    __tablename__ = "qc_rule_results"
    __table_args__ = (
        UniqueConstraint("content_item_id", "rule_id", "run_id", name="uq_item_rule_run"),
        Index("ix_qc_rule_results_item_run_passed", "content_item_id", "run_id", "passed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False, index=True)
    meaning_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meanings.id"), nullable=True, index=True)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    layer: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ai_strategy: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("qc_runs.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    content_item_rel: Mapped["ContentItem"] = relationship("ContentItem", back_populates="rule_results")
    run_rel: Mapped["QcRun"] = relationship(back_populates="rule_results")

    def __repr__(self) -> str:
        return f"<QcRuleResult rule={self.rule_id} passed={self.passed}>"


class RetryCounter(Base):
    """重试计数器."""

    __tablename__ = "retry_counters"
    __table_args__ = (
        # Partial unique index: meaning_id IS NOT NULL
        Index(
            "uq_retry_with_meaning",
            "word_id",
            "meaning_id",
            "dimension",
            unique=True,
            postgresql_where="meaning_id IS NOT NULL",
        ),
        # Partial unique index: meaning_id IS NULL
        Index(
            "uq_retry_without_meaning",
            "word_id",
            "dimension",
            unique=True,
            postgresql_where="meaning_id IS NULL",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)
    meaning_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meanings.id", ondelete="CASCADE"), nullable=True)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    last_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<RetryCounter word={self.word_id} dim={self.dimension} count={self.count}>"


class ReviewItem(Base):
    """人工审核队列."""

    __tablename__ = "review_items"
    __table_args__ = (
        Index("ix_review_items_status_assigned", "status", "assigned_to_id"),
        CheckConstraint("status IN ('pending', 'in_progress', 'resolved')", name="ck_review_items_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False, index=True)
    meaning_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meanings.id"), nullable=True)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Phase 3: 批次派发字段（nullable，向后兼容）
    batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("review_batches.id"), nullable=True, index=True)
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    content_item_rel: Mapped["ContentItem"] = relationship("ContentItem", back_populates="review_items")

    def __repr__(self) -> str:
        return f"<ReviewItem id={self.id} status={self.status}>"


class AiErrorLog(Base):
    """AI 调用错误日志（生产 + 质检）."""

    __tablename__ = "ai_error_logs"
    __table_args__ = (
        Index("ix_ai_error_logs_phase", "phase"),
        Index("ix_ai_error_logs_word_id", "word_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    word_id: Mapped[Optional[int]] = mapped_column(ForeignKey("words.id"), nullable=True)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)  # generation / qc_layer2
    dimension: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)  # api_timeout / api_error / parse_error / unknown
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AiErrorLog id={self.id} phase={self.phase} type={self.error_type}>"


def classify_ai_error(e: Exception) -> str:
    """根据异常信息分类错误类型."""
    msg = str(e).lower()
    if "timeout" in msg or "timed out" in msg:
        return "api_timeout"
    if "status" in msg or "http" in msg or "connect" in msg:
        return "api_error"
    if "json" in msg or "parse" in msg or "decode" in msg:
        return "parse_error"
    return "unknown"


class AuditLogV2(Base):
    """增强版审计日志."""

    __tablename__ = "audit_logs_v2"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AuditLogV2 {self.entity_type}#{self.entity_id} {self.action}>"
