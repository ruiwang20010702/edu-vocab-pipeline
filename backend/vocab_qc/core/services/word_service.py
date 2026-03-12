"""词汇查询服务."""

from typing import Any

from sqlalchemy.orm import Session, subqueryload

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Phonetic, Source, Word
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS, QcStatus
from vocab_qc.core.models.quality_layer import QcRuleResult

# 终态：approved 或 rejected 都算"已完成"
_TERMINAL_STATUSES = [QcStatus.APPROVED.value, QcStatus.REJECTED.value]


def list_words(
    session: Session,
    page: int = 1,
    limit: int = 50,
    q: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """分页查询词汇，含音标、义项、内容项聚合。"""
    query = session.query(Word)
    if q:
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(Word.word.ilike(f"%{escaped_q}%", escape="\\"))

    # 子查询：该单词是否存在非终态的 content_item
    non_terminal_exists = (
        session.query(ContentItem.id)
        .filter(
            ContentItem.word_id == Word.id,
            ~ContentItem.qc_status.in_(_TERMINAL_STATUSES),
        )
        .exists()
    )

    if status == "approved":
        query = query.filter(~non_terminal_exists)
    elif status == "in_progress":
        query = query.filter(non_terminal_exists)

    total = query.count()

    # status_counts：基于同一 q 筛选条件，统计各状态数量
    base_query = session.query(Word)
    if q:
        escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base_query = base_query.filter(Word.word.ilike(f"%{escaped_q}%", escape="\\"))
    total_all = base_query.count()
    approved_count = base_query.filter(~non_terminal_exists).count()
    status_counts = {
        "approved": approved_count,
        "in_progress": total_all - approved_count,
        "total": total_all,
    }

    words = (
        query.options(
            subqueryload(Word.phonetics),
            subqueryload(Word.meanings).subqueryload(Meaning.sources),
            subqueryload(Word.content_items),
        )
        .order_by(Word.word)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    # 批量查询 issues（只显示最新一次质检的失败规则，排除已通过/重新生成前的旧记录）
    word_ids = [w.id for w in words]
    issues_map: dict[int, list] = {}
    if word_ids:
        # 收集每个 content_item 的最新 run_id
        latest_run_ids: set[str] = set()
        for w in words:
            for ci in w.content_items:
                if ci.last_qc_run_id:
                    latest_run_ids.add(ci.last_qc_run_id)

        if latest_run_ids:
            all_issues = (
                session.query(QcRuleResult)
                .filter(
                    QcRuleResult.word_id.in_(word_ids),
                    QcRuleResult.passed == False,  # noqa: E712
                    QcRuleResult.run_id.in_(latest_run_ids),
                )
                .all()
            )
            for iss in all_issues:
                issues_map.setdefault(iss.word_id, []).append(iss)

    items = [_build_word_detail_from_loaded(w, issues_map.get(w.id, [])) for w in words]
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "status_counts": status_counts,
    }


def get_word_detail(session: Session, word_id: int) -> dict[str, Any] | None:
    """获取单个词汇的完整详情。"""
    word = (
        session.query(Word)
        .options(
            subqueryload(Word.phonetics),
            subqueryload(Word.meanings).subqueryload(Meaning.sources),
            subqueryload(Word.content_items),
        )
        .filter_by(id=word_id)
        .first()
    )
    if word is None:
        return None

    # 只查询最新一次质检的失败记录
    latest_run_ids = {ci.last_qc_run_id for ci in word.content_items if ci.last_qc_run_id}
    issues = []
    if latest_run_ids:
        issues = (
            session.query(QcRuleResult)
            .filter(
                QcRuleResult.word_id == word.id,
                QcRuleResult.passed == False,  # noqa: E712
                QcRuleResult.run_id.in_(latest_run_ids),
            )
            .all()
        )
    return _build_word_detail_from_loaded(word, issues)


def _build_word_detail_from_loaded(word: Word, issues: list[QcRuleResult]) -> dict[str, Any]:
    """从已预加载的 ORM 对象组装单词详情（避免 N+1 查询）。"""
    # 按 (meaning_id, dimension) 索引内容项
    content_by_key: dict[tuple[int | None, str], ContentItem] = {}
    # 按 meaning_id 收集助记
    mnemonics_by_meaning: dict[int, list] = {}
    for item in word.content_items:
        content_by_key[(item.meaning_id, item.dimension)] = item
        if item.dimension in MNEMONIC_DIMENSIONS and item.meaning_id:
            mnemonics_by_meaning.setdefault(item.meaning_id, []).append(item)

    meanings_data = []
    for m in word.meanings:
        meanings_data.append({
            "id": m.id,
            "word_id": m.word_id,
            "pos": m.pos,
            "definition": m.definition,
            "sources": [{"id": s.id, "meaning_id": s.meaning_id, "source_name": s.source_name} for s in m.sources],
            "chunk": content_by_key.get((m.id, "chunk")),
            "sentence": content_by_key.get((m.id, "sentence")),
            "mnemonics": mnemonics_by_meaning.get(m.id, []),
        })

    # 词级维度: syllable（meaning_id=None）
    syllable_item = content_by_key.get((None, "syllable"))

    # 完成状态：所有 content_items 都是终态 → approved，否则 in_progress
    all_terminal = all(
        ci.qc_status in _TERMINAL_STATUSES for ci in word.content_items
    ) if word.content_items else False
    completion_status = "approved" if all_terminal else "in_progress"

    return {
        "id": word.id,
        "word": word.word,
        "created_at": word.created_at,
        "updated_at": word.updated_at,
        "phonetics": word.phonetics,
        "syllable": syllable_item,
        "completion_status": completion_status,
        "meanings": meanings_data,
        "issues": [
            {
                "id": iss.id,
                "content_item_id": iss.content_item_id,
                "rule_id": iss.rule_id,
                "field": iss.dimension,
                "message": iss.detail or "",
                "severity": "error",
            }
            for iss in issues
        ],
    }
