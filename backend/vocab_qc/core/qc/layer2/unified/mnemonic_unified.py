"""Mnemonic 维度合并 AI 校验."""

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

# 精简 prompt 作为 fallback（完整 prompt 加载失败时使用）
UNIFIED_MNEMONIC_SYSTEM = """你是中小学英语教学专家。请对给定的助记内容执行以下检查:
1. N5_AI: 老师话术是否包含完整步骤框架
2. N6: 助记逻辑是否合理，是否为伪助记

返回 JSON: {"results": [{"rule_id": "N5_AI", "passed": ..., "detail": ...},
{"rule_id": "N6", "passed": ..., "detail": ...}]}"""


class UnifiedMnemonicChecker:
    dimension = "mnemonic"
    rule_ids = ["N5_AI", "N6"]

    async def check(
        self, client: AiClient, content: str, word: str,
        meaning: Optional[str] = None, **kwargs,
    ) -> list[RuleResult]:
        pos = kwargs.get("pos", "")
        item_dimension = kwargs.get("item_dimension", "")
        user_prompt = f"单词: {word}\n词性: {pos or '未知'}\n义项: {meaning or '无'}\n助记内容:\n{content}"

        # 所有助记维度优先使用完整 prompt + 纯文本输出
        if item_dimension and item_dimension.startswith("mnemonic_"):
            return await self._check_with_full_prompt(client, user_prompt, item_dimension)

        # 未传 item_dimension 时回退精简 prompt
        return await self._check_with_simple_prompt(client, user_prompt)

    async def _check_with_full_prompt(
        self, client: AiClient, user_prompt: str, dimension: str,
    ) -> list[RuleResult]:
        """使用完整 prompt + 文本输出格式。"""
        full_prompt = load_full_prompt(dimension)
        if not full_prompt:
            logger.warning("无法加载 %s 完整 prompt，回退到精简模式", dimension)
            return await self._check_with_simple_prompt(client, user_prompt)

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
            response = await client.check(UNIFIED_MNEMONIC_SYSTEM, user_prompt)
            return [
                RuleResult(rule_id=item["rule_id"], passed=item.get("passed", False), detail=item.get("detail"))
                for item in response.get("results", [])
            ]
        except Exception as e:
            return [RuleResult(rule_id=rid, passed=False, detail=f"AI 调用失败: {e}") for rid in self.rule_ids]
