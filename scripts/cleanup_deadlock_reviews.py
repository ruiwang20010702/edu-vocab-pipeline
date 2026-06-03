"""一次性运维脚本：解除审核后台"无 UI 出口"的死锁孤儿 pending ReviewItem。

背景：当某助记 content_item 处于 rejected，或 (content='' 且 retry_count 已达上限) 时，
前端把它归入"已拒绝助记"只读区且无解锁按钮，但其 ReviewItem 仍 pending，导致批次
pending_count 永远 >0、领不了下一批（confine 词即此例）。本脚本批量将这类 review
置 resolved，解开卡死批次。

判定与清理逻辑复用 batch_service._resolve_deadlocked_orphans（单一事实来源）。

用法：
    # 预览（默认，不写库）
    PYTHONPATH=backend python scripts/cleanup_deadlock_reviews.py
    # 执行
    PYTHONPATH=backend python scripts/cleanup_deadlock_reviews.py --apply

回滚：将打印出的 review_ids 的 status 改回 'pending'、resolution/resolved_at/reviewer 置空。
"""

import argparse

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from vocab_qc.core.config import settings
from vocab_qc.core.db import sync_engine
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Word
from vocab_qc.core.models.enums import QcStatus, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.services.batch_service import _resolve_deadlocked_orphans


def _query_orphans(session: Session):
    """与 _resolve_deadlocked_orphans 同口径：列出将被解除的死锁孤儿明细。"""
    max_retries = settings.ai_max_retries
    return (
        session.query(ReviewItem, ContentItem, Word)
        .join(ContentItem, ContentItem.id == ReviewItem.content_item_id)
        .join(Word, Word.id == ReviewItem.word_id)
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
        .order_by(ReviewItem.batch_id, Word.word)
        .all()
    )


def main():
    parser = argparse.ArgumentParser(description="解除死锁孤儿 pending ReviewItem")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认仅预览）")
    args = parser.parse_args()

    with Session(sync_engine) as session:
        rows = _query_orphans(session)
        print(f"=== 死锁孤儿 pending ReviewItem: {len(rows)} 条 ===")
        batch_counts: dict = {}
        review_ids = []
        for ri, ci, w in rows:
            review_ids.append(ri.id)
            if ri.batch_id is not None:
                batch_counts[ri.batch_id] = batch_counts.get(ri.batch_id, 0) + 1
            clen = len(ci.content or "")
            print(
                f"  review#{ri.id} batch={ri.batch_id} word={w.word!r} "
                f"dim={ci.dimension} qc={ci.qc_status} retry={ci.retry_count} clen={clen}"
            )
        print(f"\n受影响批次（batch_id: 条数）: {dict(sorted(batch_counts.items()))}")

        if not args.apply:
            print("\n[dry-run] 未写库。确认无误后加 --apply 执行。")
            return

        n = _resolve_deadlocked_orphans(session)
        session.commit()
        print(f"\n[applied] 已解除 {n} 条死锁孤儿。")
        print(f"涉及 review_ids = {review_ids}")
        print("回滚：将这些 review 的 status 改回 'pending'，resolution/resolved_at/reviewer 置空。")


if __name__ == "__main__":
    main()
