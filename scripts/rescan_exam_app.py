"""一次性脚本：回扫 mnemonic_exam_app 维度的 layer1 漏检数据。

背景:
    5-08 prompt 升级新增 exam_sentence 字段后，新生产的部分数据 LLM 漏字段
    但 status 仍被标为 approved（layer1 应 fail 但漏判）。本脚本把这部分
    "v3 时代 approved 但不达标"的 ContentItem 重置为 pending，让生产编排
    重新跑（应用新 prompt）。

⚠️ 历史决策（commit 06050a7）：v3 prompt 升级**不回灌**历史 v2 时代数据。
    所以脚本默认只扫指定 package（一般是 18单词），不动其他批次。

排除项:
    - dimension != mnemonic_exam_app
    - content 已包含 exam_sentence 字段
    - 显式排除清单 EXCLUDED_WORDS（保留历史决策的真旧数据）
    - 默认按 --package 过滤（限定批次范围）

用法:
    PYTHONPATH=backend python3 scripts/rescan_exam_app.py --package 18单词
    PYTHONPATH=backend python3 scripts/rescan_exam_app.py --package 18单词 --execute
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.qc.layer1.mnemonic_rules import N6ExamSentence

# 保留旧风格内容、不重置的词清单（历史已 approve 的 v2 风格内容）
EXCLUDED_WORDS = {"firework"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True,
                        help="限定批次名（必填，例如 '18单词'）")
    parser.add_argument("--execute", action="store_true",
                        help="真正执行变更（默认 dry-run）")
    args = parser.parse_args()
    print("⚠️  --execute 模式" if args.execute else "🔍 dry-run 模式")
    print(f"  限定批次: {args.package}")

    rule = N6ExamSentence()
    with SyncSessionLocal() as session:
        try:
            rows = session.execute(text("""
                SELECT ci.id, w.word, ci.qc_status, ci.content
                FROM content_items ci
                JOIN meanings m ON m.id = ci.meaning_id
                JOIN words w ON w.id = m.word_id
                JOIN package_words pw ON pw.word_id = w.id
                JOIN packages p ON p.id = pw.package_id
                WHERE ci.dimension = 'mnemonic_exam_app'
                  AND ci.qc_status = :approved
                  AND p.name = :pkg
                ORDER BY w.word
            """), {"approved": QcStatus.APPROVED.value, "pkg": args.package}).fetchall()

            to_reset: list[tuple[int, str]] = []  # (ci_id, word)
            for ciid, word, _, content in rows:
                if word in EXCLUDED_WORDS:
                    continue
                result = rule.check(content=content, word=word, dimension="mnemonic_exam_app")
                if not result.passed:
                    to_reset.append((ciid, word))

            print(f"\n═══ 扫描结果 ═══")
            print(f"  approved 总数: {len(rows)}")
            print(f"  应重置（N6 失败 + 不在排除清单）: {len(to_reset)}")
            for ciid, word in to_reset:
                print(f"    ci_id={ciid:5d}  word={word}")

            if not to_reset:
                print("\n  无需操作")
                session.rollback()
                return

            ci_ids = [ciid for ciid, _ in to_reset]
            ri_count = session.execute(
                text("SELECT COUNT(*) FROM review_items WHERE content_item_id = ANY(:ids)"),
                {"ids": ci_ids},
            ).scalar() or 0
            print(f"\n  关联 review_items 将级联删除: {ri_count}")

            if args.execute:
                # 1. 删除关联 review_items（这些 review 是基于不达标的 content 做的）
                session.execute(
                    text("DELETE FROM review_items WHERE content_item_id = ANY(:ids)"),
                    {"ids": ci_ids},
                )
                # 2. 重置 ContentItem：status → pending, content → '', last_qc_run_id → NULL
                session.execute(
                    text("""
                        UPDATE content_items
                        SET qc_status = :pending, content = '', content_cn = '',
                            last_qc_run_id = NULL, retry_count = 0
                        WHERE id = ANY(:ids)
                    """),
                    {"pending": QcStatus.PENDING.value, "ids": ci_ids},
                )
                session.commit()
                print(f"  ✅ 已重置 {len(ci_ids)} 条 ContentItem 为 pending，删除 {ri_count} 条 review_item")
            else:
                session.rollback()
                print(f"  (dry-run，未执行)")
        except Exception:
            session.rollback()
            print("\n❌ 出错回滚")
            raise


if __name__ == "__main__":
    main()
