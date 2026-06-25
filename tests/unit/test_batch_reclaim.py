"""批次自愈单测：陈旧批次6h空闲回收 + 空内容死锁孤儿自愈。"""

from datetime import UTC, datetime, timedelta

from vocab_qc.core.config import settings
from vocab_qc.core.models import ContentItem, ReviewItem, Word
from vocab_qc.core.models.batch_layer import ReviewBatch
from vocab_qc.core.models.enums import ReviewReason
from vocab_qc.core.services import batch_service


def _mk_word(db, name):
    w = Word(word=name)
    db.add(w)
    db.flush()
    return w


# ── 改动1：陈旧批次自动回收 ──


def test_reclaim_stale_batch_releases_items(db_session):
    """in_progress 批次空闲超 6h（无 resolved 动作）→ pending 项回池 + 批次完结。"""
    w = _mk_word(db_session, "staleword")
    ci = ContentItem(word_id=w.id, dimension="chunk", content="x", qc_status="layer2_failed", retry_count=0)
    db_session.add(ci)
    db_session.flush()
    batch = ReviewBatch(user_id=99, status="in_progress", word_count=1, reviewed_count=0)
    db_session.add(batch)
    db_session.flush()
    ri = ReviewItem(
        content_item_id=ci.id, word_id=w.id, dimension="chunk",
        reason=ReviewReason.LAYER2_FAILED.value, status="pending",
        batch_id=batch.id, assigned_to_id=99,
    )
    db_session.add(ri)
    db_session.flush()
    batch.created_at = datetime.now(UTC) - timedelta(hours=settings.review_batch_idle_timeout_hours + 1)
    db_session.commit()

    n = batch_service._reclaim_stale_batches(db_session)
    db_session.refresh(batch)
    db_session.refresh(ri)
    assert n == 1
    assert batch.status == "completed"
    assert ri.batch_id is None and ri.assigned_to_id is None


def test_active_batch_not_reclaimed(db_session):
    """批次虽老，但最近有 resolved 审核动作 → 不回收（按空闲而非创建时间）。"""
    w = _mk_word(db_session, "activeword")
    ci1 = ContentItem(word_id=w.id, dimension="chunk", content="x", qc_status="approved", retry_count=0)
    ci2 = ContentItem(word_id=w.id, dimension="sentence", content="x", qc_status="layer2_failed", retry_count=0)
    db_session.add_all([ci1, ci2])
    db_session.flush()
    batch = ReviewBatch(user_id=99, status="in_progress", word_count=1, reviewed_count=1)
    db_session.add(batch)
    db_session.flush()
    db_session.add_all([
        ReviewItem(
            content_item_id=ci1.id, word_id=w.id, dimension="chunk",
            reason=ReviewReason.LAYER2_FAILED.value, status="resolved", resolution="approved",
            resolved_at=datetime.now(UTC), batch_id=batch.id, assigned_to_id=99,
        ),
        ReviewItem(
            content_item_id=ci2.id, word_id=w.id, dimension="sentence",
            reason=ReviewReason.LAYER2_FAILED.value, status="pending",
            batch_id=batch.id, assigned_to_id=99,
        ),
    ])
    db_session.flush()
    batch.created_at = datetime.now(UTC) - timedelta(hours=settings.review_batch_idle_timeout_hours + 1)
    db_session.commit()

    n = batch_service._reclaim_stale_batches(db_session)
    db_session.refresh(batch)
    assert n == 0
    assert batch.status == "in_progress"


# ── 改动2：空内容死锁孤儿自愈 ──


def test_reject_dead_empty_orphan(db_session):
    """空内容 + 重试耗尽 + 无 pending 审核项 → 置 rejected 终态出列。"""
    w = _mk_word(db_session, "orphanword")
    ci = ContentItem(
        word_id=w.id, dimension="mnemonic_word_in_word", content="",
        qc_status="layer2_failed", retry_count=settings.ai_max_retries,
    )
    db_session.add(ci)
    db_session.commit()

    n = batch_service._reject_dead_empty_orphans(db_session)
    db_session.refresh(ci)
    assert n == 1
    assert ci.qc_status == "rejected"


def test_orphan_not_rejected_when_content_or_retry_left(db_session):
    """有内容、或空但还能重试 → 不拒（仅清理真不可救的）。"""
    w = _mk_word(db_session, "keepword")
    ci_content = ContentItem(
        word_id=w.id, dimension="chunk", content="有内容",
        qc_status="layer2_failed", retry_count=settings.ai_max_retries,
    )
    ci_retry = ContentItem(
        word_id=w.id, dimension="sentence", content="",
        qc_status="layer2_failed", retry_count=0,
    )
    db_session.add_all([ci_content, ci_retry])
    db_session.commit()

    n = batch_service._reject_dead_empty_orphans(db_session)
    db_session.refresh(ci_content)
    db_session.refresh(ci_retry)
    assert n == 0
    assert ci_content.qc_status == "layer2_failed"
    assert ci_retry.qc_status == "layer2_failed"


def test_dead_empty_with_pending_review_not_touched(db_session):
    """空内容项若仍挂 pending 审核项，归 _resolve_deadlocked_orphans 处理，这里不碰。"""
    w = _mk_word(db_session, "pendingorphan")
    ci = ContentItem(
        word_id=w.id, dimension="mnemonic_sound_meaning", content="",
        qc_status="layer2_failed", retry_count=settings.ai_max_retries,
    )
    db_session.add(ci)
    db_session.flush()
    db_session.add(ReviewItem(
        content_item_id=ci.id, word_id=w.id, dimension="mnemonic_sound_meaning",
        reason=ReviewReason.LAYER2_FAILED.value, status="pending",
    ))
    db_session.commit()

    n = batch_service._reject_dead_empty_orphans(db_session)
    db_session.refresh(ci)
    assert n == 0
    assert ci.qc_status == "layer2_failed"
