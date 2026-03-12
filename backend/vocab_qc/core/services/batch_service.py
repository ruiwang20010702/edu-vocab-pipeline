"""批次派发服务: 按词分配审核批次，防并发碰撞."""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.enums import BatchStatus, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem


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

    # Step 1: 查 word_ids（不加锁，DISTINCT 不兼容 FOR UPDATE）
    word_ids = [
        row[0] for row in
        session.query(distinct(ReviewItem.word_id))
        .filter_by(status=ReviewStatus.PENDING.value)
        .filter(ReviewItem.assigned_to_id.is_(None))
        .limit(batch_size)
        .all()
    ]
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

    items = (
        session.query(ReviewItem)
        .filter_by(batch_id=batch_id, word_id=word_id)
        .all()
    )
    if not items:
        raise ValueError("该词不在此批次中")

    for item in items:
        item.batch_id = None
        item.assigned_to_id = None

    session.flush()
    update_batch_progress(session, batch_id)


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

    # 释放所有 PENDING 状态的 ReviewItem
    pending_items = (
        session.query(ReviewItem)
        .filter_by(batch_id=batch_id, status=ReviewStatus.PENDING.value)
        .all()
    )
    for item in pending_items:
        item.batch_id = None
        item.assigned_to_id = None

    batch.status = BatchStatus.COMPLETED.value
    batch.completed_at = datetime.now(UTC)
    session.flush()
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
