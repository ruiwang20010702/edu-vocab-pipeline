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
        """触发重新生成（≤3次）+ 自动质检.

        Returns:
            {"success": bool, "qc_passed": bool, "retry_count": int, "message": str}
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
                "qc_passed": False,
                "retry_count": counter.count,
                "message": "已达到最大重试次数，请手动修改",
            }
        session.refresh(counter)
        content_item.retry_count = counter.count

        # 调用生成器重新生成内容
        self._do_regenerate(session, content_item)

        # 如果生成器标记为 rejected（助记类型不适用），直接 resolve
        if content_item.qc_status == QcStatus.REJECTED.value:
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.reviewer = reviewer
            review.resolved_at = datetime.now(UTC)
            session.flush()
            self._update_batch_progress(session, review.batch_id)
            return {
                "success": True,
                "qc_passed": True,
                "retry_count": counter.count,
                "message": "该助记类型不适用，已跳过",
            }

        # 重置质检状态
        content_item.qc_status = QcStatus.PENDING.value
        session.flush()

        # 自动运行质检
        qc_passed = self._run_qc_for_item(session, content_item)

        if qc_passed:
            # 质检通过 → 标记 approved，审核项 resolved
            content_item.qc_status = QcStatus.APPROVED.value
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.reviewer = reviewer
            review.resolved_at = datetime.now(UTC)
            message = f"第{counter.count}次重新生成成功，质检通过"
        else:
            # 质检失败 → 审核项保持 pending，内容已更新
            message = f"第{counter.count}次重新生成完成，但质检未通过"

        log_action(
            session,
            entity_type="review_item",
            entity_id=review.id,
            action="regenerate",
            actor=reviewer,
            new_value={"retry_count": counter.count, "qc_passed": qc_passed},
        )

        session.flush()
        self._update_batch_progress(session, review.batch_id)

        # 查询最新质检失败问题
        from vocab_qc.core.models.quality_layer import QcRuleResult
        new_issues = []
        if content_item.last_qc_run_id and not qc_passed:
            failed_results = (
                session.query(QcRuleResult)
                .filter_by(content_item_id=content_item.id, run_id=content_item.last_qc_run_id, passed=False)
                .all()
            )
            new_issues = [
                {"rule_id": r.rule_id, "field": r.dimension, "message": r.detail or ""}
                for r in failed_results
            ]

        return {
            "success": True,
            "qc_passed": qc_passed,
            "retry_count": counter.count,
            "message": message,
            "new_content": content_item.content,
            "new_content_cn": content_item.content_cn,
            "new_issues": new_issues,
        }

    @staticmethod
    def _do_regenerate(session: Session, content_item: ContentItem) -> None:
        """调用生成器重新生成单个 ContentItem 的内容。"""
        from vocab_qc.core.models.data_layer import Meaning, Word
        from vocab_qc.core.services.production_service import _GENERATORS

        generator = _GENERATORS.get(content_item.dimension)
        if generator is None:
            return

        word = session.query(Word).filter_by(id=content_item.word_id).first()
        if word is None:
            return

        meaning_text = None
        pos = None
        if content_item.meaning_id:
            meaning = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
            if meaning:
                meaning_text = meaning.definition
                pos = meaning.pos

        result = generator.generate(
            word=word.word, meaning=meaning_text, pos=pos, session=session,
        )

        if result.get("valid") is False:
            content_item.content = ""
            content_item.qc_status = QcStatus.REJECTED.value
            return

        content_item.content = result.get("content", "")
        if result.get("content_cn"):
            content_item.content_cn = result["content_cn"]

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

    @staticmethod
    def _run_qc_for_item(session: Session, content_item: ContentItem) -> bool:
        """对单个内容项运行 Layer 1 + Layer 2 质检，返回是否全部通过。"""
        from vocab_qc.core.models.data_layer import Meaning, Phonetic, Word
        from vocab_qc.core.qc.layer2.runner import Layer2Runner
        from vocab_qc.core.qc.runner import Layer1Runner

        word = session.query(Word).filter_by(id=content_item.word_id).first()
        word_text = word.word if word else ""

        meaning_text = None
        meaning_texts: dict[int, str] = {}
        if content_item.meaning_id:
            meaning = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
            if meaning:
                meaning_text = meaning.definition
                meaning_texts[meaning.id] = meaning_text

        # 构建额外参数
        extra: dict = {"content_cn": content_item.content_cn or ""}
        phonetic = session.query(Phonetic).filter_by(word_id=content_item.word_id).first()
        if phonetic:
            extra["ipa"] = phonetic.ipa
            extra["syllables"] = phonetic.syllables
        if content_item.dimension == "meaning" and content_item.meaning_id:
            meaning_obj = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
            if meaning_obj and meaning_obj.pos:
                extra["pos"] = meaning_obj.pos

        word_texts = {content_item.word_id: word_text}
        extra_kwargs = {content_item.id: extra}

        # Layer 1
        l1_runner = Layer1Runner()
        l1_runner.run(session, [content_item], word_texts, meaning_texts, extra_kwargs)

        if content_item.qc_status != QcStatus.LAYER1_PASSED.value:
            return False

        # Layer 2
        l2_runner = Layer2Runner()
        l2_runner.run(session, [content_item], word_texts, meaning_texts, extra_kwargs=extra_kwargs)

        return content_item.qc_status == QcStatus.LAYER2_PASSED.value

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
