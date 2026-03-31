"""生产编排服务: 导入后触发 生成→质检→入队审核 全流程."""

import asyncio
import logging
from datetime import UTC, datetime
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
from vocab_qc.core.models.ai_task_queue import AiTaskStatus
from vocab_qc.core.models.enums import QcStatus
from vocab_qc.core.models.package_layer import Package, PackageWord
from vocab_qc.core.models.quality_layer import AiErrorLog, AiUsageLog, classify_ai_error
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
    return {
        row[0]
        for row in session.query(PackageWord.word_id)
        .filter_by(package_id=package_id)
        .all()
    }


def step_generate(
    session: Session,
    package_id: int,
    word_ids: set[int] | None = None,
) -> int:
    """Step 1: 为 Package 生成内容（独立事务）。

    Args:
        word_ids: 可选，仅处理指定的 word_id 子集（分批模式）。
                  为 None 时处理整个 Package。
    """
    pkg = session.query(Package).filter_by(id=package_id).first()
    if pkg is None:
        raise ValueError(f"Package {package_id} 不存在")

    pkg.status = "processing"
    if pkg.started_at is None:
        pkg.started_at = datetime.now(UTC)
    session.flush()

    if word_ids is None:
        word_ids = _get_word_ids_for_package(session, package_id)
    if not word_ids:
        return 0

    items = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids))
        .filter_by(qc_status=QcStatus.PENDING.value)
        .all()
    )
    generated = _generate_content(session, items, package_id=package_id)
    session.flush()
    return generated


def step_qc_layer1(
    session: Session,
    package_id: int,
    qc_service: Optional[QcService] = None,
    word_ids: set[int] | None = None,
) -> dict:
    """Step 2: Layer 1 质检 + 失败项入队审核（批量，独立事务）。

    Args:
        word_ids: 可选，仅处理指定的 word_id 子集（分批模式）。
    """
    qc = qc_service or QcService()
    if word_ids is None:
        word_ids = _get_word_ids_for_package(session, package_id)

    result = qc.run_layer1_batch(session, word_ids)
    if result.get("run_id"):
        qc.enqueue_failed_for_review(session, result["run_id"])

    session.flush()
    return {"passed": result["passed"], "failed": result["failed"]}


def step_qc_layer2(
    session: Session,
    package_id: int,
    qc_service: Optional[QcService] = None,
    word_ids: set[int] | None = None,
) -> dict:
    """Step 3: Layer 2 AI 质检 + 失败项入队审核（批量，独立事务）。

    Args:
        word_ids: 可选，仅处理指定的 word_id 子集（分批模式）。
    """
    qc = qc_service or QcService()
    if word_ids is None:
        word_ids = _get_word_ids_for_package(session, package_id)

    result = qc.run_layer2_batch(session, word_ids, package_id=package_id)
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
    pkg.completed_at = datetime.now(UTC)
    pkg.status = "completed"
    session.flush()


