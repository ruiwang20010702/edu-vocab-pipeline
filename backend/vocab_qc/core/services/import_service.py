"""数据导入服务: 解析文件 → 创建 Word / Meaning / ContentItem。"""

import csv
import io
import json
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# 字段长度限制
_MAX_WORD_LEN = 100
_MAX_POS_LEN = 20
_MAX_DEFINITION_LEN = 500
_MAX_SOURCE_LEN = 200
_MAX_IPA_LEN = 200

from sqlalchemy.orm import Session

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Phonetic, Source, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageWord
from vocab_qc.core.models.quality_layer import RetryCounter, ReviewItem


def _truncate_field(value: str, max_len: int, field_name: str, word: str) -> str:
    """截断超长字段并记录警告。"""
    if len(value) > max_len:
        _logger.warning("字段 %s 超长截断 (len=%d>%d) word=%s", field_name, len(value), max_len, word)
        return value[:max_len]
    return value


def import_from_json(session: Session, data: list[dict[str, Any]], batch_name: str, *, force: bool = False) -> dict:
    """从 JSON 数据导入词汇。

    期望格式:
    [
      {
        "word": "kind",
        "meanings": [
          {"pos": "adj.", "definition": "善良的", "sources": ["人教七上U1"]}
        ]
      }
    ]
    """
    package = _get_or_create_package(session, batch_name, force=force)
    word_count = 0
    imported_words: list[Word] = []
    imported_meanings: list[tuple[Word, Meaning]] = []

    # 收集待批量处理的来源和词映射
    pending_sources: list[tuple[int, str]] = []  # (meaning_id, source_name)
    pending_word_ids: list[int] = []  # word_ids for PackageWord

    for entry in data:
        word_text = entry.get("word", "").strip()
        if not word_text:
            continue

        word = _get_or_create_word(session, word_text)
        word_count += 1
        imported_words.append(word)
        pending_word_ids.append(word.id)

        # 音标（IPA）— 从 Excel/JSON 导入
        ipa = entry.get("ipa", "").strip()
        if ipa:
            _upsert_phonetic_ipa(session, word, ipa)

        for m_data in entry.get("meanings", []):
            pos = m_data.get("pos", "").strip()
            definition = m_data.get("definition", "").strip()
            if not pos or not definition:
                continue

            meaning = _find_or_create_meaning(session, word, pos, definition)
            imported_meanings.append((word, meaning))

            # 收集来源（延迟到循环后批量处理）
            for src_name in m_data.get("sources", []):
                pending_sources.append((meaning.id, src_name))

    # 批量去重 Source：一次查询已有的 → add_all 新增的
    if pending_sources:
        # 分批查询已存在的 (meaning_id, source_name) 对
        existing_source_pairs: set[tuple[int, str]] = set()
        unique_meaning_ids = list({mid for mid, _ in pending_sources})
        for i in range(0, len(unique_meaning_ids), 900):
            chunk = unique_meaning_ids[i:i + 900]
            for row in session.query(Source.meaning_id, Source.source_name).filter(
                Source.meaning_id.in_(chunk),
            ).all():
                existing_source_pairs.add((row[0], row[1]))

        new_sources = []
        seen_pairs: set[tuple[int, str]] = set()
        for mid, sname in pending_sources:
            pair = (mid, sname)
            if pair not in existing_source_pairs and pair not in seen_pairs:
                new_sources.append(Source(meaning_id=mid, source_name=sname))
                seen_pairs.add(pair)
        if new_sources:
            session.add_all(new_sources)

    # 批量去重 PackageWord：一次查询已有的 → add_all 新增的
    if pending_word_ids:
        existing_pw_word_ids: set[int] = set()
        for i in range(0, len(pending_word_ids), 900):
            chunk = pending_word_ids[i:i + 900]
            existing_pw_word_ids.update(
                row[0] for row in session.query(PackageWord.word_id).filter(
                    PackageWord.package_id == package.id,
                    PackageWord.word_id.in_(chunk),
                ).all()
            )
        new_pws = []
        seen_word_ids: set[int] = set()
        for wid in pending_word_ids:
            if wid not in existing_pw_word_ids and wid not in seen_word_ids:
                new_pws.append(PackageWord(package_id=package.id, word_id=wid))
                seen_word_ids.add(wid)
        if new_pws:
            session.add_all(new_pws)

    session.flush()

    # 创建 ContentItem 占位记录（chunk/sentence/mnemonic 均按义项）
    _create_content_placeholders(session, imported_words, imported_meanings)

    # 更新 Package 统计
    package.status = "pending"
    package.total_words = word_count
    package.processed_words = 0

    session.flush()
    return {"batch_id": str(package.id), "word_count": word_count}


