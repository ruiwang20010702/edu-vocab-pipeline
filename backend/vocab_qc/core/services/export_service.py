"""导出服务: 仅导出已通过审核的内容."""

import io
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from vocab_qc.core.logging_config import log_elapsed
from vocab_qc.core.models import ContentItem, Meaning, Phonetic, QcStatus, Source, Word
from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS, QC_TERMINAL_STATUSES

logger = logging.getLogger(__name__)

_MNEMONIC_TYPE_LABELS: dict[str, str] = {
    "mnemonic_root_affix": "词根词缀",
    "mnemonic_word_in_word": "词中词",
    "mnemonic_sound_meaning": "音义联想",
    "mnemonic_exam_app": "考试应用",
}

# 导出层 POS 规范化映射：去点后若为旧的 art，统一映射到新规范 det
_POS_NORMALIZE_MAP: dict[str, str] = {"art": "det"}


def _normalize_pos_for_export(pos: str | None) -> str:
    """导出层规范化 POS：去尾部 '.'，并把旧 'art' 映射到新规范 'det'。"""
    if not pos:
        return ""
    stripped = pos.rstrip(".")
    return _POS_NORMALIZE_MAP.get(stripped, stripped)


def _format_mnemonic_export(item: "ContentItem") -> dict[str, Any]:
    """助记导出: 解析 JSON content 为结构化数据。"""
    base = {"type": item.dimension}
    try:
        data = json.loads(item.content)
        if isinstance(data, dict):
            base.update(
                {k: data.get(k, "") for k in ("formula", "chant", "extension_words", "script")}
            )
            return base
    except (json.JSONDecodeError, TypeError):
        pass
    base["content"] = item.content
    return base


_MNEMONIC_FIELD_KEYS: tuple[str, ...] = (
    "formula", "chant", "extension_words",
    "exam_sentence", "exam_sentence_translation", "script",
)


def _parse_mnemonic_fields(content: str) -> dict[str, str]:
    """从助记 content 中提取 formula/chant/extension_words/exam_sentence/exam_sentence_translation/script。

    旧数据无 extension_words / exam_sentence / exam_sentence_translation 字段时返回空串。
    """
    empty = dict.fromkeys(_MNEMONIC_FIELD_KEYS, "")
    if not content:
        return empty
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "formula" in data:
            return {k: data.get(k, "") for k in _MNEMONIC_FIELD_KEYS}
    except (json.JSONDecodeError, TypeError):
        pass
    formula = re.search(r"\[核心公式\]\s*([\s\S]*?)(?=\[助记口诀\]|$)", content)
    chant = re.search(r"\[助记口诀\]\s*([\s\S]*?)(?=\[老师话术\]|$)", content)
    script = re.search(r"\[老师话术\]\s*([\s\S]*?)$", content)
    return {
        "formula": (formula.group(1).strip() if formula else ""),
        "chant": (chant.group(1).strip() if chant else ""),
        "extension_words": "",
        "exam_sentence": "",
        "exam_sentence_translation": "",
        "script": (script.group(1).strip() if script else ""),
    }


def _is_meaning_exportable(items: list["ContentItem"]) -> bool:
    """义项可导出条件：所有 ContentItem 都处于终态，且至少有 1 个 approved."""
    if not items:
        return False
    return (
        all(ci.qc_status in QC_TERMINAL_STATUSES for ci in items)
        and any(ci.qc_status == QcStatus.APPROVED.value for ci in items)
    )