def _auto_approve_passed(session: Session, word_ids: set[int]) -> int:
    """将通过全部质检的 ContentItem 自动提升为 approved。

    - layer2_passed → approved（通过了 L1 + L2）
    - layer1_passed 且该维度无 L2 规则 → approved（L2 不适用）
    """
    if not word_ids:
        return 0

    from sqlalchemy import update

    # L2 有规则的维度
    l2_dimensions = {"sentence", "chunk", "mnemonic_root_affix",
                     "mnemonic_word_in_word", "mnemonic_sound_meaning",
                     "mnemonic_exam_app"}

    # 1. layer2_passed → approved（批量 UPDATE）
    r1 = session.execute(
        update(ContentItem)
        .where(
            ContentItem.word_id.in_(word_ids),
            ContentItem.qc_status == QcStatus.LAYER2_PASSED.value,
        )
        .values(qc_status=QcStatus.APPROVED.value)
    )

    # 2. layer1_passed 且无 L2 规则（如 syllable）→ approved（批量 UPDATE）
    r2 = session.execute(
        update(ContentItem)
        .where(
            ContentItem.word_id.in_(word_ids),
            ContentItem.qc_status == QcStatus.LAYER1_PASSED.value,
            ~ContentItem.dimension.in_(l2_dimensions),
        )
        .values(qc_status=QcStatus.APPROVED.value)
    )

    count = r1.rowcount + r2.rowcount
    if count:
        session.flush()
        logger.info("自动批准 auto_approved=%d (l2_passed=%d no_l2=%d)", count, r1.rowcount, r2.rowcount)

        # 清理已 approved 内容对应的 pending review_items（防止数据不一致）
        from vocab_qc.core.models.quality_layer import ReviewItem
        from vocab_qc.core.models.enums import ReviewStatus, ReviewResolution
        approved_ci_ids = [
            row[0] for row in
            session.query(ContentItem.id)
            .filter(
                ContentItem.word_id.in_(word_ids),
                ContentItem.qc_status == QcStatus.APPROVED.value,
            )
            .all()
        ]
        if approved_ci_ids:
            resolved = session.execute(
                update(ReviewItem)
                .where(
                    ReviewItem.content_item_id.in_(approved_ci_ids),
                    ReviewItem.status == ReviewStatus.PENDING.value,
                )
                .values(
                    status=ReviewStatus.RESOLVED.value,
                    resolution=ReviewResolution.APPROVED.value,
                    resolved_at=datetime.now(UTC),
                )
            )
            if resolved.rowcount:
                logger.info("清理已批准内容的残留审核项 count=%d", resolved.rowcount)
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
    import time as _time
    qc = qc_service or QcService()

    pkg = session.query(Package).filter_by(id=package_id).first()
    if pkg is None:
        raise ValueError(f"Package {package_id} 不存在")

    pkg.status = "processing"
    pkg.started_at = datetime.now(UTC)
    session.flush()

    # 获取 Package 关联的所有 word_id
    word_ids_from_package = _get_word_ids_for_package(session, package_id)

    logger.info("生产开始 package_id=%s 词数=%d", package_id, len(word_ids_from_package))

    if not word_ids_from_package:
        pkg.status = "completed"
        pkg.processed_words = 0
        session.flush()
        return {"generated": 0, "qc_passed": 0, "qc_failed": 0, "enqueued": 0}

    # 获取所有待生成的 ContentItem（content 为空且状态 pending）
    items = (
        session.query(ContentItem)
        .filter(ContentItem.word_id.in_(word_ids_from_package))
        .filter_by(qc_status=QcStatus.PENDING.value)
        .all()
    )

    _t0 = _time.monotonic()

    # Step 1: 生成内容
    generated = _generate_content(session, items, package_id=package_id)
    session.flush()
    logger.info("生成阶段完成 package_id=%s 成功=%d 总待生成=%d", package_id, generated, len(items))

    # Step 2: 运行 Layer 1 质检（批量）
    qc_result = qc.run_layer1_batch(session, word_ids_from_package)
    if qc_result.get("run_id"):
        qc.enqueue_failed_for_review(session, qc_result["run_id"])
    session.flush()

    logger.info("L1质检完成 package_id=%s passed=%d failed=%d", package_id, qc_result["passed"], qc_result["failed"])

    # Step 3: 运行 Layer 2 AI 质检（批量，仅针对 Layer 1 通过项）
    l2_result = qc.run_layer2_batch(session, word_ids_from_package, package_id=package_id)
    if l2_result.get("run_id"):
        qc.enqueue_layer2_failed_for_review(session, l2_result["run_id"])

    logger.info("L2质检完成 package_id=%s passed=%d failed=%d", package_id, l2_result["passed"], l2_result["failed"])

    # Step 4: 自动批准通过全部质检的项目
    auto_approved = _auto_approve_passed(session, word_ids_from_package)

    # 更新 Package 状态
    pkg.processed_words = len(word_ids_from_package)
    pkg.completed_at = datetime.now(UTC)
    pkg.status = "completed"
    session.flush()

    _elapsed = _time.monotonic() - _t0
    logger.info(
        "生产完成 package_id=%s 耗时=%.1fs generated=%d l1_passed=%d l1_failed=%d l2_passed=%d l2_failed=%d auto_approved=%d",
        package_id, _elapsed, generated,
        qc_result["passed"], qc_result["failed"],
        l2_result["passed"], l2_result["failed"],
        auto_approved,
    )

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