def _parse_csv_text(text: str) -> list[dict[str, Any]]:
    """将 CSV 文本解析为词汇 entries 列表。"""
    reader = csv.DictReader(io.StringIO(text))
    entries: dict[str, dict[str, Any]] = {}
    for row in reader:
        word = row.get("word", "").strip()
        if not word:
            continue
        if len(word) > _MAX_WORD_LEN:
            _logger.warning("CSV 跳过超长单词 (len=%d): %s...", len(word), word[:30])
            continue
        if word not in entries:
            entries[word] = {"word": word, "meanings": []}
        pos = _truncate_field(row.get("pos", "").strip(), _MAX_POS_LEN, "pos", word)
        definition = _truncate_field(row.get("definition", "").strip(), _MAX_DEFINITION_LEN, "definition", word)
        source = _truncate_field(row.get("source", "").strip(), _MAX_SOURCE_LEN, "source", word)
        ipa = _truncate_field(row.get("ipa", "").strip(), _MAX_IPA_LEN, "ipa", word)
        if ipa and not entries[word].get("ipa"):
            entries[word]["ipa"] = ipa
        if pos and definition:
            entries[word]["meanings"].append({
                "pos": pos,
                "definition": definition,
                "sources": [source] if source else [],
            })
    return list(entries.values())


def import_from_csv(session: Session, content: str, batch_name: str) -> dict:
    """从 CSV 导入。期望列: word, pos, definition, source。"""
    entries = _parse_csv_text(content)
    return import_from_json(session, entries, batch_name)


