"""Syllable 维度合并 AI 校验."""

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
UNIFIED_SYLLABLE_SYSTEM = (
    "你是中小学英语语音教学质检专家。"
    "请对给定的音节切分结果执行以下所有检查项，并返回 JSON 结果。\n\n"
    "检查项:\n"
    "1. SA1: 单音节准确性 — 若单词仅含一个发音元音，则不应切分；"
    "若非单音节却未切分，也不通过\n"
    "2. SA2: 元音锚点完整性 — 每个切分块必须恰好包含一个发音元音"
    "（词尾 -le 成节辅音例外）\n"
    "3. SA3: 原子单位保护 — "
    "辅音二合字母(sh/ch/th/ph/wh/ck/gh/gn/kn/ng/wr/sc/qu)、"
    "元音组合(ee/ea/ou/ai/ay/ey/ie/oa/oe/oo/ow/ue/ui)、"
    "r控元音(ar/er/ir/or/ur) 不得跨音节拆分\n"
    "4. SA4: 静音字母处理 — 静音字母(词尾 silent-e、silent gh 等)"
    "不得独立成音节，须附着到前一个元音的音节\n"
    "5. SA5: 辅音切分位置 — VCV 模式单辅音归后(pa·per)；"
    "VCCV 模式双辅音从中切(sud·den)；双写辅音须切开标记闭音节(ap·ple)\n"
    "6. SA6: 前缀完整性 — 常见前缀(re-/un-/dis-/pre-/mis-/over- 等)"
    "在语音允许时保持完整\n"
    "7. SA7: 分隔符格式 — 必须使用且仅使用中圆点 · (U+00B7)，"
    "不允许其他分隔符\n\n"
    '返回 JSON 格式:\n'
    '{\n'
    '    "results": [\n'
    '        {"rule_id": "SA1", "passed": true/false, "detail": "原因"},\n'
    '        {"rule_id": "SA2", "passed": true/false, "detail": "原因"},\n'
    '        ...\n'
    '    ]\n'
    '}'
)


class UnifiedSyllableChecker:
    """合并检查器：一次调用检查所有音节切分规则."""

    dimension = "syllable"
    rule_ids = ["SA1", "SA2", "SA3", "SA4", "SA5", "SA6", "SA7"]

    async def check(
        self,
        client: AiClient,
        content: str,
        word: str,
        meaning: Optional[str] = None,
        **kwargs: Any,
    ) -> list[RuleResult]:
        user_prompt = f"单词: {word}\n音节切分: {content}\n\n请对以上音节切分执行所有检查项。"

        # 优先使用完整 prompt + 纯文本输出
        full_prompt = load_full_prompt("syllable")
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
            response = await client.check(UNIFIED_SYLLABLE_SYSTEM, user_prompt)
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
