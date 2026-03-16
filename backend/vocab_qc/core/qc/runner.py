"""质检运行器: 协调 Layer 1/2 规则执行."""

import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

# 确保 Layer 1 规则被加载
import vocab_qc.core.qc.layer1  # noqa: F401
from vocab_qc.core.models import ContentItem, QcRuleResult, QcRun, QcStatus
from vocab_qc.core.qc.base import ItemCheckResult
from vocab_qc.core.qc.registry import RuleRegistry


class Layer1Runner:
    """Layer 1 算法校验运行器."""

    def check_item(
        self, item: ContentItem, word_text: str,
        meaning_text: Optional[str] = None, **extra,
    ) -> ItemCheckResult:
        """对单个内容项执行所有适用的 Layer 1 规则."""
        rules = RuleRegistry.get_layer1_rules(dimension=item.dimension)
        results = []

        # 合并默认参数和额外参数，extra 中的值优先级更高
        base_kwargs = {"content_cn": item.content_cn or "", "dimension": item.dimension}
        base_kwargs.update(extra)

        for rule_id, checker in rules.items():
            result = checker.check(
                content=item.content,
                word=word_text,
                meaning=meaning_text,
                **base_kwargs,
            )
            results.append(result)

        return ItemCheckResult(
            content_item_id=item.id,
            word_id=item.word_id,
            meaning_id=item.meaning_id,
            dimension=item.dimension,
            results=results,
        )

    def run(
        self, session: Session, items: list[ContentItem],
        word_texts: dict[int, str], meaning_texts: dict[int, str],
        extra_kwargs: Optional[dict[int, dict]] = None,
    ) -> str:
        """执行 Layer 1 批量校验，结果写入数据库.

        Args:
            session: 数据库会话
            items: 待校验的内容项列表
            word_texts: {word_id: word_text} 映射
            meaning_texts: {meaning_id: definition_text} 映射
            extra_kwargs: {content_item_id: {extra_key: value}} 额外参数

        Returns:
            run_id: 本次运行 ID
        """
        run_id = str(uuid.uuid4())
        extra_kwargs = extra_kwargs or {}

        # 创建运行记录
        qc_run = QcRun(
            id=run_id,
            layer=1,
            scope="batch",
            total_items=len(items),
            passed_items=0,
            failed_items=0,
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

            check_result = self.check_item(item, word_text, meaning_text, **extra)

            # 写入规则结果
            for rule_result in check_result.results:
                qc_rule_result = QcRuleResult(
                    content_item_id=item.id,
                    word_id=item.word_id,
                    meaning_id=item.meaning_id,
                    dimension=item.dimension,
                    rule_id=rule_result.rule_id,
                    layer=1,
                    passed=rule_result.passed,
                    detail=rule_result.detail,
                    run_id=run_id,
                )
                session.add(qc_rule_result)

            # 更新内容项状态
            if check_result.all_passed:
                item.qc_status = QcStatus.LAYER1_PASSED.value
                passed_count += 1
            else:
                item.qc_status = QcStatus.LAYER1_FAILED.value
                failed_count += 1
            item.last_qc_run_id = run_id

        # 更新运行记录
        qc_run.passed_items = passed_count
        qc_run.failed_items = failed_count
        qc_run.finished_at = datetime.now(UTC)
        qc_run.status = "completed"

        session.flush()
        return run_id