def _generate_content(session: Session, items: list[ContentItem], *, package_id: int | None = None) -> int:
    """为空的 ContentItem 并发调用 AI 生成器填充内容。

    Step A: 预加载数据 + AI config，构造纯参数任务列表
    Step B: asyncio 并发调用 AI（不涉及 DB session）
    Step C: 主线程批量写入结果
    """
    if not items:
        return 0

    # 任务队列模式：提交/轮询解耦，支持高并发和重启恢复
    if settings.ai_use_task_queue:
        return _generate_content_queued(session, items, package_id=package_id)

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
    usage_logs: list[AiUsageLog] = []

    async def _generate_all() -> dict[int, dict]:
        semaphore = asyncio.Semaphore(settings.ai_max_concurrency)

        stagger = settings.ai_request_stagger

        async def _call_one(task: tuple, index: int = 0) -> tuple[int, dict]:
            item_id, dimension, word_text, meaning_text, pos = task
            generator = _GENERATORS[dimension]
            config = ai_configs[dimension]
            async with semaphore:
                if stagger > 0 and index > 0:
                    await asyncio.sleep((index % settings.ai_max_concurrency) * stagger)
                result = await asyncio.wait_for(
                    generator.generate_async(
                        word=word_text, meaning=meaning_text, pos=pos,
                        _preloaded_config=config,
                    ),
                    timeout=settings.ai_task_timeout,
                )
            return item_id, result

        async_tasks = [asyncio.create_task(_call_one(t, i)) for i, t in enumerate(tasks)]
        # 动态超时：每任务 5s 基准，下限 10 分钟，上限 30 分钟
        _gather_timeout = min(max(600, len(tasks) * 5), 1800)
        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=_gather_timeout,
            )
        except asyncio.TimeoutError:
            for t in async_tasks:
                t.cancel()
            # 等待取消完成，忽略 CancelledError
            await asyncio.gather(*async_tasks, return_exceptions=True)
            raise

        from vocab_qc.core.generators.base import AiUsageInfo, estimate_cost

        results: dict[int, dict] = {}
        for i, r in enumerate(gathered):
            item_id = tasks[i][0]
            if isinstance(r, Exception):
                logger.warning("生成失败 item_id=%s: %s(%s)", item_id, type(r).__name__, r, exc_info=True)
                results[item_id] = {}
                item = item_map[item_id]
                # 从 AiRequestError 或其 __cause__ 提取结构化信息
                cause = r.__cause__ if r.__cause__ else r
                status_code = getattr(cause, "status_code", None)
                resp_body = getattr(cause, "response_body", None) or ""
                elapsed = getattr(cause, "elapsed_ms", None)
                task_no = getattr(cause, "task_no", None) or ""
                error_logs.append(AiErrorLog(
                    content_item_id=item_id,
                    word_id=item.word_id,
                    phase="generation",
                    dimension=item.dimension,
                    error_type=classify_ai_error(cause),
                    error_message=str(r)[:2000],
                    http_status_code=status_code,
                    response_body=resp_body[:500] if resp_body else None,
                    elapsed_ms=elapsed,
                    ai_model=settings.ai_model,
                    gateway_task_no=task_no or None,
                    retry_count=settings.ai_max_retries,
                ))
            else:
                result_item_id, result_data = r
                # 提取 usage 信息（由 _do_request/_call_ai_async 附着）
                usage: AiUsageInfo | None = result_data.pop("__usage__", None)
                if usage and usage.total_tokens > 0:
                    item = item_map[result_item_id]
                    dim_model = ai_configs[item.dimension].model
                    usage_logs.append(AiUsageLog(
                        phase="generation",
                        dimension=item.dimension,
                        ai_model=dim_model,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        estimated_cost_usd=estimate_cost(dim_model, usage),
                        word_id=item.word_id,
                        content_item_id=result_item_id,
                        package_id=package_id,
                    ))
                results[result_item_id] = result_data

        # P-H2: CLI 路径清理 HTTP 客户端
        from vocab_qc.core.generators.base import close_http_clients
        await close_http_clients()

        return results

    # P-H1: 同步桥接
    from vocab_qc.core.async_bridge import run_async_in_sync
    results = run_async_in_sync(_generate_all())

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

    # 持久化 AI 错误日志 + 用量日志
    for log in error_logs:
        session.add(log)
    for log in usage_logs:
        session.add(log)

    session.flush()
    return count


