"""一次性运维脚本：为「生产异常终止(status=failed)」的 Package 补跑自动批准。

背景：_run_production_bg 在 any_failed=True 时只标 pkg.status='failed'，跳过了
step_finalize（其中含 _auto_approve_passed）。导致已通过全部质检的 layer2_passed
内容卡在「未批准」，合格率虚低。本脚本复用 _auto_approve_passed 补跑批准，并把
status 修正为 completed。

判定与现有生产流水线一致：
  - layer2_passed → approved
  - layer1_passed 且该维度无 L2 规则（如 syllable）→ approved

用法：
    PYTHONPATH=backend python scripts/approve_passed_package.py --package 19            # 预览
    PYTHONPATH=backend python scripts/approve_passed_package.py --package 19 --apply
"""

import argparse

from sqlalchemy import func
from sqlalchemy.orm import Session
from vocab_qc.core.db import sync_engine
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package
from vocab_qc.core.services.production_service import (
    _auto_approve_passed,
    _get_word_ids_for_package,
)

# 有 L2 规则的维度（与 _auto_approve_passed 内的判定保持一致）
L2_DIMENSIONS = {
    "sentence", "chunk", "mnemonic_root_affix",
    "mnemonic_word_in_word", "mnemonic_sound_meaning", "mnemonic_exam_app",
}


def main():
    ap = argparse.ArgumentParser(description="为异常终止的 Package 补跑自动批准")
    ap.add_argument("--package", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="真正写库（默认仅预览）")
    args = ap.parse_args()

    with Session(sync_engine) as s:
        pkg = s.query(Package).filter_by(id=args.package).first()
        if pkg is None:
            raise SystemExit(f"package {args.package} 不存在")
        word_ids = set(_get_word_ids_for_package(s, args.package))
        total_ci = (
            s.query(func.count(ContentItem.id))
            .filter(ContentItem.word_id.in_(word_ids))
            .scalar()
        )
        approved_before = (
            s.query(func.count(ContentItem.id))
            .filter(ContentItem.word_id.in_(word_ids),
                    ContentItem.qc_status == QcStatus.APPROVED.value)
            .scalar()
        )
        # 将被批准的两类
        n_l2 = (
            s.query(func.count(ContentItem.id))
            .filter(ContentItem.word_id.in_(word_ids),
                    ContentItem.qc_status == QcStatus.LAYER2_PASSED.value)
            .scalar()
        )
        n_l1_no_l2 = (
            s.query(func.count(ContentItem.id))
            .filter(ContentItem.word_id.in_(word_ids),
                    ContentItem.qc_status == QcStatus.LAYER1_PASSED.value,
                    ~ContentItem.dimension.in_(L2_DIMENSIONS))
            .scalar()
        )
        will_approve = n_l2 + n_l1_no_l2
        after = approved_before + will_approve

        print(f"package {pkg.id} {pkg.name!r}")
        print(f"  status={pkg.status} processed={pkg.processed_words}/{pkg.total_words} 关联词={len(word_ids)}")
        print(f"  content_items 总数={total_ci}")
        print(f"  当前 approved={approved_before} ({100*approved_before//max(total_ci,1)}%)")
        print(f"  将批准: layer2_passed={n_l2} + layer1_passed(无L2维度)={n_l1_no_l2} = {will_approve}")
        print(f"  批准后 approved={after} ({100*after//max(total_ci,1)}%)")
        print("  status 将修正: failed → completed")

        if not args.apply:
            print("\n[dry-run] 未写库。确认无误后加 --apply 执行。")
            return

        n = _auto_approve_passed(s, word_ids)
        pkg.status = "completed"
        if pkg.completed_at is None:
            from datetime import UTC, datetime
            pkg.completed_at = datetime.now(UTC)
        s.commit()
        print(f"\n[applied] 自动批准 {n} 条，package.status → completed。")


if __name__ == "__main__":
    main()
