"""Mnemonic 维度合并 AI 校验."""

from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient

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
        user_prompt = f"单词: {word}\n词性: {pos or '未知'}\n义项: {meaning or '无'}\n助记内容:\n{content}"
        try:
            response = await client.check(UNIFIED_MNEMONIC_SYSTEM, user_prompt)
            return [
                RuleResult(rule_id=item["rule_id"], passed=item.get("passed", False), detail=item.get("detail"))
                for item in response.get("results", [])
            ]
        except Exception as e:
            return [RuleResult(rule_id=rid, passed=False, detail=f"AI 调用失败: {e}") for rid in self.rule_ids]