def _generate_content_queued(
    session: Session,
    items: list[ContentItem],
    *,
    package_id: int | None = None,
) -> int:
    """任务队列模式：enqueue → submit → poll → collect → writeback.

    提交与轮询解耦，支持高并发（每批 20 个连续提交）和容器重启恢复。
    """
    import uuid

    from vocab_qc.core.generators.base import (
        AiUsageInfo,
        _strip_markdown_fences,
        estimate_cost,
        extract_usage,
    )
    from vocab_qc.core.polling_pool import PollingPool
    from vocab_qc.core.task_queue import TaskQueueService, TaskSpec

    batch_key = f"gen:{package_id or uuid.uuid4().hex[:8]}"

    # --- Step A: 预加载 + 构造 TaskSpec ---
    word_ids = {item.word_id for item in items}
    meaning_ids = {item.meaning_id for item in items if item.meaning_id}
    words_map = {w.id: w for w in session.query(Word).filter(Word.id.in_(word_ids)).all()}
    meanings_map = (
        {m.id: m for m in session.query(Meaning).filter(Meaning.id.in_(meaning_ids)).all()}
        if meaning_ids else {}
    )

    ai_configs: dict[str, Any] = {}
    for dim, gen in _GENERATORS.items():
        ai_configs[dim] = gen.get_ai_config(session)

    specs: list[TaskSpec] = []
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

        generator = _GENERATORS[item.dimension]
        config = ai_configs[item.dimension]

        # 构造 Gateway 请求 body（内部调用子类的 _build_user_prompt + config）
        submit_body = generator.make_submit_body(
            word=word.word, meaning=meaning_text, pos=pos, _preloaded_config=config,
        )

        specs.append(TaskSpec(
            batch_key=batch_key,
            phase="generation",
            submit_body=submit_body,
            content_item_id=item.id,
            dimension=item.dimension,
            ai_model=config.model if config else settings.ai_model,
            word_id=item.word_id,
            package_id=package_id,
        ))
        item_map[item.id] = item

    if not specs:
        return 0

    # --- Step B: 入队 + 提交 + 轮询 ---
    # 用独立 session 入队，避免在外层 session 上 commit 破坏事务边界
    from vocab_qc.core.db import SyncSessionLocal
    enqueue_session = SyncSessionLocal()
    try:
        TaskQueueService.enqueue_tasks(enqueue_session, specs)
        enqueue_session.commit()
    except Exception:
        enqueue_session.rollback()
        raise
    finally:
        enqueue_session.close()

    async def _submit_and_wait() -> None:
        pool = PollingPool.get_instance()
        await pool.submit_batch(batch_key)
        # 动态超时：每任务 10s 基准，下限 10 分钟，上限 60 分钟
        timeout = min(max(600, len(specs) * 10), 3600)
        done = await pool.wait_for_batch(batch_key, timeout=timeout)
        if not done:
            logger.warning("批次 %s 轮询超时, 部分任务可能未完成", batch_key)

    from vocab_qc.core.async_bridge import run_async_in_sync
    run_async_in_sync(_submit_and_wait())

    # --- Step C: 收集结果 + 写回 ---
    completed = TaskQueueService.collect_completed(session, batch_key)
    count = 0

    for task in completed:
        item = item_map.get(task.content_item_id)
        if item is None:
            continue

        if task.status == AiTaskStatus.FAILED.value:
            item.content = ""
            item.qc_status = QcStatus.LAYER1_FAILED.value
            session.add(AiErrorLog(
                content_item_id=task.content_item_id,
                word_id=item.word_id,
                phase="generation",
                dimension=item.dimension,
                error_type=task.error_type or "unknown",
                error_message=task.error_message or "",
                ai_model=task.ai_model,
                gateway_task_no=task.gateway_task_no,
            ))
            count += 1
            continue

        # 解析结果
        result_data = task.result_data or {}
        try:
            usage = extract_usage(result_data)
            from vocab_qc.core.generators.base import parse_ai_response
            raw_content = _strip_markdown_fences(parse_ai_response(result_data))
            import json
            parsed = json.loads(raw_content)
        except Exception as e:
            logger.warning("结果解析失败 task_id=%d: %s", task.id, e)
            item.content = ""
            item.qc_status = QcStatus.LAYER1_FAILED.value
            count += 1
            continue

        if parsed.get("valid") is False:
            item.content = ""
            item.qc_status = QcStatus.REJECTED.value
            count += 1
            continue

        content = parsed.get("content", "")
        if not content:
            item.content = ""
            item.qc_status = QcStatus.LAYER1_FAILED.value
            count += 1
            continue

        item.content = content
        if parsed.get("content_cn"):
            item.content_cn = parsed["content_cn"]

        # 用量日志
        if usage and usage.total_tokens > 0:
            dim_model = task.ai_model or settings.ai_model
            session.add(AiUsageLog(
                phase="generation",
                dimension=item.dimension,
                ai_model=dim_model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                estimated_cost_usd=estimate_cost(dim_model, usage),
                word_id=item.word_id,
                content_item_id=task.content_item_id,
                package_id=package_id,
            ))

        count += 1

    session.flush()
    return count
