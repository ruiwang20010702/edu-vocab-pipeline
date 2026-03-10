"""数据导入服务: 解析文件 → 创建 Word / Meaning / ContentItem。"""

import csv
import io
import json
from typing import Any

from sqlalchemy.orm import Session

from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Source, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageMeaning


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

    for entry in data:
        word_text = entry.get("word", "").strip()
        if not word_text:
            continue

        word = _get_or_create_word(session, word_text)
        word_count += 1
        imported_words.append(word)

        for m_data in entry.get("meanings", []):
            pos = m_data.get("pos", "").strip()
            definition = m_data.get("definition", "").strip()
            if not pos or not definition:
                continue

            meaning = _find_or_create_meaning(session, word, pos, definition)
            imported_meanings.append((word, meaning))

            # 来源
            for src_name in m_data.get("sources", []):
                existing = (
                    session.query(Source)
                    .filter_by(meaning_id=meaning.id, source_name=src_name)
                    .first()
                )
                if existing is None:
                    session.add(Source(meaning_id=meaning.id, source_name=src_name))

            # 包-义项映射
            existing_pm = (
                session.query(PackageMeaning)
                .filter_by(package_id=package.id, meaning_id=meaning.id)
                .first()
            )
            if existing_pm is None:
                session.add(PackageMeaning(package_id=package.id, meaning_id=meaning.id))

    # 创建 ContentItem 占位记录（chunk/sentence 按义项, mnemonic 按单词）
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
        if word not in entries:
            entries[word] = {"word": word, "meanings": []}
        pos = row.get("pos", "").strip()
        definition = row.get("definition", "").strip()
        source = row.get("source", "").strip()
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
        if word not in entries:
            entries[word] = {"word": word, "meanings": []}
        pos = str(row[col_map.get("pos", -1)] or "").strip() if "pos" in col_map else ""
        definition = str(row[col_map.get("definition", -1)] or "").strip() if "definition" in col_map else ""
        source = str(row[col_map.get("source", -1)] or "").strip() if "source" in col_map else ""
        if pos and definition:
            entries[word]["meanings"].append({
                "pos": pos,
                "definition": definition,
                "sources": [source] if source else [],
            })
    return list(entries.values())


def parse_upload(file_content: bytes, filename: str) -> list[dict[str, Any]]:
    """根据文件扩展名解析上传内容。"""
    lower = filename.lower()
    if lower.endswith(".json"):
        return json.loads(file_content.decode("utf-8"))
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
    - 删除该包独占义项的 pending ContentItem（chunk/sentence）
    - 删除该包独占单词的 pending mnemonic ContentItem
    - 删除该包的 PackageMeaning 映射
    - 不删除已生成的内容（非空 content），不删除跨包共享的数据
    """
    from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

    # 1. 找出该包关联的所有 meaning_id
    old_pm_rows = session.query(PackageMeaning).filter_by(package_id=pkg.id).all()
    old_meaning_ids = {pm.meaning_id for pm in old_pm_rows}
    if not old_meaning_ids:
        return

    # 2. 找出哪些 meaning 被其他包共享
    shared_meaning_ids: set[int] = set()
    for mid in old_meaning_ids:
        other = (
            session.query(PackageMeaning)
            .filter(PackageMeaning.meaning_id == mid, PackageMeaning.package_id != pkg.id)
            .first()
        )
        if other is not None:
            shared_meaning_ids.add(mid)

    exclusive_meaning_ids = old_meaning_ids - shared_meaning_ids

    # 3. 找出独占义项对应的 word_id
    exclusive_word_ids: set[int] = set()
    if exclusive_meaning_ids:
        meanings = session.query(Meaning).filter(Meaning.id.in_(exclusive_meaning_ids)).all()
        candidate_word_ids = {m.word_id for m in meanings}
        # 只有当该词的所有义项都是本包独占时，才算独占词
        for wid in candidate_word_ids:
            word_meaning_ids = {m.id for m in session.query(Meaning).filter_by(word_id=wid).all()}
            if word_meaning_ids <= exclusive_meaning_ids:
                exclusive_word_ids.add(wid)

    # 4. 删除独占义项的 pending chunk/sentence
    if exclusive_meaning_ids:
        session.query(ContentItem).filter(
            ContentItem.meaning_id.in_(exclusive_meaning_ids),
            ContentItem.dimension.in_(("chunk", "sentence")),
            ContentItem.qc_status == QcStatus.PENDING.value,
            ContentItem.content == "",
        ).delete(synchronize_session=False)

    # 5. 删除独占单词的 pending mnemonic
    if exclusive_word_ids:
        session.query(ContentItem).filter(
            ContentItem.word_id.in_(exclusive_word_ids),
            ContentItem.dimension.in_(MNEMONIC_DIMENSIONS),
            ContentItem.qc_status == QcStatus.PENDING.value,
            ContentItem.content == "",
        ).delete(synchronize_session=False)

    # 6. 删除 PackageMeaning 映射
    session.query(PackageMeaning).filter_by(package_id=pkg.id).delete(synchronize_session=False)
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

    - chunk / sentence: 按义项生成（防止多义词张冠李戴）
    - mnemonic: 按单词生成（面向拼写/发音，与义项无关）
    """
    # chunk + sentence — 每个义项各一条
    for word, meaning in meanings:
        for dim in ("chunk", "sentence"):
            exists = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, meaning_id=meaning.id, dimension=dim)
                .first()
            )
            if exists is None:
                session.add(
                    ContentItem(
                        word_id=word.id,
                        meaning_id=meaning.id,
                        dimension=dim,
                        content="",
                        qc_status=QcStatus.PENDING.value,
                    )
                )

    # mnemonic — 每个单词 4 条（4 种助记类型，与义项无关）
    from vocab_qc.core.models.enums import MNEMONIC_DIMENSIONS

    seen_word_ids: set[int] = set()
    for word in words:
        if word.id in seen_word_ids:
            continue
        seen_word_ids.add(word.id)
        for mnem_dim in MNEMONIC_DIMENSIONS:
            exists = (
                session.query(ContentItem)
                .filter_by(word_id=word.id, dimension=mnem_dim)
                .first()
            )
            if exists is None:
                session.add(
                    ContentItem(
                        word_id=word.id,
                        meaning_id=None,
                        dimension=mnem_dim,
                        content="",
                        qc_status=QcStatus.PENDING.value,
                    )
                )


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
