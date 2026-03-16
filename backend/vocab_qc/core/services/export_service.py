"""导出服务: 仅导出已通过审核的内容."""

import io
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from vocab_qc.core.models import ContentItem, Meaning, Phonetic, QcStatus, Source, Word
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

_MNEMONIC_TYPE_LABELS: dict[str, str] = {
    "mnemonic_root_affix": "词根词缀",
    "mnemonic_word_in_word": "词中词",
    "mnemonic_sound_meaning": "音义联想",
    "mnemonic_exam_app": "考试应用",
}


def _format_mnemonic_export(item: "ContentItem") -> dict[str, Any]:
    """助记导出: 解析 JSON content 为结构化数据。"""
    base = {"type": item.dimension}
    try:
        data = json.loads(item.content)
        if isinstance(data, dict):
            base.update({k: data.get(k, "") for k in ("formula", "chant", "script")})
            return base
    except (json.JSONDecodeError, TypeError):
        pass
    base["content"] = item.content
    return base


def _parse_mnemonic_fields(content: str) -> dict[str, str]:
    """从助记 content 中提取 formula/chant/script。"""
    if not content:
        return {"formula": "", "chant": "", "script": ""}
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "formula" in data:
            return {k: data.get(k, "") for k in ("formula", "chant", "script")}
    except (json.JSONDecodeError, TypeError):
        pass
    formula = re.search(r"\[核心公式\]\s*([\s\S]*?)(?=\[助记口诀\]|$)", content)
    chant = re.search(r"\[助记口诀\]\s*([\s\S]*?)(?=\[老师话术\]|$)", content)
    script = re.search(r"\[老师话术\]\s*([\s\S]*?)$", content)
    return {
        "formula": (formula.group(1).strip() if formula else ""),
        "chant": (chant.group(1).strip() if chant else ""),
        "script": (script.group(1).strip() if script else ""),
    }


