"""Sentence 维度合并 AI 校验."""

from typing import Any, Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient

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

        try:
            response = await client.check(UNIFIED_SENTENCE_SYSTEM, user_prompt)
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
