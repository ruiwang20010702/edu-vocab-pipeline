"""Chunk 维度 AI 校验: C3."""

from typing import Optional

from vocab_qc.core.qc.layer2.ai_base import AiRuleChecker
from vocab_qc.core.qc.registry import RuleRegistry


@RuleRegistry.register_layer2
class C3ChunkCollocation(AiRuleChecker):
    """C3: 语块是否为高频固定搭配."""

    rule_id = "C3"
    dimension = "chunk"
    description = "搭配合理性"
    system_prompt = (
        "你是英语教学质检专家。判断给定的语块是否为英语中的高频固定搭配（动+宾、形+名、动+介等），"
        "而非随意组合。返回 JSON: {\"passed\": true/false, \"detail\": \"原因\"}"
    )

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"单词: {word}\n义项: {meaning or '无'}\n语块: {content}\n\n请判断此语块是否为英语高频固定搭配。"
