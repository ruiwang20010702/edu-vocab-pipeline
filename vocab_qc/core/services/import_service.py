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


def import_from_json(session: Session, data: list[dict[str, Any]], batch_name: str) -> dict:
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
    package = _get_or_create_package(session, batch_name)
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


def import_from_csv(session: Session, content: str, batch_name: str) -> dict:
    """从 CSV 导入。期望列: word, pos, definition, source。"""
    reader = csv.DictReader(io.StringIO(content))
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

    return import_from_json(session, list(entries.values()), batch_name)


def parse_upload(file_content: bytes, filename: str) -> list[dict[str, Any]]:
    """根据文件扩展名解析上传内容。"""
    lower = filename.lower()
    if lower.endswith(".json"):
        return json.loads(file_content.decode("utf-8"))
    if lower.endswith(".csv"):
        text = file_content.decode("utf-8")
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
    raise ValueError(f"不支持的文件格式: {filename}，请使用 .json 或 .csv")


def _get_or_create_package(session: Session, name: str) -> Package:
    pkg = session.query(Package).filter_by(name=name).first()
    if pkg is not None:
        return pkg
    pkg = Package(name=name)
    session.add(pkg)
    session.flush()
    return pkg


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