def _iter_approved_batches(session: Session, batch_size: int = 500):
    """P-M1: 分批查询已审核通过的词汇数据，避免全量加载到内存。"""
    from collections import defaultdict

    from sqlalchemy import distinct

    # 一次查出所有有 approved 内容的 word_id
    approved_word_ids = [
        row[0]
        for row in session.query(distinct(ContentItem.word_id))
        .filter_by(qc_status=QcStatus.APPROVED.value)
        .all()
    ]
    if not approved_word_ids:
        return

    for i in range(0, len(approved_word_ids), batch_size):
        batch_ids = approved_word_ids[i : i + batch_size]

        words = {w.id: w for w in session.query(Word).filter(Word.id.in_(batch_ids)).all()}
        phonetics = {}
        for p in session.query(Phonetic).filter(Phonetic.word_id.in_(batch_ids)).all():
            phonetics[p.word_id] = p

        all_meanings = session.query(Meaning).filter(Meaning.word_id.in_(batch_ids)).all()
        meanings_by_word: dict[int, list[Meaning]] = defaultdict(list)
        meaning_ids = []
        for m in all_meanings:
            meanings_by_word[m.word_id].append(m)
            meaning_ids.append(m.id)

        sources_by_meaning: dict[int, list[Source]] = defaultdict(list)
        if meaning_ids:
            for s in session.query(Source).filter(Source.meaning_id.in_(meaning_ids)).all():
                sources_by_meaning[s.meaning_id].append(s)

        approved_items = (
            session.query(ContentItem)
            .filter(
                ContentItem.word_id.in_(batch_ids),
                ContentItem.qc_status == QcStatus.APPROVED.value,
            )
            .all()
        )

        content_index: dict[tuple[int, int | None, str], ContentItem] = {}
        mnemonics_by_meaning: dict[int, list[ContentItem]] = defaultdict(list)
        for ci in approved_items:
            if ci.dimension in MNEMONIC_DIMENSIONS and ci.meaning_id:
                mnemonics_by_meaning[ci.meaning_id].append(ci)
            else:
                content_index[(ci.word_id, ci.meaning_id, ci.dimension)] = ci

        for word_id in batch_ids:
            word = words.get(word_id)
            if not word:
                continue

            phonetic = phonetics.get(word_id)
            syllable_item = content_index.get((word_id, None, "syllable"))
            syllables = (
                syllable_item.content if syllable_item
                else (phonetic.syllables if phonetic else "")
            )
            result: dict[str, Any] = {
                "id": word.id,
                "word": word.word,
                "syllables": syllables,
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

            yield result


class ExportService:
    """导出服务: 门禁 + 格式化输出."""

    def export_word(self, session: Session, word_id: int) -> dict[str, Any] | None:
        """导出单个词的完整数据（仅 approved 内容）."""
        from collections import defaultdict

        word = session.query(Word).filter_by(id=word_id).first()
        if not word:
            return None

        phonetic = session.query(Phonetic).filter_by(word_id=word.id).first()
        meanings = session.query(Meaning).filter_by(word_id=word.id).all()

        # 批量加载该词所有 approved ContentItem（1 条查询）
        approved_items = (
            session.query(ContentItem)
            .filter(
                ContentItem.word_id == word.id,
                ContentItem.qc_status == QcStatus.APPROVED.value,
            )
            .all()
        )

        # 按 (meaning_id, dimension) 建索引
        content_index: dict[tuple[int | None, str], ContentItem] = {}
        mnemonics_by_meaning: dict[int, list[ContentItem]] = defaultdict(list)
        for ci in approved_items:
            if ci.dimension in MNEMONIC_DIMENSIONS and ci.meaning_id:
                mnemonics_by_meaning[ci.meaning_id].append(ci)
            else:
                content_index[(ci.meaning_id, ci.dimension)] = ci

        # 批量加载该词所有义项的来源（1 条查询）
        meaning_ids = [m.id for m in meanings]
        sources_by_meaning: dict[int, list[Source]] = defaultdict(list)
        if meaning_ids:
            for s in session.query(Source).filter(Source.meaning_id.in_(meaning_ids)).all():
                sources_by_meaning[s.meaning_id].append(s)

        # 音节优先用 syllable ContentItem，fallback 到 Phonetic 表
        syllable_item = content_index.get((None, "syllable"))
        syllables = (
            syllable_item.content if syllable_item
            else (phonetic.syllables if phonetic else "")
        )

        result: dict[str, Any] = {
            "id": word.id,
            "word": word.word,
            "syllables": syllables,
            "ipa": phonetic.ipa if phonetic else "",
            "meanings": [],
        }

        for meaning in meanings:
            chunk = content_index.get((meaning.id, "chunk"))
            sentence = content_index.get((meaning.id, "sentence"))

            meaning_data = {
                "pos": meaning.pos,
                "def": meaning.definition,
                "sources": [s.source_name for s in sources_by_meaning.get(meaning.id, [])],
                "chunk": chunk.content if chunk else None,
                "chunk_cn": chunk.content_cn if chunk else None,
                "sentence": sentence.content if sentence else None,
                "sentence_cn": sentence.content_cn if sentence else None,
                "mnemonics": [_format_mnemonic_export(m) for m in mnemonics_by_meaning.get(meaning.id, [])],
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
            # 音节优先用 syllable ContentItem，fallback 到 Phonetic 表
            syllable_item = content_index.get((word_id, None, "syllable"))
            syllables = (
                syllable_item.content if syllable_item
                else (phonetic.syllables if phonetic else "")
            )
            result: dict[str, Any] = {
                "id": word.id,
                "word": word.word,
                "syllables": syllables,
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

    def export_to_excel(self, session: Session) -> io.BytesIO:
        """导出已通过词汇数据为 Excel，每个义项一行，4 种助记各占 3 列。

        P-M1: 使用分批查询，避免全量加载到内存。
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        data = _iter_approved_batches(session)

        wb = Workbook()
        ws = wb.active
        ws.title = "词表导出"

        # 4 种助记类型，每种 3 列（公式/口诀/话术）
        mnemonic_types = [
            ("mnemonic_root_affix", "词根词缀"),
            ("mnemonic_word_in_word", "词中词"),
            ("mnemonic_sound_meaning", "谐音联想"),
            ("mnemonic_exam_app", "考试应用"),
        ]

        base_headers = [
            "单词", "音标", "音节", "词性", "释义", "教材来源",
            "语块", "语块翻译", "例句", "例句翻译",
        ]
        mn_headers = []
        for _, label in mnemonic_types:
            mn_headers += [f"{label}·公式", f"{label}·口诀", f"{label}·话术"]
        headers = base_headers + mn_headers

        # 表头样式
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
        wrap_align = Alignment(wrap_text=True, vertical="top")

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = wrap_align

        row = 2
        for word_data in data:
            word = word_data["word"]
            ipa = word_data.get("ipa", "")
            syllables = word_data.get("syllables", "")
            meanings = word_data.get("meanings", [])

            if not meanings:
                ws.cell(row=row, column=1, value=word)
                ws.cell(row=row, column=2, value=ipa)
                ws.cell(row=row, column=3, value=syllables)
                row += 1
                continue

            for m in meanings:
                ws.cell(row=row, column=1, value=word)
                ws.cell(row=row, column=2, value=ipa)
                ws.cell(row=row, column=3, value=syllables)
                ws.cell(row=row, column=4, value=m.get("pos", ""))
                ws.cell(row=row, column=5, value=m.get("def", ""))
                sources = m.get("sources", [])
                ws.cell(row=row, column=6, value="; ".join(sources) if sources else "")
                ws.cell(row=row, column=7, value=m.get("chunk") or "")
                ws.cell(row=row, column=8, value=m.get("chunk_cn") or "")
                ws.cell(row=row, column=9, value=m.get("sentence") or "")
                ws.cell(row=row, column=10, value=m.get("sentence_cn") or "")

                # 助记：按 type 建索引
                mn_by_type: dict[str, dict[str, str]] = {}
                for mn in m.get("mnemonics", []):
                    mn_by_type[mn["type"]] = _parse_mnemonic_fields(mn.get("content", ""))

                # 4 种类型各写 3 列，缺失填 false
                col_offset = len(base_headers) + 1
                for mn_key, _ in mnemonic_types:
                    fields = mn_by_type.get(mn_key)
                    if fields:
                        ws.cell(row=row, column=col_offset, value=fields["formula"])
                        ws.cell(row=row, column=col_offset + 1, value=fields["chant"])
                        ws.cell(row=row, column=col_offset + 2, value=fields["script"])
                    else:
                        ws.cell(row=row, column=col_offset, value="false")
                        ws.cell(row=row, column=col_offset + 1, value="false")
                        ws.cell(row=row, column=col_offset + 2, value="false")
                    col_offset += 3

                for c in range(1, len(headers) + 1):
                    ws.cell(row=row, column=c).alignment = wrap_align

                row += 1

        # 列宽
        base_widths = [12, 18, 14, 8, 24, 18, 24, 24, 36, 36]
        mn_widths = [22, 22, 30] * 4
        for i, w in enumerate(base_widths + mn_widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

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
