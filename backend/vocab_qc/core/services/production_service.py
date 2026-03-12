"""生产编排服务: 导入后触发 生成→质检→入队审核 全流程."""

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from vocab_qc.core.config import settings
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
from vocab_qc.core.models.quality_layer import AiErrorLog, classify_ai_error
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


def _get_word_ids_for_package(session: Session, package_id: int) -> set[int]:
    """获取 Package 关联的所有 word_id。"""
    meaning_ids = {
        row[0]
        for row in session.query(PackageMeaning.meaning_id)
        .filter_by(package_id=package_id)
        .all()
    }
    if not meaning_ids:
        return set()
    return {
        row[0]
        for row in session.query(Meaning.word_id)
        .filter(Meaning.id.in_(meaning_ids))
        .all()
    }


def step_generate(session: Session, package_id: int) -> int:
    """Step 1: 为 Package 生成内容（独立事务）。"""
    pkg = session.query(Package).filter_by(id=package_id).first()
    if pkg is None:
        raise ValueError(f"Package {package_id} 不存在")

    pkg.status = "processing"
    session.flush()

    word_ids = _get_word_ids_for_package(session, package_id)
    if not word_ids:
        return 0

    items = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids))
        .filter_by(qc_status=QcStatus.PENDING.value)
        .all()
    )
    generated = _generate_content(session, items)
    session.flush()
    return generated


def step_qc_layer1(session: Session, package_id: int, qc_service: Optional[QcService] = None) -> dict:
    """Step 2: Layer 1 质检 + 失败项入队审核（批量，独立事务）。"""
    qc = qc_service or QcService()
    word_ids = _get_word_ids_for_package(session, package_id)

    result = qc.run_layer1_batch(session, word_ids)
    if result.get("run_id"):
        qc.enqueue_failed_for_review(session, result["run_id"])

    session.flush()
    return {"passed": result["passed"], "failed": result["failed"]}


def step_qc_layer2(session: Session, package_id: int, qc_service: Optional[QcService] = None) -> dict:
    """Step 3: Layer 2 AI 质检 + 失败项入队审核（批量，独立事务）。"""
    qc = qc_service or QcService()
    word_ids = _get_word_ids_for_package(session, package_id)

    result = qc.run_layer2_batch(session, word_ids)
    if result.get("run_id"):
        qc.enqueue_layer2_failed_for_review(session, result["run_id"])

    session.flush()
    return {"passed": result["passed"], "failed": result["failed"]}


def step_finalize(session: Session, package_id: int) -> None:
    """标记 Package 为 completed，更新 processed_words，自动批准通过项。"""
    pkg = session.query(Package).filter_by(id=package_id).first()
    if pkg is None:
        return

    word_ids = _get_word_ids_for_package(session, package_id)
    _auto_approve_passed(session, word_ids)
    pkg.processed_words = len(word_ids)
    pkg.status = "completed"
    session.flush()


def _auto_approve_passed(session: Session, word_ids: set[int]) -> int:
    """将通过全部质检的 ContentItem 自动提升为 approved。

    - layer2_passed → approved（通过了 L1 + L2）
    - layer1_passed 且该维度无 L2 规则 → approved（L2 不适用）
    """
    if not word_ids:
        return 0

    # L2 有规则的维度
    _L2_DIMENSIONS = {"sentence", "chunk", "mnemonic_root_affix",
                      "mnemonic_word_in_word", "mnemonic_sound_meaning",
                      "mnemonic_exam_app"}

    count = 0

    # 1. layer2_passed → approved
    l2_passed = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids))
        .filter_by(qc_status=QcStatus.LAYER2_PASSED.value)
        .all()
    )
    for item in l2_passed:
        item.qc_status = QcStatus.APPROVED.value
        count += 1

    # 2. layer1_passed 且无 L2 规则（如 syllable）→ approved
    l1_passed = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids))
        .filter_by(qc_status=QcStatus.LAYER1_PASSED.value)
        .all()
    )
    for item in l1_passed:
        if item.dimension not in _L2_DIMENSIONS:
            item.qc_status = QcStatus.APPROVED.value
            count += 1

    if count:
        session.flush()
    return count


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

    # Step 2: 运行 Layer 1 质检（批量）
    qc_result = qc.run_layer1_batch(session, word_ids_from_meanings)
    if qc_result.get("run_id"):
        qc.enqueue_failed_for_review(session, qc_result["run_id"])
    session.flush()

    # Step 3: 运行 Layer 2 AI 质检（批量，仅针对 Layer 1 通过项）
    l2_result = qc.run_layer2_batch(session, word_ids_from_meanings)
    if l2_result.get("run_id"):
        qc.enqueue_layer2_failed_for_review(session, l2_result["run_id"])

    # Step 4: 自动批准通过全部质检的项目
    auto_approved = _auto_approve_passed(session, word_ids_from_meanings)

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
        "auto_approved": auto_approved,
    }