def _parse_excel(file_content: bytes) -> list[dict[str, Any]]:
    """将 Excel 文件解析为词汇 entries 列表。

    期望列: word, pos, definition, source（与 CSV 格式一致）。
    """
    from openpyxl import load_workbook

    try:
        wb = load_workbook(filename=io.BytesIO(file_content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"无法解析 Excel 文件: {exc}") from exc
    ws = wb.active
    if ws is None:
        raise ValueError("Excel 文件中没有工作表")

    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise ValueError("Excel 文件为空")

    # 首行为表头，查找列索引
    header = [str(c).strip().lower() if c else "" for c in rows[0]]
    col_map: dict[str, int] = {}
    for alias, key in [
        ("word", "word"), ("单词", "word"),
        ("pos", "pos"), ("词性", "pos"),
        ("definition", "definition"), ("释义", "definition"), ("中文释义", "definition"),
        ("source", "source"), ("来源", "source"), ("教材来源", "source"),
        ("ipa", "ipa"), ("音标", "ipa"),
    ]:
        if alias in header and key not in col_map:
            col_map[key] = header.index(alias)

    if "word" not in col_map:
        raise ValueError("Excel 缺少必要的 'word'（或 '单词'）列")

    entries: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        word = str(row[col_map["word"]] or "").strip()
        if not word:
            continue
        if len(word) > _MAX_WORD_LEN:
            _logger.warning("Excel 跳过超长单词 (len=%d): %s...", len(word), word[:30])
            continue
        if word not in entries:
            entries[word] = {"word": word, "meanings": []}
        pos = _truncate_field(
            str(row[col_map.get("pos", -1)] or "").strip() if "pos" in col_map else "",
            _MAX_POS_LEN, "pos", word,
        )
        definition = _truncate_field(
            str(row[col_map.get("definition", -1)] or "").strip() if "definition" in col_map else "",
            _MAX_DEFINITION_LEN, "definition", word,
        )
        source = _truncate_field(
            str(row[col_map.get("source", -1)] or "").strip() if "source" in col_map else "",
            _MAX_SOURCE_LEN, "source", word,
        )
        ipa = _truncate_field(
            str(row[col_map.get("ipa", -1)] or "").strip() if "ipa" in col_map else "",
            _MAX_IPA_LEN, "ipa", word,
        )
        if ipa and not entries[word].get("ipa"):
            entries[word]["ipa"] = ipa
        if pos and definition:
            entries[word]["meanings"].append({
                "pos": pos,
                "definition": definition,
                "sources": [source] if source else [],
            })
    return list(entries.values())


# S-H2: Magic bytes 校验映射
_MAGIC_BYTES = {
    ".xlsx": [b"PK\x03\x04"],  # ZIP (OOXML)
    ".xls": [b"\xd0\xcf\x11\xe0"],  # OLE2
    ".json": [],  # JSON 靠解析校验
    ".csv": [],   # CSV 靠解析校验
}


def _validate_magic_bytes(file_content: bytes, filename: str) -> None:
    """校验文件 magic bytes 与扩展名一致，防止恶意文件伪装。"""
    lower = filename.lower()
    for ext, signatures in _MAGIC_BYTES.items():
        if lower.endswith(ext):
            if not signatures:
                return  # JSON/CSV 无固定 magic bytes
            for sig in signatures:
                if file_content[:len(sig)] == sig:
                    return
            raise ValueError(f"文件内容与 {ext} 格式不匹配，请确认文件完整性")
    raise ValueError(f"不支持的文件格式: {filename}")


def parse_upload(file_content: bytes, filename: str) -> list[dict[str, Any]]:
    """根据文件扩展名解析上传内容。"""
    _validate_magic_bytes(file_content, filename)
    lower = filename.lower()
    if lower.endswith(".json"):
        data = json.loads(file_content.decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("JSON 文件格式错误：期望数组格式，如 [{\"word\": \"hello\", ...}]")
        return data
    if lower.endswith(".csv"):
        return _parse_csv_text(file_content.decode("utf-8"))
    if lower.endswith((".xlsx", ".xls")):
        return _parse_excel(file_content)
    raise ValueError(f"不支持的文件格式: {filename}，请使用 .xlsx, .csv 或 .json")


def _get_or_create_package(session: Session, name: str, *, force: bool = False) -> Package:
    pkg = session.query(Package).filter_by(name=name).first()
    if pkg is not None:
        if pkg.status == "pending":
            return pkg
        if not force:
            raise ValueError(f"批次 '{name}' 已在处理中（状态: {pkg.status}），不可重复导入")
        # force=True: 清理旧数据，重新导入
        _clean_package_data(session, pkg)
        pkg.status = "pending"
        pkg.processed_words = 0
        session.flush()
        return pkg
    pkg = Package(name=name)
    session.add(pkg)
    session.flush()
    return pkg


def _clean_package_data(session: Session, pkg: Package) -> None:
    """清理批次关联的旧数据，为重新导入做准备。

    策略：
    - 删除该包独占词的 pending ContentItem（chunk/sentence/mnemonic/syllable）
    - 删除该包的 PackageWord 映射
    - 不删除已生成的内容（非空 content），不删除跨包共享的数据
    """
    from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

    # 1. 找出该包关联的所有 word_id
    old_pw_rows = session.query(PackageWord).filter_by(package_id=pkg.id).all()
    old_word_ids = {pw.word_id for pw in old_pw_rows}
    if not old_word_ids:
        return

    # 2. 找出哪些 word 被其他包共享
    shared_word_ids: set[int] = set()
    for wid in old_word_ids:
        other = (
            session.query(PackageWord)
            .filter(PackageWord.word_id == wid, PackageWord.package_id != pkg.id)
            .first()
        )
        if other is not None:
            shared_word_ids.add(wid)

    exclusive_word_ids = old_word_ids - shared_word_ids

    # 3. 找出独占词的所有 meaning_id
    exclusive_meaning_ids: set[int] = set()
    if exclusive_word_ids:
        exclusive_meaning_ids = {
            row[0] for row in
            session.query(Meaning.id).filter(Meaning.word_id.in_(exclusive_word_ids)).all()
        }

    # 4. 收集要删除的 ContentItem IDs，先删关联的 ReviewItem 再删 ContentItem
    ci_ids_to_delete: list[int] = []
    if exclusive_meaning_ids:
        ci_ids_to_delete.extend(
            row[0] for row in session.query(ContentItem.id).filter(
                ContentItem.meaning_id.in_(exclusive_meaning_ids),
                ContentItem.dimension.in_(("chunk", "sentence", *MNEMONIC_DIMENSIONS)),
                ContentItem.qc_status == QcStatus.PENDING.value,
                ContentItem.content == "",
            ).all()
        )

    # 5. 收集独占词的 pending syllable IDs
    if exclusive_word_ids:
        ci_ids_to_delete.extend(
            row[0] for row in session.query(ContentItem.id).filter(
                ContentItem.word_id.in_(exclusive_word_ids),
                ContentItem.dimension == "syllable",
                ContentItem.qc_status == QcStatus.PENDING.value,
                ContentItem.content == "",
            ).all()
        )

    # 6. 先删关联的 ReviewItem，再删 ContentItem（防止孤儿 ReviewItem）
    if ci_ids_to_delete:
        session.query(ReviewItem).filter(
            ReviewItem.content_item_id.in_(ci_ids_to_delete),
        ).delete(synchronize_session=False)
        session.query(ContentItem).filter(
            ContentItem.id.in_(ci_ids_to_delete),
        ).delete(synchronize_session=False)

    # 7. 删除独占词的 RetryCounter
    if exclusive_meaning_ids:
        session.query(RetryCounter).filter(
            RetryCounter.meaning_id.in_(exclusive_meaning_ids),
        ).delete(synchronize_session=False)
    if exclusive_word_ids:
        session.query(RetryCounter).filter(
            RetryCounter.word_id.in_(exclusive_word_ids),
            RetryCounter.meaning_id.is_(None),
        ).delete(synchronize_session=False)

    # 8. 删除 PackageWord 映射
    session.query(PackageWord).filter_by(package_id=pkg.id).delete(synchronize_session=False)
    session.flush()


def _get_or_create_word(session: Session, word_text: str) -> Word:
    word = session.query(Word).filter_by(word=word_text).first()
    if word is not None:
        return word
    word = Word(word=word_text)
    session.add(word)
    session.flush()
    return word


def _create_content_placeholders(
    session: Session,
    words: list[Word],
    meanings: list[tuple[Word, Meaning]],
) -> None:
    """为导入的数据创建 ContentItem 占位记录。

    chunk / sentence / mnemonic 均按义项生成（防止一词多义混淆）。
    syllable 按单词生成（词级维度，meaning_id=None）。
    """
    from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

    per_meaning_dims = ("chunk", "sentence", *MNEMONIC_DIMENSIONS)

    # 批量预查已存在的 ContentItem (word_id, meaning_id, dimension) 三元组
    all_word_ids = list({w.id for w in words})
    existing_triples: set[tuple[int, int | None, str]] = set()

    for i in range(0, len(all_word_ids), 900):
        chunk = all_word_ids[i:i + 900]
        for row in session.query(
            ContentItem.word_id, ContentItem.meaning_id, ContentItem.dimension,
        ).filter(ContentItem.word_id.in_(chunk)).all():
            existing_triples.add((row[0], row[1], row[2]))

    new_items: list[ContentItem] = []

    for word, meaning in meanings:
        for dim in per_meaning_dims:
            if (word.id, meaning.id, dim) not in existing_triples:
                new_items.append(ContentItem(
                    word_id=word.id,
                    meaning_id=meaning.id,
                    dimension=dim,
                    content="",
                    qc_status=QcStatus.PENDING.value,
                ))
                existing_triples.add((word.id, meaning.id, dim))

    # 词级维度: syllable（每个单词一条，meaning_id=None）
    for word in words:
        if (word.id, None, "syllable") not in existing_triples:
            new_items.append(ContentItem(
                word_id=word.id,
                meaning_id=None,
                dimension="syllable",
                content="",
                qc_status=QcStatus.PENDING.value,
            ))
            existing_triples.add((word.id, None, "syllable"))

    if new_items:
        session.add_all(new_items)
        session.flush()


def _upsert_phonetic_ipa(session: Session, word: Word, ipa: str) -> None:
    """创建或更新 Phonetic 记录的 IPA 音标。"""
    phonetic = session.query(Phonetic).filter_by(word_id=word.id).first()
    if phonetic is None:
        session.add(Phonetic(word_id=word.id, ipa=ipa, syllables=""))
    else:
        phonetic.ipa = ipa
    session.flush()


def _find_or_create_meaning(session: Session, word: Word, pos: str, definition: str) -> Meaning:
    """释义合并：释义文本完全一致 → 复用；否则新建。"""
    existing = (
        session.query(Meaning)
        .filter_by(word_id=word.id, pos=pos, definition=definition)
        .first()
    )
    if existing is not None:
        return existing
    meaning = Meaning(word_id=word.id, pos=pos, definition=definition)
    session.add(meaning)
    session.flush()
    return meaning
