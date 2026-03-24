"""一次性脚本：为已有的 AiUsageLog 回填 package_id。

用法:
    PYTHONPATH=backend python3 scripts/backfill_usage_package_id.py [--dry-run]

逻辑:
1. phase='generation' 且 package_id IS NULL 且 word_id IS NOT NULL
   → 通过 package_words 表 JOIN 回填 package_id
2. phase='qc_layer2' 且 package_id IS NULL
   → 通过时间范围匹配最近 processing/completed 的 Package（近似归因）
"""

import argparse
import sys
from pathlib import Path

# 确保能 import backend 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text

from vocab_qc.core.db import SyncSessionLocal


def backfill_generation(session, dry_run: bool) -> int:
    """回填 generation 阶段的 package_id（精确归因）。"""
    sql = text("""
        UPDATE ai_usage_logs
        SET package_id = pw.package_id
        FROM package_words pw
        WHERE ai_usage_logs.word_id = pw.word_id
          AND ai_usage_logs.phase = 'generation'
          AND ai_usage_logs.package_id IS NULL
          AND ai_usage_logs.word_id IS NOT NULL
    """)

    if dry_run:
        count_sql = text("""
            SELECT COUNT(*) FROM ai_usage_logs u
            JOIN package_words pw ON u.word_id = pw.word_id
            WHERE u.phase = 'generation'
              AND u.package_id IS NULL
              AND u.word_id IS NOT NULL
        """)
        count = session.execute(count_sql).scalar()
        print(f"[DRY-RUN] generation 阶段待回填: {count} 条")
        return count

    result = session.execute(sql)
    count = result.rowcount
    print(f"generation 阶段已回填: {count} 条")
    return count


def backfill_qc_layer2(session, dry_run: bool) -> int:
    """回填 qc_layer2 阶段的 package_id（按时间范围近似归因）。

    策略：找到每条 L2 usage log 创建时间前最近一个 status='processing' 或 'completed'
    的 Package，将其 package_id 赋值给该 log。
    """
    # 对于 PostgreSQL，使用 LATERAL JOIN 找最近 Package
    sql = text("""
        UPDATE ai_usage_logs u
        SET package_id = nearest_pkg.id
        FROM (
            SELECT DISTINCT ON (u2.id) u2.id AS log_id, p.id
            FROM ai_usage_logs u2
            CROSS JOIN LATERAL (
                SELECT p.id
                FROM packages p
                WHERE p.started_at IS NOT NULL
                  AND p.started_at <= u2.created_at
                ORDER BY p.started_at DESC
                LIMIT 1
            ) p
            WHERE u2.phase = 'qc_layer2'
              AND u2.package_id IS NULL
        ) nearest_pkg
        WHERE u.id = nearest_pkg.log_id
    """)

    if dry_run:
        count_sql = text("""
            SELECT COUNT(*) FROM ai_usage_logs
            WHERE phase = 'qc_layer2' AND package_id IS NULL
        """)
        count = session.execute(count_sql).scalar()
        print(f"[DRY-RUN] qc_layer2 阶段待回填: {count} 条（近似归因）")
        return count

    try:
        result = session.execute(sql)
        count = result.rowcount
        print(f"qc_layer2 阶段已回填: {count} 条（近似归因）")
        return count
    except Exception as e:
        # SQLite 不支持 LATERAL JOIN，跳过
        print(f"qc_layer2 回填跳过（可能是 SQLite 不支持）: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="回填 AiUsageLog 的 package_id")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不执行更新")
    args = parser.parse_args()

    session = SyncSessionLocal()
    try:
        gen_count = backfill_generation(session, args.dry_run)
        l2_count = backfill_qc_layer2(session, args.dry_run)

        if not args.dry_run:
            session.commit()
            print(f"\n总计回填: {gen_count + l2_count} 条，已提交。")
        else:
            print(f"\n[DRY-RUN] 总计待回填: {gen_count + l2_count} 条")
    except Exception as e:
        session.rollback()
        print(f"回填失败: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