logger = logging.getLogger(__name__)


def _generate_content(session: Session, items: list[ContentItem]) -> int:
    """为空的 ContentItem 并发调用 AI 生成器填充内容。

    Step A: 预加载数据 + AI config，构造纯参数任务列表
    Step B: asyncio 并发调用 AI（不涉及 DB session）
    Step C: 主线程批量写入结果
    """
    if not items:
        return 0

    # --- Step A: 预加载，构造任务 ---
    word_ids = {item.word_id for item in items}
    meaning_ids = {item.meaning_id for item in items if item.meaning_id}
    words_map = {w.id: w for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
    meanings_map = (
        {m.id: m for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all()}
        if meaning_ids else {}
    )

    # 预加载每个维度的 AI config（避免异步调用内读 DB）
    ai_configs: dict[str, Any] = {}
    for dim, gen in _GENERATORS.items():
        ai_configs[dim] = gen.get_ai_config(session)

    # 构造纯参数任务列表
    tasks: list[tuple[int, str, str, Optional[str], Optional[str]]] = []
    item_map: dict[int, ContentItem] = {}
    for item in items:
        if item.content:
            continue
        if item.dimension not in _GENERATORS:
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

        tasks.append((item.id, item.dimension, word.word, meaning_text, pos))
        item_map[item.id] = item

    if not tasks:
        return 0

    # --- Step B: asyncio 并发 AI 调用 ---
    error_logs: list[AiErrorLog] = []

    async def _generate_all() -> dict[int, dict]:
        semaphore = asyncio.Semaphore(settings.ai_max_concurrency)

        async def _call_one(task: tuple) -> tuple[int, dict]:
            item_id, dimension, word_text, meaning_text, pos = task
            generator = _GENERATORS[dimension]
            config = ai_configs[dimension]
            async with semaphore:
                result = await generator.generate_async(
                    word=word_text, meaning=meaning_text, pos=pos,
                    _preloaded_config=config,
                )
            return item_id, result

        async_tasks = [asyncio.create_task(_call_one(t)) for t in tasks]
        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=300,  # 5 分钟总超时，防止永久挂起
            )
        except asyncio.TimeoutError:
            for t in async_tasks:
                t.cancel()
            # 等待取消完成，忽略 CancelledError
            await asyncio.gather(*async_tasks, return_exceptions=True)
            raise

        results: dict[int, dict] = {}
        for i, r in enumerate(gathered):
            item_id = tasks[i][0]
            if isinstance(r, Exception):
                logger.warning("生成失败 item_id=%s: %s", item_id, r)
                results[item_id] = {}
                item = item_map[item_id]
                error_logs.append(AiErrorLog(
                    content_item_id=item_id,
                    word_id=item.word_id,
                    phase="generation",
                    dimension=item.dimension,
                    error_type=classify_ai_error(r),
                    error_message=str(r)[:2000],
                    ai_model=settings.ai_model,
                    retry_count=settings.ai_max_retries,
                ))
            else:
                results[r[0]] = r[1]
        return results

    # 同步桥接：在独立事件循环中运行异步任务
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        results = asyncio.run(_generate_all())
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            results = pool.submit(asyncio.run, _generate_all()).result()

    # --- Step C: 主线程批量写入 ---
    count = 0
    for item_id, result in results.items():
        item = item_map[item_id]

        if result.get("valid") is False:
            item.content = ""
            item.qc_status = QcStatus.REJECTED.value
            count += 1
            continue

        content = result.get("content", "")
        if not content:
            # 生成失败（空字典或 content 为空）→ 标记为 LAYER1_FAILED 让质检流程接管
            item.content = ""
            item.qc_status = QcStatus.LAYER1_FAILED.value
            count += 1
            continue

        item.content = content
        if result.get("content_cn"):
            item.content_cn = result["content_cn"]
        count += 1

    # 持久化 AI 错误日志
    for log in error_logs:
        session.add(log)

    session.flush()
    return count
