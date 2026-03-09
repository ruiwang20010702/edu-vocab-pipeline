"""词汇查询服务."""

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Phonetic, Source, Word
from vocab_qc.core.models.enums import QcStatus
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
    words = query.order_by(Word.word).offset((page - 1) * limit).limit(limit).all()

    items = [_build_word_detail(session, w) for w in words]
    return {"items": items, "total": total, "page": page, "limit": limit}


def get_word_detail(session: Session, word_id: int) -> dict[str, Any] | None:
    """获取单个词汇的完整详情。"""
    word = session.query(Word).filter_by(id=word_id).first()
    if word is None:
        return None
    return _build_word_detail(session, word)


def _build_word_detail(session: Session, word: Word) -> dict[str, Any]:
    """组装单词详情数据。"""
    phonetics = session.query(Phonetic).filter_by(word_id=word.id).all()
    meanings = session.query(Meaning).filter_by(word_id=word.id).all()

    meanings_data = []
    for m in meanings:
        sources = session.query(Source).filter_by(meaning_id=m.id).all()

        chunk = (
            session.query(ContentItem)
            .filter_by(word_id=word.id, meaning_id=m.id, dimension="chunk")
            .first()
        )
        sentence = (
            session.query(ContentItem)
            .filter_by(word_id=word.id, meaning_id=m.id, dimension="sentence")
            .first()
        )

        meanings_data.append({
            "id": m.id,
            "word_id": m.word_id,
            "pos": m.pos,
            "definition": m.definition,
            "sources": [{"id": s.id, "meaning_id": s.meaning_id, "source_name": s.source_name} for s in sources],
            "chunk": chunk,
            "sentence": sentence,
        })

    mnemonic = (
        session.query(ContentItem)
        .filter_by(word_id=word.id, dimension="mnemonic")
        .first()
    )

    # 获取未通过的规则结果作为 issues
    issues = (
        session.query(QcRuleResult)
        .filter_by(word_id=word.id, passed=False)
        .all()
    )

    return {
        "id": word.id,
        "word": word.word,
        "created_at": word.created_at,
        "updated_at": word.updated_at,
        "phonetics": phonetics,
        "meanings": meanings_data,
        "mnemonic": mnemonic,
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
