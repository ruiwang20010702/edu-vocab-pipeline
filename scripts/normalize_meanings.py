"""一次性脚本：规范化 meanings 表的 pos / definition + 合并重复义项。

用法:
    # 默认 dry-run：只打印变更计划，不动数据
    PYTHONPATH=backend python3 scripts/normalize_meanings.py

    # 真正执行（事务化，失败回滚）
    PYTHONPATH=backend python3 scripts/normalize_meanings.py --execute

逻辑:
1. 阶段 1：全表规范化 pos / definition（复用 import_service 的规范化函数）
2. 阶段 2：合并按归一化 key 重复的义项 —— 保留 created_at 最早的为主，
   把其他义项的 ContentItem/Source 转移或删除（"旧胜"策略）

⚠️ 执行前请先备份 meanings / content_items / review_items / sources / retry_counters 表
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text

from vocab_qc.core.db import SyncSessionLocal
from vocab_qc.core.services.import_service import _normalize_definition, _normalize_pos


def stage1_normalize(session, *, execute: bool) -> dict:
    """阶段 1：全表规范化 pos + definition。"""
    rows = session.execute(text("SELECT id, pos, definition FROM meanings")).fetchall()
    pos_changes: list[tuple[int, str, str]] = []  # (id, old, new)
    def_changes: list[tuple[int, str, str]] = []
    for mid, pos, defi in rows:
        new_pos = _normalize_pos(pos or "")
        new_def = _normalize_definition(defi or "")
        if new_pos != (pos or ""):
            pos_changes.append((mid, pos, new_pos))
        if new_def != (defi or ""):
            def_changes.append((mid, defi, new_def))

    print(f"\n═══ 阶段 1: 全表规范化 ═══")
    print(f"  POS 将更新: {len(pos_changes)} 条")
    for mid, old, new in pos_changes[:10]:
        print(f"    meaning_id={mid:5d}  {old!r:10s} → {new!r}")
    if len(pos_changes) > 10:
        print(f"    ... (还有 {len(pos_changes) - 10} 条)")

    print(f"  Definition 将更新: {len(def_changes)} 条")
    for mid, old, new in def_changes[:10]:
        print(f"    meaning_id={mid:5d}  {old!r}  →  {new!r}")
    if len(def_changes) > 10:
        print(f"    ... (还有 {len(def_changes) - 10} 条)")

    if execute:
        for mid, _, new_pos in pos_changes:
            session.execute(text("UPDATE meanings SET pos = :p WHERE id = :id"), {"p": new_pos, "id": mid})
        for mid, _, new_def in def_changes:
            session.execute(text("UPDATE meanings SET definition = :d WHERE id = :id"), {"d": new_def, "id": mid})
        session.flush()
        print(f"  ✅ 已执行 {len(pos_changes)} 个 pos UPDATE + {len(def_changes)} 个 definition UPDATE")
    else:
        print(f"  (dry-run，未执行)")

    return {"pos_updates": len(pos_changes), "def_updates": len(def_changes)}


def stage2_merge_duplicates(session, *, execute: bool) -> dict:
    """阶段 2：合并按归一化 key 重复的义项（保留最早的，删除晚来的）。"""
    # 此时阶段 1 已让 pos/definition 入库时即规范化（execute 模式下），
    # 但为了 dry-run 也准确，统一用归一化函数计算 key 再分组
    rows = session.execute(text("""
        SELECT m.id, m.word_id, m.pos, m.definition, m.created_at
        FROM meanings m ORDER BY m.created_at ASC, m.id ASC
    """)).fetchall()

    groups: dict[tuple[int, str, str], list] = defaultdict(list)
    for mid, wid, pos, defi, ct in rows:
        key = (wid, _normalize_pos(pos or ""), _normalize_definition(defi or ""))
        groups[key].append((mid, ct))

    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"\n═══ 阶段 2: 合并重复义项 ═══")
    print(f"  按归一化 key 重复的组: {len(duplicate_groups)}")

    total_deleted_meanings = 0
    total_deleted_ci = 0
    total_deleted_ri = 0
    total_deleted_src = 0

    for key, members in duplicate_groups.items():
        wid, npos, ndef = key
        members.sort(key=lambda x: (x[1], x[0]))  # created_at 升序
        keep_id = members[0][0]
        delete_ids = [m[0] for m in members[1:]]

        # 查 word 名字便于审核
        word_row = session.execute(text("SELECT word FROM words WHERE id = :id"), {"id": wid}).fetchone()
        word = word_row[0] if word_row else f"<wid={wid}>"

        # 级联统计
        ci_ids = [r[0] for r in session.execute(
            text("SELECT id FROM content_items WHERE meaning_id = ANY(:ids)"),
            {"ids": delete_ids},
        ).fetchall()]
        ri_count = session.execute(
            text("SELECT COUNT(*) FROM review_items WHERE content_item_id = ANY(:ids)"),
            {"ids": ci_ids},
        ).scalar() or 0
        src_count = session.execute(
            text("SELECT COUNT(*) FROM sources WHERE meaning_id = ANY(:ids)"),
            {"ids": delete_ids},
        ).scalar() or 0

        print(f"\n  {word!r}  pos={npos!r}  def={ndef!r}")
        print(f"    保留 meaning_id={keep_id}  删除 meaning_id={delete_ids}")
        print(f"    级联删除: ContentItem={len(ci_ids)}  ReviewItem={ri_count}  Source={src_count}")

        total_deleted_meanings += len(delete_ids)
        total_deleted_ci += len(ci_ids)
        total_deleted_ri += ri_count
        total_deleted_src += src_count

        if execute:
            # 顺序：review_items → content_items → transfer sources → retry_counters → meanings
            if ci_ids:
                session.execute(
                    text("DELETE FROM review_items WHERE content_item_id = ANY(:ids)"),
                    {"ids": ci_ids},
                )
                session.execute(
                    text("DELETE FROM content_items WHERE id = ANY(:ids)"),
                    {"ids": ci_ids},
                )
            # Source transfer：把被合并方的 source 改挂到保留方，去重 (meaning_id, source_name, textbook_id, word_book_id, unit_id)
            session.execute(
                text("""
                    UPDATE sources s SET meaning_id = :keep
                    WHERE s.meaning_id = ANY(:ids)
                      AND NOT EXISTS (
                        SELECT 1 FROM sources s2
                        WHERE s2.meaning_id = :keep
                          AND s2.source_name = s.source_name
                          AND s2.textbook_id IS NOT DISTINCT FROM s.textbook_id
                          AND s2.word_book_id IS NOT DISTINCT FROM s.word_book_id
                          AND s2.unit_id IS NOT DISTINCT FROM s.unit_id
                      )
                """),
                {"keep": keep_id, "ids": delete_ids},
            )
            # 剩余的（与保留方完全重复的）source 直接删
            session.execute(
                text("DELETE FROM sources WHERE meaning_id = ANY(:ids)"),
                {"ids": delete_ids},
            )
            session.execute(
                text("DELETE FROM retry_counters WHERE meaning_id = ANY(:ids)"),
                {"ids": delete_ids},
            )
            session.execute(
                text("DELETE FROM meanings WHERE id = ANY(:ids)"),
                {"ids": delete_ids},
            )

    print(f"\n  汇总：删除 {total_deleted_meanings} 条 meaning + {total_deleted_ci} 条 ContentItem"
          f" + {total_deleted_ri} 条 ReviewItem + {total_deleted_src} 条 Source")
    if execute:
        session.flush()
        print(f"  ✅ 已执行")
    else:
        print(f"  (dry-run，未执行)")

    return {
        "duplicate_groups": len(duplicate_groups),
        "deleted_meanings": total_deleted_meanings,
        "deleted_content_items": total_deleted_ci,
        "deleted_review_items": total_deleted_ri,
        "deleted_sources": total_deleted_src,
    }


def verify_post_state(session) -> None:
    """执行后校验：确保 0 条裸 pos / 0 条半角分号 / 0 条归一化重复。"""
    bare_pos = session.execute(text(
        r"SELECT COUNT(*) FROM meanings WHERE pos !~ '\.$' AND TRIM(pos) != ''"
    )).scalar()
    half_semicolon = session.execute(text(
        r"SELECT COUNT(*) FROM meanings WHERE definition ~ '[;,():!?]'"
    )).scalar()

    rows = session.execute(text("SELECT word_id, pos, definition FROM meanings")).fetchall()
    seen = set()
    dup = 0
    for wid, pos, defi in rows:
        k = (wid, pos, defi)
        if k in seen:
            dup += 1
        seen.add(k)

    print(f"\n═══ 执行后校验 ═══")
    print(f"  剩余裸 pos 数: {bare_pos} (应为 0)")
    print(f"  剩余半角中文标点 definition 数: {half_semicolon} (应为 0)")
    print(f"  剩余 (word_id, pos, definition) 重复数: {dup} (应为 0)")
    ok = bare_pos == 0 and half_semicolon == 0 and dup == 0
    print(f"  {'✅ 全部通过' if ok else '❌ 校验失败'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="真正执行变更（默认 dry-run，只打印计划）")
    args = parser.parse_args()

    if args.execute:
        print("⚠️  --execute 模式：将真实修改生产数据库")
    else:
        print("🔍 dry-run 模式：仅打印计划，不动数据")

    with SyncSessionLocal() as session:
        try:
            s1 = stage1_normalize(session, execute=args.execute)
            s2 = stage2_merge_duplicates(session, execute=args.execute)
            if args.execute:
                session.commit()
                print(f"\n✅ 事务已提交")
                verify_post_state(session)
            else:
                session.rollback()
                print(f"\n(dry-run，事务未提交)")
            print(f"\n汇总: 阶段1={s1}  阶段2={s2}")
        except Exception:
            session.rollback()
            print(f"\n❌ 出错回滚")
            raise


if __name__ == "__main__":
    main()
