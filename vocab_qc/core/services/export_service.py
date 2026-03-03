"""导出服务: 仅导出已通过审核的内容."""

import json
from typing import Any

from sqlalchemy.orm import Session

from vocab_qc.core.models import ContentItem, Meaning, Phonetic, QcStatus, Source, Word


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
            "mnemonic": None,
        }

        for meaning in meanings:
            sources = session.query(Source).filter_by(meaning_id=meaning.id).all()

            # 获取 approved 的语块
            chunk = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, meaning_id=meaning.id, dimension="chunk", qc_status=QcStatus.APPROVED.value)
                .first()
            )

            # 获取 approved 的例句
            sentence = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, meaning_id=meaning.id, dimension="sentence", qc_status=QcStatus.APPROVED.value)
                .first()
            )

            meaning_data = {
                "pos": meaning.pos,
                "def": meaning.definition,
                "sources": [s.source_name for s in sources],
                "chunk": chunk.content if chunk else None,
                "sentence": sentence.content if sentence else None,
                "sentence_cn": sentence.content_cn if sentence else None,
            }
            result["meanings"].append(meaning_data)

        # 获取 approved 的助记
        mnemonic = (
            session.query(ContentItem)
            .filter_by(word_id=word.id, dimension="mnemonic", qc_status=QcStatus.APPROVED.value)
            .first()
        )
        result["mnemonic"] = mnemonic.content if mnemonic else None

        return result

    def export_all_approved(self, session: Session) -> list[dict[str, Any]]:
        """导出所有有 approved 内容的词."""
        words = session.query(Word).all()
        results = []
        for word in words:
            data = self.export_word(session, word.id)
            if data:
                results.append(data)
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
