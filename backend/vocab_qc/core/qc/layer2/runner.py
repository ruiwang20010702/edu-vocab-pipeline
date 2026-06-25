"""Layer 2 异步运行器."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

# 确保 Layer 2 规则被加载
import vocab_qc.core.qc.layer2.per_rule  # noqa: F401
from vocab_qc.core.models import ContentItem, QcRuleResult, QcRun, QcStatus
from vocab_qc.core.models.enums import AiStrategy
from vocab_qc.core.models.quality_layer import AiErrorLog, AiUsageLog, classify_ai_error
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient, AiRuleChecker
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
from vocab_qc.core.qc.layer2.unified.syllable_unified import UnifiedSyllableChecker
from vocab_qc.core.qc.registry import RuleRegistry

logger = logging.getLogger(__name__)


class Layer2Runner:
    """Layer 2 AI 语义校验运行器."""

    def __init__(self, client: Optional[AiClient] = None):
        self.client = client or AiClient()
        self._dimension_clients: dict[str, AiClient] = {}
        _mnemonic_checker = UnifiedMnemonicChecker()
        self._unified_checkers = {
            "syllable": UnifiedSyllableChecker(),
            "sentence": UnifiedSentenceChecker(),
            "chunk": UnifiedChunkChecker(),
            "mnemonic_root_affix": _mnemonic_checker,
            "mnemonic_word_in_word": _mnemonic_checker,
            "mnemonic_sound_meaning": _mnemonic_checker,
            "mnemonic_exam_app": _mnemonic_checker,
        }

    def _get_client_for_dimension(self, dimension: str) -> AiClient:
        """获取维度对应的 AiClient（有缓存）。"""
        if dimension in self._dimension_clients:
            return self._dimension_clients[dimension]
        return self.client

    def load_dimension_configs(self, session) -> None:
        """从 DB 加载质检维度的 AI 配置，为不同维度创建独立 AiClient。"""
        from vocab_qc.core.config import settings as _settings
        from vocab_qc.core.services.prompt_service import get_active_prompt

        for dim in self._unified_checkers:
            prompt = get_active_prompt(session, "quality", dim)
            if prompt and (prompt.ai_api_base_url or prompt.model):
                self._dimension_clients[dim] = AiClient(
                    api_key=_settings.ai_api_key,
                    base_url=prompt.ai_api_base_url,
                    model=prompt.model,
                )

    def _flush_usage_logs(self, session: Session, *, package_id: int | None = None) -> None:
        """从所有 client drain usage 记录，聚合后写入 AiUsageLog。"""
        from vocab_qc.core.generators.base import AiUsageInfo, estimate_cost

        all_clients = {self.client} | set(self._dimension_clients.values())
        for client in all_clients:
            records = client.drain_usage_records()
            if not records:
                continue
            agg = AiUsageInfo(
                prompt_tokens=sum(r.prompt_tokens for r in records),
                completion_tokens=sum(r.completion_tokens for r in records),
                total_tokens=sum(r.total_tokens for r in records),
            )
            session.add(AiUsageLog(
                phase="qc_layer2",
                dimension=None,
                ai_model=client.model,
                prompt_tokens=agg.prompt_tokens,
                completion_tokens=agg.completion_tokens,
                total_tokens=agg.total_tokens,
                estimated_cost_usd=estimate_cost(client.model, agg),
                package_id=package_id,
            ))

    async def check_item_per_rule(
        self,
        item: ContentItem,
        word_text: str,
        meaning_text: Optional[str] = None,
        **extra,
    ) -> list[RuleResult]:
        """Per-rule 策略：每条规则独立调用 AI."""
        client = self._get_client_for_dimension(item.dimension)
        rules = RuleRegistry.get_layer2_rules(dimension=item.dimension)
        tasks = []
        for rule_id, checker in rules.items():
            if isinstance(checker, AiRuleChecker):
                tasks.append(checker.check(client, item.content, word_text, meaning_text, **extra))

        if not tasks:
            return []

        return list(await asyncio.gather(*tasks))

    async def check_item_unified(
        self,
        item: ContentItem,
        word_text: str,
        meaning_text: Optional[str] = None,
        **extra,
    ) -> list[RuleResult]:
        """Unified 策略：按维度合并调用 AI."""
        client = self._get_client_for_dimension(item.dimension)
        checker = self._unified_checkers.get(item.dimension)
        if checker is None:
            return []
        return await checker.check(
            client, item.content, word_text, meaning_text,
            item_dimension=item.dimension, **extra,
        )

    async def _collect_ai_results(
        self,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        strategy: AiStrategy,
        extra_kwargs: dict[int, dict],
    ) -> tuple[dict[int, list[RuleResult]], list[AiErrorLog]]:
        """纯 AI 调用，不涉及 session 操作。并发执行所有 item 检查。"""

        from vocab_qc.core.config import settings as _settings
        stagger = _settings.ai_request_stagger

        async def _check_one(item: ContentItem, index: int = 0) -> tuple[int, list[RuleResult]]:
            if stagger > 0 and index > 0:
                await asyncio.sleep((index % _settings.ai_max_concurrency) * stagger)
            word_text = word_texts.get(item.word_id, "")
            meaning_text = meaning_texts.get(item.meaning_id, "") if item.meaning_id else None
            extra = extra_kwargs.get(item.id, {})

            if strategy == AiStrategy.PER_RULE:
                results = await self.check_item_per_rule(item, word_text, meaning_text, **extra)
            else:
                results = await self.check_item_unified(item, word_text, meaning_text, **extra)
            return item.id, results

        # 分批 gather，避免一次创建过多 asyncio Task（大批量时数万个）
        # 超时保护：与生成阶段一致，防止 L2 无限等待
        _L2_GATHER_TIMEOUT = 1200  # 20 分钟
        gather_batch_size = _settings.production_batch_size * 8  # ~400 items/batch
        all_gathered: list = []
        global_index = 0
        for batch_start in range(0, len(items), gather_batch_size):
            batch_items = items[batch_start:batch_start + gather_batch_size]
            batch_tasks = [_check_one(item, global_index + i) for i, item in enumerate(batch_items)]
            global_index += len(batch_items)
            try:
                batch_results = await asyncio.wait_for(
                    asyncio.gather(*batch_tasks, return_exceptions=True),
                    timeout=_L2_GATHER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "L2 质检 gather 超时 (%ds)，batch %d-%d/%d 被跳过",
                    _L2_GATHER_TIMEOUT, batch_start,
                    min(batch_start + gather_batch_size, len(items)), len(items),
                )
                # 超时的任务标记为异常，后续统一处理为 LAYER2_FAILED
                batch_results = [
                    TimeoutError(f"L2 gather timeout after {_L2_GATHER_TIMEOUT}s")
                ] * len(batch_tasks)
            all_gathered.extend(batch_results)

        results_map: dict[int, list[RuleResult]] = {}
        error_logs: list[AiErrorLog] = []
        for i, r in enumerate(all_gathered):
            if isinstance(r, Exception):
                logger.warning("AI 质检任务异常: %s", r, exc_info=True)
                failed_item = items[i]
                dim_client = self._get_client_for_dimension(failed_item.dimension)
                # 从 AiRequestError 或其 __cause__ 提取结构化信息
                cause = r.__cause__ if r.__cause__ else r
                status_code = getattr(cause, "status_code", None)
                resp_body = getattr(cause, "response_body", None) or ""
                elapsed = getattr(cause, "elapsed_ms", None)
                task_no = getattr(cause, "task_no", None) or ""
                error_logs.append(AiErrorLog(
                    content_item_id=failed_item.id,
                    word_id=failed_item.word_id,
                    phase="qc_layer2",
                    dimension=failed_item.dimension,
                    error_type=classify_ai_error(cause),
                    error_message=str(r)[:2000],
                    http_status_code=status_code,
                    response_body=resp_body[:500] if resp_body else None,
                    elapsed_ms=elapsed,
                    ai_model=dim_client.model,
                    gateway_task_no=task_no or None,
                ))
                continue
            item_id, item_results = r
            results_map[item_id] = item_results
        return results_map, error_logs

    def _collect_ai_results_queued(
        self,
        session: Session,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        extra_kwargs: dict[int, dict],
        package_id: int | None = None,
    ) -> tuple[dict[int, list[RuleResult]], list[AiErrorLog]]:
        """任务队列模式：enqueue → submit → poll → collect → parse."""
        import json as _json

        from vocab_qc.core.async_bridge import run_async_in_sync
        from vocab_qc.core.generators.base import (
            _strip_markdown_fences,
            extract_usage,
            parse_ai_response,
        )
        from vocab_qc.core.models.ai_task_queue import AiTaskStatus
        from vocab_qc.core.polling_pool import PollingPool
        from vocab_qc.core.task_queue import TaskQueueService, TaskSpec

        batch_key = f"l2:{uuid.uuid4().hex[:8]}"

        # Step 1: 为每个 item 构造 submit_body
        specs: list[TaskSpec] = []
        item_meta: dict[int, dict] = {}  # item_id → {checker, use_json_format}

        for item in items:
            checker = self._unified_checkers.get(item.dimension)
            if checker is None:
                continue
            if not hasattr(checker, "build_prompts"):
                continue

            word_text = word_texts.get(item.word_id, "")
            meaning_text = meaning_texts.get(item.meaning_id, "") if item.meaning_id else None
            extra = extra_kwargs.get(item.id, {})

            system_prompt, user_prompt, use_json_format = checker.build_prompts(
                item.content, word_text, meaning_text,
                item_dimension=item.dimension, **extra,
            )

            client = self._get_client_for_dimension(item.dimension)
            submit_body = client.make_submit_body(
                system_prompt, user_prompt, use_json_format=use_json_format,
            )

            specs.append(TaskSpec(
                batch_key=batch_key,
                phase="qc_layer2",
                submit_body=submit_body,
                content_item_id=item.id,
                dimension=item.dimension,
                ai_model=client.model,
                word_id=item.word_id,
                package_id=package_id,
            ))
            item_meta[item.id] = {
                "checker": checker,
                "use_json_format": use_json_format,
            }

        if not specs:
            return {}, []

        # Step 2: 入队（独立 session，不破坏外层事务） + 提交 + 轮询
        from vocab_qc.core.db import SyncSessionLocal as _SyncSessionLocal
        enqueue_session = _SyncSessionLocal()
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
            timeout = min(max(600, len(specs) * 10), 3600)
            done = await pool.wait_for_batch(batch_key, timeout=timeout)
            if not done:
                logger.warning("L2 批次 %s 轮询超时", batch_key)

        run_async_in_sync(_submit_and_wait())

        # 将超时仍活跃的任务标记为 FAILED（防止 collect_completed 遗漏）
        from vocab_qc.core.models.ai_task_queue import AiTaskQueue
        timeout_session = _SyncSessionLocal()
        try:
            timed_out = (
                timeout_session.query(AiTaskQueue)
                .filter_by(batch_key=batch_key)
                .filter(AiTaskQueue.status.in_([
                    AiTaskStatus.PENDING.value,
                    AiTaskStatus.SUBMITTED.value,
                    AiTaskStatus.POLLING.value,
                ]))
                .all()
            )
            for t in timed_out:
                t.status = AiTaskStatus.FAILED.value
                t.error_message = "L2 质检轮询超时"
            if timed_out:
                timeout_session.commit()
                logger.warning(
                    "L2 标记超时任务 batch=%s count=%d",
                    batch_key, len(timed_out),
                )
        except Exception:
            timeout_session.rollback()
        finally:
            timeout_session.close()

        # Step 3: 收集 + 解析
        completed = TaskQueueService.collect_completed(session, batch_key)
        results_map: dict[int, list[RuleResult]] = {}
        error_logs: list[AiErrorLog] = []

        for task in completed:
            cid = task.content_item_id
            if cid is None:
                continue
            meta = item_meta.get(cid)
            if meta is None:
                continue

            checker = meta["checker"]
            use_json = meta["use_json_format"]

            if task.status == AiTaskStatus.FAILED.value:
                error_logs.append(AiErrorLog(
                    content_item_id=cid,
                    word_id=task.word_id,
                    phase="qc_layer2",
                    dimension=task.dimension,
                    error_type=task.error_type or "unknown",
                    error_message=task.error_message or "",
                    ai_model=task.ai_model,
                    gateway_task_no=task.gateway_task_no,
                ))
                continue

            # 解析 Gateway 原始响应
            raw_data = task.result_data or {}
            try:
                # 提取 usage 信息（Token 用量）
                usage = extract_usage(raw_data)
                if usage and usage.total_tokens > 0:
                    from vocab_qc.core.generators.base import estimate_cost
                    session.add(AiUsageLog(
                        phase="qc_layer2",
                        dimension=task.dimension,
                        ai_model=task.ai_model or self.client.model,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        estimated_cost_usd=estimate_cost(task.ai_model or self.client.model, usage),
                        word_id=task.word_id,
                        content_item_id=cid,
                        package_id=package_id,
                    ))

                content_str = _strip_markdown_fences(parse_ai_response(raw_data))
                if use_json:
                    parsed = _json.loads(content_str)
                else:
                    parsed = {"raw_text": content_str}
                results_map[cid] = checker.parse_ai_response(parsed, use_json)
            except Exception as e:
                logger.warning("L2 结果解析失败 task_id=%d: %s", task.id, e)
                error_logs.append(AiErrorLog(
                    content_item_id=cid,
                    word_id=task.word_id,
                    phase="qc_layer2",
                    dimension=task.dimension,
                    error_type="parse_error",
                    error_message=str(e)[:2000],
                    ai_model=task.ai_model,
                ))

        return results_map, error_logs

    def _save_results(
        self,
        session: Session,
        items: list[ContentItem],
        results_map: dict[int, list[RuleResult]],
        strategy: AiStrategy,
        run_id: str,
        failed_item_ids: frozenset[int] = frozenset(),
        error_messages: dict[int, str] | None = None,
    ) -> tuple[int, int]:
        """将 AI 结果写入数据库（主线程，session 安全）。"""
        passed_count = 0
        failed_count = 0

        for item in items:
            results = results_map.get(item.id, [])
            if not results:
                if item.id in failed_item_ids:
                    # AI 调用失败：标记为 LAYER2_FAILED，进入审核队列
                    item.qc_status = QcStatus.LAYER2_FAILED.value
                    item.last_qc_run_id = run_id
                    failed_count += 1
                    # 补写错误原因，让前端能显示
                    err_msg = (error_messages or {}).get(item.id, "L2 AI 质检调用失败")
                    dim_client = self._get_client_for_dimension(item.dimension)
                    session.add(QcRuleResult(
                        content_item_id=item.id,
                        word_id=item.word_id,
                        meaning_id=item.meaning_id,
                        dimension=item.dimension,
                        rule_id="L2_ERR",
                        layer=2,
                        passed=False,
                        detail=err_msg,
                        ai_model=dim_client.model,
                        ai_strategy=strategy.value,
                        run_id=run_id,
                    ))
                else:
                    # 兜底：无结果也不在失败集 → 标记为 LAYER2_FAILED
                    item.qc_status = QcStatus.LAYER2_FAILED.value
                    item.last_qc_run_id = run_id
                    failed_count += 1
                    dim_client = self._get_client_for_dimension(item.dimension)
                    session.add(QcRuleResult(
                        content_item_id=item.id,
                        word_id=item.word_id,
                        meaning_id=item.meaning_id,
                        dimension=item.dimension,
                        rule_id="L2_UNTRACKED",
                        layer=2,
                        passed=False,
                        detail="L2 质检未返回结果（可能因超时或任务丢失）",
                        ai_model=dim_client.model,
                        ai_strategy=strategy.value,
                        run_id=run_id,
                    ))
                    logger.warning(
                        "L2 未跟踪 item=%d dim=%s → LAYER2_FAILED",
                        item.id, item.dimension,
                    )
                continue
            all_passed = all(r.passed for r in results)

            dim_client = self._get_client_for_dimension(item.dimension)
            for result in results:
                qc_rule_result = QcRuleResult(
                    content_item_id=item.id,
                    word_id=item.word_id,
                    meaning_id=item.meaning_id,
                    dimension=item.dimension,
                    rule_id=result.rule_id,
                    layer=2,
                    passed=result.passed,
                    detail=result.detail,
                    ai_model=dim_client.model,
                    ai_strategy=strategy.value,
                    run_id=run_id,
                )
                session.add(qc_rule_result)

            if all_passed:
                item.qc_status = QcStatus.LAYER2_PASSED.value
                passed_count += 1
            else:
                item.qc_status = QcStatus.LAYER2_FAILED.value
                failed_count += 1
            item.last_qc_run_id = run_id

        return passed_count, failed_count

    async def run_async(
        self,
        session: Session,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        strategy: AiStrategy = AiStrategy.UNIFIED,
        extra_kwargs: Optional[dict[int, dict]] = None,
        package_id: int | None = None,
    ) -> str:
        """异步执行 Layer 2 批量校验."""
        logger.info("Layer2Runner.run_async 开始 items=%d strategy=%s", len(items), strategy.value)
        self.load_dimension_configs(session)
        run_id = str(uuid.uuid4())
        extra_kwargs = extra_kwargs or {}

        qc_run = QcRun(
            id=run_id,
            layer=2,
            scope="batch",
            ai_strategy=strategy.value,
            ai_model=self.client.model,
            total_items=len(items),
            status="running",
        )
        session.add(qc_run)
        session.flush()

        # AI 调用（不涉及 session）
        results_map, error_logs = await self._collect_ai_results(
            items, word_texts, meaning_texts, strategy, extra_kwargs,
        )

        # DB 写入（session 安全）
        failed_ids = frozenset(
            log.content_item_id for log in error_logs if log.content_item_id
        )
        err_msgs = {
            log.content_item_id: log.error_message
            for log in error_logs
            if log.content_item_id and log.error_message
        }
        passed_count, failed_count = self._save_results(
            session, items, results_map, strategy, run_id,
            failed_item_ids=failed_ids, error_messages=err_msgs,
        )

        for log in error_logs:
            session.add(log)

        # 收集所有 client 的 usage 记录并写入
        self._flush_usage_logs(session, package_id=package_id)

        qc_run.passed_items = passed_count
        qc_run.failed_items = failed_count
        qc_run.finished_at = datetime.now(UTC)
        qc_run.status = "completed"

        session.flush()

        logger.info(
            "Layer2Runner.run_async 完成 run_id=%s passed=%d failed=%d errors=%d",
            run_id, passed_count, failed_count, len(error_logs),
        )

        return run_id

    def run(
        self,
        session: Session,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        strategy: AiStrategy = AiStrategy.UNIFIED,
        extra_kwargs: Optional[dict[int, dict]] = None,
        package_id: int | None = None,
    ) -> str:
        """同步桥接：AI 调用在独立线程/事件循环，DB 操作在主线程."""
        from vocab_qc.core.config import settings as _settings

        logger.info("Layer2Runner.run 开始 items=%d strategy=%s", len(items), strategy.value)
        self.load_dimension_configs(session)
        run_id = str(uuid.uuid4())
        extra_kwargs = extra_kwargs or {}

        qc_run = QcRun(
            id=run_id,
            layer=2,
            scope="batch",
            ai_strategy=strategy.value,
            ai_model=self.client.model,
            total_items=len(items),
            status="running",
        )
        session.add(qc_run)
        session.flush()

        # 任务队列模式 vs 原模式
        if _settings.ai_use_task_queue and strategy != AiStrategy.UNIFIED:
            logger.warning(
                "ai_use_task_queue=True 仅支持 UNIFIED 策略，当前 strategy=%s，回退到直连模式",
                strategy.value,
            )
        if _settings.ai_use_task_queue and strategy == AiStrategy.UNIFIED:
            results_map, error_logs = self._collect_ai_results_queued(
                session, items, word_texts, meaning_texts, extra_kwargs, package_id,
            )
        else:
            coro = self._collect_ai_results(items, word_texts, meaning_texts, strategy, extra_kwargs)
            from vocab_qc.core.async_bridge import run_async_in_sync
            results_map, error_logs = run_async_in_sync(coro)

        # Step 2: DB 写入（主线程，session 安全）
        failed_ids = frozenset(
            log.content_item_id for log in error_logs if log.content_item_id
        )
        err_msgs = {
            log.content_item_id: log.error_message
            for log in error_logs
            if log.content_item_id and log.error_message
        }
        passed_count, failed_count = self._save_results(
            session, items, results_map, strategy, run_id,
            failed_item_ids=failed_ids, error_messages=err_msgs,
        )

        for log in error_logs:
            session.add(log)

        # 收集所有 client 的 usage 记录并写入
        self._flush_usage_logs(session, package_id=package_id)

        qc_run.passed_items = passed_count
        qc_run.failed_items = failed_count
        qc_run.finished_at = datetime.now(UTC)
        qc_run.status = "completed"

        session.flush()

        logger.info(
            "Layer2Runner.run 完成 run_id=%s passed=%d failed=%d errors=%d",
            run_id, passed_count, failed_count, len(error_logs),
        )

        return run_id
