"""生产编排服务: 导入后触发 生成→质检→入队审核 全流程."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.generators.chunk import ChunkGenerator
from vocab_qc.core.generators.mnemonic import (
    ExamAppMnemonicGenerator,
    RootAffixMnemonicGenerator,
    SoundMeaningMnemonicGenerator,
    WordInWordMnemonicGenerator,
)
from vocab_qc.core.generators.sentence import SentenceGenerator
from vocab_qc.core.generators.syllable import SyllableGenerator
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageMeaning
from vocab_qc.core.services.qc_service import QcService

# 维度→生成器映射
_GENERATORS = {
    "chunk": ChunkGenerator(),
    "sentence": SentenceGenerator(),
    "syllable": SyllableGenerator(),
    "mnemonic_root_affix": RootAffixMnemonicGenerator(),
    "mnemonic_word_in_word": WordInWordMnemonicGenerator(),
    "mnemonic_sound_meaning": SoundMeaningMnemonicGenerator(),
    "mnemonic_exam_app": ExamAppMnemonicGenerator(),
}


# TODO(perf): 当前 run_production 在单个 session 事务中执行所有操作（包括 AI 调用），
# 会导致长事务占用数据库连接。应拆分为多个独立 session：
# 1. session1: 生成内容 → commit
# 2. session2: Layer 1 质检 → commit
# 3. session3: Layer 2 AI 质检 → commit
# 每步失败后需将 Package.status 标记为 failed。
def run_production(
    session: Session,
    package_id: int,
    qc_service: Optional[QcService] = None,
) -> dict:
    """为指定 Package 执行完整生产流水线。

    流程: 生成内容 → Layer 1 质检 → Layer 2 AI 质检 → 失败项入队审核

    Returns:
        {"generated": int, "qc_passed": int, "qc_failed": int,
         "l2_passed": int, "l2_failed": int, "enqueued": int}
    """
    qc = qc_service or QcService()

    pkg = session.query(Package).filter_by(id=package_id).first()
    if pkg is None:
        raise ValueError(f"Package {package_id} 不存在")

    pkg.status = "processing"
    session.flush()

    # 获取 Package 下所有义项关联的 word_id
    package_meaning_rows = (
        session.query(PackageMeaning.meaning_id)
        .filter_by(package_id=package_id)
        .all()
    )
    meaning_ids = {row[0] for row in package_meaning_rows}

    if not meaning_ids:
        pkg.status = "completed"
        pkg.processed_words = 0
        session.flush()
        return {"generated": 0, "qc_passed": 0, "qc_failed": 0, "enqueued": 0}

    # 找出所有 word_id
    word_ids_from_meanings = {
        row[0]
        for row in session.query(Meaning.word_id)
        .filter(Meaning.id.in_(meaning_ids))
        .all()
    }

    # 获取所有待生成的 ContentItem（content 为空且状态 pending）
    items = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids_from_meanings))
        .filter_by(qc_status=QcStatus.PENDING.value)
        .all()
    )

    # Step 1: 生成内容
    generated = _generate_content(session, items)
    session.flush()

    # Step 2: 运行 Layer 1 质检
    qc_result = {"passed": 0, "failed": 0}
    for word_id in word_ids_from_meanings:
        result = qc.run_layer1(session, scope=f"word_id:{word_id}")
        qc_result["passed"] += result.get("passed", 0)
        qc_result["failed"] += result.get("failed", 0)

        # 失败项入队审核
        if result.get("run_id"):
            qc.enqueue_failed_for_review(session, result["run_id"])
    session.flush()

    # Step 3: 运行 Layer 2 AI 质检（仅针对 Layer 1 通过项）
    l2_result = {"passed": 0, "failed": 0}
    for word_id in word_ids_from_meanings:
        result = qc.run_layer2(session, scope=f"word_id:{word_id}")
        l2_result["passed"] += result.get("passed", 0)
        l2_result["failed"] += result.get("failed", 0)

        # Layer 2 失败项入队审核
        if result.get("run_id"):
            qc.enqueue_layer2_failed_for_review(session, result["run_id"])

    # 更新 Package 状态
    pkg.processed_words = len(word_ids_from_meanings)
    pkg.status = "completed"
    session.flush()

    enqueued = qc_result["failed"] + l2_result["failed"]
    return {
        "generated": generated,
        "qc_passed": qc_result["passed"],
        "qc_failed": qc_result["failed"],
        "l2_passed": l2_result["passed"],
        "l2_failed": l2_result["failed"],
        "enqueued": enqueued,
    }


def _generate_content(session: Session, items: list[ContentItem]) -> int:
    """为空的 ContentItem 调用生成器填充内容。"""
    if not items:
        return 0

    # 批量预加载 Word 和 Meaning，避免 N+1
    word_ids = {item.word_id for item in items}
    meaning_ids = {item.meaning_id for item in items if item.meaning_id}
    words_map = {w.id: w for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
    meanings_map = {m.id: m for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all()} if meaning_ids else {}

    count = 0
    for item in items:
        if item.content:  # 已有内容则跳过
            continue

        generator = _GENERATORS.get(item.dimension)
        if generator is None:
            continue

        word = words_map.get(item.word_id)
        if word is None:
            continue

        meaning_text = None
        pos = None
        if item.meaning_id:
            meaning = meanings_map.get(item.meaning_id)
            if meaning:
                meaning_text = meaning.definition
                pos = meaning.pos

        result = generator.generate(
            word=word.word,
            meaning=meaning_text,
            pos=pos,
            session=session,
        )

        # 助记类型返回 valid: false → 该类型不适用，跳过
        if result.get("valid") is False:
            item.content = ""
            item.qc_status = QcStatus.REJECTED.value
            count += 1
            continue

        item.content = result.get("content", "")
        if result.get("content_cn"):
            item.content_cn = result["content_cn"]

        count += 1

    session.flush()
    return count
