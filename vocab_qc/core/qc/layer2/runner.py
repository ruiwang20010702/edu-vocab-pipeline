"""Layer 2 异步运行器."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from vocab_qc.core.models import ContentItem, QcRuleResult, QcRun, QcStatus
from vocab_qc.core.models.enums import AiStrategy
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient, AiRuleChecker
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
from vocab_qc.core.qc.registry import RuleRegistry

# 确保 Layer 2 规则被加载
import vocab_qc.core.qc.layer2.per_rule  # noqa: F401


class Layer2Runner:
    """Layer 2 AI 语义校验运行器."""

    def __init__(self, client: Optional[AiClient] = None):
        self.client = client or AiClient()
        _mnemonic_checker = UnifiedMnemonicChecker()
        self._unified_checkers = {
            "sentence": UnifiedSentenceChecker(),
            "chunk": UnifiedChunkChecker(),
            "mnemonic_root_affix": _mnemonic_checker,
            "mnemonic_word_in_word": _mnemonic_checker,
            "mnemonic_sound_meaning": _mnemonic_checker,
            "mnemonic_exam_app": _mnemonic_checker,
        }

    async def check_item_per_rule(
        self,
        item: ContentItem,
        word_text: str,
        meaning_text: Optional[str] = None,
        **extra,
    ) -> list[RuleResult]:
        """Per-rule 策略：每条规则独立调用 AI."""
        rules = RuleRegistry.get_layer2_rules(dimension=item.dimension)
        tasks = []
        for rule_id, checker in rules.items():
            if isinstance(checker, AiRuleChecker):
                tasks.append(checker.check(self.client, item.content, word_text, meaning_text, **extra))

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
        checker = self._unified_checkers.get(item.dimension)
        if checker is None:
            return []
        return await checker.check(self.client, item.content, word_text, meaning_text, **extra)

    async def run_async(
        self,
        session: Session,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        strategy: AiStrategy = AiStrategy.PER_RULE,
        extra_kwargs: Optional[dict[int, dict]] = None,
    ) -> str:
        """异步执行 Layer 2 批量校验."""
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

        passed_count = 0
        failed_count = 0

        for item in items:
            word_text = word_texts.get(item.word_id, "")
            meaning_text = meaning_texts.get(item.meaning_id, "") if item.meaning_id else None
            extra = extra_kwargs.get(item.id, {})

            if strategy == AiStrategy.PER_RULE:
                results = await self.check_item_per_rule(item, word_text, meaning_text, **extra)
            else:
                results = await self.check_item_unified(item, word_text, meaning_text, **extra)

            all_passed = all(r.passed for r in results) if results else True

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
                    ai_model=self.client.model,
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

        qc_run.passed_items = passed_count
        qc_run.failed_items = failed_count
        qc_run.finished_at = datetime.now(UTC)
        qc_run.status = "completed"

        session.flush()
        return run_id

    def run(
        self,
        session: Session,
        items: list[ContentItem],
        word_texts: dict[int, str],
        meaning_texts: dict[int, str],
        strategy: AiStrategy = AiStrategy.PER_RULE,
        extra_kwargs: Optional[dict[int, dict]] = None,
    ) -> str:
        """同步桥接：自动检测是否在事件循环内，选择合适的调用方式."""
        coro = self.run_async(session, items, word_texts, meaning_texts, strategy, extra_kwargs)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（CLI 场景），直接 asyncio.run
            return asyncio.run(coro)
        else:
            # 已在事件循环内（FastAPI 场景），使用线程池执行
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
