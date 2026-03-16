"""Chunk 维度合并 AI 校验."""

from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient

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
        try:
            response = await client.check(UNIFIED_CHUNK_SYSTEM, user_prompt)
            return [
                RuleResult(rule_id=item["rule_id"], passed=item.get("passed", False), detail=item.get("detail"))
                for item in response.get("results", [])
            ]
        except Exception as e:
            return [RuleResult(rule_id="C3", passed=False, detail=f"AI 调用失败: {e}")]
