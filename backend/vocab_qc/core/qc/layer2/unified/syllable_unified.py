"""Syllable 维度合并 AI 校验."""

from typing import Any, Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient

UNIFIED_SYLLABLE_SYSTEM = """你是中小学英语语音教学质检专家。请对给定的音节切分结果执行以下所有检查项，并返回 JSON 结果。

检查项:
1. SA1: 单音节准确性 — 若单词仅含一个发音元音，则不应切分；若非单音节却未切分，也不通过
2. SA2: 元音锚点完整性 — 每个切分块必须恰好包含一个发音元音（词尾 -le 成节辅音例外）
3. SA3: 原子单位保护 — 辅音二合字母(sh/ch/th/ph/wh/ck/gh/gn/kn/ng/wr/sc/qu)、元音组合(ee/ea/ou/ai/ay/ey/ie/oa/oe/oo/ow/ue/ui)、r控元音(ar/er/ir/or/ur) 不得跨音节拆分
4. SA4: 静音字母处理 — 静音字母(词尾 silent-e、silent gh 等)不得独立成音节，须附着到前一个元音的音节
5. SA5: 辅音切分位置 — VCV 模式单辅音归后(pa·per)；VCCV 模式双辅音从中切(sud·den)；双写辅音须切开标记闭音节(ap·ple)
6. SA6: 前缀完整性 — 常见前缀(re-/un-/dis-/pre-/mis-/over- 等)在语音允许时保持完整
7. SA7: 分隔符格式 — 必须使用且仅使用中圆点 · (U+00B7)，不允许其他分隔符

返回 JSON 格式:
{
    "results": [
        {"rule_id": "SA1", "passed": true/false, "detail": "原因"},
        {"rule_id": "SA2", "passed": true/false, "detail": "原因"},
        ...
    ]
}"""


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

        try:
            response = await client.check(UNIFIED_SYLLABLE_SYSTEM, user_prompt)
            results = []
            for item in response.get("results", []):
                results.append(
                    RuleResult(
                        rule_id=item["rule_id"],
                        passed=item.get("passed", False),
                        detail=item.get("detail"),
                    )
                )
            return results
        except Exception as e:
            return [RuleResult(rule_id=rid, passed=False, detail=f"AI 调用失败: {e}") for rid in self.rule_ids]
