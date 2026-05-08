"""通用重置脚本：把指定 package + 维度 + 状态的 ContentItem 重置为 pending，便于按新 prompt 重生产。

背景:
    prompt 升级后需要让历史 approved/rejected 的 mnemonic 内容走新 prompt 重生产。
    本脚本按 --package + --dimensions + --statuses 三个白名单精确圈定要重置的 item，
    清空 content 并删除关联 review_items，下一次 produce_batch 会重新生成。

⚠️ 高风险操作:
    - DELETE review_items（审核员的工作记录会丢失）
    - UPDATE content_items 状态从 approved/rejected → pending
    必须先 dry-run 确认命中数符合预期，再加 --execute。

用法:
    # dry-run 看影响
    PYTHONPATH=backend python3 scripts/reset_mnemonic_for_regen.py \
        --package "剑桥释义_101_150词" \
        --dimensions mnemonic_exam_app,mnemonic_word_in_word,mnemonic_root_affix,mnemonic_sound_meaning \
        --statuses approved,rejected

    # 确认后执行
    PYTHONPATH=backend python3 scripts/reset_mnemonic_for_regen.py \
        --package "剑桥释义_101_150词" \
        --dimensions mnemonic_exam_app,mnemonic_word_in_word,mnemonic_root_affix,mnemonic_sound_meaning \
        --statuses approved,rejected \
        --execute
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS, QcStatus

ALLOWED_STATUSES = {s.value for s in QcStatus}
DEFAULT_DIMENSIONS = ",".join(sorted(MNEMONIC_DIMENSIONS))
DEFAULT_STATUSES = "approved,rejected"


def _parse_csv(raw: str, label: str, allowed: set[str]) -> list[str]:
    items = [s.strip() for s in raw.split(",") if s.strip()]
    if not items:
        raise ValueError(f"--{label} 不能为空")
    bad = [s for s in items if s not in allowed]
    if bad:
        raise ValueError(f"--{label} 含非法值 {bad}，可选: {sorted(allowed)}")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--package", required=True, help="批次名（必填，例如 '剑桥释义_101_150词'）")
    parser.add_argument(
        "--dimensions",
        default=DEFAULT_DIMENSIONS,
        help=f"维度白名单（逗号分隔，默认 4 个 mnemonic）。可选: {sorted(MNEMONIC_DIMENSIONS)}",
    )
    parser.add_argument(
        "--statuses",
        default=DEFAULT_STATUSES,
        help=f"qc_status 白名单（逗号分隔，默认 {DEFAULT_STATUSES}）。可选: {sorted(ALLOWED_STATUSES)}",
    )
    parser.add_argument("--execute", action="store_true", help="真正执行变更（默认 dry-run）")
    args = parser.parse_args()

    dimensions = _parse_csv(args.dimensions, "dimensions", set(MNEMONIC_DIMENSIONS) | ALLOWED_STATUSES)
    # dimensions 严格限定在 mnemonic 范围（防止误伤其他维度）
    bad_dims = [d for d in dimensions if d not in MNEMONIC_DIMENSIONS]
    if bad_dims:
        raise SystemExit(f"--dimensions 必须是 mnemonic 维度，非法值: {bad_dims}")

    statuses = _parse_csv(args.statuses, "statuses", ALLOWED_STATUSES)
    # 终态以外的状态本身就在 pending 流水线里，不允许传
    if any(s == QcStatus.PENDING.value for s in statuses):
        raise SystemExit("--statuses 不允许传 pending（已经是目标态）")

    print("⚠️  --execute 模式" if args.execute else "🔍 dry-run 模式")
    print(f"  限定批次:   {args.package}")
    print(f"  维度白名单: {dimensions}")
    print(f"  状态白名单: {statuses}")
    print()

    with SyncSessionLocal() as session:
        try:
            rows = session.execute(
                text(
                    """
                    SELECT ci.id, ci.dimension, ci.qc_status, w.word
                    FROM content_items ci
                    JOIN package_words pw ON pw.word_id = ci.word_id
                    JOIN packages p ON p.id = pw.package_id
                    JOIN words w ON w.id = ci.word_id
                    WHERE p.name = :pkg
                      AND ci.dimension = ANY(:dims)
                      AND ci.qc_status = ANY(:statuses)
                    ORDER BY ci.dimension, ci.qc_status, w.word
                    """
                ),
                {"pkg": args.package, "dims": dimensions, "statuses": statuses},
            ).fetchall()

            if not rows:
                print("  ⚠️  无命中，请检查 --package 名称是否正确")
                session.rollback()
                return

            ci_ids = [r[0] for r in rows]
            counter = Counter((r[1], r[2]) for r in rows)

            ri_count = (
                session.execute(
                    text("SELECT COUNT(*) FROM review_items WHERE content_item_id = ANY(:ids)"),
                    {"ids": ci_ids},
                ).scalar()
                or 0
            )

            distinct_words = len({r[3] for r in rows})

            print("═══ 命中预览 ═══")
            print(f"  涉及单词数:     {distinct_words}")
            print(f"  ContentItem 数: {len(ci_ids)}")
            print(f"  关联 review_items（将级联删除）: {ri_count}")
            print()
            print("  按维度 × 状态分组:")
            for (dim, st), cnt in sorted(counter.items()):
                print(f"    {dim:30s}  {st:10s}  {cnt:5d}")

            if not args.execute:
                session.rollback()
                print("\n  (dry-run，未执行)")
                return

            # --- execute ---
            session.execute(
                text("DELETE FROM review_items WHERE content_item_id = ANY(:ids)"),
                {"ids": ci_ids},
            )
            session.execute(
                text(
                    """
                    UPDATE content_items
                    SET qc_status = :pending,
                        content = '',
                        content_cn = '',
                        last_qc_run_id = NULL,
                        retry_count = 0
                    WHERE id = ANY(:ids)
                    """
                ),
                {"pending": QcStatus.PENDING.value, "ids": ci_ids},
            )
            session.commit()
            print(f"\n  ✅ 重置 {len(ci_ids)} 条 ContentItem，删除 {ri_count} 条 review_item")
        except Exception:
            session.rollback()
            print("\n❌ 出错回滚")
            raise


if __name__ == "__main__":
    main()
