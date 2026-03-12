"""一次性修复脚本：为 layer1/2_failed 且无 pending ReviewItem 的 ContentItem 补建审核项.

用法：
    PYTHONPATH=backend python scripts/fix_orphan_failed_items.py [--dry-run]
"""

import argparse
import sys

from sqlalchemy.orm import Session

from vocab_qc.core.db import sync_engine
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.enums import QcStatus, ReviewReason, ReviewStatus
from vocab_qc.core.models.quality_layer import ReviewItem
from vocab_qc.core.services.review_service import ReviewService


def find_orphan_failed_items(session: Session) -> list[ContentItem]:
    """查找所有 failed 且无 pending ReviewItem 的 ContentItem."""
    pending_review_item_ids = (
        session.query(ReviewItem.content_item_id)
        .filter(ReviewItem.status == ReviewStatus.PENDING.value)
        .subquery()
    )
    return (
        session.query(ContentItem)
        .filter(
            ContentItem.qc_status.in_([
                QcStatus.LAYER1_FAILED.value,
                QcStatus.LAYER2_FAILED.value,
            ]),
            ContentItem.id.notin_(session.query(pending_review_item_ids)),
        )
        .all()
    )


def main():
    parser = argparse.ArgumentParser(description="为孤立 failed 项补建 ReviewItem")
    parser.add_argument("--dry-run", action="store_true", help="仅打印，不写入")
    args = parser.parse_args()

    review_svc = ReviewService()

    with Session(sync_engine) as session:
        orphans = find_orphan_failed_items(session)
        print(f"找到 {len(orphans)} 个孤立 failed 项：")
        for item in orphans:
            reason = (
                ReviewReason.LAYER2_FAILED
                if item.qc_status == QcStatus.LAYER2_FAILED.value
                else ReviewReason.LAYER1_FAILED
            )
            print(f"  - ContentItem#{item.id} word_id={item.word_id} "
                  f"dim={item.dimension} status={item.qc_status} → {reason.value}")
            if not args.dry_run:
                review_svc.create_review_item(session, item, reason, priority=10)

        if args.dry_run:
            print("\n[DRY RUN] 未写入数据库。")
        else:
            session.commit()
            print(f"\n已为 {len(orphans)} 个项创建 ReviewItem。")


if __name__ == "__main__":
    main()
