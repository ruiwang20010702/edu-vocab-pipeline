"""批次派发服务: 按词分配审核批次，防并发碰撞."""

import logging
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import and_, distinct, exists, func, or_, select, update
from sqlalchemy.orm import Session

from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.enums import BatchStatus, QcStatus, ReviewReason, ReviewResolution, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem


def _repair_orphan_failed_items(session: Session) -> int:
    """为异常态且无 pending ReviewItem 的 ContentItem 自动补建审核项。

    覆盖三类孤儿：
    - layer1_failed / layer2_failed：竞态导致 ReviewItem 已 resolve 但 CI 仍 failed
    - layer1_passed：L2 QC 未执行或结果丢失，卡在中间态

    使用 savepoint 隔离，避免内部 IntegrityError 回滚影响外层事务。
    每次最多处理 500 条，超出部分留给下次 assign 处理。
    """
    from vocab_qc.core.config import settings
    from vocab_qc.core.services.review_service import ReviewService

    orphan_items = (
        session.query(ContentItem)
        .filter(
            ContentItem.qc_status.in_([
                QcStatus.LAYER1_FAILED.value,
                QcStatus.LAYER2_FAILED.value,
                QcStatus.LAYER1_PASSED.value,
            ]),
        )
        .filter(
            ~exists(
                select(ReviewItem.id).where(
                    ReviewItem.content_item_id == ContentItem.id,
                    ReviewItem.status == ReviewStatus.PENDING.value,
                )
            ),
        )
        # 排除"空内容且重试耗尽"的死锁项：给它们补 review 无意义（前端无重生出口），
        # 反而制造永久 pending 孤儿。这类由 _resolve_deadlocked_orphans 负责清理。
        .filter(
            ~and_(
                func.coalesce(ContentItem.content, "") == "",
                ContentItem.retry_count >= settings.ai_max_retries,
            )
        )
        .limit(500)
        .all()
    )
    if not orphan_items:
        return 0

    # 按实际状态分组，使用正确的 ReviewReason
    failed_items = [
        ci for ci in orphan_items
        if ci.qc_status in (QcStatus.LAYER1_FAILED.value, QcStatus.LAYER2_FAILED.value)
    ]
    l1_passed_items = [
        ci for ci in orphan_items
        if ci.qc_status == QcStatus.LAYER1_PASSED.value
    ]

    review_svc = ReviewService()
    count = 0

    # 用 savepoint 隔离，防止 create_review_items_batch 内部的
    # IntegrityError 回滚影响 assign_batch 已完成的工作（如批次完结）
    if failed_items:
        nested = session.begin_nested()
        try:
            count += review_svc.create_review_items_batch(
                session, failed_items, ReviewReason.LAYER1_FAILED, priority=10,
            )
            nested.commit()
        except Exception:
            nested.rollback()
            logger.exception("孤儿修复（failed）写入失败，跳过")

    if l1_passed_items:
        nested = session.begin_nested()
        try:
            count += review_svc.create_review_items_batch(
                session, l1_passed_items, ReviewReason.LAYER2_FAILED, priority=10,
            )
            nested.commit()
        except Exception:
            nested.rollback()
            logger.exception("孤儿修复（l1_passed）写入失败，跳过")

    if count > 0:
        logger.warning("自动补建孤儿 ReviewItem: %d 条（共 %d 个异常 ContentItem）", count, len(orphan_items))
    return count


