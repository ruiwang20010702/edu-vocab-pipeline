"""人工审核服务: approve/regenerate/manual_edit + 重试计数."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
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

logger = logging.getLogger(__name__)


def _lookup_package_id(session: Session, word_id: int) -> int | None:
    """通过 word_id 反查所属 Package ID（一词多包时取最新导入的）。"""
    from vocab_qc.core.models.package_layer import PackageWord

    row = (
        session.query(PackageWord.package_id)
        .filter_by(word_id=word_id)
        .order_by(PackageWord.id.desc())
        .first()
    )
    return row[0] if row else None


class ReviewService:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def _check_concurrency(self, review: ReviewItem, user_id: Optional[int] = None) -> None:
        """并发前置检查：状态 + 分配归属。"""
        if review.status != ReviewStatus.PENDING.value:
            raise ValueError("该审核项已被处理")
        if user_id is not None:
            # 已分配到批次的审核项，必须由批次所有者操作
            if review.batch_id is not None and review.assigned_to_id != user_id:
                raise ValueError("该审核项已分配给其他审核员")
            # 未分配到批次但已指定给某人
            if review.assigned_to_id is not None and review.assigned_to_id != user_id:
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
        nested = session.begin_nested()  # SAVEPOINT
        session.add(review)
        try:
            nested.commit()
        except IntegrityError:
            # 并发创建：部分唯一索引拦截了重复 pending 项
            nested.rollback()
            logger.debug(
                "ReviewItem 重复入队（已忽略）: content_item_id=%d",
                content_item.id,
            )
            existing = session.query(ReviewItem).filter_by(
                content_item_id=content_item.id,
                status=ReviewStatus.PENDING.value,
            ).first()
            return existing  # type: ignore[return-value]
        return review

    def create_review_items_batch(
        self,
        session: Session,
        content_items: list[ContentItem],
        reason: ReviewReason,
        priority: int = 0,
    ) -> int:
        """批量创建审核项（入队），自动去重已有 PENDING 项.

        分批 900 条查询，兼容 SQLite 999 参数限制。

        Returns:
            实际新增的审核项数量
        """
        if not content_items:
            return 0

        ci_ids = [item.id for item in content_items]

        # 分批查询已存在的 PENDING 审核项
        existing_ids: set[int] = set()
        for i in range(0, len(ci_ids), 900):
            chunk = ci_ids[i:i + 900]
            existing_ids.update(
                row[0] for row in session.query(ReviewItem.content_item_id)
                .filter(
                    ReviewItem.content_item_id.in_(chunk),
                    ReviewItem.status == ReviewStatus.PENDING.value,
                )
                .all()
            )

        new_reviews = [
            ReviewItem(
                content_item_id=item.id,
                word_id=item.word_id,
                meaning_id=item.meaning_id,
                dimension=item.dimension,
                reason=reason.value,
                priority=priority,
                status=ReviewStatus.PENDING.value,
            )
            for item in content_items if item.id not in existing_ids
        ]
        if not new_reviews:
            logger.info("审核项入队 reason=%s total=%d enqueued=%d", reason.value, len(content_items), 0)
            return 0

        # 先尝试批量写入（快路径，无并发冲突时一次完成）
        session.add_all(new_reviews)
        try:
            session.flush()
            logger.info("审核项入队 reason=%s total=%d enqueued=%d", reason.value, len(content_items), len(new_reviews))
            return len(new_reviews)
        except IntegrityError:
            session.rollback()

        # 慢路径：逐条用 savepoint 隔离，跳过重复项
        created = 0
        for review in new_reviews:
            nested = session.begin_nested()  # SAVEPOINT
            session.add(review)
            try:
                nested.commit()
                created += 1
            except IntegrityError:
                nested.rollback()  # 仅回滚到 savepoint
                logger.debug(
                    "ReviewItem 批量入队重复（已忽略）: content_item_id=%d",
                    review.content_item_id,
                )
        session.flush()
        logger.info("审核项入队 reason=%s total=%d enqueued=%d", reason.value, len(content_items), created)
        return created

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

        logger.info("审核通过 review_id=%d reviewer=%s content_item_id=%d", review_id, reviewer, review.content_item_id)

        session.flush()
        self._update_batch_progress(session, review.batch_id)
        return review

    def mark_not_applicable(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        user_id: Optional[int] = None,
    ) -> ReviewItem:
        """标记助记内容为不适用（清空内容 + rejected 状态）."""
        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()

        if not content_item.dimension.startswith("mnemonic_"):
            raise ValueError("仅助记维度支持标记不适用")

        old_status = review.status
        review.status = ReviewStatus.RESOLVED.value
        review.resolution = ReviewResolution.REGENERATE.value
        review.reviewer = reviewer
        review.review_note = "人工标记为不适用"
        review.resolved_at = datetime.now(UTC)

        content_item.content = ""
        content_item.qc_status = QcStatus.REJECTED.value

        log_action(
            session,
            entity_type="review_item",
            entity_id=review.id,
            action="mark_not_applicable",
            actor=reviewer,
            old_value={"status": old_status},
            new_value={"status": review.status, "qc_status": "rejected"},
        )

        logger.info("标记不适用 review_id=%d reviewer=%s content_item_id=%d", review_id, reviewer, review.content_item_id)

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

        logger.info("重新生成 review_id=%d reviewer=%s retry=%d qc_passed=%s", review_id, reviewer, counter.count, qc_passed)

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

    # ---- 异步 regenerate（三阶段拆分） ----

    def _regen_preload(
        self, session: Session, review_id: int, reviewer: str, user_id: Optional[int],
    ) -> dict[str, Any]:
        """Phase 1: DB 预加载 + 前置校验。返回 context dict 或含 early_return 的 dict。"""
        from vocab_qc.core.generators.base import estimate_cost
        from vocab_qc.core.models.data_layer import Meaning, Word
        from vocab_qc.core.services.production_service import _GENERATORS

        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()
        counter = self._get_or_create_counter(session, content_item)

        # 原子递增计数 + 上限检查
        result = session.execute(
            update(RetryCounter)
            .where(RetryCounter.id == counter.id, RetryCounter.count < self.max_retries)
            .values(count=RetryCounter.count + 1, last_retry_at=datetime.now(UTC))
        )
        if result.rowcount == 0:
            return {"early_return": {
                "success": False, "qc_passed": False,
                "retry_count": counter.count, "message": "已达到最大重试次数，请手动修改",
            }}
        session.refresh(counter)
        content_item.retry_count = counter.count

        generator = _GENERATORS.get(content_item.dimension)
        if generator is None:
            return {"early_return": {
                "success": False, "qc_passed": False,
                "retry_count": counter.count, "message": "未找到对应生成器",
            }}

        word = session.query(Word).filter_by(id=content_item.word_id).first()
        if word is None:
            return {"early_return": {
                "success": False, "qc_passed": False,
                "retry_count": counter.count, "message": "单词不存在",
            }}

        meaning_text = None
        pos = None
        if content_item.meaning_id:
            meaning = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
            if meaning:
                meaning_text = meaning.definition
                pos = meaning.pos

        ai_config = generator.resolve_ai_config(session=session)

        return {
            "review": review,
            "content_item": content_item,
            "counter": counter,
            "generator": generator,
            "ai_config": ai_config,
            "word_text": word.word,
            "word_id": content_item.word_id,
            "meaning_text": meaning_text,
            "pos": pos,
            "estimate_cost": estimate_cost,
            "reviewer": reviewer,
        }

    def _regen_writeback_and_qc(
        self, session: Session, ctx: dict[str, Any], gen_result: dict, reviewer: str,
    ) -> dict:
        """Phase 3: 写入生成结果 + 运行质检 + 更新状态，返回最终 response dict。"""
        from vocab_qc.core.models.quality_layer import AiUsageLog, QcRuleResult

        content_item = ctx["content_item"]
        review = ctx["review"]
        counter = ctx["counter"]
        generator = ctx["generator"]
        ai_config = ctx["ai_config"]
        estimate_cost = ctx["estimate_cost"]

        # 记录 AI 用量
        usage = gen_result.pop("__usage__", None)
        if usage and usage.total_tokens > 0:
            session.add(AiUsageLog(
                phase="generation",
                dimension=content_item.dimension,
                ai_model=ai_config.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost_usd=estimate_cost(ai_config.model, usage),
                word_id=content_item.word_id,
                content_item_id=content_item.id,
                package_id=_lookup_package_id(session, content_item.word_id),
            ))

        # 处理 rejected（助记类型不适用）
        if gen_result.get("valid") is False:
            content_item.content = ""
            content_item.qc_status = QcStatus.REJECTED.value
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.reviewer = reviewer
            review.resolved_at = datetime.now(UTC)
            session.flush()
            self._update_batch_progress(session, review.batch_id)
            return {
                "success": True, "qc_passed": True,
                "retry_count": counter.count, "message": "该助记类型不适用，已跳过",
                "new_content": None, "new_content_cn": None, "new_issues": [],
            }

        # 写入生成结果
        content_item.content = gen_result.get("content", "")
        if gen_result.get("content_cn"):
            content_item.content_cn = gen_result["content_cn"]
        # G 方案：记录本条生成时所用 prompt 的版本指纹
        content_item.generated_with_prompt_id = ai_config.prompt_id
        content_item.generated_with_prompt_hash = ai_config.prompt_hash

        # 重置质检状态 + 运行质检
        content_item.qc_status = QcStatus.PENDING.value
        session.flush()
        qc_passed = self._run_qc_for_item(session, content_item)

        if qc_passed:
            content_item.qc_status = QcStatus.APPROVED.value
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.REGENERATE.value
            review.reviewer = reviewer
            review.resolved_at = datetime.now(UTC)
            message = f"第{counter.count}次重新生成成功，质检通过"
        else:
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

    async def regenerate_async(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        user_id: Optional[int] = None,
    ) -> dict:
        """异步重新生成：preload(sync→thread) → AI生成(async) → 写回+QC(sync→thread)。"""
        # Phase 1: DB 预加载
        ctx = await asyncio.to_thread(
            self._regen_preload, session, review_id, reviewer, user_id
        )
        if ctx.get("early_return"):
            return ctx["early_return"]

        # Phase 2: AI 生成（async，不占 worker）
        gen_result = await ctx["generator"].generate_async(
            word=ctx["word_text"],
            meaning=ctx["meaning_text"],
            pos=ctx["pos"],
            _preloaded_config=ctx["ai_config"],
        )

        # Phase 3: 写回结果 + 质检
        return await asyncio.to_thread(
            self._regen_writeback_and_qc, session, ctx, gen_result, reviewer
        )

    @staticmethod
    def _do_regenerate(session: Session, content_item: ContentItem) -> None:
        """调用生成器重新生成单个 ContentItem 的内容。"""
        from vocab_qc.core.generators.base import estimate_cost
        from vocab_qc.core.models.data_layer import Meaning, Word
        from vocab_qc.core.models.quality_layer import AiUsageLog
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

        # 提取并记录 AI 用量（由 _do_request 附着 __usage__）
        usage = result.pop("__usage__", None)
        if usage and usage.total_tokens > 0:
            ai_config = generator.get_ai_config(session)
            session.add(AiUsageLog(
                phase="generation",
                dimension=content_item.dimension,
                ai_model=ai_config.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost_usd=estimate_cost(ai_config.model, usage),
                word_id=content_item.word_id,
                content_item_id=content_item.id,
                package_id=_lookup_package_id(session, content_item.word_id),
            ))

        if result.get("valid") is False:
            content_item.content = ""
            content_item.qc_status = QcStatus.REJECTED.value
            return

        content_item.content = result.get("content", "")
        if result.get("content_cn"):
            content_item.content_cn = result["content_cn"]
        # G 方案：记录本条生成时所用 prompt 的版本指纹（复用 usage 分支的 ai_config 否则现取）
        cfg = locals().get("ai_config") or generator.get_ai_config(session)
        content_item.generated_with_prompt_id = cfg.prompt_id
        content_item.generated_with_prompt_hash = cfg.prompt_hash

    def manual_edit(
        self,
        session: Session,
        review_id: int,
        reviewer: str,
        new_content: str,
        new_content_cn: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> dict:
        """人工修改内容 + 自动质检.

        Returns:
            {"success": bool, "qc_passed": bool, "message": str, "new_issues": list}
        """
        review = self._lock_review_item(session, review_id)
        self._check_concurrency(review, user_id)

        content_item = session.query(ContentItem).filter_by(id=review.content_item_id).one()

        old_content = content_item.content
        content_item.content = new_content
        if new_content_cn is not None:
            content_item.content_cn = new_content_cn

        content_item.qc_status = QcStatus.PENDING.value
        session.flush()

        # 自动运行质检（人工编辑跳过 Layer 2 AI 校验）
        qc_passed = self._run_qc_for_item(session, content_item, skip_layer2=True)

        if qc_passed:
            content_item.qc_status = QcStatus.APPROVED.value
            review.status = ReviewStatus.RESOLVED.value
            review.resolution = ReviewResolution.MANUAL_EDIT.value
            review.reviewer = reviewer
            review.resolved_at = datetime.now(UTC)
            message = "保存成功，质检通过"
        else:
            message = "已保存，但质检未通过，请继续修改"

        log_action(
            session,
            entity_type="content_item",
            entity_id=content_item.id,
            action="manual_edit",
            actor=reviewer,
            old_value={"content": old_content},
            new_value={"content": new_content},
        )

        logger.info("人工修改 review_id=%d reviewer=%s qc_passed=%s", review_id, reviewer, qc_passed)

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
            "retry_count": content_item.retry_count or 0,
            "message": message,
            "new_content": content_item.content,
            "new_content_cn": content_item.content_cn,
            "new_issues": new_issues,
        }

    def get_pending_reviews(
        self,
        session: Session,
        dimension: Optional[str] = None,
        batch_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ReviewItem], int]:
        """获取待审核队列，返回 (items, total)."""
        query = session.query(ReviewItem).filter_by(status=ReviewStatus.PENDING.value)
        if batch_id is not None:
            query = query.filter_by(batch_id=batch_id)
        if dimension:
            query = query.filter_by(dimension=dimension)
        total = query.count()
        items = query.order_by(ReviewItem.priority.desc(), ReviewItem.created_at).offset(offset).limit(limit).all()
        return items, total

    @staticmethod
    def _run_qc_for_item(session: Session, content_item: ContentItem, *, skip_layer2: bool = False) -> bool:
        """对单个内容项运行质检，返回是否全部通过。

        Args:
            skip_layer2: 为 True 时跳过 Layer 2 AI 语义校验（人工编辑场景）。
        """
        from vocab_qc.core.models.data_layer import Meaning, Phonetic, Word
        from vocab_qc.core.qc.layer2.runner import Layer2Runner
        from vocab_qc.core.qc.runner import Layer1Runner

        word = session.query(Word).filter_by(id=content_item.word_id).first()
        word_text = word.word if word else ""

        meaning_texts: dict[int, str] = {}
        extra: dict = {"content_cn": content_item.content_cn or ""}

        if content_item.meaning_id:
            meaning = session.query(Meaning).filter_by(id=content_item.meaning_id).first()
            if meaning:
                meaning_texts[meaning.id] = meaning.definition
                if meaning.pos:
                    extra["pos"] = meaning.pos

        phonetic = session.query(Phonetic).filter_by(word_id=content_item.word_id).first()
        if phonetic:
            extra["ipa_uk"] = phonetic.ipa_uk or ""
            extra["ipa_us"] = phonetic.ipa_us or ""
            extra["syllables"] = phonetic.syllables

        word_texts = {content_item.word_id: word_text}
        extra_kwargs = {content_item.id: extra}

        # Layer 1
        l1_runner = Layer1Runner()
        l1_runner.run(session, [content_item], word_texts, meaning_texts, extra_kwargs)

        if content_item.qc_status != QcStatus.LAYER1_PASSED.value:
            return False

        # Layer 2（仅对有 Layer 2 规则的维度执行；人工编辑时跳过）
        if skip_layer2:
            return True
        l2_runner = Layer2Runner()
        has_l2 = content_item.dimension in l2_runner._unified_checkers
        if has_l2:
            pkg_id = _lookup_package_id(session, content_item.word_id)
            l2_runner.run(
                session, [content_item], word_texts, meaning_texts,
                extra_kwargs=extra_kwargs, package_id=pkg_id,
            )
            return content_item.qc_status == QcStatus.LAYER2_PASSED.value

        # 无 Layer 2 规则的维度（如 syllable），Layer 1 通过即算通过
        return True

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
