"""Mnemonic 维度 AI 校验: N5(完整性), N6."""

from typing import Optional

from vocab_qc.core.qc.layer2.ai_base import AiRuleChecker
from vocab_qc.core.qc.registry import RuleRegistry


@RuleRegistry.register_layer2
class N5ScriptCompleteness(AiRuleChecker):
    """N5: 老师话术完整性（AI 部分）."""

    rule_id = "N5_AI"
    dimension = "mnemonic"
    description = "话术完整性"
    system_prompt = (
        "你是中小学英语教学专家。判断给定的老师话术是否包含完整的步骤框架，逻辑是否通顺。"
        "返回 JSON: {\"passed\": true/false, \"detail\": \"原因\"}"
    )

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"单词: {word}\n助记内容:\n{content}\n\n请判断老师话术部分是否包含完整步骤框架。"


@RuleRegistry.register_layer2
class N6LogicReasonableness(AiRuleChecker):
    """N6: 助记逻辑合理性."""

    rule_id = "N6"
    dimension = "mnemonic"
    description = "逻辑合理性"
    system_prompt = (
        "你是中小学英语教学专家。判断给定的助记拆解逻辑是否合理，是否存在'伪助记'（牵强的拆解）。"
        "返回 JSON: {\"passed\": true/false, \"detail\": \"原因\"}"
    )

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        return f"单词: {word}\n助记内容:\n{content}\n\n请判断此助记的逻辑是否合理，是否为伪助记。"
