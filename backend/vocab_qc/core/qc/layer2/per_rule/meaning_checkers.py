"""Meaning 维度 AI 校验: M7."""

from typing import Optional

from vocab_qc.core.qc.layer2.ai_base import AiRuleChecker
from vocab_qc.core.qc.registry import RuleRegistry


@RuleRegistry.register_layer2
class M7PosDefinitionMatch(AiRuleChecker):
    """M7: 词义与词性是否严格匹配."""

    rule_id = "M7"
    dimension = "meaning"
    description = "词义-词性匹配"
    system_prompt = (
        "你是英语教学质检专家。判断给定的词义是否与标注的词性严格匹配。"
        "返回 JSON: {\"passed\": true/false, \"detail\": \"原因\"}"
    )

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        pos = kwargs.get("pos", "")
        return f"单词: {word}\n词性: {pos}\n释义: {meaning or content}\n\n请判断释义是否与标注的词性匹配。"