def _resolve_deadlocked_orphans(session: Session, batch_id: Optional[int] = None) -> int:
    """自动解除"无 UI 出口"的死锁孤儿 pending ReviewItem。

    死锁定义：pending ReviewItem 指向的 content_item 满足下列任一：
    - qc_status='rejected'（AI 判定助记不适用，本应 resolved）；
    - content='' 且 retry_count >= ai_max_retries（空内容且重试耗尽，前端无重生出口）。

    这类项被前端归入"已拒绝助记"只读区且无解锁按钮，会让批次 pending_count 永远 >0
    而卡死、领不了下一批。在 assign 时主动 resolve 它们，使卡死批次自愈完结。

    batch_id 为 None 时全局清理（供一次性运维脚本复用）。
    用 savepoint 隔离，避免内部异常影响外层 assign 事务。
    """
    from vocab_qc.core.config import settings
    max_retries = settings.ai_max_retries
    query = (
        session.query(ReviewItem)
        .join(ContentItem, ContentItem.id == ReviewItem.content_item_id)
        .filter(ReviewItem.status == ReviewStatus.PENDING.value)
        .filter(
            or_(
                ContentItem.qc_status == QcStatus.REJECTED.value,
                and_(
                    func.coalesce(ContentItem.content, "") == "",
                    ContentItem.retry_count >= max_retries,
                ),
            )
        )
    )
    if batch_id is not None:
        query = query.filter(ReviewItem.batch_id == batch_id)
    orphans = query.all()
    if not orphans:
        return 0

    nested = session.begin_nested()
    try:
        affected_batches = set()
        for ri in orphans:
            ri.status = ReviewStatus.RESOLVED.value
            ri.resolution = ReviewResolution.REGENERATE.value
            ri.reviewer = "system:deadlock-cleanup"
            ri.resolved_at = datetime.now(UTC)
            if ri.batch_id is not None:
                affected_batches.add(ri.batch_id)
        session.flush()
        for bid in affected_batches:
            update_batch_progress(session, bid)
        nested.commit()
    except Exception:
        nested.rollback()
        logger.exception("死锁孤儿自愈写入失败，跳过")
        return 0

    logger.warning("自动解除死锁孤儿 ReviewItem: %d 条 (batch_id=%s)", len(orphans), batch_id)
    return len(orphans)


def assign_batch(session: Session, user_id: int, batch_size: int = 10) -> Optional[ReviewBatch]:
    """原子领取一批待审单词。

    按 word_id 分组，每个词的所有 ReviewItem 打包到同一批次。
    使用 SQLite 兼容的方式防并发（生产环境用 FOR UPDATE SKIP LOCKED）。
    """
    # 检查是否已有未完成的批次
    existing = (
        session.query(ReviewBatch)
        .filter_by(user_id=user_id, status=BatchStatus.IN_PROGRESS.value)
        .first()
    )
    if existing is not None:
        # 先自愈：解除本批次内"无 UI 出口"的死锁孤儿，避免它们让批次永久卡死、领不了下一批
        _resolve_deadlocked_orphans(session, existing.id)
        # 检查是否还有待审核项
        pending_count = (
            session.query(func.count())
            .select_from(ReviewItem)
            .filter_by(batch_id=existing.id, status=ReviewStatus.PENDING.value)
            .scalar()
        )
        if pending_count > 0:
            return existing
        # 无待审核项 → 自动完结该批次
        existing.status = BatchStatus.COMPLETED.value
        existing.completed_at = datetime.now(UTC)
        session.flush()

    # 前置检查：排除正在生产中的 Package 关联的 word
    from vocab_qc.core.models.package_layer import Package, PackageWord

    processing_word_ids = {
        row[0] for row in
        session.query(PackageWord.word_id)
        .join(Package, Package.id == PackageWord.package_id)
        .filter(Package.status == "processing")
        .all()
    }

    # 领取前全局自愈死锁孤儿：content='' 且达上限 / rejected 的 pending 项被 resolve，
    # 使其不进入下方 status=pending 的捞取，避免被打包进新批次卡住审核员（点开无内容）。
    # existing 分支（上方）的局部清理只治"上一批"，这里补全"新建批次"路径的同源缺口。
    _resolve_deadlocked_orphans(session)

    # 孤儿修复：失败的 ContentItem 无 pending ReviewItem 时自动补建
    _repair_orphan_failed_items(session)

    # Step 1: 查 word_ids（不加锁，DISTINCT 不兼容 FOR UPDATE）
    query_step1 = (
        session.query(distinct(ReviewItem.word_id))
        .filter_by(status=ReviewStatus.PENDING.value)
        .filter(ReviewItem.assigned_to_id.is_(None))
    )
    if processing_word_ids:
        query_step1 = query_step1.filter(~ReviewItem.word_id.in_(processing_word_ids))
    word_ids = [row[0] for row in query_step1.limit(batch_size).all()]
    if not word_ids:
        return None

    # Step 2: 锁定具体的 ReviewItem 行
    query = (
        session.query(ReviewItem)
        .filter(ReviewItem.word_id.in_(word_ids))
        .filter_by(status=ReviewStatus.PENDING.value)
        .filter(ReviewItem.assigned_to_id.is_(None))
    )
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect == "postgresql":
        query = query.with_for_update(skip_locked=True)
    items = query.all()
    if not items:
        # 并发场景下所有词已被他人领走
        return None

    # 创建批次
    actual_word_ids = {item.word_id for item in items}
    batch = ReviewBatch(
        user_id=user_id,
        status=BatchStatus.IN_PROGRESS.value,
        word_count=len(actual_word_ids),
        reviewed_count=0,
    )
    session.add(batch)
    session.flush()

    for item in items:
        item.batch_id = batch.id
        item.assigned_to_id = user_id

    session.flush()

    logger.info("批次领取 batch_id=%d user_id=%d word_count=%d item_count=%d", batch.id, user_id, len(actual_word_ids), len(items))

    return batch


