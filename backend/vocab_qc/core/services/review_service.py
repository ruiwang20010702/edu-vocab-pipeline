"""人工审核服务: approve/regenerate/manual_edit + 重试计数."""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from vocab_qc.core.models import (
    ContentItem,
    QcStatus,
    RetryCounter,
    ReviewItem,
    ReviewReason,
    ReviewResolution,
    ReviewStatus,
)
from vocab_qc.core.services.audit_service import log_action
from vocab_qc.core.services.batch_service import update_batch_progress


class ReviewService:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def _check_concurrency(self, review: ReviewItem, user_id: Optional[int] = None) -> None:
        """并发前置检查：状态 + 分配归属。"""
        if review.status != ReviewStatus.PENDING.value:
            raise ValueError("该审核项已被处理")
        if review.assigned_to_id is not None and user_id is not None and review.assigned_to_id != user_id:
            raise ValueError("该审核项已分配给其他审核员")

    def _lock_review_item(self, session: Session, review_id: int) -> ReviewItem:
        """查询并锁定审核项（PostgreSQL 用 FOR UPDATE，SQLite 跳过）。"""
        query = session.query(ReviewItem).filter_by(id=review_id)
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect == "postgresql":
            query = query.with_for_update()
        review = query.one()
        return review

    def create_review_item(
        self,
        session: Session,
        content_item: ContentItem,
        reason: ReviewReason,
        priority: int = 0,
    ) -> ReviewItem:
        """创建审核项（入队）."""
        # 防止重复入队：已有 pending 项则直接返回
        existing = session.query(ReviewItem).filter_by(
            content_item_id=content_item.id,
            status=ReviewStatus.PENDING.value,
        ).first()
        if existing:
            return existing

        review = ReviewItem(
            content_item_id=content_item.id,
            word_id=content_item.word_id,
            meaning_id=content_item.meaning_id,
            dimension=content_item.dimension,
            reason=reason.value,
            priority=priority,
            status=ReviewStatus.PENDING.value,
        )
        session.add(review)
        session.flush()
        return review

    def approve(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        note: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ReviewItem:
        """通过审核."""
        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()

        old_status = review.status
        review.status = ReviewStatus.RESOLVED.value
        review.resolution = ReviewResolution.APPROVED.value
        review.reviewer = reviewer
        review.review_note = note
        review.resolved_at = datetime.now(UTC)

        content_item.qc_status = QcStatus.APPROVED.value

        log_action(
            session,
            entity_type="review_item",
            entity_id=review.id,
            action="approve",
            actor=reviewer,
            old_value={"status": old_status},
            new_value={"status": review.status, "resolution": review.resolution},
        )

        session.flush()
        self._update_batch_progress(session, review.batch_id)
        return review

    def regenerate(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        user_id: Optional[int] = None,
    ) -> dict:
        """触发重新生成（≤3次）.

        Returns:
            {"success": bool, "retry_count": int, "message": str}
        """
        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()

        # 获取或创建重试计数器
        counter = self._get_or_create_counter(session, content_item)

        # 原子递增计数 + 上限检查（单条 UPDATE 防止并发重试超限）
        result = session.execute(
            update(RetryCounter)
            .where(RetryCounter.id == counter.id, RetryCounter.count < self.max_retries)
            .values(count=RetryCounter.count + 1, last_retry_at=datetime.now(UTC))
        )
        if result.rowcount == 0:
            return {
                "success": False,
                "retry_count": counter.count,
                "message": "已达到最大重试次数，请手动修改",
            }
        session.refresh(counter)
        content_item.retry_count = counter.count

        # 更新审核项
        review.status = ReviewStatus.RESOLVED.value
        review.resolution = ReviewResolution.REGENERATE.value
        review.reviewer = reviewer
        review.resolved_at = datetime.now(UTC)

        log_action(
            session,
            entity_type="review_item",
            entity_id=review.id,
            action="regenerate",
            actor=reviewer,
            new_value={"retry_count": counter.count},
        )

        session.flush()
        self._update_batch_progress(session, review.batch_id)
        return {
            "success": True,
            "retry_count": counter.count,
            "message": f"第{counter.count}次重新生成已触发",
        }

    def manual_edit(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        new_content: str,
        new_content_cn: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> ReviewItem:
        """人工修改内容."""
        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()

        old_content = content_item.content
        content_item.content = new_content
        if new_content_cn is not None:
            content_item.content_cn = new_content_cn

        # 人工修改后需重过 Layer 1 确认格式，状态设为 pending
        content_item.qc_status = QcStatus.PENDING.value

        review.status = ReviewStatus.RESOLVED.value
        review.resolution = ReviewResolution.MANUAL_EDIT.value
        review.reviewer = reviewer
        review.resolved_at = datetime.now(UTC)

        log_action(
            session,
            entity_type="content_item",
            entity_id=content_item.id,
            action="manual_edit",
            actor=reviewer,
            old_value={"content": old_content},
            new_value={"content": new_content},
        )

        session.flush()
        self._update_batch_progress(session, review.batch_id)
        return review

    def get_pending_reviews(
        self,
        session: Session,
        dimension: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ReviewItem], int]:
        """获取待审核队列，返回 (items, total)."""
        query = session.query(ReviewItem).filter_by(status=ReviewStatus.PENDING.value)
        if dimension:
            query = query.filter_by(dimension=dimension)
        total = query.count()
        items = query.order_by(ReviewItem.priority.desc(), ReviewItem.created_at).offset(offset).limit(limit).all()
        return items, total

    def _get_or_create_counter(self, session: Session, content_item: ContentItem) -> RetryCounter:
        """获取或创建重试计数器."""
        query = session.query(RetryCounter).filter_by(
            word_id=content_item.word_id,
            dimension=content_item.dimension,
        )
        if content_item.meaning_id is not None:
            query = query.filter_by(meaning_id=content_item.meaning_id)
        else:
            query = query.filter(RetryCounter.meaning_id.is_(None))

        counter = query.first()
        if counter is None:
            counter = RetryCounter(
                word_id=content_item.word_id,
                meaning_id=content_item.meaning_id,
                dimension=content_item.dimension,
                count=0,
                max_retries=self.max_retries,
            )
            session.add(counter)
            session.flush()
        return counter

    def _update_batch_progress(self, session: Session, batch_id: Optional[int]) -> None:
        """审核操作完成后更新批次进度。"""
        if batch_id is None:
            return
        update_batch_progress(session, batch_id)