def _iter_approved_batches(session: Session, batch_size: int = 500):
    """分批查询已审核通过的词汇数据（按义项级别过滤：所有维度终态才导出）。"""
    from collections import defaultdict

    from sqlalchemy import distinct

    # 查出所有有 ContentItem 的 word_id
    all_word_ids = [
        row[0]
        for row in session.query(distinct(ContentItem.word_id)).all()
    ]
    if not all_word_ids:
        return

    for i in range(0, len(all_word_ids), batch_size):
        batch_ids = all_word_ids[i : i + batch_size]

        # 加载该批次所有 ContentItem（不限 status）
        all_items = (
            session.query(ContentItem)
            .filter(ContentItem.word_id.in_(batch_ids))
            .all()
        )

        # 按 (word_id, meaning_id) 分组
        items_by_key: dict[tuple[int, int | None], list[ContentItem]] = defaultdict(list)
        for ci in all_items:
            items_by_key[(ci.word_id, ci.meaning_id)].append(ci)

        # 判定每个 word 的 syllable 是否终态、每个义项是否可导出
        exportable_meaning_ids: set[int] = set()
        word_has_exportable: set[int] = set()
        syllable_ok: dict[int, bool] = {}

        for (word_id, meaning_id), items in items_by_key.items():
            if meaning_id is None:
                # syllable 是 word 级别
                syllable_ok[word_id] = all(
                    ci.qc_status in QC_TERMINAL_STATUSES for ci in items
                )
            else:
                if _is_meaning_exportable(items):
                    exportable_meaning_ids.add(meaning_id)
                    word_has_exportable.add(word_id)

        # 没有 syllable 记录的 word 视为 syllable OK（可能尚未生成）
        exportable_word_ids = [
            wid for wid in batch_ids
            if wid in word_has_exportable and syllable_ok.get(wid, True)
        ]
        if not exportable_word_ids:
            continue

        words = {w.id: w for w in session.query(Word).filter(Word.id.in_(exportable_word_ids)).all()}
        phonetics = {}
        for p in session.query(Phonetic).filter(Phonetic.word_id.in_(exportable_word_ids)).all():
            phonetics[p.word_id] = p

        all_meanings = session.query(Meaning).filter(Meaning.word_id.in_(exportable_word_ids)).all()
        meanings_by_word: dict[int, list[Meaning]] = defaultdict(list)
        meaning_ids = []
        for m in all_meanings:
            if m.id in exportable_meaning_ids:
                meanings_by_word[m.word_id].append(m)
                meaning_ids.append(m.id)

        sources_by_meaning: dict[int, list[Source]] = defaultdict(list)
        if meaning_ids:
            for s in session.query(Source).filter(Source.meaning_id.in_(meaning_ids)).all():
                sources_by_meaning[s.meaning_id].append(s)

        # 只取 approved 的 ContentItem 填充内容
        approved_items = [ci for ci in all_items if ci.qc_status == QcStatus.APPROVED.value]

        content_index: dict[tuple[int, int | None, str], ContentItem] = {}
        mnemonics_by_meaning: dict[int, list[ContentItem]] = defaultdict(list)
        for ci in approved_items:
            if ci.word_id not in words:
                continue
            if ci.dimension in MNEMONIC_DIMENSIONS and ci.meaning_id:
                if ci.meaning_id in exportable_meaning_ids:
                    mnemonics_by_meaning[ci.meaning_id].append(ci)
            else:
                content_index[(ci.word_id, ci.meaning_id, ci.dimension)] = ci

        for word_id in exportable_word_ids:
            word = words.get(word_id)
            if not word:
                continue

            export_meanings = meanings_by_word.get(word_id, [])
            if not export_meanings:
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
                "ipa_uk": phonetic.ipa_uk if phonetic else "",
                "ipa_us": phonetic.ipa_us if phonetic else "",
                "audio_url_uk": phonetic.audio_url_uk if phonetic else "",
                "audio_url_us": phonetic.audio_url_us if phonetic else "",
                "meanings": [],
            }

            for meaning in export_meanings:
                sources = sources_by_meaning.get(meaning.id, [])
                chunk = content_index.get((word_id, meaning.id, "chunk"))
                sentence = content_index.get((word_id, meaning.id, "sentence"))

                first_source = sources[0] if sources else None
                meaning_data = {
                    "pos": _normalize_pos_for_export(meaning.pos),
                    "def": meaning.definition,
                    "sources": [s.source_name for s in sources],
                    "textbook_id": first_source.textbook_id if first_source else None,
                    "word_book_id": first_source.word_book_id if first_source else None,
                    "unit_id": first_source.unit_id if first_source else None,
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
        """导出单个词的完整数据（按义项过滤：所有维度终态才导出）."""
        from collections import defaultdict

        logger.info("导出单词开始 word_id=%d", word_id)

        word = session.query(Word).filter_by(id=word_id).first()
        if not word:
            logger.warning("导出单词未找到 word_id=%d", word_id)
            return None

        phonetic = session.query(Phonetic).filter_by(word_id=word.id).first()
        meanings = session.query(Meaning).filter_by(word_id=word.id).all()

        # 加载该词所有 ContentItem（不限 status）
        all_items = (
            session.query(ContentItem)
            .filter(ContentItem.word_id == word.id)
            .all()
        )

        # 按 meaning_id 分组，判定哪些义项可导出
        items_by_meaning: dict[int | None, list[ContentItem]] = defaultdict(list)
        for ci in all_items:
            items_by_meaning[ci.meaning_id].append(ci)

        # syllable 终态检查
        syllable_items = items_by_meaning.get(None, [])
        if syllable_items and not all(ci.qc_status in QC_TERMINAL_STATUSES for ci in syllable_items):
            logger.info("导出单词跳过 word_id=%d syllable 未终态", word_id)
            return None

        # 筛选可导出义项
        exportable_meaning_ids = {
            mid for mid, items in items_by_meaning.items()
            if mid is not None and _is_meaning_exportable(items)
        }

        if not exportable_meaning_ids:
            logger.info("导出单词跳过 word_id=%d 无可导出义项", word_id)
            return None

        # 只取 approved 的 ContentItem 填充内容
        approved_items = [ci for ci in all_items if ci.qc_status == QcStatus.APPROVED.value]

        content_index: dict[tuple[int | None, str], ContentItem] = {}
        mnemonics_by_meaning: dict[int, list[ContentItem]] = defaultdict(list)
        for ci in approved_items:
            if ci.dimension in MNEMONIC_DIMENSIONS and ci.meaning_id:
                if ci.meaning_id in exportable_meaning_ids:
                    mnemonics_by_meaning[ci.meaning_id].append(ci)
            else:
                content_index[(ci.meaning_id, ci.dimension)] = ci

        meaning_ids = [m.id for m in meanings if m.id in exportable_meaning_ids]
        sources_by_meaning: dict[int, list[Source]] = defaultdict(list)
        if meaning_ids:
            for s in session.query(Source).filter(Source.meaning_id.in_(meaning_ids)).all():
                sources_by_meaning[s.meaning_id].append(s)

        syllable_item = content_index.get((None, "syllable"))
        syllables = (
            syllable_item.content if syllable_item
            else (phonetic.syllables if phonetic else "")
        )

        result: dict[str, Any] = {
            "id": word.id,
            "word": word.word,
            "syllables": syllables,
            "ipa_uk": phonetic.ipa_uk if phonetic else "",
            "ipa_us": phonetic.ipa_us if phonetic else "",
            "audio_url_uk": phonetic.audio_url_uk if phonetic else "",
            "audio_url_us": phonetic.audio_url_us if phonetic else "",
            "meanings": [],
        }

        for meaning in meanings:
            if meaning.id not in exportable_meaning_ids:
                continue

            chunk = content_index.get((meaning.id, "chunk"))
            sentence = content_index.get((meaning.id, "sentence"))

            sources = sources_by_meaning.get(meaning.id, [])
            first_source = sources[0] if sources else None
            meaning_data = {
                "pos": _normalize_pos_for_export(meaning.pos),
                "def": meaning.definition,
                "sources": [s.source_name for s in sources],
                "textbook_id": first_source.textbook_id if first_source else None,
                "word_book_id": first_source.word_book_id if first_source else None,
                "unit_id": first_source.unit_id if first_source else None,
                "chunk": chunk.content if chunk else None,
                "chunk_cn": chunk.content_cn if chunk else None,
                "sentence": sentence.content if sentence else None,
                "sentence_cn": sentence.content_cn if sentence else None,
                "mnemonics": [_format_mnemonic_export(m) for m in mnemonics_by_meaning.get(meaning.id, [])],
            }
            result["meanings"].append(meaning_data)

        return result

    def export_all_approved(self, session: Session) -> list[dict[str, Any]]:
        """导出所有有 approved 内容的词（复用分批生成器，避免全量加载）."""
        logger.info("导出全部已审核词汇开始")
        with log_elapsed(logger, "导出全部已审核词汇"):
            result = list(_iter_approved_batches(session))
        logger.info("导出全部已审核词汇完成 count=%d", len(result))
        return result

    def export_to_json(self, session: Session, filepath: str) -> int:
        """导出到 JSON 文件（分批写入，避免全量加载到内存）."""
        logger.info("导出 JSON 开始 filepath=%s", filepath)
        count = 0
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("[\n")
            for item in _iter_approved_batches(session):
                if count > 0:
                    f.write(",\n")
                json.dump(item, f, ensure_ascii=False, indent=2)
                count += 1
            f.write("\n]")
        logger.info("导出 JSON 完成 filepath=%s count=%d", filepath, count)
        return count

    def export_to_excel(self, session: Session) -> io.BytesIO:
        """导出已通过词汇数据为 Excel，每个义项一行，4 种助记各占 3 列。

        P-M1: 使用分批查询，避免全量加载到内存。
        """
        logger.info("导出 Excel 开始")
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        data = _iter_approved_batches(session)

        wb = Workbook()
        ws = wb.active
        ws.title = "词表导出"

        # 助记类型与各自要导出的列：通用 3 列；词根词缀额外含"同根词"为 4 列；考试应用含"例句"为 5 列
        basic_mn_cols: list[tuple[str, str]] = [
            ("formula", "公式"), ("chant", "口诀"), ("script", "话术"),
        ]
        root_affix_mn_cols: list[tuple[str, str]] = [
            ("formula", "公式"), ("chant", "口诀"),
            ("extension_words", "同根词"), ("script", "话术"),
        ]
        exam_mn_cols: list[tuple[str, str]] = [
            ("formula", "公式"), ("chant", "口诀"),
            ("exam_sentence", "例句"), ("exam_sentence_translation", "例句释义"),
            ("script", "话术"),
        ]
        mnemonic_types: list[tuple[str, str, list[tuple[str, str]]]] = [
            ("mnemonic_root_affix", "词根词缀", root_affix_mn_cols),
            ("mnemonic_word_in_word", "词中词", basic_mn_cols),
            ("mnemonic_sound_meaning", "谐音联想", basic_mn_cols),
            ("mnemonic_exam_app", "考试应用", exam_mn_cols),
        ]

        base_headers = [
            "单词", "英式音标", "美式音标", "英式音频URL", "美式音频URL",
            "音节", "词性", "释义", "教材来源",
            "教材ID", "词书ID", "单元ID",
            "语块", "语块翻译", "例句", "例句翻译",
        ]
        mn_headers: list[str] = []
        for _, label, cols in mnemonic_types:
            for _, suffix in cols:
                mn_headers.append(f"{label}·{suffix}")
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
            ipa_uk = word_data.get("ipa_uk", "")
            ipa_us = word_data.get("ipa_us", "")
            audio_uk = word_data.get("audio_url_uk", "") or ""
            audio_us = word_data.get("audio_url_us", "") or ""
            syllables = word_data.get("syllables", "")
            meanings = word_data.get("meanings", [])

            if not meanings:
                ws.cell(row=row, column=1, value=word)
                ws.cell(row=row, column=2, value=ipa_uk)
                ws.cell(row=row, column=3, value=ipa_us)
                ws.cell(row=row, column=4, value=audio_uk)
                ws.cell(row=row, column=5, value=audio_us)
                ws.cell(row=row, column=6, value=syllables)
                row += 1
                continue

            for m in meanings:
                ws.cell(row=row, column=1, value=word)
                ws.cell(row=row, column=2, value=ipa_uk)
                ws.cell(row=row, column=3, value=ipa_us)
                ws.cell(row=row, column=4, value=audio_uk)
                ws.cell(row=row, column=5, value=audio_us)
                ws.cell(row=row, column=6, value=syllables)
                ws.cell(row=row, column=7, value=m.get("pos", ""))
                ws.cell(row=row, column=8, value=m.get("def", ""))
                sources = m.get("sources", [])
                ws.cell(row=row, column=9, value="; ".join(sources) if sources else "")
                ws.cell(row=row, column=10, value=m.get("textbook_id") or "")
                ws.cell(row=row, column=11, value=m.get("word_book_id") or "")
                ws.cell(row=row, column=12, value=m.get("unit_id") or "")
                ws.cell(row=row, column=13, value=m.get("chunk") or "")
                ws.cell(row=row, column=14, value=m.get("chunk_cn") or "")
                ws.cell(row=row, column=15, value=m.get("sentence") or "")
                ws.cell(row=row, column=16, value=m.get("sentence_cn") or "")

                # 助记：按 type 建索引
                mn_by_type: dict[str, dict[str, str]] = {}
                for mn in m.get("mnemonics", []):
                    mn_by_type[mn["type"]] = _parse_mnemonic_fields(mn.get("content", ""))

                # 各类型按其 columns 写入，缺失（LLM 判定 valid:false / 该维度 rejected）留空
                col_offset = len(base_headers) + 1
                for mn_key, _, cols in mnemonic_types:
                    fields = mn_by_type.get(mn_key)
                    for i, (field_name, _) in enumerate(cols):
                        ws.cell(
                            row=row, column=col_offset + i,
                            value=(fields[field_name] if fields else ""),
                        )
                    col_offset += len(cols)

                for c in range(1, len(headers) + 1):
                    ws.cell(row=row, column=c).alignment = wrap_align

                row += 1

        # 列宽
        base_widths = [15, 22, 22, 40, 40, 18, 8, 30, 24, 12, 12, 12, 28, 28, 42, 42]
        # 通用助记列宽 = [公式 22, 口诀 22, 话术 30]
        # 词根词缀 = [公式 22, 口诀 22, 同根词 28, 话术 30]
        # 考试应用 = [公式 22, 口诀 22, 例句 35, 例句释义 30, 话术 30]
        basic_mn_widths: list[int] = [22, 22, 30]
        root_affix_mn_widths: list[int] = [22, 22, 28, 30]
        exam_mn_widths: list[int] = [22, 22, 35, 30, 30]
        mn_widths: list[int] = []
        for mn_key, _, _ in mnemonic_types:
            if mn_key == "mnemonic_exam_app":
                mn_widths += exam_mn_widths
            elif mn_key == "mnemonic_root_affix":
                mn_widths += root_affix_mn_widths
            else:
                mn_widths += basic_mn_widths
        for i, w in enumerate(base_widths + mn_widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        logger.info("导出 Excel 完成 rows=%d", row - 2)
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