def get_my_current_batch(session: Session, user_id: int) -> Optional[ReviewBatch]:
    """获取当前未完成的批次。"""
    return (
        session.query(ReviewBatch)
        .filter_by(user_id=user_id, status=BatchStatus.IN_PROGRESS.value)
        .first()
    )


def get_batch_words(session: Session, batch_id: int) -> dict:
    """获取批次中的单词及其审核项。

    返回: {"batch": ReviewBatch, "words": {word_id: [ReviewItem, ...]}}
    """
    batch = session.query(ReviewBatch).filter_by(id=batch_id).first()
    if batch is None:
        raise ValueError("批次不存在")
    items = session.query(ReviewItem).filter_by(batch_id=batch_id).all()

    words: dict[int, list[ReviewItem]] = {}
    for item in items:
        words.setdefault(item.word_id, []).append(item)

    return {"batch": batch, "words": words}


def skip_word(session: Session, batch_id: int, word_id: int, user_id: int) -> None:
    """跳过某词，释放回池中。"""
    batch = session.query(ReviewBatch).filter_by(id=batch_id).first()
    if batch is None:
        raise ValueError("批次不存在")
    if batch.user_id != user_id:
        raise ValueError("无权操作该批次")

    # 先验证该词是否在此批次中
    exists = (
        session.query(ReviewItem.id)
        .filter_by(batch_id=batch_id, word_id=word_id)
        .first()
    )
    if not exists:
        raise ValueError("该词不在此批次中")

    # 批量 UPDATE 替代逐条修改
    session.execute(
        update(ReviewItem)
        .where(ReviewItem.batch_id == batch_id, ReviewItem.word_id == word_id)
        .values(batch_id=None, assigned_to_id=None)
    )
    session.flush()
    update_batch_progress(session, batch_id)

    logger.info("跳过单词 batch_id=%d word_id=%d user_id=%d", batch_id, word_id, user_id)


def complete_batch(session: Session, batch_id: int, user_id: int) -> ReviewBatch:
    """标记批次完成。"""
    batch = session.query(ReviewBatch).filter_by(id=batch_id).first()
    if batch is None:
        raise ValueError("批次不存在")
    if batch.user_id != user_id:
        raise ValueError("无权操作该批次")

    batch.status = BatchStatus.COMPLETED.value
    batch.completed_at = datetime.now(UTC)
    session.flush()

    logger.info("批次完成 batch_id=%d user_id=%d", batch_id, user_id)

    return batch


