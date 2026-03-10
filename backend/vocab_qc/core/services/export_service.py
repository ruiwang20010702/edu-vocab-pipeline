"""导出服务: 仅导出已通过审核的内容."""

import json
from typing import Any

from sqlalchemy.orm import Session

from vocab_qc.core.models import ContentItem, Meaning, Phonetic, QcStatus, Source, Word
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS


class ExportService:
    """导出服务: 门禁 + 格式化输出."""

    def export_word(self, session: Session, word_id: int) -> dict[str, Any] | None:
        """导出单个词的完整数据（仅 approved 内容）."""
        word = session.query(Word).filter_by(id=word_id).first()
        if not word:
            return None

        phonetic = session.query(Phonetic).filter_by(word_id=word.id).first()
        meanings = session.query(Meaning).filter_by(word_id=word.id).all()

        result = {
            "id": word.id,
            "word": word.word,
            "syllables": phonetic.syllables if phonetic else "",
            "ipa": phonetic.ipa if phonetic else "",
            "meanings": [],
        }

        for meaning in meanings:
            sources = session.query(Source).filter_by(meaning_id=meaning.id).all()

            chunk = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, meaning_id=meaning.id, dimension="chunk", qc_status=QcStatus.APPROVED.value)
                .first()
            )

            sentence = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, meaning_id=meaning.id, dimension="sentence", qc_status=QcStatus.APPROVED.value)
                .first()
            )

            # 获取该义项的 approved 助记
            mnemonics = (
                session.query(ContentItem)
                .filter(
                    ContentItem.word_id == word.id,
                    ContentItem.meaning_id == meaning.id,
                    ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
                    ContentItem.qc_status == QcStatus.APPROVED.value,
                )
                .all()
            )

            meaning_data = {
                "pos": meaning.pos,
                "def": meaning.definition,
                "sources": [s.source_name for s in sources],
                "chunk": chunk.content if chunk else None,
                "chunk_cn": chunk.content_cn if chunk else None,
                "sentence": sentence.content if sentence else None,
                "sentence_cn": sentence.content_cn if sentence else None,
                "mnemonics": [{"type": m.dimension, "content": m.content} for m in mnemonics],
            }
            result["meanings"].append(meaning_data)

        return result

    def export_all_approved(self, session: Session) -> list[dict[str, Any]]:
        """导出所有有 approved 内容的词（批量预加载，避免 N+1 查询）."""
        from collections import defaultdict

        from sqlalchemy import distinct

        # 一次查出所有有 approved 内容的 word_id
        approved_word_ids = (
            session.query(distinct(ContentItem.word_id))
            .filter_by(qc_status=QcStatus.APPROVED.value)
            .all()
        )
        word_ids = [row[0] for row in approved_word_ids]
        if not word_ids:
            return []

        # 批量预加载所有相关数据
        words = {w.id: w for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
        phonetics = {}
        for p in session.query(Phonetic).filter(Phonetic.word_id.in_(word_ids)).all():
            phonetics[p.word_id] = p

        all_meanings = session.query(Meaning).filter(Meaning.word_id.in_(word_ids)).all()
        meanings_by_word: dict[int, list[Meaning]] = defaultdict(list)
        meaning_ids = []
        for m in all_meanings:
            meanings_by_word[m.word_id].append(m)
            meaning_ids.append(m.id)

        sources_by_meaning: dict[int, list[Source]] = defaultdict(list)
        if meaning_ids:
            for s in session.query(Source).filter(Source.meaning_id.in_(meaning_ids)).all():
                sources_by_meaning[s.meaning_id].append(s)

        # 批量加载所有 approved 的 ContentItem
        approved_items = (
            session.query(ContentItem)
            .filter(
                ContentItem.word_id.in_(word_ids),
                ContentItem.qc_status == QcStatus.APPROVED.value,
            )
            .all()
        )

        # 按 (word_id, meaning_id, dimension) 建索引
        content_index: dict[tuple[int, int | None, str], ContentItem] = {}
        mnemonics_by_meaning: dict[int, list[ContentItem]] = defaultdict(list)
        for ci in approved_items:
            if ci.dimension in MNEMONIC_DIMENSIONS and ci.meaning_id:
                mnemonics_by_meaning[ci.meaning_id].append(ci)
            else:
                content_index[(ci.word_id, ci.meaning_id, ci.dimension)] = ci

        # 在内存中组装结果
        results = []
        for word_id in word_ids:
            word = words.get(word_id)
            if not word:
                continue

            phonetic = phonetics.get(word_id)
            result: dict[str, Any] = {
                "id": word.id,
                "word": word.word,
                "syllables": phonetic.syllables if phonetic else "",
                "ipa": phonetic.ipa if phonetic else "",
                "meanings": [],
            }

            for meaning in meanings_by_word.get(word_id, []):
                sources = sources_by_meaning.get(meaning.id, [])
                chunk = content_index.get((word_id, meaning.id, "chunk"))
                sentence = content_index.get((word_id, meaning.id, "sentence"))

                meaning_data = {
                    "pos": meaning.pos,
                    "def": meaning.definition,
                    "sources": [s.source_name for s in sources],
                    "chunk": chunk.content if chunk else None,
                    "chunk_cn": chunk.content_cn if chunk else None,
                    "sentence": sentence.content if sentence else None,
                    "sentence_cn": sentence.content_cn if sentence else None,
                    "mnemonics": [
                        {"type": m.dimension, "content": m.content}
                        for m in mnemonics_by_meaning.get(meaning.id, [])
                    ],
                }
                result["meanings"].append(meaning_data)

            results.append(result)
        return results

    def export_to_json(self, session: Session, filepath: str) -> int:
        """导出到 JSON 文件."""
        data = self.export_all_approved(session)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return len(data)

    def get_export_readiness(self, session: Session) -> dict:
        """检查导出就绪状态."""
        total = session.query(ContentItem).count()
        approved = session.query(ContentItem).filter_by(qc_status=QcStatus.APPROVED.value).count()
        pending = session.query(ContentItem).filter_by(qc_status=QcStatus.PENDING.value).count()

        return {
            "total_items": total,
            "approved": approved,
            "pending": pending,
            "not_approved": total - approved,
            "ready_rate": round(approved / total * 100, 1) if total > 0 else 0,
        }
