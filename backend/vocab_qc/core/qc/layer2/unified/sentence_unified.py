"""Sentence 维度合并 AI 校验."""

import logging
from typing import Any, Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient
from vocab_qc.core.qc.layer2.unified.full_prompt import (
    TEXT_OUTPUT_INSTRUCTION,
    load_full_prompt,
    parse_text_result,
)

logger = logging.getLogger(__name__)

# 精简 prompt 作为 fallback
UNIFIED_SENTENCE_SYSTEM = """你是中小学英语教学质检专家。请对给定的例句执行以下所有检查项，并返回 JSON 结果。

检查项:
1. E1: 语法是否在初中教学大纲范围内
2. E2: 是否以简单陈述句结构（主谓宾/主系表）为主
3. E3: 连接词是否仅使用 and/but/so/because
4. E4: 如有定语从句，是否仅由 that/which/who 引导且 ≤ 5 词
5. E5: 是否包含禁区结构（非谓语作状语/虚拟语气/倒装/独立主格）
6. E8: 中文翻译是否与英文语义对应
7. E9: 例句中目标词用法是否对应标注义项
8. E10: 是否自然地道，无中式英语
9. E11: 内容是否阳光中性

返回 JSON 格式:
{
    "results": [
        {"rule_id": "E1", "passed": true/false, "detail": "原因"},
        {"rule_id": "E2", "passed": true/false, "detail": "原因"},
        ...
    ]
}"""


class UnifiedSentenceChecker:
    """合并检查器：一次调用检查所有例句规则."""

    dimension = "sentence"
    rule_ids = ["E1", "E2", "E3", "E4", "E5", "E8_AI", "E9", "E10", "E11"]

    async def check(
        self,
        client: AiClient,
        content: str,
        word: str,
        meaning: Optional[str] = None,
        content_cn: str = "",
        **kwargs: Any,
    ) -> list[RuleResult]:
        pos = kwargs.get("pos", "")
        user_prompt = (
            f"单词: {word}\n词性: {pos or '未知'}\n义项: {meaning or '无'}\n"
            f"英文例句: {content}\n中文翻译: {content_cn}\n\n"
            "请对以上例句执行所有检查项。"
        )

        # 优先使用完整 prompt + 纯文本输出
        full_prompt = load_full_prompt("sentence")
        if full_prompt:
            return await self._check_with_full_prompt(client, user_prompt, full_prompt)

        # 回退精简 prompt + JSON
        return await self._check_with_simple_prompt(client, user_prompt)

    async def _check_with_full_prompt(
        self, client: AiClient, user_prompt: str, full_prompt: str,
    ) -> list[RuleResult]:
        """使用完整 prompt + 文本输出格式。"""
        system_prompt = full_prompt + TEXT_OUTPUT_INSTRUCTION
        try:
            response = await client.check(system_prompt, user_prompt, use_json_format=False)
            raw_text = response.get("raw_text", "")
            return parse_text_result(raw_text, self.rule_ids)
        except Exception as e:
            return [RuleResult(rule_id=rid, passed=False, detail=f"AI 调用失败: {e}") for rid in self.rule_ids]

    async def _check_with_simple_prompt(
        self, client: AiClient, user_prompt: str,
    ) -> list[RuleResult]:
        """使用精简 prompt + JSON 格式（fallback）。"""
        try:
            response = await client.check(UNIFIED_SENTENCE_SYSTEM, user_prompt)
            return [
                RuleResult(
                    rule_id=item["rule_id"],
                    passed=item.get("passed", False),
                    detail=item.get("detail"),
                )
                for item in response.get("results", [])
            ]
        except Exception as e:
            return [RuleResult(rule_id=rid, passed=False, detail=f"AI 调用失败: {e}") for rid in self.rule_ids]
