"""词汇查询服务."""

from typing import Any

from sqlalchemy.orm import Session, subqueryload

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Phonetic, Source, Word
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS
from vocab_qc.core.models.quality_layer import QcRuleResult


def list_words(
    session: Session,
    page: int = 1,
    limit: int = 50,
    q: str | None = None,
) -> dict[str, Any]:
    """分页查询词汇，含音标、义项、内容项聚合。"""
    query = session.query(Word)
    if q:
        query = query.filter(Word.word.ilike(f"%{q}%"))

    total = query.count()

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

    # 批量查询 issues（一次查出所有 word_ids 的失败规则）
    word_ids = [w.id for w in words]
    issues_map: dict[int, list] = {}
    if word_ids:
        all_issues = (
            session.query(QcRuleResult)
            .filter(QcRuleResult.word_id.in_(word_ids), QcRuleResult.passed == False)  # noqa: E712
            .all()
        )
        for iss in all_issues:
            issues_map.setdefault(iss.word_id, []).append(iss)

    items = [_build_word_detail_from_loaded(w, issues_map.get(w.id, [])) for w in words]
    return {"items": items, "total": total, "page": page, "limit": limit}


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

    issues = (
        session.query(QcRuleResult)
        .filter_by(word_id=word.id, passed=False)
        .all()
    )
    return _build_word_detail_from_loaded(word, issues)


def _build_word_detail_from_loaded(word: Word, issues: list[QcRuleResult]) -> dict[str, Any]:
    """从已预加载的 ORM 对象组装单词详情（避免 N+1 查询）。"""
    # 按 (meaning_id, dimension) 索引内容项
    content_by_key: dict[tuple[int | None, str], ContentItem] = {}
    mnemonics = []
    for item in word.content_items:
        content_by_key[(item.meaning_id, item.dimension)] = item
        if item.dimension in MNEMONIC_DIMENSIONS:
            mnemonics.append(item)

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
        })

    return {
        "id": word.id,
        "word": word.word,
        "created_at": word.created_at,
        "updated_at": word.updated_at,
        "phonetics": word.phonetics,
        "meanings": meanings_data,
        "mnemonics": mnemonics,
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
