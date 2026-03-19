"""Chunk 维度合并 AI 校验."""

import logging
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient
from vocab_qc.core.qc.layer2.unified.full_prompt import (
    TEXT_OUTPUT_INSTRUCTION,
    load_full_prompt,
    parse_text_result,
)

logger = logging.getLogger(__name__)

# 精简 prompt 作为 fallback
UNIFIED_CHUNK_SYSTEM = """你是英语教学质检专家。请判断给定的语块是否为高频固定搭配。
返回 JSON: {"results": [{"rule_id": "C3", "passed": true/false, "detail": "原因"}]}"""


class UnifiedChunkChecker:
    dimension = "chunk"
    rule_ids = ["C3"]

    async def check(
        self, client: AiClient, content: str, word: str,
        meaning: Optional[str] = None, **kwargs,
    ) -> list[RuleResult]:
        user_prompt = f"单词: {word}\n义项: {meaning or '无'}\n语块: {content}"

        # 优先使用完整 prompt + 纯文本输出
        full_prompt = load_full_prompt("chunk")
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
            return [RuleResult(rule_id="C3", passed=False, detail=f"AI 调用失败: {e}")]

    async def _check_with_simple_prompt(
        self, client: AiClient, user_prompt: str,
    ) -> list[RuleResult]:
        """使用精简 prompt + JSON 格式（fallback）。"""
        try:
            response = await client.check(UNIFIED_CHUNK_SYSTEM, user_prompt)
            return [
                RuleResult(rule_id=item["rule_id"], passed=item.get("passed", False), detail=item.get("detail"))
                for item in response.get("results", [])
            ]
        except Exception as e:
            return [RuleResult(rule_id="C3", passed=False, detail=f"AI 调用失败: {e}")]