def update_batch_progress(session: Session, batch_id: int) -> None:
    """更新批次中已审完的词数。当所有词审完时自动标记完成。"""
    if batch_id is None:
        return

    batch = session.query(ReviewBatch).filter_by(id=batch_id).first()
    if batch is None or batch.status != BatchStatus.IN_PROGRESS.value:
        return

    # 统计批次中所有 word_id
    total_word_ids = (
        session.query(distinct(ReviewItem.word_id))
        .filter_by(batch_id=batch_id)
        .all()
    )
    all_word_ids = {row[0] for row in total_word_ids}

    # 单条聚合查询：一次查出每个 word_id 的 pending 数量
    pending_counts = dict(
        session.query(ReviewItem.word_id, func.count())
        .filter_by(batch_id=batch_id, status=ReviewStatus.PENDING.value)
        .group_by(ReviewItem.word_id)
        .all()
    )
    reviewed_count = sum(1 for wid in all_word_ids if wid not in pending_counts)

    batch.word_count = len(all_word_ids)
    batch.reviewed_count = reviewed_count

    # 全部审完 → 自动完成
    if len(all_word_ids) == 0 or reviewed_count >= len(all_word_ids):
        batch.status = BatchStatus.COMPLETED.value
        batch.completed_at = datetime.now(UTC)
        # 释放残留的 pending items 回池中，防止变成僵尸
        session.execute(
            update(ReviewItem)
            .where(ReviewItem.batch_id == batch_id, ReviewItem.status == ReviewStatus.PENDING.value)
            .values(batch_id=None, assigned_to_id=None)
        )

    session.flush()


def release_batch(session: Session, batch_id: int, user_id: int) -> ReviewBatch:
    """释放批次：将未处理的审核项释放回池中，批次标记为完成。"""
    batch = session.query(ReviewBatch).filter_by(id=batch_id).first()
    if batch is None:
        raise ValueError("批次不存在")
    if batch.user_id != user_id:
        raise ValueError("无权操作该批次")
    if batch.status != BatchStatus.IN_PROGRESS.value:
        raise ValueError("该批次不可释放")

    # 批量释放所有 PENDING 状态的 ReviewItem（直接 UPDATE，省去 SELECT）
    session.execute(
        update(ReviewItem)
        .where(
            ReviewItem.batch_id == batch_id,
            ReviewItem.status == ReviewStatus.PENDING.value,
        )
        .values(batch_id=None, assigned_to_id=None)
    )

    batch.status = BatchStatus.COMPLETED.value
    batch.completed_at = datetime.now(UTC)
    session.flush()

    logger.info("批次释放 batch_id=%d user_id=%d", batch_id, user_id)

    return batch


def get_stats(session: Session) -> dict:
    """审核进度统计。"""
    total_words = (
        session.query(func.count(distinct(ReviewItem.word_id)))
        .filter_by(status=ReviewStatus.PENDING.value)
        .scalar()
    )

    reviewed_words = (
        session.query(func.count(distinct(ReviewItem.word_id)))
        .filter(ReviewItem.status != ReviewStatus.PENDING.value)
        .scalar()
    )

    # 各审核员进度
    reviewer_stats = (
        session.query(
            ReviewBatch.user_id,
            func.count(ReviewBatch.id).label("batch_count"),
            func.sum(ReviewBatch.reviewed_count).label("total_reviewed"),
        )
        .group_by(ReviewBatch.user_id)
        .all()
    )

    return {
        "pending_words": total_words or 0,
        "reviewed_words": reviewed_words or 0,
        "reviewers": [
            {
                "user_id": row.user_id,
                "batch_count": row.batch_count,
                "reviewed_words": int(row.total_reviewed or 0),
            }
            for row in reviewer_stats
        ],
    }
