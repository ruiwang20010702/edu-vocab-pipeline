"""生产编排服务: 导入后触发 生成→质检→入队审核 全流程."""

from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.generators.chunk import ChunkGenerator
from vocab_qc.core.generators.mnemonic import MnemonicGenerator
from vocab_qc.core.generators.sentence import SentenceGenerator
from vocab_qc.core.models.content_layer import ContentItem
from vocab_qc.core.models.data_layer import Meaning, Word
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageMeaning
from vocab_qc.core.services.qc_service import QcService

# 维度→生成器映射
_GENERATORS = {
    "chunk": ChunkGenerator(),
    "sentence": SentenceGenerator(),
    "mnemonic": MnemonicGenerator(),
}


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

    # Step 2: 运行 Layer 1 质检
    qc_result = {"passed": 0, "failed": 0}
    for word_id in word_ids_from_meanings:
        result = qc.run_layer1(session, scope=f"word_id:{word_id}")
        qc_result["passed"] += result.get("passed", 0)
        qc_result["failed"] += result.get("failed", 0)

        # Step 3: 失败项入队审核
        if result.get("run_id"):
            qc.enqueue_failed_for_review(session, result["run_id"])

    # Step 4: 运行 Layer 2 AI 质检（仅针对 Layer 1 通过项）
    l2_result = {"passed": 0, "failed": 0}
    for word_id in word_ids_from_meanings:
        result = qc.run_layer2(session, scope=f"word_id:{word_id}")
        l2_result["passed"] += result.get("passed", 0)
        l2_result["failed"] += result.get("failed", 0)

        # Step 5: Layer 2 失败项入队审核
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
    count = 0
    for item in items:
        if item.content:  # 已有内容则跳过
            continue

        generator = _GENERATORS.get(item.dimension)
        if generator is None:
            continue

        # 获取关联数据
        word = session.query(Word).filter_by(id=item.word_id).first()
        if word is None:
            continue

        meaning_text = None
        pos = None
        if item.meaning_id:
            meaning = session.query(Meaning).filter_by(id=item.meaning_id).first()
            if meaning:
                meaning_text = meaning.definition
                pos = meaning.pos

        result = generator.generate(
            word=word.word,
            meaning=meaning_text,
            pos=pos,
        )

        item.content = result.get("content", "")
        if result.get("content_cn"):
            item.content_cn = result["content_cn"]

        count += 1

    session.flush()
    return count
